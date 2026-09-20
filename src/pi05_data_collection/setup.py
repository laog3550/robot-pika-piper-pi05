#!/usr/bin/env python3

from distutils.core import setup

from catkin_pkg.python_setup import generate_distutils_setup


setup(**generate_distutils_setup(
    packages=["pi05_data_collection"],
    package_dir={"": "src"},
))
