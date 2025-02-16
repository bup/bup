from difflib import unified_diff
from os import environb
from pathlib import Path
from sys import stderr
import re

from wvpytest import *

from bup import git, tree
from bup.helpers import mkdirp
from buptest import ex, exo


def test_abbreviate():
    l1 = [b'1234', b'1235', b'1236']
    WVPASSEQ(tree._abbreviate_tree_names(l1), l1)
    l2 = [b'aaaa', b'bbbb', b'cccc']
    WVPASSEQ(tree._abbreviate_tree_names(l2), [b'a', b'b', b'c'])
    l3 = [b'.bupm']
    WVPASSEQ(tree._abbreviate_tree_names(l3), [b'.b'])
    l4 = [b'..strange..name']
    WVPASSEQ(tree._abbreviate_tree_names(l4), [b'..s'])
    l5 = [b'justone']
    WVPASSEQ(tree._abbreviate_tree_names(l5), [b'j'])

# We assume ascii below so that we can use difflib for failures, which
# only supports strings...

# These paths should generate a two level deep split tree, and if you
# drop the last one, a single level tree.

split_src = ['00055f95-8cf7-4a01-8819-f6423c731b1a',
             '01bf344a-deaf-4ffb-8cc6-ad86b03c63e2',
             '01cc9d94-7006-461e-aace-c5919e1ceb9a',
             '01cf2c47-43ff-4427-865e-01788a3bb910',
             '01e1e4bd-6950-4694-a259-f7d66600e776',
             '0c2e3b73-2a44-487c-9aaa-f7428dc3d015',
             '0c3028cc-90f2-4f46-ad3b-94a21498e2ce',
             '0c34aa4a-a479-437a-82b7-e19208a46be8',
             '0c3a4773-6c7f-4efd-9edc-5628698b65bc',
             '191b396b-fec7-47f6-a5ba-089ce9ca2956',
             '192697c4-b855-4c93-9f3d-2e66a4879c6b',
             '192ba072-38f1-4aaa-8515-a334febaeb34',
             '192cf67d-d6ee-4e76-8f7c-da7546812bb1',
             '1f1d9ecc-5ad0-4c70-8b7c-9b4eab55d271',
             '1f1d9f04-9d74-4cee-bb4d-b7eae08d7f50',
             '1f21d232-42f0-49d2-bbfd-3561bdb2cd78',
             '1f2936a1-0ece-4335-90e4-cc1883b9dd93',
             '1f98f6db-dc1e-4ea7-99e4-7f385c9aa363',
             '1f9ce8b4-b0b2-463a-872d-bdc902427b26',
             '1f9d4cf1-57a9-4897-9572-5044e2bda6a8',
             '1fa53c9a-d8f0-4b93-9a96-90ad6cbf0295',
             '24ad9373-5d28-49c5-9649-5bbd29e52c7b',
             '24af5545-e51c-4b26-b72a-ea758bdec9ae',
             '24af964f-d47d-44ab-a593-9cb213c89869',
             '24bc10a8-ac57-4859-9a29-509fc0ff7dc0',
             '265195da-ef80-47e0-8df8-a134c57af25d',
             '26534c1b-a7ba-4737-9612-14b24e729006',
             '26572cc0-b704-4352-a5a3-d7d4e7f571a6',
             '26640125-4b33-4bde-ba4e-8751d15894c5',
             '27ae178a-fba2-4b80-a37e-6d14b610ca1f',
             '27b40c6f-c5a2-4d90-90a9-6a76612d9935',
             '27b75972-28a3-40cf-a73b-1b7e554d2e84',
             '27b8eb00-0faa-4b8f-9d1a-19a83a9eec07',
             '2c55f6cb-7ce4-49df-a260-ed8850b3b055',
             '2c56fa06-72f4-4a94-b5f3-0e6199f88c36',
             '2c58a92d-172e-45a8-837e-36dba98b95cb',
             '2c61e2a2-a45f-48d0-b1d7-aa31ae9344b9',
             '3921bf33-75ca-4507-8fdf-a881ff106484',
             '392295d4-4df0-4066-a223-a4dec17849a8',
             '3922ed17-3726-4640-88c7-30fc1b181893',
             '392fce08-523d-4ae2-b860-3de201252edb',
             '477066dd-44cb-4a24-bcb7-414a23edaa9f',
             '4774c87c-9a9c-45a8-89a0-fdca65694a97',
             '47773c76-3611-4d32-a10a-a02a7b903e2b',
             '477d130b-d0ed-4b93-9da7-a83a1f775257',
             '480214dc-e63c-4089-b5b2-713419a20681',
             '4806c496-7650-4647-934c-2c6c22c15209',
             '480abcd9-330e-45b5-81ad-a4fb9accef84',
             '480ca556-ecc9-4b75-9dfb-4951af51df53',
             '48c45a41-11b0-4bc0-a2a4-9d4c53a9a8ba',
             '48c5e1d1-1f94-4ac5-b35e-d74f3e2de569',
             '48ca9b38-a77c-49b0-a8af-a40b876498b5',
             '48ef2c71-dfac-4160-a152-8f46bb78cc24',
             '50935f33-3c48-4547-99b1-41843bd8fcbb',
             '50960add-9801-43df-9b77-1108046d9190',
             '509ad170-9107-47bb-bc02-9839290f48d9',
             '50a173fc-c6bb-4d4e-a5fd-3c26268145b8',
             '52399901-eb4f-433f-8942-9bb8bbc020f1',
             '523b3f3d-2d89-4a4c-b6a5-a9401684b1be',
             '5243f3b8-dba5-430a-b204-c494f94b5bc8',
             '524dfc5d-dd60-4f08-a8e0-7b63dd13110c',
             '5ae4e67c-b751-4126-80f4-f551c7f8ea9b',
             '5ae9aea6-859e-44fe-9d6c-39b1f8c21296',
             '5aec70e7-fa39-4ebd-8285-e79565db5454',
             '5af4985e-b509-41ff-b1fb-90eeab8599e2',
             '61d07f00-69ab-41da-b2c1-ad35ff21b6c2',
             '61d6a7a1-bb38-4c1b-a1d4-c80ca8320170',
             '61d9986c-be88-4616-bb2a-e805b9d2e614',
             '61d9a4e9-88f8-4f06-90f6-a0e2a8d00fff',
             '66541d38-ccb2-4474-b30c-1a020b3418d1',
             '666290b0-faa6-42c7-8bea-5be5e38f9e7d',
             '6662e657-1a38-483a-9947-188478718454',
             '666712d7-0cb7-4b39-bc86-bb1f792cb75c',
             '66cf73bd-7627-46d3-900b-b11ca122ac9e',
             '66d0d5de-e1f7-4225-9c58-324ab1f0e46a',
             '66d48a1b-0bdc-47b9-b471-55aaeb5d6062',
             '66d6571f-a65c-483a-9c44-905baac6ca1c']

