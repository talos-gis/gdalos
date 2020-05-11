from pathlib import Path
import re
from gdalos_calc import viewshed_params
import talos


def talos_run(md, interval, grid_range, center, oz, tz, output_path, func_name, classname, comb_classname):
    save_to_file = True
    talos.DeleteObjects(classname)
    talos.SetScriptWGSGeo(False)

    for i in grid_range:
        for j in grid_range:
            ox = center[0] + i * interval
            oy = center[1] + j * interval
            p = (ox, oy)
            f = talos.CreateObject(classname)
            name = '{}_{}'.format(i, j)
            talos.SetVal(f, 'Name', name)
            talos.SetVal(f, 'Geometry', p)
            talos.SetVal(f, 'Range', md)
            talos.SetVal(f, 'Height', oz)
            talos.SetVal(f, 'TargetHeight', tz)
            talos.Run(func_name)
            if save_to_file:
                filename = output_path / (name + '.tif')
                # talos.ShowMessage(filename)
                talos.RasterSaveToFile(f, str(filename), False)
    if save_to_file:
        combined = talos.GetObjects(comb_classname)[0]
        filename = output_path / 'combined.tif'
        # talos.ShowMessage(filename)
        talos.RasterSaveToFile(combined, str(filename), False)


if __name__ == "__main__":
    output_path = Path(r'd:\dev\talos\data\comb')
    vp = viewshed_params.get_test_viewshed_params()
    func_name = 'Viewshed'
    classname = 'T'+func_name
    comb_classname = 'TGlobal' + re.sub('[a-z]', '', func_name)

    talos_run(vp.md, vp.interval, vp.grid_range, vp.center, vp.oz, vp.tz, output_path, func_name, classname, comb_classname)
