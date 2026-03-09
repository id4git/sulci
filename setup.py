"""
setup.py — legacy compatibility shim.

Modern Python packaging uses pyproject.toml.
This file exists only for tools that require setup.py to be present.
All configuration lives in pyproject.toml.
"""
from setuptools import setup

if __name__ == "__main__":
    setup()
