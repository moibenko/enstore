from __future__ import print_function
######################################################################
# src/$RCSfile$   $Revision$

from builtins import str
import os
import sys
import getpass
import posixpath
import re
import glob

TMP_DIR = "/tmp/enstore"
TIMEOUT = 3
RETRIES = 2


def set_trace_key():
    # get who we are
    us = getpass.getuser()
    us_dir = "%s/%s" % (TMP_DIR, us)
    # check if the directory /tmp/enstore/us exists.  if not create it.
    if not posixpath.exists(TMP_DIR):
        # the path did not exist, create it
        os.mkdir(TMP_DIR)
        os.mkdir(us_dir)
    else:
        if not posixpath.exists(us_dir):
            os.mkdir(us_dir)
    # set an environment variable that will tell trace where to put the key
    os.environ["TRACE_KEY"] = "%s/%s" % (us_dir, "trace.cgi")


def find_gnuplot():
    gnuplot_info = os.popen(
        ". /usr/local/etc/setups.sh;ups list -K @PROD_DIR gnuplot").readlines()
    gnuplot_dir = gnuplot_info[0].strip()
    gnuplot_dir = gnuplot_dir.replace("\"", "")
    return gnuplot_dir


def find_enstore():
    enstore_info = os.popen(
        ". /usr/local/etc/setups.sh;setup enstore;ups list -K @PROD_DIR enstore;echo $ENSTORE_CONFIG_PORT;echo $ENSTORE_CONFIG_HOST;echo $PATH").readlines()
#    enstore_info = os.popen(". /usr/local/etc/setups.sh;setup enstore -q efb efb;ups list -K @PROD_DIR enstore -q efb efb;echo $ENSTORE_CONFIG_PORT;echo $ENSTORE_CONFIG_HOST;echo $SETUP_HTMLGEN;echo $SETUP_LIBTPPY").readlines()
    enstore_dir = enstore_info[0].strip()
    enstore_dir = enstore_dir.replace("\"", "")
    enstore_src = "%s/src" % (enstore_dir,)
    enstore_modules = "%s/modules" % (enstore_dir,)
    htmlgen_dir = "%s/HTMLgen" % (enstore_dir,)
    libtppy_dir = "%s/BerkeleyDB" % (enstore_dir,)
    sys.path.append(enstore_src)
    sys.path.append(enstore_modules)
    sys.path.append(htmlgen_dir)
    sys.path.append(libtppy_dir)

    # set command path
    os.environ['PATH'] = enstore_info[3]
    # set PYTHONPATH
    os.environ['PYTHONPATH'] = ':'.join(sys.path)

    # fix up the config host and port to give to the command
    config_host = enstore_info[2].strip()
    config_port = enstore_info[1].strip()

    # we must create a pointer in the environment ot the trace key we are
    # going to use.   first see if the directory exists and if not create it.
    set_trace_key()

    return (config_host, config_port)


def set_pattern_search(pat, sensit):
    if sensit:
        # case sensitive pattern matching.
        patr = re.compile(pat)
    else:
        # case insensitive pattern matching
        patr = re.compile(pat, re.IGNORECASE)
    return patr


def pgrep_html(pat, files, sensit):
    patr = set_pattern_search(pat, sensit)
    for filen in files:
        filename = filen.split("/")[-1]
        print("<H3>%s</H3><BR>" % (filen,))
        lineno = 1
        # until the situation with zlib and python are resolved we must only
        # support flat files
        fd = open(filen, 'r')
        # support both log files that are flat and those that are gzipped
        # import gzip
        # if string.find(filename, ".gz") == -1:
        # not a gzipped file
        # fd = open(file, 'r')
        # else:
        # fd = gzip.open(file, 'r')
        line = fd.readline()
        while line:
            if patr.search(line) >= 0:
                # only print out the name of the file and not the directory
                # path
                print('[<B>%s</B>] %04d) %s<BR>' % (filename, lineno, line))
            lineno = lineno + 1
            line = fd.readline()
        else:
            fd.close()
        print("<HR>")


def agrep_html(pat1, pat2, files, sensit):
    patr1 = set_pattern_search(pat1, sensit)
    if pat2:
        patr2 = set_pattern_search(pat2, sensit)
    else:
        patr2 = None
    import enstore_html
    import alarm
    matched_alarms = {}
    i = 0
    for filen in files:
        date = filen.split("/")[-1][4:]
        for line in open(filen, 'r').readlines():
            if patr1.search(line) >= 0:
                if patr2:
                    rtn = patr2.search(line)
                else:
                    rtn = 1
                if rtn >= 0:
                    # we have an alarm line that matches both search strings, turn it
                    # into an alarm
                    anAlarm = alarm.LogFileAlarm(line, date)
                    # we cannot use the alarm id as a unique key because the id is from the log
                    # file and is only good to the second.  so it may not be unique, > 1 alarm
                    # may have been recorded within a second.
                    matched_alarms[i] = anAlarm
                    i = i + 1

    # we do not want any background
    doc = enstore_html.EnAlarmSearchPage("")
    doc.body(matched_alarms)
    print(str(doc))
