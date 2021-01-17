import math
from gdalos.rectangle import GeoRectangle


def find_two_greatest_devisors(x: int):
    sqrtx = int(math.sqrt(x))
    for y in range(sqrtx, 1, -1):
        if x % y == 0:
            return int(x / y), y
    return x, 1


def make_partitions(x_parts, y_parts=None):
    if y_parts is None:
        x_parts, y_parts = find_two_greatest_devisors(x_parts)
    return list(
        GeoRectangle(i, j, x_parts, y_parts)
        for i in range(x_parts)
        for j in range(y_parts)
    )


if __name__ == '__main__':
    for i in range(100):
        print('{:2d} = {:2d} x {:2d}'.format(i, *find_two_greatest_devisors(i)))
