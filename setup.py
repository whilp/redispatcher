import sys

from setuptools import setup

meta = dict(
    name="redispatcher",
    version="0.1.0",
    description="asynchronous Redis client",
    author="Will Maier",
    author_email="willmaier@ml1.net",
    py_modules=["redispatcher"],
    test_suite="tests",
    install_requires=["setuptools"],
    keywords="redis asyncore asynchronous nosql",
    url="http://packages.python.org/redispatcher",
    classifiers=[
        "Development Status :: 3 - Alpha",
        "Intended Audience :: Developers",
        "License :: OSI Approved :: BSD License",
        "License :: OSI Approved :: MIT License",
        "Natural Language :: English",
        "Programming Language :: Python",
        "Topic :: Database",
    ],
    entry_points={
        "console_scripts": [
            "redispatcher = redispatcher:run",
        ]
    },
)

# Automatic conversion for Python 3 requires distribute.
if False and sys.version_info >= (3,):
    meta.update(dict(
        use_2to3=True,
    ))

setup(**meta)
