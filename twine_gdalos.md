# installing twine
python -m pip install twine wheel

# uploade to twine

## delete old dists
rm dist/*.*
del dist\*.*

## creating the package
python setup.py sdist bdist_wheel

## uploading the dist via twine
python -m twine upload dist/*.gz dist/*.whl

## one liner to the test pypi
rm dist/*.* ; python setup.py sdist bdist_wheel && python -m twine upload dist/*.gz dist/*.whl ; rm dist/*.*
or (test)
rm dist/*.* ; python setup.py sdist bdist_wheel && python -m twine upload --repository-url https://test.pypi.org/legacy/ dist/*.gz dist/*.whl ; rm dist/*.*

# upgrade gdalos
python -m pip install --upgrade gdalos
or (test)
python -m pip install --index-url https://test.pypi.org/simple/ --upgrade gdalos