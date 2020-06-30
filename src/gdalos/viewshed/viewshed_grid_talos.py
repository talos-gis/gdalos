import os
from pathlib import Path
import re
from gdalos.viewshed.viewshed_grid_params import ViewshedGridParams
import talos


def talos_run(vp: ViewshedGridParams, output_path, func_name, classname, comb_classname, save_to_file):
    talos.DeleteObjects(classname)
    talos.SetScriptWGSGeo(False)

    arr = vp.get_array()

    output_path1 = output_path / func_name
    os.makedirs(output_path1, exist_ok=True)
    output_path2 = output_path / comb_classname
    os.makedirs(output_path2, exist_ok=True)

    for vp1 in arr:
        f = talos.CreateObject(classname)
        talos.SetVal(f, 'Name', vp1.name)
        talos.SetVal(f, 'Geometry', vp1.oxy)
        talos.SetVal(f, 'Range', vp1.max_r)
        talos.SetVal(f, 'Height', vp1.oz)
        talos.SetVal(f, 'TargetHeight', vp1.tz)
        talos.Run(func_name)
        if save_to_file:
            filename = output_path1 / (vp1.name + '.tif')
            # talos.ShowMessage(filename)
            talos.RasterSaveToFile(f, str(filename), False)
    if save_to_file:
        combined = talos.GetObjects(comb_classname)[0]
        filename = output_path2 / 'combined.tif'
        # talos.ShowMessage(filename)
        talos.RasterSaveToFile(combined, str(filename), False)


if __name__ == "__main__":
    output_path = Path(r'd:\dev\gis\maps\comb_ViewshedBackend.TALOS0')
    save_to_file = True
    vp = ViewshedGridParams()
    func_name = 'FieldOfSight'
    classname = 'T'+func_name
    comb_classname = 'TGlobal' + re.sub('[a-z]', '', func_name)

    talos_run(vp, output_path, func_name, classname, comb_classname, save_to_file)
