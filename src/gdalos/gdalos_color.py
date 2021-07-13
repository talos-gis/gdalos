import glob
import math
from pathlib import Path
from plistlib import Dict

from osgeo_utils.auxiliary.base import num
from osgeo_utils.auxiliary.color_palette import *  # noqa
from osgeo_utils.auxiliary.color_table import *  # noqa


def read_talos_palette(s: str) -> ColorPalette:
    res = ColorPalette()
    x = s.split(';')
    min_value = num(x[0])
    count = int(x[1])
    selected = x[2]
    lock_values = x[3]
    multiplier = num(x[4])
    special_draw = x[5]
    interpolate = x[6]
    log_base = num(x[8])
    if log_base == 0:
        ln_log_base = None
    else:
        ln_log_base = math.log(log_base)
    j = 8
    for i in range(count):
        name = x[j]
        color = x[j+2]
        color = res.pas_color_to_rgb(color)
        brush = x[j+3]
        key = min_value + i * multiplier
        if ln_log_base:
            key = math.exp(ln_log_base * key)  # == log_base^key
        res.pal[key] = color
        j += 4
    # flags = x[j]
    # pal_version = x[j+1]
    return res


def talos_to_color_file(talos_pal: str, color_filename: Path) -> Path:
    pal = read_talos_palette(talos_pal)
    pal = pal.replace_absolute_values_with_percent(ndv=True)
    pal.write_color_file(color_filename)
    return pal


def test_talos_pal(talos_paletts=None):
    if talos_paletts is None:
        talos_paletts = [
            ('percents',
             '0;7;6;0;16.666666666667;0;1;1;0;|;$CC00007F;0;3;2|;$CC0000FF;0;3;2|;$CC00FFFF;0;3;2|;$CC00FF00;0;3;2|;$CCFFFF00;0;3;2|;$CCFF0000;0;3;2|;$CCFF00FF;0;3;2')
        ]
    dir_path = Path(r'sample/color_files')
    for name, talos_pal in talos_paletts:
        path = dir_path / Path(name+'.txt')
        pal = talos_to_color_file(talos_pal, path)
        print(path, pal)


def test_xml(dir_path):
    for ext in ['qlr', 'qml']:
        for filename in glob.glob(base.path_join(dir_path, '**', '*.' + ext)):
            pal, filename = xml_to_color_file(filename, type=ext)
            print(filename, pal)


def read_color_palette_dict(color_palette: ColorPalette, d: Dict[str, str]):
    # {
    #     "0": "#FFff0000",
    #     "1": "#FF00ff00",
    #     "254": "#66000000",
    #     "255": "#00000000"
    # }
    color_palette.pal.clear()
    if "values" in d:
        d = d["values"]
    # nv = d.get('noDateValue')
    for key, color in d.items():
        if key != 'nv':
            key = num(key)
        if str(color).startswith('#'):
            color = int(color[1:], 16)
        color_palette.pal[key] = color


if __name__ == "__main__":
    test_talos_pal()
    # path = Path('/home/idan/maps/comb')
    path = Path(r'sample/color_files')
    test_xml(dir_path=path)
