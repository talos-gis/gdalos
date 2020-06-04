from collections import namedtuple

ViewshedGridParams = namedtuple('ViewshedGridParams', ['md', 'interval', 'grid_range', 'center', 'oz', 'tz'])


def get_test_viewshed_params() -> ViewshedGridParams:
    res = ViewshedGridParams
    res.md = 2000
    res.interval = res.md / 2
    j = 1
    res.grid_range = range(-j, j + 1)
    res.center = (700_000, 3550_000)
    res.oz = 10
    res.tz = 10
    return res

