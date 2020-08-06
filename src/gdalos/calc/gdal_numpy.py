import numpy as np
import gdal

gdal_dt_to_np_dt = {gdal.GDT_Byte: np.uint8,
                    gdal.GDT_UInt16: np.uint16,
                    gdal.GDT_Int16: np.int16,
                    gdal.GDT_UInt32: np.uint32,
                    gdal.GDT_Int32: np.int32,
                    gdal.GDT_Float32: np.float32,
                    gdal.GDT_Float64: np.float64}
