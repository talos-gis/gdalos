from setuptools import setup, find_packages

from src.gdalos import (
    __pacakge_name__,
    __author__,
    __author_email__,
    __license__,
    __url__,
    __version__,
    __description__,
)

classifiers = [
    'Development Status :: 5 - Production/Stable',
    'Intended Audience :: Developers',
    'Intended Audience :: Science/Research',
    'License :: OSI Approved :: MIT License',
    'Operating System :: OS Independent',
    'Programming Language :: Python :: 3',
    'Topic :: Scientific/Engineering :: GIS',
    'Topic :: Scientific/Engineering :: Information Analysis',
]

__readme__ = open('README.rst', encoding="utf-8").read()
__readme_type__ = 'text/x-rst'

package_root = 'src'   # package sources are under this dir
packages = find_packages(package_root)  # include all packages under package_root
package_dir = {'': package_root}  # packages sources are under package_root

setup(
    name=__pacakge_name__,
    version=__version__,
    author=__author__,
    author_email=__author_email__,
    license=__license__,
    url=__url__,
    long_description=__readme__,
    long_description_content_type=__readme_type__,
    description=__description__,
    packages=packages,
    package_dir=package_dir,
    extras_require={"gdal": ["gdal"], "PyQt": ["fidget", "PyQt5"], "PySide": ["fidget", "PySide2"]},
    python_requires=">=3.6.0",
    include_package_data=True,
    data_files=[("", ["README.rst", "LICENSE"])],
)
