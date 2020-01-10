"""
AWS storage

Uses the following AWS products:
 * S3 object storage for data, metadata and idx files
 * DynamoDB for consistent file listing and config storage

TODO:
 * Aborting Incomplete Multipart Uploads Using a Bucket Lifecycle Policy
   (https://docs.aws.amazon.com/AmazonS3/latest/dev/mpuoverview.html)
"""
from __future__ import absolute_import
import fnmatch
import datetime
import hashlib, base64

from bup.storage import BupStorage, FileAlreadyExists, FileNotFound, Kind, FileModified

try:
    import boto3
    from boto3.dynamodb.conditions import Attr
    from botocore.exceptions import ClientError
except ImportError:
    boto3 = None


AWS_CHUNK_SIZE = 1024 * 1024 * 5


def _nowstr():
    # time.time() appears to return the same, but doesn't
    # actually seem to guarantee UTC
    return datetime.datetime.utcnow().strftime('%s')

def _munge(name):
    # do some sharding - S3 uses the first few characters for this
    assert name.startswith('pack-')
    return name[5:9] + '/' + name

class S3Reader:
    def __init__(self, storage, name):
        self.storage = storage
        self.name = name
        self.objname = _munge(name)
        response = storage.dynamo.query(TableName=storage.table,
                                        ConsistentRead=True,
                                        KeyConditionExpression='filename = :nm',
                                        ExpressionAttributeValues={
                                            ':nm': { 'S': name, }
                                        })
        assert response['Count'] in (0, 1)
        if response['Count'] == 0:
            raise FileNotFound(name)
        self.offs = 0
        assert name == response['Items'][0]['filename']['S']
        self.size = int(response['Items'][0]['size']['N'])
        self.cache = None

    def _read_from_cache(self, sz):
        if self.cache is not None:
            if len(self.cache) >= self.offs + sz:
                offs = self.offs
                self.offs += sz
                return self.cache[offs:offs + sz]
        return None

    def read(self, sz=None):
        if sz is None:
            sz = self.size - self.offs
        data = self._read_from_cache(sz)
        if data is not None:
            return data

        startrange = '%d-' % self.offs
        if sz is not None:
            range = startrange + '%d' % (self.offs + sz, )
        storage = self.storage
        ret = storage.s3.get_object(
            Bucket=storage.bucket,
            Key=self.objname,
            Range=range,
        )
        # TODO: limit the cache? AWS appears to return the full object
        # even for something like a 10MB object, at least, so not sure
        # what the cutoff is - we should probably limit it, or store it
        # in a file (configurable?)
        if not 'ContentRange' in ret:
            self.cache = ret['Body'].read()
            return self._read_from_cache(sz)
        assert ret['ContentRange'].startswith(startrange)
        self.offs += sz
        return ret['Body'].read(sz)

    def close(self):
        self.cache = None

    def seek(self, offs):
        self.offs = offs

def _check_exc(e, *codes):
    if not hasattr(e, 'response'):
        return False
    if not 'Error' in e.response:
        return False
    if not 'Code' in e.response['Error']:
        return False
    if not e.response['Error']['Code'] in codes:
        raise