split_1 = ['.bupd.1.bupd',
           '.bupm',
           '00/.bupm',
           '00/00055f95-8cf7-4a01-8819-f6423c731b1a',
           '00/01bf344a-deaf-4ffb-8cc6-ad86b03c63e2',
           '00/01cc9d94-7006-461e-aace-c5919e1ceb9a',
           '00/01cf2c47-43ff-4427-865e-01788a3bb910',
           '01e/.bupm',
           '01e/01e1e4bd-6950-4694-a259-f7d66600e776',
           '01e/0c2e3b73-2a44-487c-9aaa-f7428dc3d015',
           '01e/0c3028cc-90f2-4f46-ad3b-94a21498e2ce',
           '01e/0c34aa4a-a479-437a-82b7-e19208a46be8',
           '0c3a/.bupm',
           '0c3a/0c3a4773-6c7f-4efd-9edc-5628698b65bc',
           '0c3a/191b396b-fec7-47f6-a5ba-089ce9ca2956',
           '0c3a/192697c4-b855-4c93-9f3d-2e66a4879c6b',
           '0c3a/192ba072-38f1-4aaa-8515-a334febaeb34',
           '192c/.bupm',
           '192c/192cf67d-d6ee-4e76-8f7c-da7546812bb1',
           '192c/1f1d9ecc-5ad0-4c70-8b7c-9b4eab55d271',
           '192c/1f1d9f04-9d74-4cee-bb4d-b7eae08d7f50',
           '192c/1f21d232-42f0-49d2-bbfd-3561bdb2cd78',
           '1f29/.bupm',
           '1f29/1f2936a1-0ece-4335-90e4-cc1883b9dd93',
           '1f29/1f98f6db-dc1e-4ea7-99e4-7f385c9aa363',
           '1f29/1f9ce8b4-b0b2-463a-872d-bdc902427b26',
           '1f29/1f9d4cf1-57a9-4897-9572-5044e2bda6a8',
           '1fa/.bupm',
           '1fa/1fa53c9a-d8f0-4b93-9a96-90ad6cbf0295',
           '1fa/24ad9373-5d28-49c5-9649-5bbd29e52c7b',
           '1fa/24af5545-e51c-4b26-b72a-ea758bdec9ae',
           '1fa/24af964f-d47d-44ab-a593-9cb213c89869',
           '24b/.bupm',
           '24b/24bc10a8-ac57-4859-9a29-509fc0ff7dc0',
           '24b/265195da-ef80-47e0-8df8-a134c57af25d',
           '24b/26534c1b-a7ba-4737-9612-14b24e729006',
           '24b/26572cc0-b704-4352-a5a3-d7d4e7f571a6',
           '266/.bupm',
           '266/26640125-4b33-4bde-ba4e-8751d15894c5',
           '266/27ae178a-fba2-4b80-a37e-6d14b610ca1f',
           '266/27b40c6f-c5a2-4d90-90a9-6a76612d9935',
           '266/27b75972-28a3-40cf-a73b-1b7e554d2e84',
           '27b8/.bupm',
           '27b8/27b8eb00-0faa-4b8f-9d1a-19a83a9eec07',
           '27b8/2c55f6cb-7ce4-49df-a260-ed8850b3b055',
           '27b8/2c56fa06-72f4-4a94-b5f3-0e6199f88c36',
           '27b8/2c58a92d-172e-45a8-837e-36dba98b95cb',
           '2c6/.bupm',
           '2c6/2c61e2a2-a45f-48d0-b1d7-aa31ae9344b9',
           '2c6/3921bf33-75ca-4507-8fdf-a881ff106484',
           '2c6/392295d4-4df0-4066-a223-a4dec17849a8',
           '2c6/3922ed17-3726-4640-88c7-30fc1b181893',
           '392f/.bupm',
           '392f/392fce08-523d-4ae2-b860-3de201252edb',
           '392f/477066dd-44cb-4a24-bcb7-414a23edaa9f',
           '392f/4774c87c-9a9c-45a8-89a0-fdca65694a97',
           '392f/47773c76-3611-4d32-a10a-a02a7b903e2b',
           '477d/.bupm',
           '477d/477d130b-d0ed-4b93-9da7-a83a1f775257',
           '477d/480214dc-e63c-4089-b5b2-713419a20681',
           '477d/4806c496-7650-4647-934c-2c6c22c15209',
           '477d/480abcd9-330e-45b5-81ad-a4fb9accef84',
           '480c/.bupm',
           '480c/480ca556-ecc9-4b75-9dfb-4951af51df53',
           '480c/48c45a41-11b0-4bc0-a2a4-9d4c53a9a8ba',
           '480c/48c5e1d1-1f94-4ac5-b35e-d74f3e2de569',
           '480c/48ca9b38-a77c-49b0-a8af-a40b876498b5',
           '48e/.bupm',
           '48e/48ef2c71-dfac-4160-a152-8f46bb78cc24',
           '48e/50935f33-3c48-4547-99b1-41843bd8fcbb',
           '48e/50960add-9801-43df-9b77-1108046d9190',
           '48e/509ad170-9107-47bb-bc02-9839290f48d9',
           '50a/.bupm',
           '50a/50a173fc-c6bb-4d4e-a5fd-3c26268145b8',
           '50a/52399901-eb4f-433f-8942-9bb8bbc020f1',
           '50a/523b3f3d-2d89-4a4c-b6a5-a9401684b1be',
           '50a/5243f3b8-dba5-430a-b204-c494f94b5bc8',
           '524d/.bupm',
           '524d/524dfc5d-dd60-4f08-a8e0-7b63dd13110c',
           '524d/5ae4e67c-b751-4126-80f4-f551c7f8ea9b',
           '524d/5ae9aea6-859e-44fe-9d6c-39b1f8c21296',
           '524d/5aec70e7-fa39-4ebd-8285-e79565db5454',
           '5af/.bupm',
           '5af/5af4985e-b509-41ff-b1fb-90eeab8599e2',
           '5af/61d07f00-69ab-41da-b2c1-ad35ff21b6c2',
           '5af/61d6a7a1-bb38-4c1b-a1d4-c80ca8320170',
           '5af/61d9986c-be88-4616-bb2a-e805b9d2e614',
           '61d9a/.bupm',
           '61d9a/61d9a4e9-88f8-4f06-90f6-a0e2a8d00fff',
           '61d9a/66541d38-ccb2-4474-b30c-1a020b3418d1',
           '61d9a/666290b0-faa6-42c7-8bea-5be5e38f9e7d',
           '61d9a/6662e657-1a38-483a-9947-188478718454',
           '6667/.bupm',
           '6667/666712d7-0cb7-4b39-bc86-bb1f792cb75c',
           '6667/66cf73bd-7627-46d3-900b-b11ca122ac9e',
           '6667/66d0d5de-e1f7-4225-9c58-324ab1f0e46a',
           '6667/66d48a1b-0bdc-47b9-b471-55aaeb5d6062']

