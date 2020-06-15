# http://resources.esri.com/help/9.3/arcgisdesktop/com/gp_toolref/spatial_analyst_tools/how_viewshed_works.htm
# https://desktop.arcgis.com/en/arcmap/10.3/tools/spatial-analyst-toolbox/using-viewshed-and-observer-points-for-visibility.htm
# For applications involving visibility with radio waves,
# the refraction correction to be applied depends on the wavelength of the signal.
# The location of telecommunication sites is not merely a simple matter of determining the intervisibility
# but, rather, involves a number of parameters associated with the modeling of radio wave propagation
# including reflection, refraction specific to the frequency, attenuation (signal weakening),
# interference, atmospheric effects, and so on.
# Nonetheless, Observer Points and Viewshed are appropriate tools to use during the preliminary
# investigation stages of assessing possible telecommunication sites and coverage.

# http://web.soccerlab.polymtl.ca/grass/monsterViewer.php?functionName=main&fileName=/data/project-manager/grass/grassSVN/grass-addons/raster/r.viewshed/main.cc&iframe=true&width=100%&height=100%#cloneCode
# atmospheric refraction coeff. 1/7 for visual, 0.325 for radio waves,
# in future we might calculate this based on the physics, for now we just fudge by the 1/7th approximation.

# https://invest.readthedocs.io/en/3.4.1/final_ecosystem_services/scenic_quality.html
# refraction (float) – The earth curvature correction option corrects for the curvature of the
# earth and refraction of visible light in air. Changes in air density curve the light downward causing
# an observer to see further and the earth to appear less curved. While the magnitude of this effect varies
# with atmospheric conditions, a standard rule of thumb is that refraction of visible light reduces the
# apparent curvature of the earth by one-seventh. By default, this model corrects for the curvature of the
# earth and sets the refractivity coefficient to 0.13.

# https://gdal.org/programs/gdal_viewshed.html
# https://grass.osgeo.org/grass78/manuals/r.viewshed.html
# grass refraction_coeff  = 1/7 ~= 0.14286
# gdal: curve_coefficient(cc) = 1-refraction_coeff = 0.85714 ~= 6/7
# gdal: height_corrected = dem_height - cc * target_distance^2/sphere_diameter = dem_height
# talos: earth_curve_factor = 1/cc = 1/(1-refraction_coeff); refraction_coeff = 1-1/earth_curve_factor
# talos: refraction_coeff = 1/7 -> earth_curve_factor = 7/6

# refraction_coeff values
# 0 -> normal sphere without correction
# 1/7 ~= 0.14286 -> normal correction for visible light
# 0.25~0.325 -> radio waves
# 1 -> flat earth


def height_correction(target_distance, refraction_coeff, sphere_radius=6378137):
    sphere_diameter = sphere_radius*2
    cc = 1-refraction_coeff
    return - cc * target_distance**2/sphere_diameter


# from itertools import chain
# lst = list(chain.from_iterable(((10*10**i, 50*10**i) for i in range(1, 6))))
lst = (100, 500, 1_000, 5_000, 10_000, 50_000, 100_000, 500_000)
for d in lst:
    for rf in (0, 1/7, 1/4, 0.325):
        print('d: {} rf: {:.5f} height_correction: {:2f}'.format(d, rf, height_correction(d, rf)))
    print('')
