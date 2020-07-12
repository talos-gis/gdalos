import os
import re
import gdal
from xml.dom import minidom
from collections import OrderedDict
from pathlib import Path
import glob
import tempfile
from typing import Sequence
import math


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

    def set_num_to_percent(self, ndv=True):
        new_pal = ColorPalette()
        for num, val in self.pal.items():
            if not isinstance(num, str):
                if num < 0:
                    num = 0
                elif num > 100:
                    num = 100
                num = str(num)+'%'
            new_pal.pal[num] = val
        new_pal._all_numeric = False
        if ndv:
            new_pal.pal['nv'] = 0
        return new_pal

    def apply_percent(self, min_val, max_val):
        if self._all_numeric:
            # nothing to do
            return
        all_numeric = True
        new_pal = self.pal.copy()
        for num in self.pal.keys():
            if not isinstance(num, str):
                continue
            is_percent = num.endswith('%')
            if is_percent:
                new_num = num.rstrip('%')
                try:
                    new_num = to_number(new_num)
                    if is_percent:
                        new_num = (max_val - min_val) * new_num * 0.01 + min_val
                    new_pal[new_num] = new_pal.pop(num)
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

    def read_talos_palette(self, s: str):
        self.pal.clear()
        self._all_numeric = True
        x = s.split(';')
        min_value = float(x[0])
        count = int(x[1])
        selected = x[2]
        lock_values = x[3]
        multiplier = float(x[4])
        special_draw = x[5]
        interpolate = x[6]
        log_base = float(x[8])
        if log_base == 0:
            ln_log_base = None
        else:
            ln_log_base = math.log(log_base)
        j = 8
        for i in range(count):
            name = x[j]
            color = x[j+2]
            color = self.pas_color_to_rgb(color)
            brush = x[j+3]
            key = min_value + i * multiplier
            if ln_log_base:
                key = math.exp(ln_log_base * key)  # == log_base^key
            self.pal[key] = color
            j += 4
        # flags = x[j]
        # pal_version = x[j+1]

    def read_color_file(self, color_filename):
        self.pal.clear()
        with open(str(color_filename)) as fp:
            for line in fp:
                split_line = line.strip().split(' ', maxsplit=1)
                if len(split_line) < 2:
                    continue
                try:
                    color = self.pal_color_to_rgb(split_line[1])
                    key = split_line[0].strip()
                except:
                    raise Exception('Error reading palette line: {}'.format(line))
                try:
                    key = to_number(key)
                except ValueError:
                    # should be percent
                    self._all_numeric = False
                    pass
                self.pal[key] = color

    def write_color_file(self, color_filename):
        os.makedirs(os.path.dirname(str(color_filename)), exist_ok=True)
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
            color = color + (alpha << 8*3)  # * 256**3
            key = int(palette_entry.getAttribute("value"))
            self.pal[key] = color

    def get_color_table(self, min_val=0, max_val=256, fill_missing_colors=True):
        # create color table
        color_table = gdal.ColorTable()
        if fill_missing_colors:
            keys = list(self.pal.keys())
            vals = list(self.pal.values())
            c = self.color_to_cc(vals[0])
            for key in range(min_val, max_val):
                if key in keys:
                    c = self.color_to_cc(self.pal[key])
                color_table.SetColorEntry(key, c)
        else:
            for key, col in self.pal.items():
                color_table.SetColorEntry(key, self.color_to_cc(col))  # set color for each key

        return color_table

    @staticmethod
    def format_number(num):
        return num if isinstance(num, str) else '{:.2f}'.format(num)

    @staticmethod
    def format_color(col):
        return col if isinstance(col, str) else '#{:06X}'.format(col)

    @staticmethod
    def color_to_cc(color):
        # if color < 256:
        #     return color
        # else:
            b = byte(color, 0)
            g = byte(color, 1)
            r = byte(color, 2)
            a = byte(color, 3)

            if a < 255:
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
                return (((((255 << 8) + int(cc[0])) << 8) + int(cc[1])) << 8) + int(cc[2])
            elif len(cc) == 4:
                return (((((int(cc[3]) << 8) + int(cc[0])) << 8) + int(cc[1])) << 8) + int(cc[2])
            else:
                return 0
        except:
            return 0

    @staticmethod
    def pas_color_to_rgb(col):
        # $CC00FF80
        # $AARRGGBB
        if isinstance(col, str):
            col = str(col).strip('$')
        return int(col, 16)


def qlr_to_color_file(qlr_filename: Path) -> Path:
    qlr_filename = Path(qlr_filename)
    pal = ColorPalette()
    pal.read_qlr(qlr_filename)
    color_filename = qlr_filename.with_suffix('.txt')
    pal.write_color_file(color_filename)
    return pal, color_filename


def talos_to_color_file(talos_pal: str, color_filename: Path) -> Path:
    pal = ColorPalette()
    pal.read_talos_palette(talos_pal)
    pal = pal.set_num_to_percent(ndv=True)
    pal.write_color_file(color_filename)
    return pal, color_filename


def get_file_from_strings(color_palette):
    temp_color_filename = None
    if isinstance(color_palette, ColorPalette):
        temp_color_filename = tempfile.mktemp(suffix='.txt')
        color_filename = temp_color_filename
        color_palette.write_color_file(temp_color_filename)
    elif isinstance(color_palette, (Path, str)):
        color_filename = color_palette
    elif isinstance(color_palette, Sequence):
        temp_color_filename = tempfile.mktemp(suffix='.txt')
        color_filename = temp_color_filename
        with open(temp_color_filename, 'w') as f:
            for item in color_palette:
                f.write(item+'\n')
    else:
        raise Exception('Unknown color palette type {}'.format(color_palette))
    return color_filename, temp_color_filename


def get_color_table(color_palette):
    if color_palette is None:
        return None
    color_filename, temp_color_filename = get_file_from_strings(color_palette)
    pal = ColorPalette()
    pal.read(color_filename)
    color_table = pal.get_color_table()
    if temp_color_filename:
        os.remove(temp_color_filename)
    return color_table


def test_talos_pal(talos_paletts):
    dir_path = Path(r'sample/color_files')
    for name, talos_pal in talos_paletts:
        path = dir_path / Path(name+'.txt')
        pal, filename = talos_to_color_file(talos_pal, path)
        print(filename, pal)


def test_qlr():
    # dir_path = Path('/home/idan/maps/comb')
    dir_path = Path(r'sample/color_files')
    for filename in glob.glob(str(dir_path / '*.qlr')):
        pal, filename = qlr_to_color_file(filename)
        print(filename, pal)


if __name__ == "__main__":
    my_talos_paletts = [
        ('percents',
         '0;7;6;0;16.666666666667;0;1;1;0;|;$CC00007F;0;3;2|;$CC0000FF;0;3;2|;$CC00FFFF;0;3;2|;$CC00FF00;0;3;2|;$CCFFFF00;0;3;2|;$CCFF0000;0;3;2|;$CCFF00FF;0;3;2')
    ]
    test_talos_pal(my_talos_paletts)
    # test_qlr()


