#!/usr/bin/env python
import sys
import os
import subprocess

# copy shell script files to proper location
# args:
# source directory
# destination directory

def usage(args):
    print('usage: {} source_dir, destination_dir'.format(sys.argv[0]))


if len (sys.argv) != 3:
    usage(sys.argv)
    sys.exit(1)

src_dir = sys.argv[1]
dst_dir = sys.argv[2]
os.makedirs(dst_dir, mode=0o777, exist_ok=True)
all_files = os.listdir(src_dir)
for f in all_files:
    fin = os.path.join(src_dir, f)
    print(fin)
    if os.path.isfile(fin):
        cmd = 'file -i {} | grep shellscript'.format(fin)
        p = subprocess.Popen(cmd, shell=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
        if p.wait() == 0:
            fout = os.path.join(dst_dir, f)
            cmd = 'cp -p {} {}'.format(fin, fout)
            print("COPY", fin, fout)
            p = subprocess.Popen(cmd, shell=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)


