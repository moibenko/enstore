#
# system import
import sys
import time
import string
import os
import stat
import string

# enstore imports
import Trace
import alarm
import e_errors

# used to force timestamping
FORCE = 1

# ENCP line pieces from log file
ETIME = 0
ENODE = 1
EUSER = 2
ESTATUS = 3
EXRATE = 4
EBYTES = 5
EDEV = 6
EURATE = 7
EDICTS = 8

# different MOUNT line pieces from log file
MDEV = 4
MSTART = 5
MDICTS = 6

# message is either a mount request or an actual mount
MREQUEST = 0
MMOUNT = 1

TRUE = 1
FALSE = 0
START_TIME = "start_time"
STOP_TIME = "stop_time"
LOG_PREFIX = "LOG-"
BG_COLOR = "FFFFFF"
tdata = "<TD NOSAVE>"
trow = "<TR NOSAVE>\n"
tdata_end = "</TD>\n"
TMP = ".tmp"

default_dir = "./"

def ascii_file_name():
    return "enstore_system.txt"

def inq_file_name():
    return "enstore_system.html"

def default_ascii_file():
    return default_dir+ascii_file_name()

def default_inq_file():
    return default_dir+inq_file_name()

def encp_html_file_name():
    return "encp_"+inq_file_name()

def default_encp_html_file():
    return default_dir+encp_html_file_name()

def config_html_file_name():
    return "config_"+inq_file_name()

def default_config_html_file():
    return default_dir+config_html_file_name()

def status_html_file_name():
    return "status_"+inq_file_name()

def default_status_html_file():
    return default_dir+status_html_file_name()

# translate time.time output to a person readable format.
# strip off the day and reorganize things a little
def format_time(theTime, sep=" "):
    return time.strftime("%Y-%b-%d"+sep+"%H:%M:%S", time.localtime(theTime))

# format the timestamp value
def get_ts():
    return format_time(time.time(), "_")

# strip off anything before the '/'
def strip_file_dir(str):
    ind = string.rfind(str, "/")
    if not ind == -1:
	str = str[(ind+1):]

# locate and pull out the dictionaries in the text message. assume that if
# there is more than one dict, they are of the form -
#
#                 dict1 , dict2 , dict3 ...
#
# with only a comma and whitespace between them
def get_dict(text):
    dicts = []
    start = string.find(text, "{")
    if not start == -1:
        end = string.rfind(text, "}")
        if not end == -1:
            # we have a start and an end curly brace, assume that all inbetween
            # are part of the dictionaries
            try:
                dicts = eval(text[start:end+1])
                if len(dicts) == 1:
                    # dicts is a dictionary, we want to return a list
                    dicts = [dicts,]
            except SyntaxError:
                # the text was not in the right format so ignore it
                pass
    return dicts

# parse the encp line
def parse_encp_line(line):
    [etime, enode, etmp, euser, estatus, etmp2, etype, erest] = \
                                                   string.split(line, None, 7)
    if 0: print etmp2,etype # quiet lint

    try:
        [erest2, erest3] = string.splitfields(erest, ":", 1)
        # erest2 has the file name info which we do not need, get the 
        # total data transfer rate from the end of erest3
        [erest2, tt] = string.splitfields(erest3, "(", 1)
        [tt, etmp] = string.splitfields(tt, ")",1)
        # pull out the name of the media changer
        mc = get_dict(etmp)
        [tt, etmp] = string.splitfields(tt, " ",1)
        erate = string.splitfields(erest2, " ")
    except ValueError:
        # we do not handle this formatting
        return []
    return [etime, enode, euser, estatus, tt, erate[1], erate[5], erate[7], mc]

# given a list of media changers and a log file message, see if any of the
# media changers are mentioned in the log file message
def mc_in_list(msg, mcs):
    for msgDict in msg:
        for mc in mcs:
            if mc == msgDict.get("media_changer", ""):
                return 1
    else:
        return 0

