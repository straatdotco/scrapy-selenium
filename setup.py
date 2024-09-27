from setuptools import setup, find_packages

with open('requirements/requirements.txt') as f:
    requirements = f.read().splitlines()

setup(
    name='scrapy-selenium',
    version='1.2.1',
    author='James Uttaro',
    author_email='james@classic.com',
    url='https://github.com/straatdotco/scrapy-selenium',
    license='MIT',
    description='Scrapy with selenium',
    packages=find_packages(exclude=['*tests*']),
    install_requires=requirements
)


