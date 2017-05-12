import hashlib
import functools
from collections import OrderedDict


def sha1_hash(input_bytes):
    """ Hash given bytes with hashlib.sha1 and return the digest (as bytes) """
    return hashlib.sha1(input_bytes).digest()


def sorted_pathdict(input_dict):
    """ Sorts a parsed torrent filelist dict by alphabat, directories first """
    directories = OrderedDict()
    files = OrderedDict()

    for key, value in input_dict.items():
        if isinstance(value, dict):
            directories[key] = sorted_pathdict(value)
        else:
            files[key] = value

    return OrderedDict(sorted(directories.items()) + sorted(files.items()))


def cached_function(f):
    sentinel = object()
    f._cached_value = sentinel

    @functools.wraps(f)
    def decorator(*args, **kwargs):
        if f._cached_value is sentinel:
            print('Evaluating', f, args, kwargs)
            f._cached_value = f(*args, **kwargs)
        return f._cached_value
    return decorator


def flattenDict(d, result=None):
    if result is None:
        result = {}
    for key in d:
        value = d[key]
        if isinstance(value, dict):
            value1 = {}
            for keyIn in value:
                value1["/".join([key, keyIn])] = value[keyIn]
            flattenDict(value1, result)
        elif isinstance(value, (list, tuple)):
            for indexB, element in enumerate(value):
                if isinstance(element, dict):
                    value1 = {}
                    index = 0
                    for keyIn in element:
                        newkey = "/".join([key, keyIn])
                        value1["/".join([key, keyIn])] = value[indexB][keyIn]
                        index += 1
                    for keyA in value1:
                        flattenDict(value1, result)
        else:
            result[key] = value
    return result