class EnStatus:

    # output the blocksize info
    def output_blocksizes(self, info, prefix, key):
	prefix2 = "                  "
	str = prefix
	ctr = 0
	for a_key in info.keys():
	    if a_key != 'status':
	        if ctr == 3:
	            str = str+",\n"+prefix2
	            ctr = 0
	        elif ctr > 0:
	            str = str+",  "
	        ctr = ctr+1
	        str = str+a_key+" : "+repr(info[a_key])
	self.text[key] = str+"\n"

    # output the passed alive status
    def output_alive(self, host, tag, status, time, key):
	ftime = format_time(time)
	str = self.unquote(tag)+self.unquote(status['work'])+" on "+\
	      self.format_ip_address(host, status['address'])+" at "+\
	      ftime+"\n"
	self.text[key] = str

    # output the timeout error
    def output_etimedout(self, address, tag, time, key, last_time=0):
	ftime = format_time(time)
	str = tag + "timed out on "+self.unquote(repr(address))+" at "+\
	       ftime+"\n"
	if last_time:
	    i = len(tag)
	    if not last_time == -1:
	        ltime = format_time(last_time)
	    else:
		ltime = "----"
	    str = str+i*" "+"last alive at "+ltime+"\n"
	self.text[key] = str

    # output timeout error when trying to get config dict from config server
    def output_noconfigdict(self, tag, time, key):
	ftime = format_time(time)
	str = tag + "timed out while getting config dict at "+ftime+"\n"
	self.text[key] = str

    # output a line stating that we do not support this server
    def output_nofunc(self, key):
	str = key+" : NOT SUPPORTED IN INQUISITOR\n"
	self.text[key] = str

    # output the library manager suspect volume list
    def output_suspect_vols(self, ticket, key):
	sm = self.format_lm_suspect_vols(ticket)
	Trace.trace(12, repr(sm))
	self.text[key] = self.text[key]+sm

    # output the library manager queues
    def output_lmqueues(self, ticket, key):
	fq = self.format_lm_queues(ticket)
        Trace.trace(12, repr(fq))
	self.text[key] = self.text[key]+fq

    # output the library manager queues
    def output_moverstatus(self, ticket, key):
	fs = self.format_moverstatus(ticket)
	Trace.trace(12, repr(fs))
	self.text[key] = self.text[key]+fs

    # output the library manager mover list
    def output_lmmoverlist(self, ticket, key):
	fq = self.format_lm_moverlist(ticket)
	Trace.trace(12, repr(fq))
	self.text[key] = self.text[key]+fq

    # remove all single quotes
    def unquote(self, s):
        if 0: print self # quiet lint
	return string.replace(s,"'","")

    # format the status, just use the first element
    def format_status(self, status):
	return self.unquote(status[0])

    # format the ip address - replace the ip address with the actual host name
    def format_ip_address(self, host, address):
	return "("+self.unquote(host)+", "+repr(address[1])+")"

    # parse the library manager queues returned from "getwork"
    def parse_lm_queues(self, work, spacing, prefix):
	string = prefix
	first_line_spacing = ""
	for mover in work:
	    callback_addr = mover['callback_addr']
	    encp = mover['encp']
	    # not found in pending work
	    try:
	        fc = mover['fc']
	    except:
	        pass
	    times = mover['times']
	    vc = mover['vc']
	    wrapper = mover['wrapper']
	    machine = wrapper['machine']

	    string = string+first_line_spacing

	    # not found in pending work
	    try:
	        string = string+mover['mover']+", "
	    except:
	        pass
	    string = string+"from NODE: "+self.unquote(machine[1])+" ("+\
	             self.unquote(machine[0])+"),  PORT: "+\
	             repr(callback_addr[1])
	    if mover['work'] == 'write_to_hsm':
	        string = string+spacing+"WRITE to: "
	    else:
		string = string+spacing+"READ to: "
	    string = string+wrapper['fullname']+",  BYTES: "+\
	             repr(wrapper['size_bytes'])
	    # not found in pending work
	    try:
	        string = string+spacing+"DEVICE LABEL: "+fc['external_label']+\
	             ",  "
	    except:
	        string = string+spacing
	    string = string+"FILE FAMILY: "+vc['file_family']
	    # not found in reads
	    try:
	        string = string+",  FILE FAMILY WIDTH: "+\
	                 repr(vc['file_family_width'])
	    except:
	        pass
	    string = string+spacing+"PRIORITIES:  CURRENT "+\
	             repr(encp['curpri'])+",  BASE "+repr(encp['basepri'])+\
	             ",  DELTA "+repr(encp['delpri'])+"  and  AGETIME: "+\
	             repr(encp['agetime'])
	    string = string+spacing+"JOB SUBMITTED: "+\
	             format_time(times['t0'])
	    # not found in pending work
	    try:
	        string = string+",  DEQUEUED: "+\
	                 format_time(times['lm_dequeued'])
	    except:
	        pass
	    # not found in reads
	    try:
	        string = string+spacing+"FILE MODIFIED: "+\
	                 format_time(wrapper['mtime'])
	    except:
	        pass
	    string = string+"\n"

	    # reset this to prepare for another queued element
	    first_line_spacing = spacing
	return string+"\n"

    # format the library manager work queues for output
    def format_lm_queues(self, ticket):
	string = "    Work for: "
	spacing = "\n          "
	work = ticket['at movers']
	if len(work) != 0:
	    string = self.parse_lm_queues(work, spacing, string)
	else:
	    string = "    No work at movers\n"
	pending_work = ticket['pending_work']
	if len(pending_work) != 0:
	    string = string+"\n    Pending work: "
	    string = self.parse_lm_queues(pending_work, spacing, string)
	else:
	    string = string+"    No pending work\n\n"
	return string

    def format_lm_suspect_vols(self, ticket):
        if 0: print self # quiet lint
	str =     "\n    SUSPECT VOLUMES : "
	spacing = "\n                      "
	sus_vols = ticket['suspect_volumes']
	if len(sus_vols) != 0:
	    for svol in sus_vols:
	        str = str+svol['external_label']+" - "
	        movers = svol['movers']
	        if len(movers) != 0:
	            not_first_one = 0
	            for mover in movers:
	                if not_first_one:
	                    str=str+", "
	                str = str+mover
	                not_first_one = 1
	        str = str+spacing
	else:
	    str = str + "NONE"
	return str+"\n\n"

    # parse the library manager moverlist ticket
    def parse_lm_moverlist(self, work):
        if 0: print self # quiet lint
	string = "    KNOWN MOVER           PORT    STATE         LAST SUMMONED        TRY COUNT\n"
	for mover in work:
	    (address, port) = mover['address']
	    time = format_time(mover['last_checked'])
	    string = string+"    %(m)-18.18s    %(p)-4.4d    %(s)-10.10s    %(lc)-20.20s    %(tc)-3d\n" % {'m':mover['mover'], 'p':port, 's':mover['state'], 'lc':time, 'tc':mover['summon_try_cnt']}

	string = string+"\n"
        if 0: print address # quiet lint
	return string

    # format the library manager mover list for output
    def format_lm_moverlist(self, ticket):
	string = "    Known Movers: "
	work = ticket['moverlist']
	if len(work) != 0:
	    string = self.parse_lm_moverlist(work)
	else:
	    string = "    No moverlist\n"
	return string

    mfile = ""
    
    # format the mover status information
    def format_moverstatus(self, ticket):
        if 0: print self     # lint fix
	spacing = "\n    "
	aString = spacing+"Completed Transfers : "+repr(ticket["no_xfers"])
	if ticket["state"] == "busy":
	    p = "Current Transfer : "
	    if ticket["mode"] == "r":
	        m = " reading "+repr(ticket["bytes_to_xfer"])+\
                    " bytes from Enstore"
                f_in = 1
                f_out = 0
                got_vol = 1
	    elif ticket["mode"] == "w":
	        m = " writing "+repr(ticket["bytes_to_xfer"])+\
                    " bytes to Enstore"
                f_in = 0
                f_out = 1
                got_vol = 1
            elif ticket["mode"] == "u":
                got_vol = 0
                m = " dismounting volume %s"%ticket['tape']
            else:
                got_vol = 0
                m = " "
	elif ticket["state"] == "idle":
	    p = "Last Transfer : "
	    m = " "
            if ticket['no_xfers'] > 0:
                got_vol = 1
                work = ticket['work_ticket'].get('work', "")
                if string.find(work, "read") != -1:
                    f_in = 1
                    f_out = 0
                elif string.find(work, "write") != -1:
                    f_in = 0
                    f_out = 1
                else:
                    # we don't know what the last transfer was
                    got_vol = 0
            else:
                got_vol = 0
        else:
            got_vol = 0
            m = ""
            p = "Unknown State : "

        if got_vol:
            v = ",  Volume : "+ticket['tape']
            mfile = spacing+" "*(len(p)+1)+ticket['files'][f_in]+" --> "+\
                    ticket['files'][f_out]
        else:
            v = ""
            mfile = ""

	aString = aString+",  Current State : "+ticket["state"]+m
        if p:
            aString = aString+spacing+p+" Read "+\
                      repr(ticket["rd_bytes"])+" bytes,  Wrote "+\
                      repr(ticket["wr_bytes"])+" bytes"+v
        return aString+mfile+"\n\n"

