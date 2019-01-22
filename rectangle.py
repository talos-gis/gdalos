class GeoRectangle:
    def __init__(self, x, y, w, h):
        self.x = x
        self.y = y
        self.w = w
        self.h = h

    @classmethod
    def from_lrdu(cls, l, r, d, u):
        return cls(l, u, r-l, u-d)

    @classmethod
    def from_points(cls, points):
        return cls.from_lrdu(
            min(p[0] for p in points),
            max(p[0] for p in points),
            min(p[1] for p in points),
            max(p[1] for p in points),
        )

    def crop(self, other: 'GeoRectangle'):
        return GeoRectangle.from_lrdu(
            max(self.left, other.left),
            min(self.right, other.right),
            max(self.down, other.down),
            min(self.up, other.up)
        )

    @property
    def left(self):
        return self.x

    @property
    def right(self):
        return self.x + self.w

    @property
    def up(self):
        return self.y

    @property
    def down(self):
        return self.y - self.h

    @property
    def lurd(self):
        return self.left, self.right, self.up, self.down

    @property
    def ldru(self):
        return self.left, self.down, self.up, self.up

    @property
    def lrdu(self):
        return self.left, self.right, self.up, self.down
