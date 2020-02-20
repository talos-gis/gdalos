import setuptools

import gdalos_data

setuptools.setup(
    name='gdalos',
    version=gdalos_data.__version__,
    author=gdalos_data.__author__,
    license=gdalos_data.__license__,
    url=gdalos_data.__url__,
    description='a simple gdal translate/warp/addo python wrapper for raster batch processing',
    packages=['gdalos', 'gdalos_data', 'gdalos_qt'],
    install_requires=['gdal'],
    extras_require={
        'PyQt': ['fidget', 'PyQt5'],
        'PySide': ['fidget', 'PySide2']
    },
    python_requires='>=3.6.0',
    include_package_data=True,
    data_files=[
        ('', ['README.md', 'LICENSE']),
    ],
)