class EnFile:

    def __init__(self, file):
        self.file_name = file 
	self.filedes = 0

    def open(self, mode='w'):
	try:
            self.filedes = open(self.file_name, mode)
            Trace.trace(10,"%s open "%self.file_name)
        except IOError:
            self.filedes = 0
            Trace.log(e_errors.WARNING,
                      "%s not openable for %s"%(self.file_name, mode))

    def close(self):
	Trace.trace(10,"enfile close "+self.file_name)
	if self.filedes:
	    self.filedes.close()
	    self.filedes = 0

    # remove the file
    def cleanup(self, keep, pts_dir):
        if not keep:
            # delete the data file
            os.system("rm %s"%self.file_name)
        else:
            if pts_dir:
                # move these files somewhere
                os.system("mv %s %s"%(self.file_name, pts_dir))

class EnStatusFile(EnFile):

    def __init__(self, file):
     	EnFile.__init__(self, file)
	self.text = {}

    # open the file
    def open(self):
        Trace.trace(12,"open "+self.file_name)
        # try to open status file for append
        EnFile.open(self, 'a')
        if not self.filedes:
            # could not open for append, try to create it
            EnFile.open(self, 'w')

    # flush everything to the file
    def flush(self):
	# well, nothing has really been written to the file, it is all stored
	# in a hash.  so we must write it all now
        if self.filedes:
            self.write_title()
            keys = self.text.keys()
            keys.sort()
            for key in keys:
                self.filedes.write(self.text[key])

            self.filedes.flush()

    # write out any title information
    def write_title(self):
        self.filedes.write("\nENSTORE SYSTEM STATUS\n")

    # remove something from the text hash that will be written to the files
    def remove_key(self, key):
	if self.text.has_key(key):
	    del self.text[key]

