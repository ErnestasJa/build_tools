import os
from setuptools import setup

def read(fname):
    return open(os.path.join(os.path.dirname(__file__), fname)).read()

setup(
    name = "build_tools",
    version = "0.0.1",
    author = "Ernestas Januševičius",
    author_email = "ernestasjanusevicius@gmail.com",
    description = ("simple build toolkit for c++ cmake projects"),
    license = "MIT",
    keywords = "build cmake c++",
    url = "https://github.com/serengeor/build_tools",
    packages=['build_tools'],
    long_description=read('README.md'),
)
