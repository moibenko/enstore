#!/usr/bin/env python

import os
import sys
import string
import socket

inv_dir = "/enstore/tape_inventory"

# this is a hack
cheat_dir = "/diska/tape-inventory"

host = string.split(socket.gethostname(), '.')[0]
if host[:3] == "rip":
	cluster = "rip"
elif host[:3] == "stk":
	cluster = "stken"
elif host[:3] == "d0e":
	cluster = "d0en"
else:
	cluster = "unknown"

special = ['TOTAL_BYTES_ON_TAPE', 'VOLUMES', 'VOLUMES_DEFINED', 'VOLUME_QUOTAS', 'VOLUME_SIZE', 'LAST_ACCESS']

catalog = {}

cmd = 'ls '+cheat_dir

for i in os.popen(cmd).readlines():
	f = os.path.basename(string.strip(i))
	# print f
	if not f in special:
		prefix = f[:3]
		if catalog.has_key(prefix):
			catalog[prefix].append(f)
		else:
			catalog[prefix] = [f]

# in the beginning ...

print "Content-type: text/html"
print

# taking care of the header

print '<html>'
print '<head>'
print '<title> Tape Inventory </title>'
print '</head>'
print '<body bgcolor="#ffffd0">'
print '<font size=7 color="#ff0000">Enstore Tape Inventory on '+cluster+'</font>'
print '<hr>'

# handle special files

print '<p>'
for i in special:
	print '|<a href="'+os.path.join(inv_dir, i)+'">', i, '</a>'
print '|'
print '<p><a href="'+inv_dir+'">Raw Directory Listing</a>'
print '<hr>'
print '<p>'
print '<h2><font color="#aa0000">Index</font></h2>'
print '<ul>'
keys = catalog.keys()
keys.sort()

for i in keys:
	print '<li><a href=#'+i+'>'+i+'</a>'
print '</ul>'

for i in keys:
	print '<hr>'
	print '<p>'
	print '<h2><a name="'+i+'"><font color="#aa0000">'+i+'</font></a></h2>'
	for j in catalog[i]:
		print '<a href="'+os.path.join(inv_dir, j)+'">', j, '</a>'

# the end
print '</body>'
print '</html>'
