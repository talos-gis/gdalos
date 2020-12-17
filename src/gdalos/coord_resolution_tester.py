# https://stackoverflow.com/questions/385132/proper-best-type-for-storing-latitude-and-longitude
# https://en.wikipedia.org/wiki/Decimal_degrees
#
# http://www.esri.com/news/arcuser/0400/wdside.html
# At the equator, an arc-second of longitude approximately equals an arc-second of latitude, which is 1/60th of a nautical mile (or 101.27 feet or 30.87 meters).
#
# 32-bit float contains 23 explicit bits of data.
# 180 * 3600 requires log2(648000) = 19.305634287546711769425914064259 bits of data. Note that sign bit is stored separately and therefore we need to amount only for 180 degrees.
# After subtracting from 23 the bits for log2(648000) we have remaining extra 3.694365712453288230574085935741 bits for sub-second data.
# That is 2 ^ 3.694365712453288230574085935741 = 12.945382716049382716049382716053 parts per second.
# Therefore a float data type can have 30.87 / 12.945382716049382716049382716053 ~= 2.38 meters precision at equator.
import math

import numpy as np


def calc_a(sec_n, sub_sec_parts, sec_to_meter):
    parts_range = np.arange(0, 1, 1/sub_sec_parts)
    ind = np.arange(sub_sec_parts)

    parts_d = np.empty(sub_sec_parts, dtype=np.float64)
    np.put(parts_d, ind, parts_range)

    parts_s = np.empty(sub_sec_parts, dtype=np.float32)
    np.put(parts_s, ind, parts_range)

    vec_s = np.array(parts_s, copy=True)
    vec_d = np.array(parts_d, copy=True)

    g_max_d = 0
    for s in range(sec_n):
        diff = np.absolute(vec_d - vec_s)
        max_d = max(diff)
        if max_d > g_max_d:
            g_max_d = max_d
        if (s*100 % sec_n == 0) or (s == sec_n-1):
            print(f'{s*100 // sec_n}%: {s}/{sec_n}: {g_max_d}s {g_max_d*sec_to_meter}')
        vec_s = vec_s + 1
        vec_d = vec_d + 1


def calc_b(sec_n, fract_count, deg_to_meter, fact):
    parts_range = np.arange(0, 1, 1 / fract_count / fact)
    ind = np.arange(fract_count)

    frac_d = np.empty(fract_count, dtype=np.float64)
    np.put(frac_d, ind, parts_range)

    frac_s = np.empty(fract_count, dtype=np.float32)
    np.put(frac_s, ind, parts_range)

    out_d = np.empty(fract_count, dtype=np.float64)
    out_s = np.empty(fract_count, dtype=np.float32)

    deg_d = np.empty(fract_count, dtype=np.float64)
    deg_s = np.empty(fract_count, dtype=np.float32)
    diff = np.empty(fract_count, dtype=np.float64)

    g_max_d = 0
    for s in range(-sec_n, sec_n, 1):
        deg_d.fill(s/fact)
        deg_s.fill(s/fact)
        np.add(deg_d, frac_d, out=out_d)
        np.add(deg_s, frac_s, out=out_s)
        np.absolute(out_d - out_s, out=diff)
        max_d = max(diff)
        if max_d > g_max_d:
            g_max_d = max_d
        if (s*100 % sec_n == 0) or (s == sec_n-1):
        # if True:
            print(f'{s*100 // sec_n}%: {s}/{sec_n}: '
                  f'{max_d}(d) {max_d * deg_to_meter}(m), '
                  f'global: {g_max_d}(d) {g_max_d * deg_to_meter}(m), '
                  f'min_deg:{min(deg_d)}, min_deg:{max(deg_d)}')


if __name__ == '__main__':
    fact = 3600
    sec_n = 180 * fact
    R = 6378137
    deg_to_meter = 2 * math.pi * R / 360

    fract_count = 10_000
    calc_b(sec_n, fract_count, deg_to_meter, fact)
