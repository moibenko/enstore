#! /usr/bin/env python
"""Script to copy given files into Python's path.
"""
from __future__ import print_function
from builtins import input
import sys
import os
import shutil
import getopt

__version__ = '$Id$'


def main():
    FORCE = 0
    try:
        opts, files = getopt.getopt(sys.argv[1:], 'f')
        if not files:
            raise getopt.error
    except getopt.error:
        print("Usage: %s [-f] pymodule [npymodule...]" % sys.argv[0])
        sys.exit(1)
    for opt in opts:
        if opt == '-f':
            FORCE = 1

    v = sys.version[:3]

    if float(v) >= 1.5:
        sp = "%s/lib/python%s/site-packages" % (sys.prefix, v)
        if not os.path.exists(sp):
            os.mkdir(sp)
    else:
        print("looks like Python is older than 1.5")
        sp = "%s/lib/python%s" % (sys.prefix, v)

    if not FORCE:
        ans = input("Install Python modules into %s? [y] " % sp)
        if ans in ('', 'y', 'Y', 'yes', 'Yes'):
            print('COPYING FILES:', end=' ')
            for file in files:
                shutil.copy2(file, sp)
                print(file, end=' ')
                sys.stdout.flush()
        print('TO', sp)
    else:
        print('COPYING FILES:', end=' ')
        for file in files:
            shutil.copy2(file, sp)
            print(file, end=' ')
            sys.stdout.flush()
        print('TO', sp)


if __name__ == '__main__':
    main()
