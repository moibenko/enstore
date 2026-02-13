#!/usr/bin/env python

# meant to parse and plot output from emass vol-drive script used in mount
# tests

import os
import sys
import pprint
import time

# Wed Mar 8 13:23:49 CST 2000 mount CA2291 DC03  0 Wed Mar 8 13:26:41 CST 2000


def tod():
    return time.strftime("%c", time.localtime(time.time()))


mon = {"Jan": "01",
       "Feb": "02",
       "Mar": "03",
       "Apr": "04",
       "May": "05",
       "Jun": "06",
       "Jul": "07",
       "Aug": "08",
       "Sep": "09",
       "Oct": "10",
       "Nov": "11",
       "Dec": "12"}

mph = {}

f = open(sys.argv[1], "r")
while 1:
    line = f.readline()
    if not line:
        break
    if line.find(' mount ') == -1:
        continue
    l = line.splitfields()
    h = l[3].splitfields(":")

    # convert to strings and back to get correct number of digits in ts field
    # (08 instead of 8, for example)
    year = int(l[5])
    month = int(mon[l[1]])
    day = int(l[2])
    hour = int(h[0])
    anhour = "%4.4d-%2.2d-%2.2d:%2.2d:00:00" % (year, month, day, hour)

    mph[anhour] = mph.get(anhour, 0) + 1

pprint.pprint(mph)

keys = list(mph.keys())
keys.sort()

dname = "/tmp/" + sys.argv[1] + ".data"
data = open(dname, "w")
for k in keys:
    text = "%s %d\n" % (k, mph[k])
    data.write(text)
data.close()

psname = "/tmp/" + sys.argv[1] + ".ps"

cname = "/tmp/" + sys.argv[1] + ".control"
control = open(cname, "w")

control.write("set output '" + psname + ".ps'\n" +
              "set terminal postscript color\n" +
              "set title 'Mount Activity  generated" + tod() + "'\n" +
              "set xlabel 'Date'\n" +
              "set timefmt \"%Y-%m-%d:%H:%M:%S\"\n" +
              "set xdata time\n" +
              "set xrange [ : ]\n" +
              "set yrange [0: ]\n" +
              "set ylabel 'Mounts/Hour'\n" +
              "set grid\n" +
              "set format x \"%m-%d:%H\"\n" +
              "#set logscale y\n" +
              "plot '" + dname +
              "' using 1:2 t 'mounts' with impulses lw 20")
control.close()


os.system("gnuplot %s;" % (cname,))
os.system("gv %s;" % (psname,))