class EnHTMLFile:

    def __init__(self, refresh):
	if refresh == -1:
	    self.refresh = 120
	else:
	    self.refresh = refresh
	self.set_header()

    # close the file
    def close(self):
        Trace.trace(12,"close %s"%self.file_name)
        if self.filedes:
            self.filedes.write(self.trailer)
            self.filedes.close()
	    self.filedes = 0

    # include a link to the main inquisitor page and a sideways page of the
    # users choice
    def page_top_buttons(self):
        if 0: print self     # lint fix
        str = '<A HREF="'+inq_file_name()+\
              '">Go Back</A>&nbsp&nbsp&nbsp<A HREF="'
        str = str+self.add_2nd_button()
        str = str+' Status Page</A><BR><BR><HR><BR><BR>'
        return str
    
    # reset the header, the refresh has changed
    def set_header(self):
	self.header = self.html_header1+repr(self.refresh)+self.html_header2

    # reset the refresh
    def set_refresh(self, value):
	self.refresh = value
	self.set_header()

    # return the current refresh value
    def get_refresh(self):
	return self.refresh

class EncpFile:

    # output the encp info
    def output_encp(self, lines, key):
	if lines != []:
            str = self.format_encp(lines, key)
	else:
	    str = self.format_no_encp()
	self.text[key] = str+"\n"

    # format the line saying there have been no encp requests
    def format_no_encp(self):
        if 0: print self # quiet lint
	return "\nencp            : NONE\n"

