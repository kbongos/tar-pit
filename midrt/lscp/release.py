# -*- coding:utf-8 -*-
#
# release.py - release information for the lscp package
#
"""LinuxSampler Control Protocol (LSCP) client library.

The LinuxSampler Control Protocol (LSCP_) is an application-level TCP network
protocol using ASCII messages primarily intended for local and remote control
of the LinuxSampler_ application.

This module defines the :class:`~lscp.LSCPClient` class, which provides an
abstraction of the details of the network communication and conversion of
passed data into or from Python data types. For every message defined by the
LSCP specification there is a matching method of :class:`~lscp.LSCPClient` for
sending this message and receiving and parsing the response.

The module aims to implement all messages defined by version 1.6 of the LSCP
specification, but in it's current alpha-state only supports a subset of the
messages for the request/response communication method and has no support for
the subscribe/notify communication method yet.

The module is implemented in pure Python, works with Python 2.7 and 3.3+ and
depends only on the standard library.


.. _linuxsampler: http://linuxsampler.org/
.. _lscp: http://www.linuxsampler.org/api/draft-linuxsampler-protocol.html

"""

name = 'lscp'
version = '0.1a1'
keywords = 'LSCP linuxsampler network audio'
author = 'Christopher Arndt'
author_email = 'chris@chrisarndt.de'
url = 'http://chrisarndt.de/projects/%s/' % name
repository = 'https://git.chrisarndt.de/%s.git' % name
download_url = url + 'download/'
license = 'MIT License'
platforms = 'POSIX, Windows, MacOS X'

classifiers = """\
Development Status :: 3 - Alpha
Environment :: Console
Environment :: MacOS X
Environment :: Win32 (MS Windows)
Intended Audience :: Developers
License :: OSI Approved :: MIT License
Operating System :: MacOS :: MacOS X
Operating System :: Microsoft :: Windows
Operating System :: POSIX
Programming Language :: Python
Programming Language :: Python :: 2.7
Programming Language :: Python :: 3
Programming Language :: Python :: 3.3
Programming Language :: Python :: 3.4
Topic :: Multimedia :: Sound/Audio
Topic :: Software Development :: Libraries :: Python Modules
"""

# parse classifiers string into list of strings
classifiers = [classifier.strip() for classifier in classifiers.splitlines()
    if classifier.strip() and not classifier.startswith('#')]

description = __doc__.splitlines()
long_description = "\n".join(description[2:]) % locals()
description = description[0]

try:
    # Python 2.x leaks loop variable from list comprehension
    del classifier
except:
    pass