class S3Writer:
    def __init__(self, storage, name):
        self.storage = storage
        self.name = name
        self.objname = _munge(name)
        self.buf = b''
        self.size = 0
        self.etags = []
        self.upload_id = None
        item = {
            'filename': {
                'S': name,
            },
            'tentative': {
                'N': '1',
            },
            'timestamp': {
                'N': _nowstr(),
            },
        }
        try:
            condition = "attribute_not_exists(filename)"
            storage.dynamo.put_item(Item=item, TableName=storage.table,
                                    ConditionExpression=condition)
        except ClientError as e:
            _check_exc(e, 'ConditionalCheckFailedException')
            raise FileAlreadyExists(name)

    def __del__(self):
        if self.storage:
            self.abort()

    def _start_upload(self):
        if self.upload_id is not None:
            return
        storage = self.storage
        # FIXME: make default configure, and by threshold
        # (must have self.storage_class_threshold <= AWS_CHUNK_SIZE)
        #if len(self.buf) > self.storage_class_threshold:
        #   storage = 'blabla'
        storage_class = 'STANDARD'
        self.upload_id = storage.s3.create_multipart_upload(
            Bucket=storage.bucket,
            StorageClass=storage_class,
            Key=self.objname,
        )['UploadId']

    def _upload_buf(self):
        self._start_upload()
        storage = self.storage
        digest = base64.b64encode(hashlib.md5(self.buf).digest())
        ret = storage.s3.upload_part(
            Body=self.buf,
            Bucket=storage.bucket,
            ContentLength=len(self.buf),
            ContentMD5=digest,
            Key=self.objname,
            UploadId=self.upload_id,
            PartNumber=len(self.etags) + 1,
        )
        self.etags.append(ret['ETag'])
        self.buf = b''

    def write(self, data):
        self.buf += data
        self.size += len(data)
        # must send at least 5 MB chunks (except last)
        if len(self.buf) >= AWS_CHUNK_SIZE:
            self._upload_buf()

    def close(self):
        if self.storage is None:
            return
        self._upload_buf()
        storage = self.storage
        storage.s3.complete_multipart_upload(
            Bucket=storage.bucket,
            Key=self.objname,
            MultipartUpload={
                'Parts': [
                    {
                        'ETag': etag,
                        'PartNumber': n + 1,
                    }
                    for n, etag in enumerate(self.etags)
                ]
            },
            UploadId=self.upload_id
        )
        item = {
            'filename': {
                'S': self.name,
            },
            'size': {
                'N': '%d' % self.size,
            },
            'timestamp': {
                'N': _nowstr(),
            },
        }
        storage.dynamo.put_item(Item=item, TableName=storage.table)
        self.storage = None
        self.etags = None

    def abort(self):
        storage = self.storage
        self.storage = None
        if self.upload_id is not None:
            storage.s3.abort_multipart_upload(Bucket=storage.bucket,
                                              Key=self.objname,
                                              UploadId=self.upload_id)
        storage.dynamo.delete_item(TableName=storage.table,
                                   Key={ 'filename': { 'S': self.name } },
                                   ReturnValues='NONE')

class DynamoReader:
    def __init__(self, storage, name):
        self.storage = storage
        self.name = name
        response = storage.dynamo.query(TableName=storage.table,
                                        ConsistentRead=True,
                                        KeyConditionExpression='filename = :nm',
                                        ExpressionAttributeValues={
                                            ':nm': { 'S': name, }
                                        })
        assert response['Count'] in (0, 1)
        if response['Count'] == 0:
            raise FileNotFound(name)
        item = response['Items'][0]
        assert item['filename']['S'] == name
        self.data = item['data']['B']
        self.offs = 0
        self.generation = int(item['generation']['N'])

    def read(self, sz=None):
        assert self.data is not None
        maxread = len(self.data) - self.offs
        if sz is None or sz > maxread:
            sz = maxread
        ret = self.data[self.offs:self.offs + sz]
        self.offs += sz
        return ret

    def close(self):
        if self.data is not None:
            self.data = None

    def seek(self, offs):
        assert self.data is not None
        self.offs = offs