class HTMLStatusFile(EnHTMLFile, EnStatusFile, EnStatus):

    html_header1 = "<title>Enstore Status</title>\n"+\
                   "<meta http-equiv=\"Refresh\" content=\""
    html_header2 = "\">\n"+\
                   "<body bgcolor=\""+BG_COLOR+"\">\n"
    html_header3 = "<pre>\n"

    def __init__(self, file, refresh):
	EnStatusFile.__init__(self, file)
	EnHTMLFile.__init__(self, refresh)
	self.header2 = self.html_header3
	self.trailer = "</pre></body>\n"

    # open the file and write the header to the file
    def open(self):
        Trace.trace(12,"open "+self.header)
	EnStatusFile.open(self)
        if self.filedes:
            self.filedes.write(self.header)
            self.filedes.write(self.header2)
            self.filedes.write(self.page_top_buttons())

    def add_2nd_button(self):
        return encp_html_file_name()+'">ENCP'

class AsciiStatusFile(EncpFile, EnStatusFile, EnStatus):

    def __init__(self, file, max_ascii_size):
	self.max_ascii_size = max_ascii_size
	EnStatusFile.__init__(self, file)

    # format the encp info taken from the log file
    def format_encp(self, lines, key):
        if 0: print self # quiet lint
	prefix =  "\n                     "
	str = key+"            : "
	spacing = ""
	# break up each line into it's component parts, format it and save it
	for line in lines:
	    einfo = parse_encp_line(line)
            if not len(einfo):
                # nothing was returned skip this line and go to the next
                continue
	    str = str+spacing+einfo[ETIME]+" on "+einfo[ENODE]+" by "+\
	          einfo[EUSER]
	    spacing = "                  "
	    if einfo[ESTATUS] == e_errors.sevdict[e_errors.INFO]:
	        str = str+" (Data Transfer Rate : "+einfo[EXRATE]+" MB/S)"
	        # what's left in erest2 is what we want, but make it clearer
	        # that the rate in this line is the user rate
	        str = str+prefix+einfo[EBYTES]+" bytes copied to "+\
	              einfo[EDEV]+" at a user rate of "+einfo[EURATE]+" MB/S\n"
	    else:
	        # there was an error or warning
	        if len(einfo) == 7:
	            str = str+prefix+einfo[4]+" : "+einfo[5]+prefix+einfo[6]
	        else:
	            # the leftover text was formatted funny, just output it
	            str = str+prefix+einfo[4]
	return str

    # move the file to a timestamped backup copy
    def timestamp(self, really=0):
	Trace.trace(11,"timestamp "+self.file_name)
	s = os.stat(self.file_name)
	if (self.max_ascii_size > 0) or (really == FORCE):
	    if (s[stat.ST_SIZE] >= self.max_ascii_size) or (really == 1):
	        self.close()
	        os.system("mv "+self.file_name+" "+self.file_name+"."+\
	                  get_ts())
	        self.open()

    # set a new max_ascii_size value
    def set_max_ascii_size(self, value):
	self.max_ascii_size = value

    # get the max_ascii_size value
    def get_max_ascii_size(self):
	return self.max_ascii_size

