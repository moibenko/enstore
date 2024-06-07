#!/usr/bin/env python

###############################################################################
#
# $Id$
#
###############################################################################

from __future__ import print_function
from builtins import range
from builtins import object
import time
import os
import threading

try:
    import multiprocessing
except ImportError:
    pass

try:
    io_lock = multiprocessing.Lock()
except NameError:
    io_lock = threading.Lock()

journal_size = 1000


class Journal(object):
    def __init__(self, journalfile, dict={}, mode=0, limit=journal_size):
        self.dict = dict
        if journalfile[-4:] == ".jou":
            self.journalfile = journalfile
        else:
            self.journalfile = journalfile + ".jou"
        if mode == 0:
            self.load()

        # This opens './file.jou' by default, and will fail
        # if `enstore start` is run in a directory where the
        # user doesn't have write access, causing the dispatcher
        # to retry for a while then die.
        self.jfile = open(self.journalfile, "a")

        self.count = 0
        self.limit = limit

    def load(self):
        io_lock.acquire()
        try:
            if os.access(self.journalfile, os.R_OK):
                f = open(self.journalfile, "r")
                l = f.readline()
                while l:
                    try:
                        exec(l)
                    except BaseException:
                        pass
                    l = f.readline()
                f.close()
        finally:
            io_lock.release()

    def keys(self):
        return list(self.dict.keys())

    def __len__(self):
        return self.dict.__len__()

    def has_key(self, key):
        return key in self.dict

    def __getitem__(self, key):
        return self.dict[key]

    def __setitem__(self, key, value):
        io_lock.acquire()
        try:
            self.dict[key] = value
            j = "self.dict['%s'] = %s\n" % (key, value)
            self.jfile.write(j)
            self.jfile.flush()
            self.count = self.count + 1
            if self.limit and self.count >= self.limit:
                self.__checkpoint()
        finally:
            io_lock.release()

    def __delitem__(self, key):
        io_lock.acquire()
        try:
            if key in self.dict:
                v = self.dict[key]
            else:
                v = {}
            j = "del self.dict['%s'] # %s\n" % (key, repr(v))
            self.jfile.write(j)
            self.jfile.flush()
            if key in self.dict:
                del self.dict[key]
            self.count = self.count + 1
            if self.limit and self.count >= self.limit:
                self.__checkpoint()
        finally:
            io_lock.release()

    def close(self):
        self.jfile.close()
        self.dict = {}

    def __del__(self):
        self.close()

    def list(self):
        for i in list(self.keys()):
            print("self.dict['%s'] = %s" % (i, repr(self.dict[i])))

    def __repr__(self):
        return repr(self.dict)

    def checkpoint(self):
        io_lock.acquire()
        try:
            self.__checkpoint()
        finally:
            io_lock.release()

    def __checkpoint(self):
        self.jfile.close()
        os.rename(self.journalfile, self.journalfile + '.' + repr(time.time()))
        self.jfile = open(self.journalfile, "w")
        self.dict = {}
        self.count = 0


if __name__ == "__main__":   # pragma: no cover
    jou = Journal('test.jou')
    for i in range(20000):
        jou[repr(i)] = {'count': i}
