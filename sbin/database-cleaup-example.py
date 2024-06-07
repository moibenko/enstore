#!/usr/bin/env python

# example of how to clean databases of garbage

from __future__ import print_function
import db
import string

f = db.DbTable('file', '/diskb/enstore-database', '/diska/enstore-journal')

for bfid in f.keys():
    if f[bfid]['external_label'].find('sam') == 0:
        print(bfid, f[bfid]['external_label'])
        del f[bfid]


v = db.DbTable('volume', '/diskb/enstore-database', '/diska/enstore-journal')

for label in v.keys():
    if label.find('sam') == 0:
        print(label)
        del v[label]