class EncpStatusFile(EncpFile, EnHTMLFile, EnStatusFile):

    html_header1 = "<title>Encp History</title>\n"+\
                   "<meta http-equiv=\"Refresh\" content=\""
    html_header2 = "\">\n"+\
                   "<body bgcolor=\""+BG_COLOR+"\">\n"

    def __init__(self, file, refresh):
        EnStatusFile.__init__(self, file)
	EnHTMLFile.__init__(self, refresh)
	self.trailer = "</body>\n"

    # open the file and write the header to the file
    def open(self):
        Trace.trace(12,"open "+self.header)
	EnStatusFile.open(self)
        if self.filedes:
            self.filedes.write(self.header)
            self.filedes.write(self.page_top_buttons())

    # write out any title information
    def write_title(self):
        # we don't want a title written out.  the encp information will be
        # enough
        pass

    # format the line saying there have been no encp requests
    def format_no_encp(self):
	return "<pre>\n\n"+EncpFile.format_no_encp(self)+"</pre>"

    # format the encp info taken from the log file
    def format_encp(self, lines, key):
        if 0: print self,key # quiet lint
	str = "<P>\n<CENTER><TABLE BORDER COLS=7 WIDTH=\"100%\" NOSAVE>\n"+ \
	      "<TH COLSPAN=7 VALIGN=CENTER>History of ENCP Commands</TH>\n"+ \
	      "<TR VALIGN=CENTER NOSAVE>\n<TD NOSAVE><B>TIME</B></TD>\n"+ \
	      "<TD NOSAVE><B>NODE</B></TD>\n<TD NOSAVE><B>USER</B></TD>\n"+ \
	      "<TD NOSAVE><B>BYTES</B></TD>\n<TD NOSAVE><B>VOLUME</B></TD>\n"+\
	      "<TD NOSAVE><B>DATA TRANSFER RATE (MB/S)</B></TD>\n"+ \
	      "<TD NOSAVE><B>USER RATE (MB/S)</B></TD>\n</TR>\n"
	str2 = "<P><PRE>\n"
	# break up each line into it's component parts, format it and save it
	for line in lines:
	    einfo = parse_encp_line(line)
            if not len(einfo):
                # nothing was returned skip this line and go to the next
                continue
	    if einfo[ESTATUS] == e_errors.sevdict[e_errors.INFO]:
	        str = str+trow+tdata+einfo[ETIME]+tdata_end+ \
	                       tdata+einfo[ENODE]+tdata_end+ \
	                       tdata+einfo[EUSER]+tdata_end+ \
	                       tdata+einfo[EBYTES]+tdata_end+ \
	                       tdata+einfo[EDEV]+tdata_end+ \
	                       tdata+einfo[EXRATE]+tdata_end+ \
	                       tdata+einfo[EURATE]+tdata_end+"</TR>\n"
	    else:
	        str2 = str2+einfo[ETIME]+" on "+einfo[ENODE]+" by "+einfo[EUSER]
 	        # there was an error or warning
	        if len(einfo) == 7:
	            str2 = str2+"\n  "+einfo[4]+" : "+einfo[5]+"\n  "+\
	                   einfo[6]+"\n"
	        else:
	            # the leftover text was formatted funny, just output it
	            str2 = str2+"\n  "+einfo[4]+"\n"
	else:
	    str = str+"</TABLE></CENTER>\n"
	return str+str2+"</PRE>\n"

    def add_2nd_button(self):
        return status_html_file_name()+'">ENSTORE'

class HTMLLogFile(EnHTMLFile, EnStatusFile):

    html_header1 = "<title>Enstore Log Files</title>\n"+\
                   "<meta http-equiv=\"Refresh\" content=\""
    html_header2 = "\">\n"+\
                   "<body bgcolor=\""+BG_COLOR+"\">\n"

    def __init__(self, file, refresh):
	EnStatusFile.__init__(self, file)
	EnHTMLFile.__init__(self, refresh)
	self.trailer = "</body>\n"

    # open the file and write the header to the file
    def open(self):
        Trace.trace(12,"open "+self.header)
	EnStatusFile.open(self)
        if self.filedes:
            self.filedes.write(self.header)

    # format the log files and write them to the file
    def write(self, logfile_dir, logfiles, log_dirs, www_host):
        # first we will create links in the file to all log file directories
        # that have been specified in the configuration file with the
        # name format robot_xxxx_dir, where 'xxxx' becomes the name of the
        # link
        if self.filedes:
            if log_dirs:
                dir_keys = log_dirs.keys()
                dir_keys.sort()
                self.filedes.write("<H1><FONT SIZE=+3>Other Log Files</FONT></H1>\n")
                for dir in dir_keys:
                    self.filedes.write('<A HREF="%s"><B>%s Log Files</B></A>\n'% \
                                       (log_dirs[dir], dir))
                self.filedes.write('<BR><BR><HR><BR>\n')

            # now output the enstore log files and their sizes
            if logfiles:
                log_keys = logfiles.keys()
                log_keys.sort()
                self.filedes.write("<H1><FONT SIZE=+3>Enstore Log Files</FONT></H1>\n")
                self.filedes.write('<TABLE BGCOLOR="#DFDFF0" NOSAVE >\n')
                self.filedes.write('<TR><TD><B>FILE</B></TD><TD ALIGN=CENTER><B>SIZE</B></TD></TR>\n')
                for log in log_keys:
                    self.filedes.write('<TR><TD><A HREF="%s%s/%s"><B>%s</B></A></TD><TD>%s</TD></TR>\n'%(www_host, logfile_dir, log, log, logfiles[log]))
                self.filedes.write('</TABLE>\n')
                    
