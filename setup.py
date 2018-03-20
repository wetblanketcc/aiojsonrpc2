from setuptools import setup, find_packages
from os import path

import aiojsonrpc2

try:
    import pypandoc
    long_description = pypandoc.convert('README.md', 'rst')
except (IOError, ImportError):
    from codecs import open
    here = path.abspath(path.dirname(__file__))
    with open(path.join(here, 'README.md'), encoding='utf-8') as f:
        long_description = f.read()

setup(
    name='aiojsonrpc2',
    version=aiojsonrpc2.__version__,
    description='Python3 asyncio JSONRPC module',
    long_description=long_description,
    keywords='jsonrpc async asyncio aio json rpc',

    license='MIT',
    author='wetblanketcc',
    author_email='35851045+wetblanketcc@users.noreply.github.com',
    url='https://github.com/wetblanketcc/aiojsonrpc2',

    classifiers=[
        'Development Status :: 4 - Beta',
        'Environment :: Web Environment',
        'Framework :: AsyncIO',
        'Intended Audience :: Developers',
        'License :: OSI Approved :: MIT License',
        'Topic :: System :: Networking',
        'Programming Language :: Python :: 3',
        'Programming Language :: Python :: 3.5',
        'Programming Language :: Python :: 3.6',
    ],

    packages=find_packages(exclude=['tests']),

    python_requires='>=3.5',
)