split_2 = ['.bupd.2.bupd',
           '.bupm',
           '0/00/.bupm',
           '0/00/00055f95-8cf7-4a01-8819-f6423c731b1a',
           '0/00/01bf344a-deaf-4ffb-8cc6-ad86b03c63e2',
           '0/00/01cc9d94-7006-461e-aace-c5919e1ceb9a',
           '0/00/01cf2c47-43ff-4427-865e-01788a3bb910',
           '0/01e/.bupm',
           '0/01e/01e1e4bd-6950-4694-a259-f7d66600e776',
           '0/01e/0c2e3b73-2a44-487c-9aaa-f7428dc3d015',
           '0/01e/0c3028cc-90f2-4f46-ad3b-94a21498e2ce',
           '0/01e/0c34aa4a-a479-437a-82b7-e19208a46be8',
           '0/0c3a/.bupm',
           '0/0c3a/0c3a4773-6c7f-4efd-9edc-5628698b65bc',
           '0/0c3a/191b396b-fec7-47f6-a5ba-089ce9ca2956',
           '0/0c3a/192697c4-b855-4c93-9f3d-2e66a4879c6b',
           '0/0c3a/192ba072-38f1-4aaa-8515-a334febaeb34',
           '0/192c/.bupm',
           '0/192c/192cf67d-d6ee-4e76-8f7c-da7546812bb1',
           '0/192c/1f1d9ecc-5ad0-4c70-8b7c-9b4eab55d271',
           '0/192c/1f1d9f04-9d74-4cee-bb4d-b7eae08d7f50',
           '0/192c/1f21d232-42f0-49d2-bbfd-3561bdb2cd78',
           '0/1f29/.bupm',
           '0/1f29/1f2936a1-0ece-4335-90e4-cc1883b9dd93',
           '0/1f29/1f98f6db-dc1e-4ea7-99e4-7f385c9aa363',
           '0/1f29/1f9ce8b4-b0b2-463a-872d-bdc902427b26',
           '0/1f29/1f9d4cf1-57a9-4897-9572-5044e2bda6a8',
           '0/1fa/.bupm',
           '0/1fa/1fa53c9a-d8f0-4b93-9a96-90ad6cbf0295',
           '0/1fa/24ad9373-5d28-49c5-9649-5bbd29e52c7b',
           '0/1fa/24af5545-e51c-4b26-b72a-ea758bdec9ae',
           '0/1fa/24af964f-d47d-44ab-a593-9cb213c89869',
           '0/24b/.bupm',
           '0/24b/24bc10a8-ac57-4859-9a29-509fc0ff7dc0',
           '0/24b/265195da-ef80-47e0-8df8-a134c57af25d',
           '0/24b/26534c1b-a7ba-4737-9612-14b24e729006',
           '0/24b/26572cc0-b704-4352-a5a3-d7d4e7f571a6',
           '0/266/.bupm',
           '0/266/26640125-4b33-4bde-ba4e-8751d15894c5',
           '0/266/27ae178a-fba2-4b80-a37e-6d14b610ca1f',
           '0/266/27b40c6f-c5a2-4d90-90a9-6a76612d9935',
           '0/266/27b75972-28a3-40cf-a73b-1b7e554d2e84',
           '0/27b8/.bupm',
           '0/27b8/27b8eb00-0faa-4b8f-9d1a-19a83a9eec07',
           '0/27b8/2c55f6cb-7ce4-49df-a260-ed8850b3b055',
           '0/27b8/2c56fa06-72f4-4a94-b5f3-0e6199f88c36',
           '0/27b8/2c58a92d-172e-45a8-837e-36dba98b95cb',
           '0/2c6/.bupm',
           '0/2c6/2c61e2a2-a45f-48d0-b1d7-aa31ae9344b9',
           '0/2c6/3921bf33-75ca-4507-8fdf-a881ff106484',
           '0/2c6/392295d4-4df0-4066-a223-a4dec17849a8',
           '0/2c6/3922ed17-3726-4640-88c7-30fc1b181893',
           '0/392f/.bupm',
           '0/392f/392fce08-523d-4ae2-b860-3de201252edb',
           '0/392f/477066dd-44cb-4a24-bcb7-414a23edaa9f',
           '0/392f/4774c87c-9a9c-45a8-89a0-fdca65694a97',
           '0/392f/47773c76-3611-4d32-a10a-a02a7b903e2b',
           '0/477d/.bupm',
           '0/477d/477d130b-d0ed-4b93-9da7-a83a1f775257',
           '0/477d/480214dc-e63c-4089-b5b2-713419a20681',
           '0/477d/4806c496-7650-4647-934c-2c6c22c15209',
           '0/477d/480abcd9-330e-45b5-81ad-a4fb9accef84',
           '0/480c/.bupm',
           '0/480c/480ca556-ecc9-4b75-9dfb-4951af51df53',
           '0/480c/48c45a41-11b0-4bc0-a2a4-9d4c53a9a8ba',
           '0/480c/48c5e1d1-1f94-4ac5-b35e-d74f3e2de569',
           '0/480c/48ca9b38-a77c-49b0-a8af-a40b876498b5',
           '0/48e/.bupm',
           '0/48e/48ef2c71-dfac-4160-a152-8f46bb78cc24',
           '0/48e/50935f33-3c48-4547-99b1-41843bd8fcbb',
           '0/48e/50960add-9801-43df-9b77-1108046d9190',
           '0/48e/509ad170-9107-47bb-bc02-9839290f48d9',
           '0/50a/.bupm',
           '0/50a/50a173fc-c6bb-4d4e-a5fd-3c26268145b8',
           '0/50a/52399901-eb4f-433f-8942-9bb8bbc020f1',
           '0/50a/523b3f3d-2d89-4a4c-b6a5-a9401684b1be',
           '0/50a/5243f3b8-dba5-430a-b204-c494f94b5bc8',
           '0/524d/.bupm',
           '0/524d/524dfc5d-dd60-4f08-a8e0-7b63dd13110c',
           '0/524d/5ae4e67c-b751-4126-80f4-f551c7f8ea9b',
           '0/524d/5ae9aea6-859e-44fe-9d6c-39b1f8c21296',
           '0/524d/5aec70e7-fa39-4ebd-8285-e79565db5454',
           '0/5af/.bupm',
           '0/5af/5af4985e-b509-41ff-b1fb-90eeab8599e2',
           '0/5af/61d07f00-69ab-41da-b2c1-ad35ff21b6c2',
           '0/5af/61d6a7a1-bb38-4c1b-a1d4-c80ca8320170',
           '0/5af/61d9986c-be88-4616-bb2a-e805b9d2e614',
           '0/61d9a/.bupm',
           '0/61d9a/61d9a4e9-88f8-4f06-90f6-a0e2a8d00fff',
           '0/61d9a/66541d38-ccb2-4474-b30c-1a020b3418d1',
           '0/61d9a/666290b0-faa6-42c7-8bea-5be5e38f9e7d',
           '0/61d9a/6662e657-1a38-483a-9947-188478718454',
           '0/6667/.bupm',
           '0/6667/666712d7-0cb7-4b39-bc86-bb1f792cb75c',
           '0/6667/66cf73bd-7627-46d3-900b-b11ca122ac9e',
           '0/6667/66d0d5de-e1f7-4225-9c58-324ab1f0e46a',
           '0/6667/66d48a1b-0bdc-47b9-b471-55aaeb5d6062',
           '66d6/6/.bupm',
           '66d6/6/66d6571f-a65c-483a-9c44-905baac6ca1c']

