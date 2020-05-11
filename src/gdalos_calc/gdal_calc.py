#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# ******************************************************************************
#
#  Project:  GDAL
#  Purpose:  Command line raster calculator with numpy syntax
#  Author:   Chris Yesson, chris.yesson@ioz.ac.uk
#
# ******************************************************************************
#  Copyright (c) 2010, Chris Yesson <chris.yesson@ioz.ac.uk>
#  Copyright (c) 2010-2011, Even Rouault <even dot rouault at spatialys.com>
#  Copyright (c) 2016, Piers Titus van der Torren <pierstitus@gmail.com>
#
#  Permission is hereby granted, free of charge, to any person obtaining a
#  copy of this software and associated documentation files (the "Software"),
#  to deal in the Software without restriction, including without limitation
#  the rights to use, copy, modify, merge, publish, distribute, sublicense,
#  and/or sell copies of the Software, and to permit persons to whom the
#  Software is furnished to do so, subject to the following conditions:
#
#  The above copyright notice and this permission notice shall be included
#  in all copies or substantial portions of the Software.
#
#  THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS
#  OR IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
#  FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL
#  THE AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
#  LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING
#  FROM, OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER
#  DEALINGS IN THE SOFTWARE.
# ******************************************************************************

################################################################
# Command line raster calculator with numpy syntax. Use any basic arithmetic supported by numpy arrays such as +-*\ along with logical operators such as >.  Note that all files must have the same dimensions, but no projection checking is performed.  Use gdal_calc.py --help for list of options.

# example 1 - add two files together
# gdal_calc.py -A input1.tif -B input2.tif --outfile=result.tif --calc="A+B"

# example 2 - average of two layers
# gdal_calc.py -A input.tif -B input2.tif --outfile=result.tif --calc="(A+B)/2"

# example 3 - set values of zero and below to null
# gdal_calc.py -A input.tif --outfile=result.tif --calc="A*(A>0)" --NoDataValue=0
################################################################

from optparse import OptionParser, OptionConflictError, Values
import os
import os.path
import sys
import shlex

import numpy

from osgeo import gdal
from osgeo import gdalnumeric
from gdalos.rectangle import GetExtent, GetOffsets

# create alphabetic list for storing input layers
AlphaList = ["A", "B", "C", "D", "E", "F", "G", "H", "I", "J", "K", "L", "M",
             "N", "O", "P", "Q", "R", "S", "T", "U", "V", "W", "X", "Y", "Z"]

# set up some default nodatavalues for each datatype
DefaultNDVLookup = {'Byte': 255, 'UInt16': 65535, 'Int16': -32767, 'UInt32': 4294967293, 'Int32': -2147483647,
                    'Float32': 3.402823466E+38, 'Float64': 1.7976931348623158E+308}


def DoesDriverHandleExtension(drv, ext):
    exts = drv.GetMetadataItem(gdal.DMD_EXTENSIONS)
    return exts is not None and exts.lower().find(ext.lower()) >= 0


def GetExtension(filename):
    ext = os.path.splitext(filename)[1]
    if ext.startswith('.'):
        ext = ext[1:]
    return ext


def GetOutputDriversFor(filename):
    drv_list = []
    ext = GetExtension(filename)
    for i in range(gdal.GetDriverCount()):
        drv = gdal.GetDriver(i)
        if (drv.GetMetadataItem(gdal.DCAP_CREATE) is not None or
            drv.GetMetadataItem(gdal.DCAP_CREATECOPY) is not None) and \
                drv.GetMetadataItem(gdal.DCAP_RASTER) is not None:
            if ext and DoesDriverHandleExtension(drv, ext):
                drv_list.append(drv.ShortName)
            else:
                prefix = drv.GetMetadataItem(gdal.DMD_CONNECTION_PREFIX)
                if prefix is not None and filename.lower().startswith(prefix.lower()):
                    drv_list.append(drv.ShortName)

    # GMT is registered before netCDF for opening reasons, but we want
    # netCDF to be used by default for output.
    if ext.lower() == 'nc' and not drv_list and \
            drv_list[0].upper() == 'GMT' and drv_list[1].upper() == 'NETCDF':
        drv_list = ['NETCDF', 'GMT']

    return drv_list


