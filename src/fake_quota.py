#!/usr/bin/env python

# this is a fake substitution when pg module is not available
# it does nothing but print the error/warning message

from __future__ import print_function


from builtins import object
def warning():
    print("quota is not available on this node")


class Quota(object):
    def __init__(self):
        warning()


class Interface(object):
    def __init__(self, args, user_mode):
        warning()


def do_work(intf):
    warning()