def pruned_ls_files(parent, output):
    files = []
    bupm_prev = False
    # Trim to just the paths in the source dir without the prefix, and
    # collapse any split .bupm/* paths into just a .bupm.
    bupm_rx = re.compile(rb'/\.bupm/.*')
    assert parent.startswith(b'/')
    assert not parent.endswith(b'/')
    for line in output.splitlines(keepends=True):
        if not line.startswith(parent[1:]):
            bupm_prev = False
            continue
        line = line[len(parent):]
        if line.startswith(b'.bupm/'):
            if not bupm_prev:
                files.append('.bupm\n')
                bupm_prev = True
            continue
        if b'/.bupm/' in line:
            if not bupm_prev:
                files.append(bupm_rx.sub(rb'/.bupm', line).decode('ascii'))
                bupm_prev = True
            continue
        bupm_prev = False
        files.append(line.decode('ascii'))
    return files

def split_tree_for_filenames(names, tmpdir):
    environb[b'BUP_DIR'] = bupdir = tmpdir + b'/bup'
    src = tmpdir + b'/src'
    git.init_repo(bupdir)
    mkdirp(src)
    for name in names:
        Path(src.decode('ascii'), name).touch()
    ex((b'git', b'--git-dir', bupdir, b'config', b'bup.split.trees', b'1'))
    ex((b'./bup', b'index', src))
    ex((b'./bup', b'save', b'-n', b'src', src))
    ls_tree = exo((b'git', b'--git-dir', bupdir,
                   b'ls-tree', b'-r', b'--name-only', b'src'))
    return pruned_ls_files(src, ls_tree.out)

def diff_split(expect, actual):
    return list(unified_diff([f'{x}\n' for x in expect],
                             actual,
                             fromfile='expect', tofile='actual'))

def test_expected_depth_1_split(tmpdir):
    diff = diff_split(split_1, split_tree_for_filenames(split_src[:-1], tmpdir))
    stderr.writelines(diff)
    assert not diff

def test_expected_depth_2_split(tmpdir):
    diff = diff_split(split_2, split_tree_for_filenames(split_src, tmpdir))
    stderr.writelines(diff)
    assert not diff
