import copy
from collections import defaultdict
from enum import IntEnum, auto
from itertools import chain, cycle, product, tee
from typing import Dict, Any

from osgeo_utils.auxiliary.base import *  # noqa

PathLike = PathLikeOrStr
SequanceNotString = SequenceNotString


def fill_arrays(*args):
    max_len = max(len(x) for x in args)
    result = []
    for x in args:
        lx = len(x)
        if lx < max_len:
            v = x[lx - 1]
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
            v = v[len_v - 1]
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


def get_dict(slotted_object):
    return {x: getattr(slotted_object, x) for x in slotted_object.__slots__}


def get_list_from_lists_dict(d: dict, vp, key_map=None) -> List:
    max_len = max(len(v) if v else 0 for v in d.values())
    result = []
    for i in range(max_len):
        vp = copy.deepcopy(vp)
        for k, v in d.items():
            if not v:
                continue
            if key_map:
                k = key_map[k]
            len_v = len(v)
            if i < len_v:
                setattr(vp, k, v[i])
                # vp1.k = v[i]
        result.append(vp)
    return result


def get_object_from_lists_dict(d: dict, vp, key_map=None):
    for k, v in d.items():
        if not v:
            continue
        if key_map:
            k = key_map[k]
        setattr(vp, k, v)
    return vp


def get_all_slots(a):
    """ gets all the slots of an object and its super class """
    return chain.from_iterable(getattr(cls, '__slots__', []) for cls in a.__mro__)


class FillMode(IntEnum):
    zip = auto()
    zip_cycle = auto()
    product = auto()


def make_points_list(x_arr, y_arr, fill_mode: FillMode):
    if isinstance(fill_mode, (tuple, list)):
        fill_mode = fill_mode[0]
    if isinstance(fill_mode, str):
        fill_mode = FillMode[fill_mode]
    if not isinstance(x_arr, Sequence):
        return x_arr, y_arr
    elif fill_mode != FillMode.product:
        # return a zip of the arrays, if are of different and do_cycle then complete the other list by cycling
        if len(x_arr) == len(y_arr) or (fill_mode != FillMode.zip_cycle):
            return list(zip(x_arr, y_arr))
        elif len(x_arr) > len(y_arr):
            return list(zip(x_arr, cycle(y_arr)))
        else:
            return list(zip(cycle(x_arr), y_arr))
    else:  # cartesian product
        return list(product(x_arr, y_arr))


def make_xy_list(pair_list):
    if isinstance(pair_list[0], Sequence):
        xs, ys = tee(pair_list)
        xs, ys = list(x[0] for x in xs), list(y[1] for y in ys)
        # r = [list(x[i]) for x in (tee(pair_arr)) for i in range(pair_arr)]

        # xs = []
        # ys = []
        # for pair in pair_list:
        #     xs.append(pair[0])
        #     ys.append(pair[1])
        return xs, ys
    else:
        return pair_list


def make_pairs(x_arr, y_arr, fill_mode):
    pair_list = make_points_list(x_arr, y_arr, fill_mode)
    result = make_xy_list(pair_list)
    return result


def lower_case_keys(d: Dict[str, Any]):
    keys = list(d.keys())
    for k in keys:
        d[k.lower()] = d.pop(k)


def list_of_dict_to_dict_of_lists(lst: List[Dict[str, Any]]):
    res = defaultdict(list)
    for d in lst:
        for k, v in d.items():
            res[k].append(v)
    return res


def inverse_list_items(lst: MaybeSequence[bool]):
    if isinstance(lst, Sequence):
        return [not elem for elem in lst]
    else:
        return not lst


def inverse_list_items_int(lst: MaybeSequence[bool]):
    if isinstance(lst, Sequence):
        return [int(not elem) for elem in lst]
    else:
        return int(not lst)
