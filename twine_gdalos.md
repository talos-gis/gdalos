# installing twine
python -m pip install twine

# uploade to twine

## delete old dists
del dist\*.gz

## creating the package
python setup.py sdist bdist

## uploading the dist via twine
python -m twine upload dist/*.gz

## one liner:
del dist\*.gz & python setup.py sdist bdist && python -m twine upload dist/*.gz

# upgrade gdalos
python -m pip install --upgrade gdalos
