def find_first(items, **filters):
    for item in items:
        if matches(item, filters):
            return item
    return None


def matches(haystack, needles):
    return all(haystack.get(k) == v for k, v in needles.items())