def GetOutputDriverFor(filename):
    drv_list = GetOutputDriversFor(filename)
    ext = GetExtension(filename)
    if not drv_list:
        if not ext:
            return 'GTiff'
        else:
            raise Exception("Cannot guess driver for %s" % filename)
    elif len(drv_list) > 1:
        print("Several drivers matching %s extension. Using %s" % (ext if ext else '', drv_list[0]))
    return drv_list[0]


################################################################


def doit(opts, args):
    # pylint: disable=unused-argument

    if opts.debug:
        print("gdal_calc.py starting calculation %s" % (opts.calc))

    # set up global namespace for eval with all functions of gdalnumeric
    global_namespace = dict([(key, getattr(gdalnumeric, key))
                             for key in dir(gdalnumeric) if not key.startswith('__')])

    if not opts.calc:
        raise Exception("No calculation provided.")
    elif not opts.outF:
        raise Exception("No output file provided.")

    if opts.format is None:
        opts.format = GetOutputDriverFor(opts.outF)

    ################################################################
    # fetch details of input layers
    ################################################################

    # set up some lists to store data for each band
    myFileNames = []
    myFiles = []
    myBands = []
    myAlphaList = []
    myDataType = []
    myDataTypeNum = []
    myNDV = []
    DimensionsCheck = None
    Dimensions = []
    ProjectionCheck = None
    GeoTransformCheck = None
    GeoTransforms = []
    GeoTransformDiffer = False

    # loop through input files - checking dimensions
    for myI, myF in opts.input_files.items():
        if not myI.endswith("_band"):
            # check if we have asked for a specific band...
            if "%s_band" % myI in opts.input_files:
                myBand = opts.input_files["%s_band" % myI]
            else:
                myBand = 1

            myFile = gdal.Open(myF, gdal.GA_ReadOnly)
            if not myFile:
                raise IOError("No such file or directory: '%s'" % myF)

            myFileNames.append(myF)
            myFiles.append(myFile)
            myBands.append(myBand)
            myAlphaList.append(myI)
            myDataType.append(gdal.GetDataTypeName(myFile.GetRasterBand(myBand).DataType))
            myDataTypeNum.append(myFile.GetRasterBand(myBand).DataType)
            myNDV.append(None if opts.ignoreNDV else myFile.GetRasterBand(myBand).GetNoDataValue())

            # check that the dimensions of each layer are the same
            myFileDimensions = [myFile.RasterXSize, myFile.RasterYSize]
            if DimensionsCheck:
                if DimensionsCheck != myFileDimensions:
                    GeoTransformDiffer = True
                    if opts.geotransforms <= 1:
                        raise Exception("Error! Dimensions of file %s (%i, %i) are different from other files (%i, %i).  Cannot proceed" %
                                        (myF, myFileDimensions[0], myFileDimensions[1], DimensionsCheck[0], DimensionsCheck[1]))
            else:
                DimensionsCheck = myFileDimensions

            # check that the Projection of each layer are the same
            myProjection = myFile.GetProjection()
            if ProjectionCheck:
                if opts.projectionCheck and ProjectionCheck != myProjection:
                    raise Exception(
                        "Error! Projection of file %s %s are different from other files %s.  Cannot proceed" %
                        (myF, myProjection, ProjectionCheck))
            else:
                ProjectionCheck = myProjection

            # check that the GeoTransforms of each layer are the same
            myFileGeoTransform = myFile.GetGeoTransform()
            if opts.geotransforms:
                Dimensions.append(myFileDimensions)
                GeoTransforms.append(myFileGeoTransform)
                if GeoTransformCheck:
                    if GeoTransformCheck != myFileGeoTransform:
                        GeoTransformDiffer = True
                        if opts.geotransforms == 1:
                            raise Exception(
                                "Error! GeoTransform of file %s %s are different from other files %s.  Cannot proceed" %
                                (myF, myFileGeoTransform, GeoTransformCheck))
                        else:
                            for i in (1, 5):
                                if GeoTransformCheck[i] != myFileGeoTransform[i]:
                                    raise Exception(
                                        "Error! Pixel size file %s %s are different from other files %s.  Cannot proceed" %
                                        (myF, myFileGeoTransform, GeoTransformCheck))
                            for i in (2, 4):
                                if GeoTransformCheck[i] != myFileGeoTransform[i]:
                                    raise Exception(
                                        "Error! The rotation of file %s is %s, only 0 is accepted.  Cannot proceed" %
                                        (myF, (myFileGeoTransform[2], myFileGeoTransform[4]), GeoTransformCheck))
                else:
                    GeoTransformCheck = myFileGeoTransform
            else:
                GeoTransformCheck = myFileGeoTransform

            if opts.debug:
                print("file %s: %s, dimensions: %s, %s, type: %s" % (
                myI, myF, DimensionsCheck[0], DimensionsCheck[1], myDataType[-1]))

    # process allBands option
    allBandsIndex = None
    allBandsCount = 1
    if opts.allBands:
        try:
            allBandsIndex = myAlphaList.index(opts.allBands)
        except ValueError:
            raise Exception("Error! allBands option was given but Band %s not found.  Cannot proceed" % (opts.allBands))
        allBandsCount = myFiles[allBandsIndex].RasterCount
        if allBandsCount <= 1:
            allBandsIndex = None

    if opts.geotransforms and GeoTransformDiffer:
        extent = GetExtent(GeoTransforms, Dimensions, opts.geotransforms == 2)
        if extent is None:
            raise Exception("Error! The requested extent is empty. Cannot proceed")
        GeoTransformCheck, DimensionsCheck = extent
        for i, myFileName in enumerate(myFileNames):
            myFile = myFiles[i]
            drv = gdal.GetDriverByName("VRT")
            dt = gdal.GetDataTypeByName(myDataType[i])
            myOut = drv.Create(
                myFileName+".vrt", DimensionsCheck[0], DimensionsCheck[1], allBandsCount, dt)
            myOut.SetGeoTransform(GeoTransformCheck)
            myOut.SetProjection(ProjectionCheck)

            offsets = GetOffsets(GeoTransforms[i], Dimensions[i], GeoTransformCheck, DimensionsCheck)
            if offsets is None:
                raise Exception("Error! The requested extent is empty. Cannot proceed")
            src_offset, dst_offset = offsets

            source_size = Dimensions[i]

            for j in range(1, allBandsCount + 1):
                band = myOut.GetRasterBand(j)
                inBand = myFile.GetRasterBand(j)
                myBlockSize = inBand.GetBlockSize()

                myOutNDV = inBand.GetNoDataValue()
                if myOutNDV is not None:
                    band.SetNoDataValue(myOutNDV)
                ndv_out = '' if myOutNDV is None else '<NODATA>%i</NODATA>' % myOutNDV

                source_xml = '<SourceFilename relativeToVRT="1">%s</SourceFilename>' % myFileName + \
                                '<SourceBand>%i</SourceBand>' % j + \
                                '<SourceProperties RasterXSize="%i" RasterYSize="%i" DataType=%s BlockXSize="%i" BlockYSize="%i"/>' % \
                                (*source_size, dt, *myBlockSize) + \
                                '<SrcRect xOff="%i" yOff="%i" xSize="%i" ySize="%i"/>' % \
                                (*src_offset, *source_size) + \
                                '<DstRect xOff="%i" yOff="%i" xSize="%i" ySize="%i"/>' % \
                                (*dst_offset, *source_size) + \
                                ndv_out
                source = '<ComplexSource>'+source_xml+'</ComplexSource>'
                band.SetMetadataItem("source_%i" % j, source, 'new_vrt_sources')
                band = None
            myFiles[i] = myOut
            myFile = None


    ################################################################
    # set up output file
    ################################################################

    # open output file exists
    if os.path.isfile(opts.outF) and not opts.overwrite:
        if allBandsIndex is not None:
            raise Exception("Error! allBands option was given but Output file exists, must use --overwrite option!")
        if opts.debug:
            print("Output file %s exists - filling in results into file" % (opts.outF))
        myOut = gdal.Open(opts.outF, gdal.GA_Update)

        error = None
        if [myOut.RasterXSize, myOut.RasterYSize] != DimensionsCheck:
            error = 'size'
        elif ProjectionCheck and ProjectionCheck != myOut.GetProjection():
            error = 'geotransform'
        elif GeoTransformCheck and GeoTransformCheck != myOut.GetGeoTransform():
            error = 'projection'
        if error:
            raise Exception("Error! Output exists, but is the wrong %s.  Use the --overwrite option to automatically overwrite the existing file" % error)

        myOutB = myOut.GetRasterBand(1)
        myOutNDV = myOutB.GetNoDataValue()
        myOutType = gdal.GetDataTypeName(myOutB.DataType)

    else:
        # remove existing file and regenerate
        if os.path.isfile(opts.outF):
            os.remove(opts.outF)
        # create a new file
        if opts.debug:
            print("Generating output file %s" % (opts.outF))

        # find data type to use
        if not opts.type:
            # use the largest type of the input files
            myOutType = gdal.GetDataTypeName(max(myDataTypeNum))
        else:
            myOutType = opts.type

        # create file
        myOutDrv = gdal.GetDriverByName(opts.format)
        myOut = myOutDrv.Create(
            opts.outF, DimensionsCheck[0], DimensionsCheck[1], allBandsCount,
            gdal.GetDataTypeByName(myOutType), opts.creation_options)

        # set output geo info based on first input layer
        if not GeoTransformCheck:
            GeoTransformCheck = myFiles[0].GetGeoTransform()
        myOut.SetGeoTransform(GeoTransformCheck)
        if not ProjectionCheck:
            ProjectionCheck = myFiles[0].GetProjection()
        myOut.SetProjection(ProjectionCheck)

        if opts.NoDataValue is not None:
            myOutNDV = opts.NoDataValue
        else:
            myOutNDV = DefaultNDVLookup[myOutType]

        for i in range(1, allBandsCount + 1):
            myOutB = myOut.GetRasterBand(i)
            myOutB.SetNoDataValue(myOutNDV)
            # write to band
            myOutB = None

    if opts.debug:
        print("output file: %s, dimensions: %s, %s, type: %s" % (
        opts.outF, myOut.RasterXSize, myOut.RasterYSize, myOutType))

    ################################################################
    # find block size to chop grids into bite-sized chunks
    ################################################################

    # use the block size of the first layer to read efficiently
    myBlockSize = myFiles[0].GetRasterBand(myBands[0]).GetBlockSize()
    # find total x and y blocks to be read
    nXBlocks = (int)((DimensionsCheck[0] + myBlockSize[0] - 1) / myBlockSize[0])
    nYBlocks = (int)((DimensionsCheck[1] + myBlockSize[1] - 1) / myBlockSize[1])
    myBufSize = myBlockSize[0] * myBlockSize[1]

    if opts.debug:
        print("using blocksize %s x %s" % (myBlockSize[0], myBlockSize[1]))

    # variables for displaying progress
    ProgressCt = -1
    ProgressMk = -1
    ProgressEnd = nXBlocks * nYBlocks * allBandsCount

    ################################################################
    # start looping through each band in allBandsCount
    ################################################################

    for bandNo in range(1, allBandsCount + 1):

        ################################################################
        # start looping through blocks of data
        ################################################################

        # store these numbers in variables that may change later
        nXValid = myBlockSize[0]
        nYValid = myBlockSize[1]

        # loop through X-lines
        for X in range(0, nXBlocks):

            # in case the blocks don't fit perfectly
            # change the block size of the final piece
            if X == nXBlocks - 1:
                nXValid = DimensionsCheck[0] - X * myBlockSize[0]

            # find X offset
            myX = X * myBlockSize[0]

            # reset buffer size for start of Y loop
            nYValid = myBlockSize[1]
            myBufSize = nXValid * nYValid

            # loop through Y lines
            for Y in range(0, nYBlocks):
                ProgressCt += 1
                if 10 * ProgressCt / ProgressEnd % 10 != ProgressMk and not opts.quiet:
                    ProgressMk = 10 * ProgressCt / ProgressEnd % 10
                    from sys import version_info
                    if version_info >= (3, 0, 0):
                        exec('print("%d.." % (10*ProgressMk), end=" ")')
                    else:
                        exec('print 10*ProgressMk, "..",')

                # change the block size of the final piece
                if Y == nYBlocks - 1:
                    nYValid = DimensionsCheck[1] - Y * myBlockSize[1]
                    myBufSize = nXValid * nYValid

                # find Y offset
                myY = Y * myBlockSize[1]

                # create empty buffer to mark where nodata occurs
                myNDVs = None

                # make local namespace for calculation
                local_namespace = {}

                # fetch data for each input layer
                for i, Alpha in enumerate(myAlphaList):

                    # populate lettered arrays with values
                    if allBandsIndex is not None and allBandsIndex == i:
                        myBandNo = bandNo
                    else:
                        myBandNo = myBands[i]
                    myval = gdalnumeric.BandReadAsArray(myFiles[i].GetRasterBand(myBandNo),
                                                        xoff=myX, yoff=myY,
                                                        win_xsize=nXValid, win_ysize=nYValid)

                    # fill in nodata values
                    if myNDV[i] is not None:
                        # myNDVs is a boolean buffer.
                        # a cell equals to 1 if there is NDV in any of the corresponsing cells in input raster bands.
                        if myNDVs is None:
                            # this is the first band that has NDV set. we initializes myNDVs to a zero buffer
                            # as we didn't see any NDV value yet.
                            myNDVs = numpy.zeros(myBufSize)
                            myNDVs.shape = (nYValid, nXValid)
                        myNDVs = 1 * numpy.logical_or(myNDVs == 1, myval == myNDV[i])

                    # add an array of values for this block to the eval namespace
                    local_namespace[Alpha] = myval
                    myval = None

                # try the calculation on the array blocks
                try:
                    myResult = eval(opts.calc, global_namespace, local_namespace)
                except:
                    print("evaluation of calculation %s failed" % (opts.calc))
                    raise

                # Propagate nodata values (set nodata cells to zero
                # then add nodata value to these cells).
                if myNDVs is not None:
                    myResult = ((1 * (myNDVs == 0)) * myResult) + (myOutNDV * myNDVs)
                elif not isinstance(myResult, numpy.ndarray):
                    myResult = numpy.ones((nYValid, nXValid)) * myResult

                # write data block to the output file
                myOutB = myOut.GetRasterBand(bandNo)
                gdalnumeric.BandWriteArray(myOutB, myResult, xoff=myX, yoff=myY)

    if not opts.quiet:
        print("100 - Done")

