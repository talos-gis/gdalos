def fill_arrays(*args):
    max_len = max(len(x) for x in args)
    result = []
    for x in range(len(args)):
        lx = len(x)
        if lx < max_len:
            v = x[lx-1]
            for i in range(lx, max_len):
                x.append(v)
        result.append(x)
    return result


def fill_arrays_dict(d: dict):
    max_len = max(len(v) for v in d.values())
    result = dict()
    for k, v in d.items():
        len_v = len(v)
        if len_v < max_len:
            v = v[len_v-1]
            for i in range(len_v, max_len):
                v.append(v)
        result[k] = v
    return result


def make_dicts_list_from_lists_dict(d: dict, key_map):
    max_len = max(len(v) for v in d.values())
    result = []
    d1 = dict()
    for i in range(max_len):
        d1 = d1.copy()
        for k, v in d.items():  # zip(new_keys, d.values()):
            if key_map:
                k = key_map[k]
            len_v = len(v)
            if i < len_v:
                d1[k] = v[i]
        result.append(d1)
    return result


def replace_keys(dicts, key_map):
    if not key_map:
        return dicts
    result = []
    single = isinstance(dicts, dict)
    if single:
        dicts = [dicts]
    for d in dicts:
        new_d = dict()
        for k, v in d.items():
            if key_map:
                k = key_map[k]
            new_d[k] = v
        result.append(new_d)
    if single:
        result = result[0]
    return result
