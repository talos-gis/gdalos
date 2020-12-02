:: delete old dists
rmdir /s/q dist
rmdir /s/q build

:: creating the package
python setup.py bdist_wheel

:: uploading the dist via twine
python -m twine upload dist/*.whl