class HTMLConfigFile(EnHTMLFile, EnStatusFile):

    html_header1 = "<title>Enstore Configuration</title>\n"+\
                   "<meta http-equiv=\"Refresh\" content=\""
    html_header2 = "\">\n"+\
                   "<body bgcolor=\""+BG_COLOR+"\">\n"+\
                   "<H1>ENSTORE Configuration</H1>\n"+\
                   '<TABLE BGCOLOR="#DFDFF0" NOSAVE >\n'+\
                   '<TR><TD ALIGN=CENTER><B>ELEMENT</B></TD><TD ALIGN=CENTER><B>KEY</B></TD><TD ALIGN=CENTER><B>VALUE</B></TD></TR>\n'

    def __init__(self, file, refresh):
	EnStatusFile.__init__(self, file)
	EnHTMLFile.__init__(self, refresh)
	self.trailer = "</TABLE>\n</body>\n"

    # open the file and write the header to the file
    def open(self):
        Trace.trace(12,"open "+self.header)
	EnStatusFile.open(self)
        if self.filedes:
            self.filedes.write(self.header)

    HTML_LINE = '<TR><TD>%s</TD><TD>%s</TD><TD>%s</TD></TR>\n'

    # format the config entry and write it to the file
    def write(self, element, dict):
        if self.filedes:
            element_written = 0
            keys = dict.keys()
            keys.sort()
            for key in keys:
                if not element_written:
                    self.filedes.write(self.HTML_LINE%(element, key,
                                                       dict[key]))
                    element_written = 1
                else:
                    self.filedes.write(self.HTML_LINE%("&nbsp;", key, dict[key]))
                    
class EnDataFile(EnFile):

    # make the data file by grepping the inFile.  fproc is any further
    # processing that must be done to the data before it is written to
    # the ofile.
    def __init__(self, inFile, oFile, text, indir="", fproc=""):
	EnFile.__init__(self, oFile)
	self.lines = []
	self.data = []
	if not indir:
	    cdcmd = " "
	else:
	    cdcmd = "cd "+indir+";"
	try:
	    os.system(cdcmd+"grep "+text+" "+inFile+fproc+"> "+oFile)
	except:
	    self.file_name = ""
	    format = str(sys.argv)+" "+\
	             str(sys.exc_info()[0])+" "+\
	             str(sys.exc_info()[1])+" "+\
	             "inquisitor plot system error"
	    Trace.trace(9,"__init__ "+format)

    def read(self, max_lines):
	i = 0
	if self.filedes:
            while i < max_lines:
                l = self.filedes.readline()
                if l:
                    self.lines.append(l)
                    i = i + 1
                else:
                    break
	return self.lines

    # read in the given file and return a list of lines that are between a
    # given start and end time
    def timed_read(self, ticket):
	do_all = FALSE
        start_time = ticket.get(START_TIME, "")
        stop_time = ticket.get(STOP_TIME, "")
        if not stop_time and not start_time:
            do_all = TRUE
	# read it in.  only save the lines that match the desired time frame
        if self.filedes:
            try:
                while TRUE:
                    line = self.filedes.readline()
                    if not line:
                        break
                    else:
                        if do_all or \
                           self.check_line(line, start_time, stop_time):
                            self.lines.append(line)
            except:
                pass
	return self.lines

    # check the line to see if the date and timestamp on the beginning of it
    # is between the given start and end values
    def check_line(self, line, start_time, stop_time):
        if 0: print self # quiet lint
	# split the line into the date/time and all the rest
	datetime, rest = string.split(line, None, 1)
        if 0: print rest # quiet lint
	# remove the beginning LOG_PREFIX
	l = string.replace(datetime,LOG_PREFIX,"")
	# now see if the date/time is between the start time and the end time
	time_ok = TRUE
	if start_time:
	    if l < start_time:
	        time_ok = FALSE
	if time_ok and stop_time:
	    if l > stop_time:
	        time_ok = FALSE
	return time_ok

