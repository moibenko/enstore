from __future__ import print_function
###############################################################################
# src/$RCSfile$   $Revision$
#
# system imports
from future import standard_library
standard_library.install_aliases()
from builtins import object
import os
import sys
import stat
import errno
import time
import traceback
import types

# enstore imports
import Trace
import checksum
import e_errors

"""
tape format:
VOL record (80 chars)
HDR1 record (80 chars)
HDR2 record (80 chars)
HDR3 record (80 chars)
HDR4 record (80 chars)
tapedata1
EOF1 record (80 chars)
EOF2 record (80 chars)
EOF3 record (80 chars)
EOF4 record (80 chars)
HDR1 record (80 chars)
HDR2 record (80 chars)
HDR3 record (80 chars)
HDR4 record (80 chars)
tapedata2
EOF1 record (80 chars)
EOF2 record (80 chars)
EOF3 record (80 chars)
EOF4 record (80 chars)
...etc...

tapedata commonly is of zero length

"""


class Wrapper(object):

    recordLength = 80

    def sw_mount(self, driver, info):
        return

    def read_pre_data(self, driver, info):
        header = driver.read(self.recordLength)
        if header[0:3] == "VOL":
            header = driver.read(self.recordLength)
        header = driver.read(self.recordLength)
        header = driver.read(self.recordLength)
        header = driver.read(self.recordLength)
        return

    def read_post_data(self, driver, info):
        self.tail1 = driver.read(self.recordLength)
        self.tail2 = driver.read(self.recordLength)
        self.tail3 = driver.read(self.recordLength)
        self.tail4 = driver.read(self.recordLength)
        return


###############################################################################

# shamelessly stolen from python's posixfile.py
class DiskDriver(object):
    states = ['open', 'closed']

    # Internal routine
    def __del__(self):
        self._file_.close()

    # Initialization routines
    def open(self, name, mode='r', bufsize=-1):
        import builtins
        return self.fileopen(builtins.open(name, mode, bufsize))

    # Initialization routines
    def fileopen(self, afile):
        if not isinstance(afile, file):
            raise TypeError('DiskDriver.fileopen() arg must be file object')
        self._file_ = afile
        # Copy basic file methods
        for method in afile.__methods__:
            setattr(self, method, getattr(afile, method))
        return self

    #
    # New methods
    #

    # this is the name of the function that the wrapper uses to read
    def read(self, size):
        return self._file_.read(size)

    # this is the name fo the funciton that the wrapper uses to write
    def write(self, buffer):
        return self._file_.write(buffer)


if __name__ == "__main__":   # pragma: no cover
    import getopt
    import Devcodes
    import FTT                          # needed for FTT.error
    import driver

    options = ["extract"]
    optlist, args = getopt.getopt(sys.argv[1:], '', options)
    (opt, val) = optlist[0]
    if not optlist:
        print(
            "usage: run1" +
            " <" +
            repr(options) +
            "> infile outfile infilenumber")
        sys.exit(1)

    if not (opt == "--extract"):
        print(
            "usage: run1" +
            " <" +
            repr(options) +
            "> infile outfile infilenumber")
        sys.exit(1)

    fin = driver.FTTDriver(0x400000)
    fin.open(args[0], "r")
    print("FIN", fin)
    fout = open(args[1], "w")

    wrapper = Wrapper()

    if opt == "--extract":
        wrapper.read_pre_data(fin, None)
        print("VOL", wrapper.vol)
        print("H1", wrapper.header1)
        print("H2", wrapper.header2)
        print("H3", wrapper.header3)
        print("H4", wrapper.header4)
    fin.close()
    fout.close()
