class GeoRectangle:
    def __init__(self, x, y, w, h):
        if w <= 0 or h <= 0:
            h = 0
            w = 0
        self.x = x
        self.y = y
        self.w = w
        self.h = h

    def __eq__(self, other):
        if not isinstance(other, GeoRectangle):
            # don't attempt to compare against unrelated types
            return False
        return self.xywh == other.xywh

    def __round__(self, *args, **kwargs):
        return self.from_lrdu(*(round(i, *args, **kwargs) for i in self.lrdu))

    def is_empty(self):
        return self.w <= 0 or self.h <= 0

    def intersect(self, other: "GeoRectangle"):
        return GeoRectangle.from_min_max(
            max(self.min_x, other.min_x),
            min(self.max_x, other.max_x),
            max(self.min_y, other.min_y),
            min(self.max_y, other.max_y),
        )

    def union(self, other: "GeoRectangle"):
        return GeoRectangle.from_min_max(
            min(self.min_x, other.min_x),
            max(self.max_x, other.max_x),
            min(self.min_y, other.min_y),
            max(self.max_y, other.max_y),
        )

    def round(self, digits):
        self.x = round(self.x, digits)
        self.y = round(self.y, digits)
        self.w = round(self.w, digits)
        self.h = round(self.h, digits)

    def align(self, geo_transform):
        # compute the pixel-aligned bounding box (larger than the feature's bbox)
        left = self.min_x - (self.min_x - geo_transform[0]) % geo_transform[1]
        right = self.max_x + (geo_transform[1] - ((self.max_x - geo_transform[0]) % geo_transform[1]))
        bottom = self.min_y + (geo_transform[5] - ((self.min_y - geo_transform[3]) % geo_transform[5]))
        top = self.max_y - (self.max_y - geo_transform[3]) % geo_transform[5]
        return self.from_lrud(left, right, top, bottom)

    def get_partition(self, part: "GeoRectangle"):
        # part: x,y - part indexes; w,h - part counts
        part_width = self.w / part.w
        part_hight = self.h / part.h
        return GeoRectangle(
            self.x + part.x * part_width,
            self.y + part.y * part_hight,
            part_width,
            part_hight,
        )

    @classmethod
    def empty(cls):
        return cls(0, 0, 0, 0)

    @classmethod
    def from_lrud(cls, l, r, u, d):
        ret = cls(l, d, r - l, u - d)
        return ret

    @classmethod
    # # same as min_max
    def from_lrdu(cls, l, r, d, u):
        ret = cls(l, d, r - l, u - d)
        return ret

    @classmethod
    # # same as min_max
    def from_xwyh(cls, x, w, y, h):
        ret = cls(x, y, w, h)
        return ret

    @classmethod
    # same as lrdu
    def from_min_max(cls, min_x, max_x, min_y, max_y):
        ret = cls(min_x, min_y, max_x - min_x, max_y - min_y)
        return ret

    @classmethod
    def from_points(cls, points):
        return cls.from_min_max(
            min(p[0] for p in points),
            max(p[0] for p in points),
            min(p[1] for p in points),
            max(p[1] for p in points),
        )

    @property
    def left(self):
        return self.x

    @property
    def right(self):
        return self.x + self.w

    @property
    def down(self):
        return self.y

    @property
    def up(self):
        return self.y + self.h

    @property
    def min_x(self):
        return self.x

    @property
    def max_x(self):
        return self.x + self.w

    @property
    def min_y(self):
        return self.y

    @property
    def max_y(self):
        return self.y + self.h

    @property
    def lurd(self):
        return self.left, self.up, self.right, self.down

    @property
    def lrud(self):
        return self.left, self.right, self.up, self.down

    @property
    def ldru(self):
        return self.left, self.down, self.right, self.up

    @property
    def lrdu(self):
        return self.left, self.right, self.down, self.up

    @property
    def xywh(self):
        return self.x, self.y, self.w, self.h

    @property
    def xwyh(self):
        return self.x, self.w, self.y, self.h

    @property
    def min_max(self):
        return self.min_x, self.max_x, self.min_y, self.max_y

    def __repr__(self):
        return f"Rectangle({self.x}, {self.y}, {self.w}, {self.h})"