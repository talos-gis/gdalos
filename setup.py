from setuptools import setup, find_packages

from src.gdalos import (
    __name__,
    __author__,
    __author_email__,
    __license__,
    __url__,
    __version__,
)

setup(
    name=__name__,
    version=__version__,
    author=__author__,
    author_email=__author_email__,
    license=__license__,
    url=__url__,
    description="a simple gdal translate/warp/addo python wrapper for raster batch processing",
    packages=find_packages("src"),  # include all packages under src
    package_dir={"": "src"},   # tell distutils packages are under src
    extras_require={"gdal": ["gdal"], "PyQt": ["fidget", "PyQt5"], "PySide": ["fidget", "PySide2"]},
    python_requires=">=3.6.0",
    include_package_data=True,
    data_files=[("", ["README.rst", "LICENSE"])],
)
