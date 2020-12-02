:: delete old dists
rmdir /s/q dist
rmdir /s/q build

:: creating the package
python setup.py sdist bdist_wheel

:: uploading the dist via twine
python -m twine upload dist/*.gz dist/*.whl
