from pathlib import Path
import re
from gdalos.viewshed.viewshed_grid_params import ViewshedGridParams
import talos


def talos_run(vp: ViewshedGridParams, output_path, func_name, classname, comb_classname):
    save_to_file = True
    talos.DeleteObjects(classname)
    talos.SetScriptWGSGeo(False)

    arr = vp.get_array()
    for vp1 in arr:
        f = talos.CreateObject(classname)
        talos.SetVal(f, 'Name', vp1.name)
        talos.SetVal(f, 'Geometry', vp1.oxy)
        talos.SetVal(f, 'Range', vp1.max_r)
        talos.SetVal(f, 'Height', vp1.oz)
        talos.SetVal(f, 'TargetHeight', vp1.tz)
        talos.Run(func_name)
        if save_to_file:
            filename = output_path / func_name / (vp1.name + '.tif')
            # talos.ShowMessage(filename)
            talos.RasterSaveToFile(f, str(filename), False)
    if save_to_file:
        combined = talos.GetObjects(comb_classname)[0]
        filename = output_path / comb_classname / 'combined.tif'
        # talos.ShowMessage(filename)
        talos.RasterSaveToFile(combined, str(filename), False)


if __name__ == "__main__":
    output_path = Path(r'd:\dev\talos\data\comb')
    vp = ViewshedGridParams()
    func_name = 'Viewshed'
    classname = 'T'+func_name
    comb_classname = 'TGlobal' + re.sub('[a-z]', '', func_name)

    talos_run(vp, output_path, func_name, classname, comb_classname)
