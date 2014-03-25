from setuptools import setup, find_packages
import sys

setup(
    name = 'opendoar',
    version = '1.0.0',
    packages = find_packages(),
    install_requires = [
        "esprit",
        "werkzeug==0.8.3",
        "Flask==0.9",
        "Flask-Login==0.1.3",
        "Flask-WTF==0.8.3",
        "requests==1.1.0",
        "markdown",
        "gitpython",
        "lxml",
        "nose",
        "futures==2.1.6",
        # for deployment
        "gunicorn",
        "newrelic",
    ] + (["setproctitle"] if "linux" in sys.platform else []),

    url = 'http://opendoar.org/',
    author = 'Cottage Labs',
    author_email = 'us@cottagelabs.com',
    description = 'OpenDOAR discovery and admin interfaces',
    license = 'Copyheart',
    classifiers = [
        'Development Status :: 3 - Alpha',
        'Environment :: Console',
        'Intended Audience :: Developers',
        'License :: Copyheart',
        'Operating System :: OS Independent',
        'Programming Language :: Python',
        'Topic :: Software Development :: Libraries :: Python Modules'
    ],
)
