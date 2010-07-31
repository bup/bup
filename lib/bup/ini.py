import os, errno

class KeyValue(object):
    def __init__(self, key, value):
        self.dirty = False
        self.key = key
        self._value = value

    def __repr__(self):
        return repr((self.key, self.value))

    def __str__(self):
        return str((self.key, self.value))

    def _getv(self):
        return self._value
    def _setv(self, value):
        self._value = value
        self.dirty = True
    value = property(_getv, _setv)
    
    __slots__ = ['dirty', 'key', '_value']


class KeyValueList(object):
    def __init__(self):
        self._lines = []
        self._keys = {}

    def __repr__(self):
        return repr(self._lines)

    def __str__(self):
        return str(self._lines)

    def _getd(self):
        for i in self.items():
            if i.dirty:
                return True
        return False
    def _setd(self, value):
        for i in self.items():
            i.dirty = value
    dirty = property(_getd, _setd)

    def _comment(self, line):
        assert(line.startswith('#') or not line)
        self._lines.append(line)
        # don't add to _keys, since we don't ever want to look it up

    def _append(self, key, obj):
        self._lines.append(obj)
        self._keys[key] = obj

    def get(self, key, defval=None):
        kv = self._keys.get(key)
        if kv:
            return kv.value
        else:
            return defval

    def set(self, key, value):
        kv = self._keys.get(key)
        if not kv:
            kv = KeyValue(key, value)
            kv.dirty = True
            self._append(key, kv)
        else:
            kv.value = value

    def keys(self):
        return (i.key for i in self._lines if isinstance(i, KeyValue))

    def items(self):
        return (i for i in self._lines if isinstance(i, KeyValue))

    # like dict.__iter__: returns just the keys
    def __iter__(self):
        return self.keys()


class Ini(object):
    def __init__(self):
        self.sections = KeyValueList()
        
    def _getd(self):
        return self.sections.dirty
    def _setd(self, value):
        self.sections.dirty = value
    dirty = property(_getd, _setd)

    def section(self, section):
        kvl = self.sections.get(section)
        if not kvl:
            kvl = KeyValueList()
            self.sections.set(section, kvl)
        return kvl

    def get(self, section, name, defval=None):
        return self.section(section).get(name, defval)

    def set(self, section, name, value):
        self.section(section).set(name, value)

    def keys(self):
        return self.sections.keys()

    def items(self):
        return self.sections.items()

    def __iter__(self):
        return self.sections.__iter__()

    def read(self, lineiter):
        cursection = self.section('')  # global section
        for _line in lineiter:
            line = _line.strip()
            if line.startswith('#') or not line:
                # a comment line
                cursection._comment(line)
            elif line.startswith('[') and line.endswith(']'):
                # start of a new section
                cursection.dirty = False
                cursection = self.section(line[1:-1])
            else:
                l = line.split('=', 1)
                if len(l) != 2:
                    sys.stdout.flush()
                    sys.stderr.write('warning: invalid config line: %r\n'
                                     % line)
                else:
                    cursection.set(l[0].strip(), l[1].strip())
        cursection.dirty = False

    def write(self):
        last_was_blank = True
        for i,sect in enumerate(self.sections.items()):
            any = False
            for kv in sect.value.items():
                if kv.value:
                    any = True
                    break
            if not any:
                continue
            if i or sect.key:
                if not last_was_blank:
                    yield ''
                yield '[%s]' % sect.key
            for row in sect.value._lines:
                if isinstance(row, KeyValue):
                    yield '%s = %s' % (row.key, row.value)
                else:
                    yield row
                last_was_blank = (not row)


class IniFile(Ini):
    def __init__(self, filename):
        Ini.__init__(self)
        self.filename = filename
        try:
            self.read(open(filename))
        except IOError, e:
            if e.errno == errno.ENOENT:
                pass
            else:
                raise

    def flush(self):
        if self.dirty:
            tmpname = self.filename + '.tmp'
            f = open(tmpname, 'w')
            for row in self.write():
                f.write('%s\n' % row)
            f.close()
            os.rename(tmpname, self.filename)
            self.dirty = False


def new(filename):
    return IniFile(filename)
