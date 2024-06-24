#!/usr/bin/env python
import sys
import os
import subprocess

# move files to proper location
# args:
# parent source directory
# parent distribution directory
# destination directory

def usage(args):
    print('usage: {} source_dir, distribution_dir, destination_dir'.format(sys.argv[0]))

if len (sys.argv) != 4:
    usage(sys.argv)
    sys.exit(1)

dst_dir = os.path.join(sys.argv[2], sys.argv[3])
src_distr = os.path.join(sys.argv[2], 'sbin')
src_dir = os.path.join(sys.argv[1], sys.argv[3]) 
os.makedirs(dst_dir, mode=0o777, exist_ok=True)
print(src_dir)
cmd = 'ls -1dp {}/*.py'.format(src_dir, src_dir)
p = subprocess.Popen(cmd, shell=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
f_list = []
for line in p.stdout.readlines():
    f_list.append(line.decode().strip().split('/')[-1].split('.')[0])
print(f_list)
for f in f_list:
    src = os.path.join(src_distr, f)
    dst = os.path.join(dst_dir, f)
    print('moving', src, dst)
    os.rename(src, dst)
