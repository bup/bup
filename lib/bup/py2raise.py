
# This file exists because the raise syntax is completely incompatible
# with Python 3.

def py2_raise(type_or_instance=None, instance_or_tuple=None, traceback=None):
    raise type_or_instance, instance_or_tuple, traceback