################################################################


def Calc(calc, outfile, NoDataValue=None, type=None, format=None, creation_options=None, allBands='', overwrite=False,
         debug=False, quiet=False, color_table=None, extent=None, **input_files):
    """ Perform raster calculations with numpy syntax.
    Use any basic arithmetic supported by numpy arrays such as +-*\ along with logical
    operators such as >. Note that all files must have the same dimensions, but no projection checking is performed.

    Keyword arguments:
        [A-Z]: input files
        [A_band - Z_band]: band to use for respective input file

    Examples:
    add two files together:
        Calc("A+B", A="input1.tif", B="input2.tif", outfile="result.tif")

    average of two layers:
        Calc(calc="(A+B)/2", A="input1.tif", B="input2.tif", outfile="result.tif")

    set values of zero and below to null:
        Calc(calc="A*(A>0)", A="input.tif", A_band=2, outfile="result.tif", NoDataValue=0)
    """
    opts = Values()
    opts.input_files = input_files
    opts.calc = calc
    opts.outF = outfile
    opts.NoDataValue = NoDataValue
    opts.type = type
    opts.format = format
    opts.creation_options = [] if creation_options is None else creation_options
    opts.allBands = allBands
    opts.overwrite = overwrite
    opts.debug = debug
    opts.quiet = quiet
    opts.color_table = color_table
    opts.extent = extent
    # extent=None - default - use the extent of the first file
    # extent=False - Intersection
    # extent=True - Union
    # extent=given extent - use the given extent

    doit(opts, None)


