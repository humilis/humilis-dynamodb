"""Setuptools entry point."""

import os
import codecs
from setuptools import setup, find_packages

from humilis_dynamodb import __version__, __author__

dirname = os.path.dirname(__file__)
description = "Humilis plug-in to deploy a DynamoDB table"

try:
    import pypandoc
    long_description = pypandoc.convert("README.md", "rst")
except(IOError, ImportError, RuntimeError):
    if os.path.isfile("README.md"):
        long_description = codecs.open(os.path.join(dirname, "README.md"),
                                       encoding="utf-8").read()
    else:
        long_description = description

setup(
    name="humilis-dynamodb",
    include_package_data=True,
    package_data={
        "": ["*.j2", "*.yaml"]},
    packages=find_packages(include=["humilis_dynamodb",
                                    "humilis_dynamodb.*"]),
    version=__version__,
    author=__author__,
    author_email="german@findhotel.net",
    url="https://github.com/humilis/humilis-dynamodb",
    license="MIT",
    description=description,
    long_description=long_description,
    install_requires=[
        "humilis>=1.0.6"],
    classifiers=[
        "Programming Language :: Python :: 3"],
    zip_safe=False,
    entry_points={
        "humilis.layers": [
            "dynamodb=humilis_dynamodb.plugin:get_layer_path"]}
)
