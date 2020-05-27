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


def make_dicts_list_from_lists_dict(d: dict, new_keys):
    max_len = max(len(v) for v in d.values())
    result = []
    new_d = dict()
    new_keys = new_keys or d.keys()
    for i in range(max_len):
        new_d = new_d.copy()
        for k, v in zip(new_keys, d.values()):
            len_v = len(v)
            if i < len_v:
                new_d[k] = v[i]
        result.append(new_d)
    return result


def replace_keys(lst: list, new_keys):
    if not new_keys:
        return lst
    result = []
    for d in lst:
        new_d = new_d.copy()
        for k, v in zip(new_keys, d.values()):
            new_d[k] = v
        result.append(new_d)
    return result
