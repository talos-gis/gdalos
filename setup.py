import setuptools

from src.gdalos_data.__data__ import (
    __author__,
    __author_email__,
    __license__,
    __url__,
    __version__,
)

setuptools.setup(
    name="gdalos",
    version=__version__,
    author=__author__,
    author_email=__author_email__,
    license=__license__,
    url=__url__,
    description="a simple gdal translate/warp/addo python wrapper for raster batch processing",
    package_dir={"": "src"},
    packages=["gdalos", "gdalos_data", "gdalos_qt"],
    install_requires=["gdal"],
    extras_require={"PyQt": ["fidget", "PyQt5"], "PySide": ["fidget", "PySide2"]},
    python_requires=">=3.6.0",
    include_package_data=True,
    data_files=[("", ["README.rst", "LICENSE"])],
)
