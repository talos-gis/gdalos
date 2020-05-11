from gdalos_calc.gdal_calc import main
import sys

# /home/idan/dev/data/6comb
"""
-A 2.tif -B 4.tif --outfile=calc.tif --calc="A+B"
--overwrite -A 0.vrt -B 1.vrt -C 2.vrt -D 3.vrt -E 4.vrt -F 5.vrt --outfile=calc_vrt6.tif --calc="1*(A>2)+1*(B>2)+1*(C>2)+1*(D>2)+1*(E>2)+1*(F>2)"
--geotransforms 1 --ignoreNoDataValue --overwrite -A 0.vrt -B 1.vrt -C 2.vrt -D 3.vrt -E 4.vrt -F 5.vrt --outfile=calc_vrt62.tif --calc="1*(A>2)+1*(B>2)+1*(C>2)+1*(D>2)+1*(E>2)+1*(F>2)"

--geotransforms 2 --ignoreNoDataValue --overwrite -A 0.tif -B 1.tif -C 2.tif -D 3.tif -E 4.tif -F 5.tif --outfile=calc_vrt6_union.tif --calc="1*(A>2)+1*(B>2)+1*(C>2)+1*(D>2)+1*(E>2)+1*(F>2)"
--geotransforms 3 --ignoreNoDataValue --overwrite -A 0.tif -B 1.tif -C 2.tif -D 3.tif -E 4.tif -F 5.tif --outfile=calc_vrt6_crop.tif --calc="1*(A>2)+1*(B>2)+1*(C>2)+1*(D>2)+1*(E>2)+1*(F>2)"

"""

main(sys.argv)