def store_input_file(option, opt_str, value, parser):
    # pylint: disable=unused-argument
    if not hasattr(parser.values, 'input_files'):
        parser.values.input_files = {}
    parser.values.input_files[opt_str.lstrip('-')] = value


def add_alpha_args(parser, argv):
    # limit the input file options to the ones in the argument list
    given_args = set([a[1] for a in argv if a[1:2] in AlphaList] + ['A'])
    for myAlpha in given_args:
        try:
            parser.add_option("-%s" % myAlpha, action="callback", callback=store_input_file, type=str,
                              help="input gdal raster file, you can use any letter (A-Z)", metavar='filename')
            parser.add_option("--%s_band" % myAlpha, action="callback", callback=store_input_file, type=int,
                              help="number of raster band for file %s (default 1)" % myAlpha, metavar='n')
        except OptionConflictError:
            pass


def main():
    usage = """usage: %prog --calc=expression --outfile=out_filename [-A filename]
                    [--A_band=n] [-B...-Z filename] [other_options]"""
    parser = OptionParser(usage)

    # define options
    parser.add_option("--calc", dest="calc",
                      help="calculation in gdalnumeric syntax using +-/* or any numpy array functions (i.e. log10())",
                      metavar="expression")
    add_alpha_args(parser, sys.argv)

    parser.add_option("--outfile", dest="outF", help="output file to generate or fill", metavar="filename")
    parser.add_option("--NoDataValue", dest="NoDataValue", type=float,
                      help="output nodata value (default datatype specific value)", metavar="value")
    parser.add_option("--ignoreNoDataValue", dest="ignoreNDV", action="store_true",
                      help="ignores the NoDataValues of the rasters", metavar="value")
    parser.add_option("--type", dest="type", help="output datatype, must be one of %s" % list(DefaultNDVLookup.keys()),
                      metavar="datatype")
    parser.add_option("--format", dest="format", help="GDAL format for output file", metavar="gdal_format")
    parser.add_option(
        "--creation-option", "--co", dest="creation_options", default=[], action="append",
        help="Passes a creation option to the output format driver. Multiple "
             "options may be listed. See format specific documentation for legal "
             "creation options for each format.", metavar="option")
    parser.add_option("--allBands", dest="allBands", default="", help="process all bands of given raster (A-Z)",
                      metavar="[A-Z]")
    parser.add_option("--overwrite", dest="overwrite", action="store_true",
                      help="overwrite output file if it already exists")
    parser.add_option("--debug", dest="debug", action="store_true", help="print debugging information")
    parser.add_option("--quiet", dest="quiet", action="store_true", help="suppress progress messages")
    parser.add_option("--optfile", dest="optfile", metavar="optfile",
                      help="Read the named file and substitute the contents into the command line options list.")
    parser.add_option("--geotransforms", dest="geotransforms", type=str,
                      help="how to treat different geotrasnforms [ignore|fail|union|intersect]")
    parser.add_option("--projectionCheck", dest="projectionCheck", action="store_true",
                      help="check that all rasters share the same projection", metavar="value")
    # when geotransforms don't agree: 0=ignore(check only dims)/1=fail (gt must also agree)/2=union/3=intersection

    (opts, args) = parser.parse_args()

    if not hasattr(opts, "input_files"):
        opts.input_files = {}

    if opts.optfile:
        with open(opts.optfile, 'r') as f:
            ofargv = [x for line in f for x in shlex.split(line, comments=True)]
        # Avoid potential recursion.
        parser.remove_option('--optfile')
        add_alpha_args(parser, ofargv)
        ofopts, ofargs = parser.parse_args(ofargv)
        # Let options given directly override the optfile.
        input_files = getattr(ofopts, 'input_files', {})
        input_files.update(opts.input_files)
        ofopts.__dict__.update({k: v for k, v in vars(opts).items() if v})
        opts = ofopts
        opts.input_files = input_files
        args = args + ofargs

    if len(sys.argv) == 1:
        parser.print_help()
        sys.exit(1)
    elif not opts.calc:
        print("No calculation provided. Nothing to do!")
        parser.print_help()
        sys.exit(1)
    elif not opts.outF:
        print("No output file provided. Cannot proceed.")
        parser.print_help()
        sys.exit(1)
    else:
        try:
            doit(opts, args)
        except IOError as e:
            print(e)
            sys.exit(1)


if __name__ == "__main__":
    main()