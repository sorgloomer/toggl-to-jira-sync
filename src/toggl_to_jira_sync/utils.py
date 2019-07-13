import functools
from collections import OrderedDict


def into_bins(items, key, sorting='asc') -> object:
    indexed = group_by(items, key)
    result = list(indexed.items())
    if not sorting:
        return result
    return sorted(result, key=key_of_kv, reverse=sorting == 'desc')


def key_of_kv(kv):
    return kv[0]


def group_by_id(items):
    return group_by(items, _id_of)


def group_by(items, key):
    keyfn = _keyify(key)
    result = OrderedDict()
    for item in items:
        key_value = keyfn(item)
        bucket = result.get(key_value)
        if bucket is None:
            bucket = []
            result[key_value] = bucket
        bucket.append(item)
    return result


def index_by_id(items):
    return index_by(items, _id_of)


def index_by(items, key):
    keyfn = _keyify(key)
    result = OrderedDict()
    for item in items:
        key_value = keyfn(item)
        result[key_value] = item
    return result


def strip_after_any(haystack, needles):
    for needle in needles:
        haystack = haystack.split(needle, 1)[0]
    return haystack


def _keyify(key):
    if isinstance(key, str):
        return lambda obj: obj[key]
    if callable(key):
        return key
    raise TypeError("key must be str or callable")


def _id_of(x):
    return x['id']
