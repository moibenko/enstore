#!/usr/bin/env python

from __future__ import print_function
from builtins import range
import time
import setpath
import checksum

s = 128 * 1024 * ' '
l = len(s)
crc = 0
t0 = time.time()
nbytes = 0
for count in range(10000):
    crc = checksum.adler32_o(crc, s, 0, l)
    nbytes = nbytes + l

now = time.time()
elapsed = now - t0

print("CRC=%s  checksummed %s bytes in %.02g seconds, rate = %.02g" % (crc, bytes, elapsed,
                                                                       bytes / elapsed))