class EnMountDataFile(EnDataFile):

    # parse the mount line
    def parse_line(self, line):
        if 0: print self # quiet lint
	[etime, enode, etmp, euser, estatus, dev, type, erest] = \
                                                   string.split(line, None, 7)
        if 0: print etmp #quiet lint
	if type == string.rstrip(Trace.MSG_MC_LOAD_REQ) :
	    # this is the request for the mount
	    start = MREQUEST
	else:
	    start = MMOUNT

	# parse out the file directory , a remnant from the grep in the time 
	# field
	strip_file_dir(etime)

        # pull out any dictionaries from the rest of the message
        msg_dicts = get_dict(erest)

	return [etime, enode, euser, estatus, dev, start, msg_dicts]

    # pull out the plottable data from each line that is from one of the
    # specified movers
    def parse_data(self, mcs):
	for line in self.lines:
	    minfo = self.parse_line(line)
            if not mcs or mc_in_list(minfo[MDICTS], mcs):
                self.data.append([minfo[MDEV], string.replace(minfo[ETIME],
                                                              LOG_PREFIX, ""),
                                  minfo[MSTART]])

class EnEncpDataFile(EnDataFile):

    # parse the encp line
    def parse_line(self, line):
        if 0: print self # quiet lint
	einfo = parse_encp_line(line)
        if not len(einfo):
            # nothing was returned skip this line
            return []
        # the time info may contain the file directory which we must
        # strip off
        strip_file_dir(einfo[ETIME])
        return [einfo[ETIME], einfo[EBYTES], einfo[EDICTS]]

    # pull out the plottable data from each line
    def parse_data(self, mcs):
	for line in self.lines:
	    einfo = self.parse_line(line)
	    if einfo and (not mcs or mc_in_list(einfo[2], mcs)):
	        self.data.append([string.replace(einfo[0], LOG_PREFIX, ""), \
	                         einfo[1]])

class EnAlarmFile(EnFile):

    # open the file, if no mode is passed in, try opening for append and
    # then write
    def open(self, mode=""):
        if mode:
            EnFile.open(self, mode)
        else:
            EnFile.open(self, "a")
            if not self.filedes:
                # the open for append did not work, now try write
                EnFile.open(self, "w")

    # read lines from the file
    def read(self):
        enAlarms = {}
        if self.filedes:
            try:
                while TRUE:
                    line = self.filedes.readline()
                    if not line:
                        break
                    else:
                        theAlarm = alarm.AsciiAlarm(line)
                        enAlarms[theAlarm.timedate] = theAlarm
            except IOError:
                pass
        return enAlarms
                
    # write the alarm to the file
    def write(self, alarm):
        if self.filedes:
            line = repr(alarm)+"\n"
            try:
                self.filedes.write(line)
            except IOError:
                pass

class EnPatrolFile(EnFile):

    # we need to save both the file name passed to us and the one we will
    # write to.  we will create the temp one and then move it to the real
    # one.
    def __init__(self, name):
        EnFile.__init__(self, name+TMP)
        self.real_file_name = name
        self.lines = []

    # we need to close the open file and move it to the real file name
    def close(self):
        EnFile.close(self)
        os.system("mv "+self.file_name+" "+self.real_file_name)

    # write out the alarm
    def write(self, alarm):
        if self.filedes:
            # tell the alarm that this is going to patrol so the alarm
            # can add the patrol expected header
            self.filedes.write(alarm.prepr())

    # rm the file
    def remove(self):
        try:
            if self.real_file_name and os.path.exists(self.real_file_name):
                os.system("rm "+self.real_file_name)
        except IOError:
            # file does not exist
            pass
