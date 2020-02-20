:Name: gdalos
:Authors: Idan Miara, Ben Avrahami

.. |license| image:: https://img.shields.io/badge/license-MIT-blue.svg?style=flat-square
   :target: https://github.com/talos-gis/gdalos/raw/master/LICENSE

.. |GDAL| image:: https://github.com/OSGeo/gdal/raw/master/gdal/data/gdalicon.png?style=flat-square
   :target: https://github.com/OSGeo/gdal

.. |cog| image:: https://www.cogeo.org/images/logo/COG_Alt_Logo.png?style=flat-square
   :width: 50
   :target: https://www.cogeo.org/

|license|

gdalos is a simple Python library and GUI for raster processing using GDAL:

* creating Cloud Optimized GeoTIFFs
* adding overviews
* cropping
* transforming
* and more!

What is Cloud Optimized GeoTIFF? |cog|
======================================
    A Cloud Optimized GeoTIFF (COG) is a regular GeoTIFF file, aimed at being hosted on a HTTP file server, with an internal organization that enables more efficient workflows on the cloud. It does this by leveraging the ability of clients issuing ​HTTP GET range requests to ask for just the parts of a file they need.


What is GDAL? |GDAL|
=====================
    GDAL is a translator library for raster and vector geospatial data formats that is released under an X/MIT style Open Source License by the Open Source Geospatial Foundation. As a library, it presents a single raster abstract data model and single vector abstract data model to the calling application for all supported formats. It also comes with a variety of useful command line utilities for data translation and processing.


What is gdalos?
===============

    gdalos is a simple multi platform :code:`GDAL` translate/warp/addo python wrapper for raster batch processing.
    It uses the gdal python interface and on top of it many rules to automate the batch processing.
    gdalos can be used to make a :code:`Cloud Optimized GeoTIFF` easily with proper overviews from any raster that can be read with GDAL.
    I hope some of you might find it useful.
    look at example.py for some examples.

    * What is gdalos_qt?
        gdalos_qt is a simple GUI wrapper for gdalos using the Qt5 library with the PyQt5 or PySide backends.
        gdalos package includes both gdalos and gdalos_qt

Installation
============

    gdalos requires Python >= 3.6. If you want to use the gdalos_qt GUI you would need Python >= 3.7.
    gdalos also requires gdal to be installed on your Python.
    You can use install gdal in multiple ways, depending on your OS and configuration:

    * :code:`pypi`: https://pypi.org/project/GDAL/
    * :code:`conda`: https://anaconda.org/conda-forge/gdal
    * :code:`OSGeo4W` (windows): use the OSGeo4W Python distribution that comes, for instance, with QGIS 3.x.

You can install gdalos using pip using one of these options::

  $ pip install gdalos          # Installs gdalos without the gdalos_qt UI dependencies
  $ pip install gdalos[pyqt]    # If you want to use gdalos_qt with the PyQt backend
  $ pip install gdalos[pyside]  # If you want to use gdalos_qt with the PySide backend


Usage - Running:
================

* Run with the Graphical UI::

    $ python -m gdalos_qt

* Creating a :code:`cog` in via the Python shell:

  >>> from gdalos import gdalos_trans
  >>> gdalos_trans('/maps/srtm.tif')

Using the gdalos_qt GUI:
========================
gdalos GUI currently is very minimalistic... basic usage is as follows:

*  press on the '...' button next to button "0" to open the "job GUI"
*  press on the '...' button next to "source file" to select a source file
*  (optional) use whichever additional process you like
    * cropping
    * wrapping
    * output
* press OK
* (optional) press on the "0" button to add more job rows and repeat the above
* press OK to start


Support
=======

If you find any issue on gdalos or have questions,
please `open an issue on our repository <https://github.com/talos-gis/gdalos/issues/new>`_

Contributing
============

You want to contribute? Awesome!

We recommend `this GitHub workflow <https://www.asmeurer.com/git-workflow/>`_
to fork the repository. To run the tests,
use `tox <https://tox.readthedocs.io/>`_::

  $ tox

Before you send us a pull request, remember to reformat all the code::

  $ tox -e reformat

This will apply black, isort, and lots of love ❤️

License
=======

|license|

gdalos is released under the MIT license, hence allowing commercial
use of the library. Please refer to the :code:`LICENSE` file.
