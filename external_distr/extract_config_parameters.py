#!/usr/bin/env python

from __future__ import print_function
import os
import sys
import configuration_server

def flatten2(prefix, value, flat_dict):
    if isinstance(value, dict):
        for i in value.keys():
            flatten2(prefix + '.' + str(i), value[i], flat_dict)
    elif isinstance(value, (list, set)):
        for i in range(len(value)):
            flatten2(prefix + '.' + str(i), value[i], flat_dict)
    else:
        flat_dict[prefix] = value


def get_by_key(adict, key):
    for i in adict.keys():
        if key in adict[i]:
            print("%s.%s.%s"%(i, key, adict[i][key]))


def get_entry(adict, key):
    for i in adict[key].keys():
        flat_dict = {}
        flatten2(i, adict[key][i], flat_dict)
        for j in flat_dict.keys():
            print("%s:%s" %(j, flat_dict[j]))


def server_hosts(adict):
    o_d = []
    for i in adict.keys():
        if ("host" in adict[i]) and (not adict[i]["host"] in o_d):
            if ((i.find("library_manager") != -1) or
                (i.find("media_changer") != -1) or
                (i.find("clerk") != -1) or
                    (i.find("server") != -1)):
                o_d.append(adict[i]["host"])

    o_d.sort()
    for i in o_d:
        h = i.split(".")[0]
        print(h)


def int_part(s):
    ipart = 0
    for ch in s:
        if ch.isdigit():
            ipart = ipart * 10. + (ord(ch)-ord('0'))*1.
    return ipart


def _sort(list_to_sort):
    o_d = {}
    for i in list_to_sort:
        o_d[int_part(i)] = i
    keys = o_d.keys()
    keys.sort()
    o_l = []
    for key in keys:
        o_l.append(o_d[key])
    return o_l


def mover_hosts(adict):
    o_d = []
    for i in adict.keys():
        if ("host" in adict[i]) and (not adict[i]["host"] in o_d):
            try:
                if i.split(".")[1] == "mover":
                    o_d.append(adict[i]["host"])
            except IndexError:
                pass

    o_l = _sort(o_d)
    for i in o_l:
        h = i.split(".")[0]
        print(h)


if __name__ == '__main__':      # testing
       # get configuration file path from ENSTORE_CONFIG_FILE
    config_file = os.environ['ENSTORE_CONFIG_FILE']

    # need a ConfigurationDict to read configuration file
    cd = configuration_server.ConfigurationDict()
    cd.read_config(config_file)

    if sys.argv[1] == "server":
        server_hosts(cd.configdict)
    elif sys.argv[1] == "mover":
        mover_hosts(cd.configdict)
    else:
        get_entry(cd.configdict, sys.argv[1])
