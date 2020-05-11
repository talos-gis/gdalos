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

    def apply_percent(self, min_val, max_val):
        if self._all_numeric:
            # nothing to do
            return
        all_numeric = True
        for val in self.pal.keys():
            if not isinstance(val, str):
                continue
            is_percent = val.endswith('%')
            if is_percent:
                new_val = val.rstrip('%')
                try:
                    new_val = to_number(new_val)
                    if is_percent:
                        val = (max_val - min_val) * val * 0.01 + min_val
                    self.pal[new_val] = self.pal.pop(val)
                except ValueError:
                    all_numeric = False
            else:
                all_numeric = False
                continue
        if all_numeric:
            self._all_numeric = True

    def read_color_file(self, color_filename, min_val=0, max_val=256):
        self.pal.clear()
        try:
            with open(str(color_filename)) as fp:
                for line in fp:
                    split_line = line.strip().split(' ', maxsplit=1)
                    color = self.pal_color_to_rgb(split_line[1])

                    value = split_line[0].strip()
                    try:
                        value = to_number(value)
                    except ValueError:
                        # percent or color name
                        self._all_numeric = False
                        pass
                    self.pal[value] = color
        except IOError:
            values = None

    def write_color_file(self, color_filename):
        with open(str(color_filename), mode='w') as fp:
            for value, color in self.pal.items():
                fp.write('{} {}\n'.format(value, self.color_to_cc(color)))

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
            value = int(palette_entry.getAttribute("value"))
            self.pal[value] = color

    def get_color_table(self):
        # create color table
        color_table = gdal.ColorTable()
        values, colors = self.pal.items()
        min_val = values[0]
        min_col = colors[0]
        max_val = values[-1]
        max_col = colors[-1]
        for val, col in self.pal.items():
            # set color for each value
            color_table.SetColorEntry(val, col)
            # if val < min_val:
            #     min_val = val
            #     min_col = col
            # if val > min_val:
            #     max_val = val
            #     max_col = col

        # fill palette below min and above max
        for i in range(0, min_val):
            color_table.SetColorEntry(i, min_col)
        for i in range(max_val, 256):
            color_table.SetColorEntry(i, max_col)
        return color_table

    @staticmethod
    def color_to_cc(color):
        if color < 256:
            res = str(color)
        else:
            b = byte(color, 1)
            g = byte(color, 2)
            r = byte(color, 3)
            a = byte(color, 4)

            res = '{} {} {}'.format(r, g, b)
            if a > 0:
                res = '{} {}'.format(res, a)
        return res

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
                return (int(cc[0]) << 8 + int(cc[1])) << 8 + int(cc[2])
            elif len(cc) == 4:
                return ((int(cc[3]) << 8 + int(cc[0])) << 8 + int(cc[1])) << 8 + int(cc[2])
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