class DynamoWriter:
    def __init__(self, storage, name, overwrite):
        self.storage = storage
        self.name = name
        self.overwrite = overwrite
        if overwrite:
            assert isinstance(overwrite, DynamoReader)
        else:
            response = storage.dynamo.query(TableName=storage.table,
                                            ConsistentRead=True,
                                            KeyConditionExpression='filename = :nm',
                                            ExpressionAttributeValues={
                                                ':nm': { 'S': name, }
                                            })
            assert response['Count'] in (0, 1)
            if response['Count'] == 1:
                raise FileAlreadyExists(name)
        self.data = b''

    def write(self, data):
        assert self.data is not None
        self.data += data

    def close(self):
        if self.data is None:
            return
        data = self.data
        self.data = None
        storage = self.storage
        if self.overwrite:
            generation = self.overwrite.generation + 1
        else:
            generation = 0
        item = {
            'filename': {
                'S': self.name,
            },
            'generation': {
                'N': '%d' % generation,
            },
            'data': {
                'B': data,
            },
            'timestamp': {
                'N': _nowstr(),
            },
        }
        if self.overwrite:
            condition = "generation = :gen"
            condvals = { ':gen': { 'N': '%d' % (generation - 1, ) }, }
            try:
                storage.dynamo.put_item(Item=item, TableName=storage.table,
                                        ConditionExpression=condition,
                                        ExpressionAttributeValues=condvals)
            except ClientError as e:
                _check_exc(e, 'ConditionalCheckFailedException')
                raise Exception("Failed to overwrite '%s', it was changed in the meantime." % self.name)
        else:
            try:
                condition = "attribute_not_exists(filename)"
                storage.dynamo.put_item(Item=item, TableName=storage.table,
                                        ConditionExpression=condition)
            except ClientError as e:
                _check_exc(e, 'ConditionalCheckFailedException')
                raise Exception("Failed to create '%s', it was created by someone else." % self.name)

    def abort(self):
        self.data = None

class AWSStorage(BupStorage):
    def __init__(self, repo, create=False):
        if boto3 is None:
            raise Exception("AWSStorage: missing boto3 module")

        self.bucket = repo.config(b's3bucket')
        if self.bucket is None:
            raise Exception("AWSStorage: must have 's3bucket' configuration")
        self.table = repo.config(b'dynamotable')
        if self.table is None:
            raise Exception("AWSStorage: must have 'dynamotable' configuration")
        region_name = repo.config(b'region')
        if region_name is None:
            raise Exception("AWSStorage: must have 'region' configuration")

        session = boto3.session.Session(
            aws_access_key_id=repo.config(b'accessKeyId'),
            aws_secret_access_key=repo.config(b'secretAccessKey'),
            aws_session_token=repo.config(b'sessionToken'),
            region_name=region_name,
        )

        self.s3 = session.client('s3')
        self.dynamo = session.client('dynamodb')

        if create:
            self.s3.create_bucket(Bucket=self.bucket, ACL='private',
                                  CreateBucketConfiguration={
                                      'LocationConstraint': region_name,
                                  })
            self.dynamo.create_table(TableName=self.table,
                                     BillingMode='PAY_PER_REQUEST',
                                     KeySchema=[
                                         {
                                             'AttributeName': 'filename',
                                             'KeyType': 'HASH',
                                         }
                                     ],
                                     AttributeDefinitions=[
                                         {
                                             'AttributeName': 'filename',
                                             'AttributeType': 'S',
                                         }
                                     ])

    def get_writer(self, name, kind, overwrite=None):
        assert kind in (Kind.DATA, Kind.METADATA, Kind.IDX, Kind.CONFIG)
        if kind == Kind.CONFIG:
            return DynamoWriter(self, name, overwrite)
        assert overwrite is None
        return S3Writer(self, name)

    def get_reader(self, name, kind):
        assert kind in (Kind.DATA, Kind.METADATA, Kind.IDX, Kind.CONFIG)
        if kind == Kind.CONFIG:
            return DynamoReader(self, name)
        return S3Reader(self, name)

    def list(self, pattern=None):
        # TODO: filter this somehow based on the pattern?
        # TODO: implement pagination!
        response = self.dynamo.scan(TableName=self.table,
                                    Select='SPECIFIC_ATTRIBUTES',
                                    AttributesToGet=['filename', 'tentative'],
                                    ConsistentRead=True)
        assert not 'LastEvaluatedKey' in response
        for item in response['Items']:
            if 'tentative' in item:
                continue
            name = item['filename']['S']
            if fnmatch.fnmatch(name, pattern):
                yield name

    def close(self):
        pass
