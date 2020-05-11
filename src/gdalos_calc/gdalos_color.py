import re
import gdal
from xml.dom import minidom
from collections import OrderedDict
from pathlib import Path
import glob


def to_number(s):
    try:
        return int(s)
    except ValueError:
        return float(s)


def byte(number, i):
    return (number & (0xff << (i * 8))) >> (i * 8)


class ColorPalette:
    __slots__ = ['pal', '_all_numeric']

    def __init__(self):
        self.pal = OrderedDict()
        self._all_numeric = True

    def __repr__(self):
        return str(self.pal)

    def apply_percent(self, min_val, max_val):
        if self._all_numeric:
            # nothing to do
            return
        all_numeric = True
        new_pal = self.pal.copy()
        for val in self.pal.keys():
            if not isinstance(val, str):
                continue
            is_percent = val.endswith('%')
            if is_percent:
                new_val = val.rstrip('%')
                try:
                    new_val = to_number(new_val)
                    if is_percent:
                        new_val = (max_val - min_val) * new_val * 0.01 + min_val
                    new_pal[new_val] = new_pal.pop(val)
                except ValueError:
                    all_numeric = False
            else:
                all_numeric = False
                continue
        if all_numeric:
            self._all_numeric = True
        self.pal = new_pal

    def read(self, filename):
        if Path(filename).suffix.lower() == '.qlr':
            self.read_qlr(filename)
        else:
            self.read_color_file(filename)

    def read_color_file(self, color_filename):
        self.pal.clear()
        with open(str(color_filename)) as fp:
            for line in fp:
                split_line = line.strip().split(' ', maxsplit=1)
                color = self.pal_color_to_rgb(split_line[1])

                key = split_line[0].strip()
                try:
                    key = to_number(key)
                except ValueError:
                    # should be percent
                    self._all_numeric = False
                    pass
                self.pal[key] = color

    def write_color_file(self, color_filename):
        with open(str(color_filename), mode='w') as fp:
            for key, color in self.pal.items():
                cc = self.color_to_cc(color)
                cc = ' '.join(str(c) for c in cc)
                fp.write('{} {}\n'.format(key, cc))

    def read_qlr(self, qlr_filename):
        self.pal.clear()
        qlr = minidom.parse(str(qlr_filename))
        #             <paletteEntry color="#ffffff" alpha="0" label="0" value="0"/>
        color_palette = qlr.getElementsByTagName("paletteEntry")
        for palette_entry in color_palette:
            color = palette_entry.getAttribute("color")
            if str(color).startswith('#'):
                color = int(color[1:], 16)
            alpha = int(palette_entry.getAttribute("alpha"))
            color = color + alpha * 255**3
            key = int(palette_entry.getAttribute("value"))
            self.pal[key] = color

    def get_color_table(self):
        # create color table
        color_table = gdal.ColorTable()
        for key, col in self.pal.items():
            color_table.SetColorEntry(key, self.color_to_cc(col))  # set color for each key

        # fill palette below min and above max
        keys = list(self.pal.keys())
        colors = list(self.pal.values())
        min_key = keys[0]
        min_col = self.color_to_cc(colors[0])
        for i in range(0, min_key):
            color_table.SetColorEntry(i, min_col)
        max_key = keys[-1]
        max_col = self.color_to_cc(colors[-1])
        for i in range(max_key+1, 256):
            color_table.SetColorEntry(i, max_col)

        return color_table

    @staticmethod
    def color_to_cc(color):
        if color < 256:
            return color
        else:
            b = byte(color, 1)
            g = byte(color, 2)
            r = byte(color, 3)
            a = byte(color, 4)

            if a > 0:
                return r, g, b, a
            else:
                return r, g, b

    @staticmethod
    def pal_color_to_rgb(cc):
        # r g b a -> argb
        # todo: support color names or just find the gdal implementation of this function...
        # cc = color components
        cc = re.findall(r'\d+', cc)
        try:
            # if not rgb_colors:
            #     return (*(int(c) for c in cc),)
            if len(cc) == 1:
                return int(cc[0])
            elif len(cc) == 3:
                return (((int(cc[0]) << 8) + int(cc[1])) << 8) + int(cc[2])
            elif len(cc) == 4:
                return (((((int(cc[3]) << 8) + int(cc[0])) << 8) + int(cc[1])) << 8) + int(cc[2])
            else:
                return 0
        except:
            return 0


def qlr_to_color_file(qlr_filename: Path) -> Path:
    qlr_filename = Path(qlr_filename)
    cp = ColorPalette()
    cp.read_qlr(qlr_filename)
    color_filename = qlr_filename.with_suffix('.txt')
    cp.write_color_file(color_filename)
    return color_filename


if __name__ == "__main__":
    cp = ColorPalette()
    dir_path = Path('/home/idan/maps/comb')
    for filename in glob.glob(str(dir_path / '*.qlr')):
        qlr_to_color_file(filename)

