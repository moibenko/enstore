#!/usr/bin/env python
"""
Find missed messages in log server out put file and fill enstore log.
"""
from __future__ import print_function
from builtins import object
import sys
import time
import socket
import os

import udp_common


class LogFixer(object):
    def __init__(self, input_file, output_dir):
        self.log_dict = {}
        self.input_file = open(input_file, 'r')
        self.output_dir = output_dir
        self.total_entries_processed = 0
        self.useful_entries_processed = 0

    def extract_log_message(self, message):
        rc = None
        # process log messages only
        # if "'work': 'log_message'" in str(message):
        #    print message
        try:
            rq, client_addr = udp_common.r_eval(message)
            # print "RQ", rq
            # print "CA", client_addr
            # idn, number, ticket = udp_common.r_eval(request, check=False)
        except Exception as detail:
            # print "DET", detail
            return None
        if rq:
            try:
                # print "RQQ", type(rq), rq
                req, inCRC = udp_common.r_eval(rq)
                # idn, number, ticket = udp_common.r_eval(rq, check=False)
            except Exception as detail:
                # print "RQ", detail
                return None
        if req:
            try:
                idn, number, ticket = udp_common.r_eval(req)
            except Exception as detail:
                # print "RQ1", detail
                return None
        # print "TICK", type(ticket), ticket
        if 'message' in ticket and 'work' in ticket and ticket['work'] == 'log_message':
            rc = idn, ticket, socket.gethostbyaddr(client_addr[0])[0]

        return rc

    def extract_time(self, id):
        # id nas the following format:
        #
        args = id.split("-")
        # print "ARGS", args
        return float(args[2])

    def udate_log_dict(self, msg):
        try:
            t = self.extract_time(msg[0])
        except Exception as detail:
            # print "DDDDDDDDDDDDD", detail
            return
        ts = time.localtime(t)
        if ts.tm_year not in self.log_dict:
            self.log_dict[ts.tm_year] = {}  # year
        if ts.tm_mon not in self.log_dict[ts.tm_year]:
            self.log_dict[ts.tm_year][ts.tm_mon] = {}
        if ts.tm_mday not in self.log_dict[ts.tm_year][ts.tm_mon]:
            self.log_dict[ts.tm_year][ts.tm_mon][ts.tm_mday] = []

        tod = time.strftime("%H:%M:%S", ts)
        self.log_dict[ts.tm_year][ts.tm_mon][ts.tm_mday].append(
            (tod, msg[1]['message'], msg[2]))

    def process_input_file(self):
        while 1:
            l = self.input_file.readline()
            if l:
                msg = self.extract_log_message(l)
                self.total_entries_processed += 1
                if msg:
                    # print "MMMMMMMMMM", msg
                    self.udate_log_dict(msg)
                    self.useful_entries_processed += 1
                    # break
            else:
                break

    def generate_output(self):
        if not os.path.exists(self.output_dir):
            try:
                os.makedirs(self.output_dir)
            except BaseException:
                print(
                    "Can not create outpit directory %s" %
                    (self.output_dir,))
                sys.exit(1)
        for year in self.log_dict:
            for month in self.log_dict[year]:
                for day in self.log_dict[year][month]:
                    fn = "LOG-%s-%s-%s" % (year, month, day)
                    output_path = os.path.join(self.output_dir, fn)
                    print("create", output_path)
                    of = open(output_path, 'w')
                    for entry in self.log_dict[year][month][day]:
                        of.write("%s %s %s\n" % (entry[0], entry[2], entry[1]))
                    of.close()


if __name__ == "__main__":
    infile = open(sys.argv[1], 'r')

    fixer = LogFixer(sys.argv[1], sys.argv[2])
    t = time.time()
    fixer.process_input_file()
    print("Total Entries %s. Useful entries %s. Processing time %s" % (fixer.total_entries_processed,
                                                                       fixer.useful_entries_processed,
                                                                       time.time() - t))
    fixer.generate_output()
