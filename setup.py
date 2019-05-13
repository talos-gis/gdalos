import setuptools

import gdalos

setuptools.setup(
    name=gdalos.__name__,
    version=gdalos.__version__,
    author=gdalos.__author__,
    description='',
    packages=['gdalos', 'gdalos_qt'],
    extras_require={
        'PyQt': ['PyQt5'],
        'PySide': ['PySide2']
    },
    python_requires='>=3.7.0',
    include_package_data=True,
    data_files=[
        ('', ['README.md']),
    ],
)
