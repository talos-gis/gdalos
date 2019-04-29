# What do we want from GDALOS?
* format conversion (including creation options like compression)
* CRS conversion
* OVR conversion/generation
* cropping
* file search

# How do we do it?
1. figure out your source and destination files (i don't like the auto-naming shtick but it can be preserved here). figure out the ovr states of each of each of these files
1. figure out the source and destination CRS 
1. figure out the source and destination windows (each window should have both a "real space" rectangle and an output resolution & size)
1. figure out the source and destination formats & creation options
1. make a list of jobs to perform, with dependencies and (expected) output size
1. sort jobs by expected size then by dependency
1. perform the jobs in that order

all throughout this process we add options to both translate, warp, and common dicts, then finally the jobs call the relevant functions with the relevant arguments.

