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


def transform_result(transform_fn):
    @decorator
    def _transform_result(target):
        return transform_fn(target())
    return _transform_result


def decorator(decorator_func):
    @functools.wraps(decorator_func)
    def _decorator(func):
        @functools.wraps(func)
        def _decorator_wrapper(*args, **kwargs):
            return decorator_func(InvocationTarget(func, args, kwargs))
        return _decorator_wrapper
    return _decorator


class InvocationTarget:
    def __init__(self, func, args, kwargs):
        self.func = func
        self.args = args
        self.kwargs = kwargs

    def forward(self):
        print(self.func, self.args, self.kwargs)
        return self.func(*self.args, **self.kwargs)

    def __call__(self):
        return self.forward()


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
