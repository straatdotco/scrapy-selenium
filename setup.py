"""This module contains the packaging routine for the pybook package"""

from setuptools import setup, find_packages

with open('requirements/requirements.txt') as f:
    requirements = f.read().splitlines()

setup(
    name='scrapy-selenium',
    version = '3.1.4',
    author='Lawrence Stewart',
    author_email='lawrence@classic.com',
    url = 'https://github.com/straatdotco/scrapy-selenium',
    licence = '...',
    description = 'Scrapy with selenium',
    packages=find_packages(exclude=['*tests*']),
    install_requires=requirements
)


