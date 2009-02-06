#!/usr/bin/env python

#########################################################################
#
# $Id$
#
#########################################################################
#                                                                       #
# Media Changer server.                                                 #
# Media Changer is an abstract object representing a physical device or #
# operator who performs mounts / dismounts of tapes on tape drives.     #
# At startup the media changer process takes its argument from the      #
# command line and cofigures based on the dictionary entry in the       #
# Configuration Server for this type of Media Changer.                  #
# It accepts then requests from its clients and performs tape mounts    #
# and dismounts                                                         #
#                                                                       #
#########################################################################

# system imports
import os
import sys
import types
import time
import popen2
import signal
import string
import socket
import hostaddr
import struct
import fcntl
#if sys.version_info < (2, 2, 0):
#    import FCNTL #FCNTL is depricated in python 2.2 and later.
#    fcntl.F_GETFL = FCNTL.F_SETLKW
#    fcntl.F_SETFL = FCNTL.F_WRLCK
#    fcntl.F_SETFL = FCNTL.F_RDLCK
#    fcntl.F_SETFL = FCNTL.F_UNLCK
import pprint
import re
import subprocess
import copy

# enstore imports
import configuration_client
import dispatching_worker
import generic_server
import monitored_server
import enstore_constants
import option
import Trace
import traceback
import e_errors
import volume_clerk_client
import timeofday
import event_relay_messages
import callback
import enstore_functions2


# The following are used by mtx
import Queue
import threading


def _lock(f, op):
	dummy = fcntl.fcntl(f.fileno(), fcntl.F_SETLKW,
			    struct.pack('2h8l', op,
					0, 0, 0, 0, 0, 0, 0, 0, 0))
	Trace.trace(21,'_lock '+repr(dummy))

def writelock(f):
        _lock(f, fcntl.F_WRLCK)

def readlock(f):
        _lock(f, fcntl.F_RDLCK)

def unlock(f):
        _lock(f, fcntl.F_UNLCK)


#Set the default log level for routine operations to 88.  This will send
# the output to the DEBUGLOG but not the LOG file (by default).  Using
# --do-print this can be overridden.
ACTION_LOG_LEVEL = 88

#There exists two work queues.  One involves tape operations.  The other
# involves queries.
QUEUE_COUNT = 2

#Make sure the number of max_work is within bounds.  The 
def bound_max_work(unbound_max_work):
	max_work = min(int(dispatching_worker.MAX_CHILDREN / QUEUE_COUNT),
		       int(unbound_max_work))
        return max(0, max_work)  #Allow zero for "pausing".
	

# media loader template class
class MediaLoaderMethods(dispatching_worker.DispatchingWorker,
                         generic_server.GenericServer):

    query_functions = ["getVolState", "getDriveState", "listDrives",
		       "listVolumes", "listVolumes2", "listClean",
		       "listSlots"]
    work_functions = ["mount", "dismount", "insert", "eject", "cleanCycle",
		      "homeAndRestart"]

    def return_max_work(self):
	return self.max_work

    def __init__(self, medch, max_work, csc):
        self.logdetail = 1
        self.name = medch
        self.name_ext = "MC"
        generic_server.GenericServer.__init__(self, csc, medch,
                                              function = self.handle_er_msg)
        Trace.init(self.log_name)
        self.max_work = bound_max_work(max_work)
        self.workQueueClosed = 0
        self.insertRA = None
        #   pretend that we are the test system
        #   remember, in a system, there is only one bfs
        #   get our port and host from the name server
        #   exit if the host is not this machine
        self.mc_config  = self.csc.get(medch)

        self.alive_interval = monitored_server.get_alive_interval(
		self.csc, medch, self.mc_config)
        dispatching_worker.DispatchingWorker.__init__(
		self, (self.mc_config['hostip'], self.mc_config['port']))
        self.idleTimeLimit = 600  # default idle time in seconds
        self.lastWorkTime = time.time()
        self.robotNotAtHome = 1
	self.set_this_error = e_errors.OK  # this is useful for testing mover errors
        self.timeInsert = time.time()

        # setup the communications with the event relay task
        self.erc.start([event_relay_messages.NEWCONFIGFILE])
        # start our heartbeat to the event relay process
        self.erc.start_heartbeat(self.name, self.alive_interval,
                                 self.return_max_work)

	# Create the lists of what is currently being done.
	self.work_list = []
	self.work_cleaning_list = []
	self.work_query_list = []


    #Also, works for dismount tickets too.
    def check_mount_ticket(self, ticket):
        if ticket['function'] in ("mount", "dismount"):
            if not ticket.has_key("vol_ticket"):
	        err_msg = 'MISSING VOL_TICKET'
	        ticket['status'] = (e_errors.MALFORMED, 0, err_msg)
                Trace.log(e_errors.ERROR, "%s" % (ticket['status'],))
                return ticket['status']
            if not ticket.has_key("drive_id"):
                err_msg = 'MISSING DRIVE_ID'
	        ticket['status'] = (e_errors.MALFORMED, 0, err_msg)
                Trace.log(e_errors.ERROR, "%s" % (ticket['status'],))
                return ticket['status']
            if not ticket['vol_ticket'].has_key("external_label"):
                err_msg = "MISSING EXTERNAL LABEL for %s %s" % \
			  (ticket["function"],ticket["drive_id"])
		ticket['status'] = (e_errors.MALFORMED, 0, err_msg)
                Trace.log(e_errors.ERROR, "%s" % (ticket['status'],))
                return ticket['status']

	return (e_errors.OK, 0, None)

    # retry function call - By default don't retry.
    def retry_function(self,function,*args):
        return apply(function,args)

    """
    #Some replys are longer than UDP allows.  This function sends the
    # information via TCP.
    def reply_with_full_answer(self, ticket):
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        try:
            sock.connect(ticket['callback_addr'])
            r = callback.write_tcp_obj(sock,ticket)
            sock.close()
            if r:
                Trace.log(e_errors.ERROR,
                              "Error calling write_tcp_obj. Callback addr. %s"
                              % (ticket['callback_addr'],))
        except:
            Trace.handle_error()
            Trace.log(e_errors.ERROR,
                      "Callback address %s" % (ticket['callback_addr'],))
    """

    #########################################################################
    # These functions are named by the media_changer_client.  All of these
    # functions should call self.DoWork().  By using self.DoWork() the
    # queue limit of requests is honored.
    #
    # Functions that use DoWork() do not need to call reply_to_caller()
    # explicitly.  set_max_work() and getwork() don't talk to the robot and
    # fall into this exception category.  robotQuery() falls into this
    # exception category because you don't want to be waiting for a tape to
    # mount/dismount for the queue to open up to find out if the robot is
    # working.
    #########################################################################
    
    # wrapper method for client - server communication
    def loadvol(self, ticket):
        ticket['function'] = "mount"
        Trace.trace(11, "loadvol %s"%(ticket,))

	#Make sure this request has all the necessary information included.
	check_status = self.check_mount_ticket(ticket)
	if not e_errors.is_ok(check_status[0]):
	    return check_status

        return self.DoWork( self.load, ticket )

    # wrapper method for client - server communication
    def unloadvol(self, ticket):
        ticket['function'] = "dismount"
	Trace.trace(11, "unloadvol %s" % (ticket,))

	#Make sure this request has all the necessary information included.
	check_status = self.check_mount_ticket(ticket)
	if not e_errors.is_ok(check_status[0]):
	    return check_status

        return self.DoWork( self.unload, ticket)

    # wrapper method for client - server communication
    def insertvol(self, ticket):
        ticket['function'] = "insert"
        if not ticket.has_key('newlib'):
            ticket['status'] = (e_errors.WRONGPARAMETER, 37, "new library name not specified")
            Trace.log(e_errors.ERROR, "ERROR:insertvol new library name not specified")
            return
        return self.DoWork( self.insert, ticket)

    # wrapper method for client - server communication
    def ejectvol(self, ticket):
        ticket['function'] = "eject"
        return self.DoWork( self.eject, ticket)

    # Is this function even used anywhere?
    def homeAndRestartRobot(self, ticket):
        ticket['function'] = "homeAndRestart"
        return self.DoWork( self.robotHomeAndRestart, ticket)

    # Puts a clean request in the cleaning_work_list queue.
    def doCleaningCycle(self, ticket):
        ticket['function'] = "cleanCycle"
        return self.DoWork( self.cleanCycle, ticket)

    def set_max_work(self, ticket):
        self.max_work = bound_max_work(ticket['max_work'])
	ticket['status'] = (e_errors.OK, 0, None)
        self.reply_to_caller(ticket)

    def __getwork(self):
        # Pack info for the tape handling operations. 
        result = []
        for i in self.work_list:
	    try:
	        if i['vol_ticket']['external_label']:
		    external_label = i['vol_ticket']['external_label']
	    except KeyError:
		    external_label = ""
	    try:
	        if i['drive_id']:
		    drive_id = i['drive_id']
	    except KeyError:
		    drive_id = ""
	    
            result.append((i['function'], external_label, drive_id,
			   i.get('pid', None), i['r_a'][0], i['timestamp']))

	# Pack info for information request operations.
	query_result = []
	for i in self.work_query_list:
	    try:
	        if i['external_label']:
		    external_label = i['external_label']
	    except KeyError:
		    external_label = ""
	    try:
	        if i['drive']:
		    drive_id = i['drive']
	    except KeyError:
		    drive_id = ""
	    
	    query_result.append((i['function'], external_label, drive_id,
				 i.get('pid', None), i['r_a'][0],
				 i['timestamp']))

	#The order for both lists is:
	# 1: type of operation (aka function)
	# 2: external_label (if it applies)
	# 3: drive (if it applies)
	# 4: process id
	# 5: requesting IP address and port number
	# 6: human readable timestamp

	return result, query_result

    def getwork(self, ticket):

	result, query_result = self.__getwork()
	
	ticket['work_list'] = result
	ticket['work_query_list'] = query_result
	ticket['max_work'] = self.max_work
	ticket['status'] = (e_errors.OK, 0, None)
        self.reply_to_caller(ticket)

    # wrapper method for client - server communication
    def viewvol(self, ticket):
        ticket['function'] = "getVolState"
        return self.DoWork( self.getVolState, ticket)

    # wrapper method for client - server communication
    def viewdrive(self, ticket):
        ticket['function'] = "getDriveState"
        rtn = self.DoWork( self.getDriveState, ticket)
	return rtn

    # wrapper method for client - server communication
    def robotQuery(self,ticket):
        # Don't retry this query or wait for the work queue to fit it in,
	# we want to know current status now.
        ticket['status'] =  self.query_robot(ticket)
        self.reply_to_caller(ticket)

    # wrapper method for client - server communication
    def list_drives(self, ticket):
        ticket['function'] = "listDrives"
        return self.DoWork( self.listDrives, ticket)

    # wrapper method for client - server communication
    def list_volumes(self, ticket):
        ticket['function'] = "listVolumes"
        return self.DoWork( self.listVolumes, ticket)

    # wrapper method for client - server communication
    def list_volumes2(self, ticket):
        ticket['function'] = "listVolumes2"
        return self.DoWork( self.listVolumes2, ticket)

    # wrapper method for client - server communication
    def list_clean(self, ticket):
        ticket['function'] = "listClean"
        return self.DoWork( self.listClean, ticket)

    # wrapper method for client - server communication
    def list_slots(self, ticket):
        ticket['function'] = "listSlots"
        return self.DoWork( self.listSlots, ticket)

    #########################################################################
    # These functions are the internal functions used within the media changer
    # for the requests received from the media changer client.
    #########################################################################

    # load volume into the drive; default, overridden for other media changers
    def load(self, ticket):
        __pychecker__ = "no-argsused"
        return (e_errors.OK, 0, None)

    # unload volume from the drive; default overridden for other media changers
    def unload(self, ticket):
        __pychecker__ = "no-argsused"
        return (e_errors.OK, 0, None)

    # insert volume into the robot; default overridden for other media changers
    def insert(self, ticket):
        __pychecker__ = "no-argsused"
        return (e_errors.OK, 0, None, "") # return "" - no inserted volumes

    # eject volume from the robot; default overridden for other media changers
    def eject(self, ticket):
        __pychecker__ = "no-argsused"
        return (e_errors.OK, 0, None)

    def robotHomeAndRestart(self, ticket):
        __pychecker__ = "no-argsused"
        return (e_errors.OK, 0, None)

    def cleanCycle(self, ticket):
        __pychecker__ = "no-argsused"
        return (e_errors.OK, 0, None)

    # getVolState in the drive; default overridden for other media changers
    def getVolState(self, ticket):
        __pychecker__ = "no-argsused"
        return (e_errors.OK, 0, None, "O") # return 'O' - occupied aka unmounted

    # getDriveState for the drive; default overridden for other media changers
    def getDriveState(self, ticket):
        __pychecker__ = "no-argsused"
        return (e_errors.OK, 0, None, "")

    def query_robot(self, ticket):
        __pychecker__ = "no-argsused"
        return (e_errors.OK, 0, None)

    def listDrives(self, ticket):
        __pychecker__ = "no-argsused"
        return (e_errors.OK, 0, None)

    def listVolumes(self, ticket):
        __pychecker__ = "no-argsused"
        return (e_errors.OK, 0, None)

    def listVolumes2(self, ticket):
        __pychecker__ = "no-argsused"
        return (e_errors.OK, 0, None)

    def listClean(self, ticket):
        __pychecker__ = "no-argsused"
        return (e_errors.OK, 0, None)

    def listSlots(self, ticket):
        __pychecker__ = "no-argsused"
        return (e_errors.OK, 0, None)

    #########################################################################
    # These functions are generic media changer internal functions.
    #########################################################################
    
    # prepare is overridden by dismount for mount; i.e. for tape drives we
    # always dismount before mount
    def prepare(self, ticket):
        __pychecker__ = "no-argsused"
        return (e_errors.OK, 0, None)

    def doWaitingInserts(self):
        pass
        return (e_errors.OK, 0, None)

    def getNretry(self):
        numberOfRetries = 3
        return numberOfRetries

    def add_to_work_list(self, ticket):
        if ticket['function'] in self.work_functions:
	    queue = self.work_list
	else:
	    queue = self.work_query_list
	    
        # search the work list of the ticket
	for i in queue:
	    #These elements contain the unique value r_a, which is set by
	    # UDPserver.
	    if i['r_a'] == ticket['r_a']:
		break
	else:
	    ticket['timestamp'] = time.ctime()
	    queue.append(ticket)

    def remove_from_work_list(self, ticket):
	    
        if ticket['function'] in self.work_functions:
	    queue = self.work_list
	else:
	    queue = self.work_query_list

	for i in queue:
	    #These elements contain the unique value r_a, which is set by
	    # UDPserver.
	    if i['r_a'] == ticket['r_a']:
		queue.remove(i)

    def exists_in_work_list(self, ticket):
	    
        if ticket['function'] in self.work_functions:
	    queue = self.work_list
	else:
	    queue = self.work_query_list

	for i in queue:
	    #These elements contain the unique value r_a, which is set by
	    # UDPserver.
	    if i['r_a'] == ticket['r_a']:
		return 1 # Found
	else:
	    return 0 #Not found

    def length_of_work_list(self, ticket):
        if ticket['function'] in self.work_functions:
	    queue = self.work_list
	else:
	    queue = self.work_query_list

	return len(queue)

    def log_work_list(self, ticket = None):
	    result, query_result = self.__getwork()
	    if ticket and ticket['function'] in self.work_functions:
		    Trace.log(ACTION_LOG_LEVEL,
			      "work_list: %s" % \
			      (str(result),))
	    elif ticket and ticket['function'] in self.query_functions:
		    Trace.log(ACTION_LOG_LEVEL,
			      "work_query_list: %s" % \
			      (str(query_result),))
	    else:
		    Trace.log(ACTION_LOG_LEVEL,
			      "work_list: %s" % \
			      (str(result),))
		    Trace.log(ACTION_LOG_LEVEL,
			      "work_query_list: %s" % \
			      (str(query_result),))

    #Used in DoWork() and WorkDone() to create consistent message strings.
    def get_common_message_string(self, ticket):
        #Output what we intend to do.
        if ticket['function'] in ("mount", "dismount"):
	    common_message = "%s %s %s" % \
			      (ticket['function'],
			       ticket['vol_ticket']['external_label'],
			       ticket['drive_id'])
	elif ticket['function'] in ("getVolState",):
	    common_message = "%s %s" % \
			     (ticket['function'],
			      ticket['external_label'])
	elif ticket['function'] in ("getDriveState",):
	    common_message = "%s %s" % \
			     (ticket['function'],
			      ticket['drive'])
	elif ticket['function'] in ("insert",):
	    common_message = "%s %s" % \
			     (ticket['function'],
			      ticket['IOarea_name'])
	elif ticket['function'] in ("eject",):
	    common_message = "%s %s" % \
			     (ticket['function'],
			      ticket['volList'])
        else: #List requests.
	    common_message = "%s" % (ticket['function'],)

	return common_message

    # Do the forking and call the function
    # 
    # A return on None means the request was dropped for one reason or
    # another.  Otherwise the return value should be a status tuple.
    def DoWork(self, function, ticket):

        #The function immediately called by dispatching worker should have
	# set a 'function' field in the ticket.
        if not ticket.has_key('function'):
            err_msg = "MISSING FUNCTION KEY"
	    ticket['status'] = (e_errors.MALFORMED, 0, err_msg)
	    Trace.log(e_errors.ERROR, "%s" % (ticket['status'],))
	    return ticket['status']

        # if this a duplicate request, drop it
	if self.exists_in_work_list(ticket):
	    message = "duplicate request, drop it %s %s" % \
		      (repr(ticket['r_a']), repr(ticket['r_a']))
	    Trace.log(ACTION_LOG_LEVEL, message)
	    return

        #Output what we intend to do.
	common_message = self.get_common_message_string(ticket)
	Trace.log(ACTION_LOG_LEVEL, "REQUESTED %s" % (common_message,))

	###
	### Determine if we need to drop the request for one reason or another.
	###
	
	# Let work list length exceed max_work for cleanCycle.
	if ticket['function'] == "cleanCycle":
	    pass
        #elif ticket['function'] in ["homeAndRestart"]:
	#    pass
        elif ticket['function'] in ("mount", "dismount", "eject", "insert"):
            # If we have max number of working children processes, assume
	    # client will resend the request.
            if len(self.work_list) >= self.max_work:
	        message = "MC Overflow: %s %s" % \
			  (repr(self.max_work), common_message)
                Trace.log(e_errors.INFO, message)
		
		#Need to call reply_to_caller() here since the request has
		# not been processed far enough for WorkDone() to reply
		# for us.
		busy_ticket = {'status' : (e_errors.MC_QUEUE_FULL, 0,
					   "retry later")}
		self.reply_to_caller(busy_ticket)
                return
	    # Else if the work queue is temporarily closed, assume client
	    # will resend the request.
            elif self.workQueueClosed and len(self.work_list) > 0:
	        message = "MC Queue Closed: %s %s" % \
			  (repr(len(self.work_list)), common_message)
                Trace.log(e_errors.INFO, message)
                return

	    # If drive is doing a clean cycle; drop request and assume client
	    # will resend the request.
	    if ticket['function'] in ("mount", "dismount"):
		for i in self.work_list:
		    try:
                        if (i['function'] == "cleanCycle" and \
			    i.has_key('drive_id') and \
			    i['drive_id'] == ticket['drive_id']):

			    message = "Dropped %s request for %s in %s, " \
				      "drive in cleaning cycle." % \
				      (ticket['function'],
				       ticket['vol_ticket']['external_label'],
				       ticket['drive_id'])
			    Trace.log(e_errors.INFO, message)
			    return
		    except:
		        Trace.handle_error()
			Trace.log(e_errors.ERROR, "ERROR %s" % (i,))
	else: # query requests
	    if len(self.work_query_list) >= self.max_work:
	        #If the request work list is full, drop request and assume
		# the client will resent the request.
		return

        ### Otherwise, we can process work.

	#Output what we are going to do.
	Trace.log(e_errors.INFO, "PROCESSING %s" % (common_message,))

        # If function is insert and queue not empty: close work queue and
	# set values to prepare for completing this operation once all
	# pending requests are fullfilled.
        if ticket['function'] == "insert":
            if len(self.work_list) > 0:
               self.workQueueClosed = 1
               self.timeInsert = time.time()
               self.insertRA = ticket['r_a']
               return
            else:
               self.workQueueClosed = 0
	       
        # If not a duplicate request or dropped request; fork the work.
        pipe = os.pipe()
	pid = self.fork(ttl=None) #no time limit
        if pid: 
	    #  in parent process
	    ticket['pid'] = pid

            self.add_select_fd(pipe[0]) #wait for reading half of pipe.
            os.close(pipe[1]) #close writing half of pipe.
            # add entry to outstanding work
	    self.add_to_work_list(ticket)
	    # log the new work list
	    self.log_work_list(ticket)
            return

        #  in child process
	message = "mcDoWork> child begin %s" % (common_message,)
        Trace.trace(ACTION_LOG_LEVEL, message)
	#Trace.log(ACTION_LOG_LEVEL, message) 
	
        os.close(pipe[0]) #Close reading half of pipe.
	
        # do the work ...
	
        # ... if this is a mount, dismount first
        if ticket['function'] == "mount":
	    message = "mcDoWork> child prepare dismount for %s" % \
			(common_message,)
            Trace.trace(ACTION_LOG_LEVEL, message)
	    Trace.log(ACTION_LOG_LEVEL, message)
	    
	    # don't print a failure  (no tape mounted) message that is
	    # really a success
            self.logdetail = 0 
	    dismount_ticket = {'work'           : 'unloadvol',
			       'vol_ticket'     : ticket['vol_ticket'],
			       'drive_id'       : ticket['drive_id'],
			       }
	    sts = self.prepare(dismount_ticket)
            self.logdetail = 1 # back on

	    message = "%s returned %s" % (message, sts[2])
            Trace.trace(ACTION_LOG_LEVEL, message)
	    Trace.log(ACTION_LOG_LEVEL, message)

	    # XXX - Why isn't sts processed for errors here?

	message = "mcDoWork> child doing %s" % (common_message,)
	Trace.trace(ACTION_LOG_LEVEL, message)
	Trace.log(ACTION_LOG_LEVEL, message)
	
	sts = function(ticket) #Call the function!

	message = "mcDoWork> child %s returned %s" % (common_message, sts)
	Trace.trace(ACTION_LOG_LEVEL, message)
	Trace.log(ACTION_LOG_LEVEL, message)

        ticket["status"] = sts
        # Send status back to MC parent via pipe then via dispatching_worker
	# and WorkDone ticket so dispatching_worker calls WorkDone().
	ticket['work'] = "WorkDone"

        #There must be a better way to write to the pipe connected to the
	# parent process.  Probably with callback.py.
	msg = repr(('0','0',ticket))
	bytecount = "%08d" % (len(msg),)
	try:
		os.write(pipe[1], bytecount)
		os.write(pipe[1], msg)
		os.close(pipe[1])
	except (OSError, IOError), msg:
		message = "mcDoWork> child %s failed reporting to parent: %s" \
			  % (common_message, str(msg))
		Trace.trace(ACTION_LOG_LEVEL, message)
		Trace.log(ACTION_LOG_LEVEL, message)

        os._exit(0)


    # dispatching_worker sends "WorkDone" ticket here and we reply_to_caller()
    def WorkDone(self, ticket):
	
        # remove work from outstanding work list
	self.remove_from_work_list(ticket)

        # log what was done
        status = ticket.get('status', None)
        if status and e_errors.is_ok(status[0]):
            level = e_errors.INFO
        else:
            level = e_errors.ERROR
	common_message = self.get_common_message_string(ticket)
	Trace.log(level, "FINISHED %s returned %s" % (common_message, status))
	# log the new work list
	self.log_work_list(ticket)

        # report back to original client - probably a mover
	#
	# Some functions need to handle the reply directly (list_volumes).
	# They, should set 'no_reply' to python true in the ticket.
	if not ticket.get('no_reply', None):
	    self.reply_to_caller(ticket)

        self.robotNotAtHome = 1
        self.lastWorkTime = time.time()
        
        # if work queue is closed and work_list is empty, do insert
	#
	# Shouldn't there be a better way of scheduling this?  Waiting until
	# a previous request complets doesn't seem correct.  This also leads
	# into how sts could/should be processed.
        sts = self.doWaitingInserts()

#########################################################################
#
# AML2 robot loader server
#
#########################################################################
class AML2_MediaLoader(MediaLoaderMethods):

    def __init__(self, medch, max_work=7, csc=None):
        global aml2

        MediaLoaderMethods.__init__(self, medch, max_work, csc)

        try:
	    import aml2
	except ImportError:
	    message = "Unable to load ACI library.  Exiting."
	    Trace.log(e_errors.ERROR, message)
	    sys.stderr.write("%s\n" % message)
	    sys.exit(1)

        # robot choices are 'R1', 'R2' or 'Both'
        if self.mc_config.has_key('RobotArm'):   # error if robot not in config
            self.robotArm = string.strip(self.mc_config['RobotArm'])
        else:
            Trace.log(e_errors.ERROR, "ERROR:mc:aml2 no robot arm key in configuration")
            self.robotArm = string.strip(self.mc_config['RobotArm']) # force the exception
            return

        if self.mc_config.has_key('IOBoxMedia'):   # error if IO box media assignments not in config
            self.mediaIOassign = self.mc_config['IOBoxMedia']
        else:
            Trace.log(e_errors.ERROR, "ERROR:mc:aml2 no IO box media assignments in configuration")
            self.mediaIOassign = self.mc_config['IOBoxMedia'] # force the exception
            return

        if self.mc_config.has_key('DriveCleanTime'):   # error if DriveCleanTime assignments not in config
            self.driveCleanTime = self.mc_config['DriveCleanTime']
        else:
            Trace.log(e_errors.ERROR, "ERROR:mc:aml2 no DriveCleanTime assignments in configuration")
            self.driveCleanTime = self.mc_config['DriveCleanTime'] # force the exception
            return

        if self.mc_config.has_key('IdleTimeHome'):
            if (type(self.mc_config['IdleTimeHome']) == types.IntType and
                self.mc_config['IdleTimeHome'] > 20):
                self.idleTimeLimit = self.mc_config['IdleTimeHome']
            else:
                Trace.log(e_errors.INFO, "mc:aml2 IdleHomeTime is not defined or too small, default used")
        self.prepare=self.unload

    # retry function call
    def retry_function(self,function,*args):
        count = self.getNretry()
        rpcErrors = 0
        sts=("",0,"")
        while count > 0 and sts[0] != e_errors.OK:
            try:
                sts=apply(function,args)
                if sts[1] != 0:
                   if self.logdetail:
                      Trace.log(e_errors.ERROR, 'retry_function: function %s %s error %s'%(repr(function),args,sts[2]))
                if sts[1] == 1 and rpcErrors < 2:  # RPC failure
                    time.sleep(10)
                    rpcErrors = rpcErrors + 1
                elif (sts[1] == 5 or         # requested drive in use
                      sts[1] == 8 or         # DAS was unable to communicate with AMU
                      sts[1] == 10 or        # AMU was unable to communicate with robot
                      #sts[1] == 34 or        # The aci request timed out
                      sts[1] == 24):         # requested volume in use
                    count = count - 1
                    time.sleep(20)
                elif (sts[1] == e_errors.MC_VOLNOTHOME): # tape not in home position
                    count = count - 1
                    time.sleep(120)
                else:
                    break
            except:
                exc,val,tb = Trace.handle_error()
                return "ERROR", 37, str(val)   #XXX very ad-hoc!
                                 ## this is "command error" in aml2.py
        return sts

    """
    def checkMyself(self):
        # do regularily scheduled internal checks
        if self.robotNotAtHome and (time.time()-self.lastWorkTime) > self.idleTimeLimit:
            self.robotNotAtHome = 0
            ticket = { 'function' : 'homeAndRestart', 'robotArm' : self.robotArm }
            sts = self.robotHomeAndRestart(ticket)
            self.lastWorkTime = time.time()
    """
    
    #########################################################################
    # These functions are overridden from the generic class.
    #########################################################################

    # load volume into the drive;
    def load(self, ticket):
        drive = ticket['drive_id']
	external_label = ticket['vol_ticket']['external_label']
	media_type = ticket['vol_ticket']['media_type']
        return self.retry_function(aml2.mount, external_label,
				   drive, media_type)

    # unload volume from the drive
    def unload(self, ticket):
        drive = ticket['drive_id']
	external_label = ticket['vol_ticket']['external_label']
	media_type = ticket['vol_ticket']['media_type']
        return self.retry_function(aml2.dismount, external_label,
				   drive, media_type)

    def insert(self, ticket):
        self.insertRA = None
        classTicket = { 'mcSelf' : self }
        ticket['timeOfCmd'] = time.time()
        ticket['medIOassign'] = self.mediaIOassign
        return self.retry_function(aml2.insert, ticket, classTicket)

    def eject(self, ticket):
        classTicket = { 'mcSelf' : self }
        ticket['medIOassign'] = self.mediaIOassign
        return self.retry_function(aml2.eject, ticket, classTicket)

    def robotHomeAndRestart(self, ticket):
        classTicket = { 'mcSelf' : self }
        ticket['robotArm'] = self.robotArm
        return self.retry_function(aml2.robotHomeAndRestart,
				   ticket, classTicket)

    def getVolState(self, ticket):
        external_label = ticket['external_label']
        media_type = ticket['media_type']
        stat,volstate = aml2.view(external_label,media_type)
        state='U' # unknown
        if stat != 0:
            #return 'BAD', stat, 'aci_view return code', state
	    return aml2.convert_status(stat)
        if volstate == None:
            return 'BAD', stat, 'volume %s not found'%(external_label,),state
        #Return the correct media type.
        ticket['media_type'] = aml2.media_names.get(volstate.media_type,
						    "unknown")
        return (e_errors.OK, 0, "", volstate.attrib)

    def cleanCycle(self, inTicket):
        __pychecker__ = "unusednames=i"
	    
        #do drive cleaning cycle
        Trace.log(e_errors.INFO, 'mc:aml2 ticket='+repr(inTicket))
        #classTicket = { 'mcSelf' : self }
        try:
            drive = inTicket['moverConfig']['mc_device']
        except KeyError:
            Trace.log(e_errors.ERROR, 'mc:aml2 no device field found in ticket.')
            status = 37
            return e_errors.DOESNOTEXIST, status, "no device field found in ticket"

        driveType = drive[:2]  # ... need device type, not actual device
        try:
            if self.driveCleanTime:
                cleanTime = self.driveCleanTime[driveType][0]  # clean time in seconds
                driveCleanCycles = self.driveCleanTime[driveType][1]  # number of cleaning cycles
            else:
                cleanTime = 60
                driveCleanCycles = 1
        except KeyError:
            cleanTime = 60
            driveCleanCycles = 1

        vcc = volume_clerk_client.VolumeClerkClient(self.csc)
        min_remaining_bytes = 1
        vol_veto_list = []
        first_found = 0
        libraryManagers = inTicket['moverConfig']['library']
        if type(libraryManagers) == types.StringType:
            lm = libraryManagers
            library = string.split(libraryManagers,".")[0]
        elif type(libraryManagers) == types.ListType:
            lm = libraryManagers[0]
            library = string.split(libraryManagers[0],".")[0]
        else:
            Trace.log(e_errors.ERROR, 'mc:aml2 library_manager field not found in ticket.')
            status = 37
            return e_errors.DOESNOTEXIST, status, "no library_manager field found in ticket"
        lm_info = self.csc.get(lm)
        if not lm_info.has_key('CleanTapeVolumeFamily'):
            Trace.log(e_errors.ERROR, 'mc: no CleanTapeVolumeFamily field found in ticket.')
            status = 37
            return e_errors.DOESNOTEXIST, status, "no CleanTapeVolumeFamily field found in ticket"
        cleanTapeVolumeFamily = lm_info['CleanTapeVolumeFamily']
        v = vcc.next_write_volume(library,
                                  min_remaining_bytes, cleanTapeVolumeFamily,
                                  vol_veto_list, first_found, exact_match=1)  # get which volume to use
        if v["status"][0] != e_errors.OK:
            Trace.log(e_errors.ERROR,"error getting cleaning volume:%s %s"%
                      (v["status"][0],v["status"][1]))
            status = 37
            return v["status"][0], 0, v["status"][1]

        for i in range(driveCleanCycles):
            Trace.log(e_errors.INFO, "AML2 clean drive %s, vol. %s"%(drive,v['external_label']))
            #rt = self.load(v['external_label'], drive, v['media_type'])
	    rt = self.retry_function(aml2.mount, v['external_label'],
				     drive, v['media_type'])
            status = rt[1]
            if status != 0:      # mount returned error
                s1,s2,s3 = self.retry_function(aml2.convert_status,status)
                return s1, s2, s3

            time.sleep(cleanTime)  # wait cleanTime seconds
            #rt = self.unload(v['external_label'], drive, v['media_type'])
	    rt = self.retry_function(aml2.dismount, v['external_label'],
				     drive, v['media_type'])
            status = rt[1]
            if status != 0:      # dismount returned error
                s1,s2,s3 = self.retry_function(aml2.convert_status,status)
                return s1, s2, s3
            Trace.log(e_errors.INFO,"AML2 Clean returned %s"%(rt,))

        retTicket = vcc.get_remaining_bytes(v['external_label'])
        remaining_bytes = retTicket['remaining_bytes']-1
        vcc.set_remaining_bytes(v['external_label'],remaining_bytes,'\0', None)
        return (e_errors.OK, 0, None)

    def doWaitingInserts(self):
        #do delayed insertvols
        if self.workQueueClosed and len(self.work_list)==0:
            self.workQueueClosed = 0
            ticket = { 'function'  : 'insert',
                       'timeOfCmd' : self.timeInsert,
                       'r_a'        : self.insertRA }
            self.DoWork( self.insert, ticket)
        return (e_errors.OK, 0, None)

    def query_robot(self, ticket):
        __pychecker__ = "no-argsused"
	
	#Name of the aci library function.
	command = "aci_robstat"

	t0 = time.time()
	status, status_code, response = self.robotStatus(self.robotArm)
	delta = time.time() - t0

        # got response, parse it and put it into the standard form
	if not e_errors.is_ok(status[0]):
		
		E=19  #19 = ???
		msg = "robot status %i: %s => %i,%s, %f" % \
		      (E, command, status_code, response, delta)
		Trace.log(e_errors.ERROR, msg)
		return (status, E, response, "", msg)
	
        msg = "%s => %i,%s, %f" % (command, status_code, response, delta)
        Trace.log(e_errors.INFO, msg)
        return (e_errors.OK, 0, msg, "", "")

    def getDriveState(self, ticket):
	drive = ticket['drive']
        stat, drivestate = aml2.drive_state(drive)

        state='N' # unknown
        if stat != 0:
            #return 'BAD', stat, "aci_drivestatus2 return code", state
	    return aml2.convert_status(stat)
        if drivestate == None:
            return 'BAD', stat, "drive %s not found" % (drive,), state

        if drivestate.drive_state == aml2.ACI_DRIVE_UP:
	    state = "U" #UP
	elif drivestate.drive_state == aml2.ACI_DRIVE_DOWN:
	    state = "D" #DOWN

	#Update the ticket with additional information.
	drive_info = {}
	drive_info['state'] = aml2.drive_state_names.get(
		drivestate.drive_state, "unknown")
	drive_info['type'] = aml2.drive_names.get(str(drivestate.drive_state),
						  "unknown")
	drive_info['status'] = 0
	drive_info['volume'] = drivestate.volser
	ticket['drive_info'] = drive_info
        return (e_errors.OK, 0, drivestate.volser, "%s %d" %
		(state, drivestate.drive_state))

    def listDrives(self, ticket):
        stat, drives = aml2.drives_states()
	if stat != 0:
	    #ticket['status'] = 'BAD', stat, "aci_drivestatus2 return code"
	    ticket['status'] = aml2.convert_status(stat)
	    drives = []  #To avoid TypeErrors.
	else:
	    ticket['status'] = (e_errors.OK, 0, "")

	drive_list = []
	for drive in drives:
	    use_state = aml2.drive_state_names.get(drive.drive_state,
						   drive.drive_state)
	    use_type = aml2.drive_names.get(drive.type, drive.type)
	    ##################################################
	    # The aml2 is not very good and knowning the difference between
	    # an LTO1 and LTO2 drive.  Ask the mover for the correct
	    # drive type.
	    movers = self.csc.get_movers2(3, 2)
	    for mover in movers:
		    if mover['mc_device'] == drive.drive_name:
			    import mover_client
			    flags = enstore_constants.NO_LOG | enstore_constants.NO_ALARM
		            mc = mover_client.MoverClient(self.csc,
							  mover['name'],
							  flags = flags,
							  rcv_timeout = 3,
							  rcv_tries = 2)
			    status = mc.status(3, 2) #Get the status.
			    del mc #Hope this helps with resource leaks!
			    if e_errors.is_ok(status['status'][0]):
				    #use_type = "%s=%s" % (status['drive_id'],
				    #			  use_type)
				    use_type = status['drive_id']
			    #Regardless of an error or not, we found the
			    # mover we were looking for.  Give up.
			    break
	    ### Without an explicit collection here, even the "del mc" above
	    ### does not work until python runs the garbage collector.
	    ### If python takes to long we run out of FDs, so force python
	    ### to reclain those resources.
	    import gc
	    gc.collect()
	    ##################################################

	    ##This doesn't seem to work.
	    #if int(drive.mount) == 1:
	    #	    use_status = "mounted"
	    #elif int(drive.mount) == 0:
	    #	    use_status = "empty"
	    #else:
	    #	    use_status = "unknown"
	    if drive.volser:
		    use_status = "mounted"
	    else:
		    use_status = "empty"
	    
	    drive_list.append({"name" : drive.drive_name,
			       "state" : use_state,
			       "status" : use_status, #Filler for AML2.
			       "volume" : drive.volser,
			       "type" : use_type,
			       })

	ticket['drive_list'] = drive_list
	return (e_errors.OK, 0, None)

    def listVolumes(self, ticket):

        if not hostaddr.allow(ticket['callback_addr']):
            return

        #We modify it if not Okay.
	ticket['status'] = (e_errors.OK, 0, None, "", "") 
	    
        stat, volumes = aml2.list_volser()
	if stat != 0:
	    ticket['status'] = aml2.convert_status(stat)
	else:
	    ticket['status'] = (e_errors.OK, 0, None, "", "")

	volume_list = []
	for volume in volumes:
	    use_media_type = aml2.media_names.get(volume.media_type, "UNKNOWN")
		
	    volume_list.append({'volume' : volume.volser,
				'type' : use_media_type,
				'state' : volume.attrib,
				'location' : "",
				})
	reply = copy.copy(ticket)
	self.reply_to_caller(reply)
	ticket['no_reply'] = 1 #Tell WorkDone() not to send the ticket again.
	reply = copy.copy(ticket)
	reply['volume_list'] = volume_list
	sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        try:
            sock.connect(ticket['callback_addr'])
            r = callback.write_tcp_obj(sock, reply)
            sock.close()
            if r:
	       message = "Error calling write_tcp_obj. Callback addr. %s" \
			 % (ticket['callback_addr'],)
               Trace.log(e_errors.ERROR, message)
	       E=6
	       ticket['status'] = (e_errors.NET_ERROR, E, message)
        except:
            Trace.handle_error()
            Trace.log(e_errors.ERROR,
		      "Callback address %s" % (ticket['callback_addr'],))
	    E=6
	    ticket['status'] = (e_errors.NET_ERROR, E, sys.exc_info()[2])

        return ticket['status']

    def listVolumes2(self, ticket):
        ticket['work'] = "list_volumes" #Use old method for AML2.
	ticket['function'] = "listVolume"
        return self.listVolumes(ticket)
	

    def listSlots(self, ticket):
	# A bug in aci_getcellinfo() requires forking in list_slots().
	# If we are the parent, just return and keep on going.  This isn't
	# the best solution because we loose keeping the reply in the
	# udp_server in case the client didn't receive the reply.  If
	# a better solution is needed, then look at timed_command() in the
	# STK implementation.
	#
	# The bug is that for every call to aci_getcellinfo() three file
	# descriptors (that are sockets) are leaked.
	#
	# By using self.fork() instead of os.fork() we get automatic process
	# tracking and termination (if needed).
	#     
	#pid = self.fork()
	#if pid != 0: # parent
	#    return

	# ... else this is the child.

	### All this extra forking code to work around aci_getcellinfo()
	### is not needed now that list_slots() uses DoWork() to call
	### listSlots.  An implicit fork() is called in DoWork() for us.

        stat, slots = aml2.list_slots()
	if stat != 0:
	    ticket['status'] = aml2.convert_status(stat)
	else:
	    ticket['status'] = (e_errors.OK, 0, "")

	slot_list = []
	for slot_info in slots:
	    #location = slot_info[0]

	    for i in range(len(slot_info[1])):
	        media_type = slot_info[1][i].eMediaType
		use_media_type = aml2.media_names.get(media_type,
						      media_type)
		slot_dict = {"location" : slot_info[0],
			     "media_type" : use_media_type,
			     }
		try:
		    slot_dict['total'] = slot_info[1][i].ulCount
	        except IndexError:
		    slot_dict['total'] = 0
		try:
		    slot_dict['free'] = slot_info[2][i].ulCount
		except IndexError:
		    slot_dict['free'] = 0
		try:
		    slot_dict['used'] = slot_info[3][i].ulCount
		except IndexError:
		    slot_dict['used'] = 0
		try:
		    slot_dict['disabled'] = slot_info[4][i].ulCount
		except IndexError:
		    slot_dict['disabled'] = 0

		slot_list.append(slot_dict)

	ticket['slot_list'] = slot_list
	return (e_errors.OK, 0, None)

	#self.reply_to_caller(ticket)
	#sys.exit(0)  #Remember we are the child here.


    def listClean(self, ticket):
	
        stat, volumes_list = aml2.list_volser()
	if stat != 0:
	    ticket['status'] = aml2.convert_status(stat)
	else:
	    ticket['status'] = (e_errors.OK, 0, "")

	vcc = volume_clerk_client.VolumeClerkClient(self.csc,
						    logc = self.logc,
						    alarmc = self.alarmc,
						    rcv_timeout=5,
						    rcv_tries=12)

	clean_list = []
        for volume_instance in volumes_list:
	    volume = volume_instance.volser
	    use_media_type = aml2.media_names.get(volume_instance.media_type,
						  "UNKNOWN")

	    if volume[0:2] != "CL":
	        #############################################
	        #Assuming cleaning tapes begin with CL is an unfortunate
		# part of this implimentation.
		#############################################
	        continue

	    vol_info = vcc.inquire_vol(volume, timeout = 5, retry = 12)
	    if e_errors.is_ok(vol_info):
	        location = "N/A"
		max_usage = "N/A"
		current_usage = "N/A"
		remaining_usage = vol_info['remaining_bytes']
		status = "N/A"
		#media_type = vol_info['media_type']
	    else:
	        location = "N/A"
		max_usage = "N/A"
		current_usage = "N/A"
		remaining_usage = "Unknown"
		status = "N/A"
		#media_type = "Unknown"

	    clean_list.append({"volume" : volume,
			       "location" : location,
			       "max_usage" : max_usage,
			       "current_usage" : current_usage,
			       "remaining_usage" : remaining_usage,
			       "status" : status,
			       "type" : use_media_type,
			       })

	ticket['status'] = (e_errors.OK, 0, None)
	reply = copy.copy(ticket)
	self.reply_to_caller(reply)
	ticket['no_reply'] = 1 #Tell WorkDone() not to send the ticket again.
	reply = copy.copy(ticket)
	reply['clean_list'] = clean_list
	sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        try:
            sock.connect(ticket['callback_addr'])
            r = callback.write_tcp_obj(sock, reply)
            sock.close()
            if r:
               Trace.log(e_errors.ERROR,
			 "Error calling write_tcp_obj. Callback addr. %s"
			 % (ticket['callback_addr'],))
            
        except:
            Trace.handle_error()
            Trace.log(e_errors.ERROR,
		      "Callback address %s" % (ticket['callback_addr'],)) 

	return (e_errors.OK, 0, None)

    #########################################################################
    # These functions are internal functions specific to AML2 media changer.
    #########################################################################

    def robotStatus(self, arm):
        return self.retry_function(aml2.robotStatus, arm)

    """
    def robotHome(self, arm):
        return self.retry_function(aml2.robotHome,arm)


    def robotStart(self, arm):
        return self.retry_function(aml2.robotStart, arm)
    """

	
#########################################################################
#
# STK robot loader server
#
#########################################################################
class STK_MediaLoader(MediaLoaderMethods):

    def __init__(self, medch, max_work=7, csc=None):
        MediaLoaderMethods.__init__(self,medch,max_work,csc)

	self.acls_host  = self.mc_config.get('acls_host',  'UNKNOWN')
	self.acls_uname = self.mc_config.get('acls_uname', 'UNKNOWN')
	self.driveCleanTime = self.mc_config.get('DriveCleanTime',
						 {'9840':[60,1],'9940':[60,1]})

        self.prepare = self.unload
        self.DEBUG = 0
        print "STK MediaLoader initialized"

    # retry function call
    def retry_function(self,function,*args):
        count = self.getNretry()
        sts=("",0,"")
        # retry every error
        while count > 0 and sts[0] != e_errors.OK:
            try:
                sts=apply(function,args)
                if sts[1] != 0:
                   if self.logdetail:
                      Trace.log(e_errors.ERROR, 'retry_function: function %s  %s  sts[1] %s  sts[2] %s  count %s'%(repr(function),args,sts[1],sts[2],count))
                   if function==self.mount:
                       time.sleep(60)
                       fixsts=apply(self.dismount,args)
                       Trace.log(e_errors.INFO, 'Tried %s %s  status=%s %s  Desperation dismount  status %s %s'%(repr(function),args,sts[1],sts[2],fixsts[1],fixsts[2]))
                   time.sleep(60)
                   count = count - 1
                else:
                    break
            except:
                exc,val,tb = Trace.handle_error()
                return str(exc),0,""
        return sts

    # simple elapsed timer
    def delta_t(self,begin):
            (ut, st,cut, cst,now) = os.times()
            return (now-begin, now)

    # execute a stk cmd_proc command, but don't wait forever for it to complete
    #mostly stolen from Demo/tkinter/guido/ShellWindow.py - spawn function
    def timed_command(self,cmd,min_response_length=0,timeout=60):

        message = ""
        blanks=0
        nread=0

        now=timeofday.tod()
        p2cread, p2cwrite = os.pipe()
        c2pread, c2pwrite = os.pipe()
        command = "(echo %s;echo logoff)|/export/home/ACSSS/bin/cmd_proc 2>&1" % (cmd,)
        cmd_lookfor = "ACSSA> %s" % (cmd,)

        # can not use dispatching work fork because we are already child.
        # need to kill explictly and children can't kill
        (dum,mark) = self.delta_t(0)
        pid = os.fork()

        if pid == 0:
            # Child
            for i in 0, 1, 2:
                try:
                    os.close(i)
                except os.error:
                    pass
            if os.dup(p2cread) <> 0:
                print 'ERROR: timed_command pc2cread bad read dup'
                Trace.log(e_errors.ERROR, 'timed_command pc2cread bad read dup')
            if os.dup(c2pwrite) <> 1:
                print 'ERROR: timed_command c2pwrite bad write dup'
                Trace.log(e_errors.ERROR, 'timed_command c2pwrite bad write dup')
            if os.dup(c2pwrite) <> 2:
                print 'ERROR: timed_command c2pwrite bad error dup'
                Trace.log(e_errors.ERROR, 'timed_command c2pwrite bad error dup')
            MAXFD = 100 # Max number of file descriptors (os.getdtablesize()???)
            for i in range(3, MAXFD):
                try:
                    os.close(i)
                except:
                    pass
            try:
                #I know this is hard-coded and inflexible. That is what I want so as to
                #prevent any possible security problem.

                os.execv('/usr/bin/rsh',[self.acls_host,'-l',self.acls_uname,command])
            finally:
                exc, msg, tb = sys.exc_info()
                Trace.log(e_errors.ERROR, "timed_command execv failed:  %s %s %s"% (exc, msg, traceback.format_tb(tb)))
                os._exit(1)

        os.close(p2cread)
        os.close(c2pwrite)
        os.close(p2cwrite)


        #wait for child to complete, or kill it
        start = time.time()
        if self.DEBUG:
            print timeofday.tod(),cmd
            Trace.trace(e_errors.INFO,"%s" %(cmd,))
        active=0
        (p,r) = (0,0)
        try:
            while active<timeout:
                p,r = os.waitpid(pid,os.WNOHANG)
                if p!=0:
                    break
	        #We need to start reading this now for really long responses.
		# Otherwise, the buffer fills up with the child waiting
		# for the parent to read something from the full buffer.
		# And the parent waits for the child to finish.
	        msg=os.read(c2pread,2000)
		if msg:
		    if self.DEBUG:
		        print msg,
		    message = message+msg
		    #Need to reset the timeout period.
		    start = time.time()
		    active = 0
		else:
		    if msg == '':
		        blanks = blanks+1
		    active = time.time() - start
		    time.sleep(1)
            else:
                msg="killing %d => %s" % (pid,cmd)
                print timeofday.tod(),msg
                Trace.trace(e_errors.INFO,msg)
                os.kill(pid,signal.SIGTERM)
                time.sleep(1)
                p,r = os.waitpid(pid,os.WNOHANG)
                if p==0:
                    msg="kill -9ing %d => %s" % (pid,cmd)
                    print timeofday.tod(),msg
                    Trace.trace(e_errors.INFO,msg)
                    os.kill(pid,signal.SIGKILL)
                    time.sleep(2)
                    p,r = os.waitpid(pid,os.WNOHANG)
        except:
            exc, msg, tb = sys.exc_info()
            Trace.log(e_errors.ERROR, "timed_command wait for child failed:  %s %s %s"% (exc, msg, traceback.format_tb(tb)))
	    os.close(c2pread)
            return -1,[], self.delta_t(mark)[0]

        if p==0:
	    os.close(c2pread)
            return -2,[], self.delta_t(mark)[0]

        # now read response from the pipe (Some of
	if string.find(cmd,'mount') != -1:  # this is a mount or a dismount command
	    maxread=100  # quick response on queries
	else:
	    maxread=10000 # slow respone on mount/dismounts

	nlines=0
	ntries=0
	jonflag=0
        # async message start with a date:  2001-12-20 07:33:17     0    Drive   0, 0,10,12: Cleaned.
        # unfortunately, not just async messages start with a date.  Alas, each message has to be parsed.
        async_date=re.compile("20\d\d-\d\d-\d\d \d\d:\d\d:\d\d")  
        while nlines<4 and ntries<3:
	  ntries=ntries+1
          #while blanks<2 and nread<maxread:
	  while nread<maxread:
            msg=os.read(c2pread,2000)
	    message = message + msg
	    if msg:
	        if self.DEBUG:
		    print msg,
            nread = nread+1
            if msg == '':
                blanks = blanks+1
#	    if self.DEBUG:
#	        nl=0
#		ml=string.split(msg,'\012')
#		for l in ml:
#                   nl=nl+1
#		   print "nread=",nread, "line=",nl, l
          response = []
          resp = string.split(message,'\012')
	  nl=0
	  for l in resp:
            if async_date.match(l):
              if string.find(l,'Place cartridges in CAP') != -1 or \
                 string.find(l,'Remove cartridges from CAP') != -1 or \
                 string.find(l,'Library error, LSM offline') != -1 or \
                 string.find(l,'Library error, Transport failure') != -1 or \
                 string.find(l,'Library error, LMU failure') != -1 or \
                 string.find(l,'LMU Recovery Complete') != -1 or \
                 string.find(l,': Offline.') != -1 or \
                 string.find(l,': Online.') != -1 or \
                 string.find(l,': Enter operation ') != -1 or \
                 string.find(l,'Clean drive') != -1 or \
                 string.find(l,'Cleaned') != -1:
                if self.DEBUG:
                  print "DELETED:", l
                jonflag=1
                continue
	    if self.DEBUG:
              print    "response line =",nl, l
            response.append(l)
	    nl=nl+1
          nlines=len(response)

	  nl=0
	  if jonflag and self.DEBUG:
	       for l in response:
		  print    "parsed lines =",nl, l
		  nl=nl+1

	os.close(c2pread)
        size = len(response)
        #if size <= 19:
        #    return -3,[], self.delta_t(mark)[0]
        status = 0
        for look in range(0,size): # 1st part of response is STK copyright information
            if string.find(response[look], cmd_lookfor, 0) == 0:
                break
        if look == size:
            status = -4
            look = 0
        else:
            if len(response[look:]) < min_response_length:
                status = -5
        if self.DEBUG:
            rightnow = timeofday.tod() # the times on fntt are not necessarily right, allows us to correlate log time
            rsp = [now,response[look:],rightnow]
            pprint.pprint(rsp)

        return status,response[look:], self.delta_t(mark)[0]

    #########################################################################
    # These functions are overridden from the generic class.
    #########################################################################

    # load volume into the drive;
    def load(self, ticket):
        """
	external_label,    # volume external label
	drive,             # drive id
	media_type):       # media type
	"""
        drive = ticket['drive_id']
	external_label = ticket['vol_ticket']['external_label']
	media_type = ticket['vol_ticket']['media_type']
        return self.retry_function(self.mount, external_label,
				   drive, media_type, ticket)

    # unload volume from the drive
    def unload(self, ticket):
        """
	external_label,  # volume external label
	drive,           # drive id
	media_type):     # media type
	"""
        drive = ticket['drive_id']
	external_label = ticket['vol_ticket']['external_label']
	media_type = ticket['vol_ticket']['media_type']
        return self.retry_function(self.dismount, external_label,
				   drive, media_type)

    def getDriveState(self, ticket):
	drive = ticket['drive']
	rt = self.retry_function(self.query_drive, drive)
	#Update the ticket with additional information.
	drive_info = {}
	drive_info['state'] = rt[2][len(drive):len(drive)+16].strip()
	drive_info['status'] = rt[2][len(drive)+16:len(drive)+16+11].strip()
	drive_info['volume'] = rt[2][len(drive)+16+11:len(drive)+16+11+11].strip()
	drive_info['type'] = rt[2][len(drive)+16+11+11:].strip()
	ticket['drive_info'] = drive_info
	return rt[0], rt[1], rt[3], rt[4]


    #FIXME - what the devil is this?
    def getVolState(self, ticket):
        external_label = ticket['external_label']
        media_type = ticket['media_type']
        rt = self.retry_function(self.query,external_label,media_type)
        Trace.trace(11, "getVolState returned %s"%(rt,))
        if rt[3] == '\000':
            state=''
        else :
            state = rt[3]
            if not state and rt[2]:  # volumes not in the robot
                state = rt[2]
	#Return the correct media type.
	try:
	    ticket['media_type'] = rt[2].split()[-1]
	except (IndexError, ValueError, TypeError, AttributeError):
	    pass

        return (rt[0], rt[1], rt[2], state)

    def cleanCycle(self, inTicket):
        __pychecker__ = "unusednames=i"
	    
        #do drive cleaning cycle
        Trace.log(e_errors.INFO, 'mc:ticket='+repr(inTicket))
        #classTicket = { 'mcSelf' : self }
        try:
            drive = inTicket['moverConfig']['mc_device']
        except KeyError:
            Trace.log(e_errors.ERROR, 'mc:no device field found in ticket.')
            status = 37
            return e_errors.DOESNOTEXIST, status, "no device field found in ticket"

        driveType = drive[:2]  # ... need device type, not actual device
        try:
            if self.driveCleanTime:
                cleanTime = self.driveCleanTime[driveType][0]  # clean time in seconds
                driveCleanCycles = self.driveCleanTime[driveType][1]  # number of cleaning cycles
            else:
                cleanTime = 60
                driveCleanCycles = 1
        except KeyError:
            cleanTime = 60
            driveCleanCycles = 1

        vcc = volume_clerk_client.VolumeClerkClient(self.csc)
        min_remaining_bytes = 1
        vol_veto_list = []
        first_found = 0
        libraryManagers = inTicket['moverConfig']['library']
        if type(libraryManagers) == types.StringType:
            lm = libraryManagers
            library = string.split(libraryManagers,".")[0]
        elif type(libraryManagers) == types.ListType:
            lm = libraryManagers[0]
            library = string.split(libraryManagers[0],".")[0]
        else:
            Trace.log(e_errors.ERROR, 'mc: library_manager field not found in ticket.')
            status = 37
            return e_errors.DOESNOTEXIST, status, "no library_manager field found in ticket"
        lm_info = self.csc.get(lm)
        if not lm_info.has_key('CleanTapeVolumeFamily'):
            Trace.log(e_errors.ERROR, 'mc: no CleanTapeVolumeFamily field found in ticket.')
            status = 37
            return e_errors.DOESNOTEXIST, status, "no CleanTapeVolumeFamily field found in ticket"
        cleanTapeVolumeFamily = lm_info['CleanTapeVolumeFamily']
        v = vcc.next_write_volume(library,
                                  min_remaining_bytes, cleanTapeVolumeFamily,
                                  vol_veto_list, first_found, exact_match=1)  # get which volume to use
        if v["status"][0] != e_errors.OK:
            Trace.log(e_errors.ERROR,"error getting cleaning volume:%s %s"%
                      (v["status"][0],v["status"][1]))
            status = 37
            return v["status"][0], 0, v["status"][1]

        for i in range(driveCleanCycles):
            Trace.log(e_errors.INFO, "STK clean drive %s, vol. %s"%(drive,v['external_label']))
            #rt = self.load(v['external_label'], drive, v['media_type'])
	    rt = self.retry_function(self.mount, v['external_label'],
				     drive, v['media_type'])
            status = rt[0]
            if status != e_errors.OK:      # mount returned error
                return status, 0, None

            time.sleep(cleanTime)  # wait cleanTime seconds
            #rt = self.unload(v['external_label'], drive, v['media_type'])
	    rt = self.retry_function(self.dismount, v['external_label'],
				     drive, v['media_type'])
            status = rt[0]
	    if status != e_errors.OK:
                return status, 0, None
            Trace.log(e_errors.INFO,"STK Clean returned %s"%(rt,))

        retTicket = vcc.get_remaining_bytes(v['external_label'])
        remaining_bytes = retTicket['remaining_bytes']-1
        vcc.set_remaining_bytes(v['external_label'],remaining_bytes,'\0', None)
        return (e_errors.OK, 0, None)

    def query_robot(self, ticket):
        __pychecker__ = "no-argsused"

        # build the command, and what to look for in the response
        command = "query server"
        answer_lookfor = "run"

        # execute the command and read the response
        # efb (dec 22, 2005) - up timeout from 10 to 60 as the queries are hanging
        #status,response,delta = self.timed_command(command,5,10)
        status,response,delta = self.timed_command(command,5,60)
        if status != 0:
            E=18
            msg = "query server %i: %s => %i,%s" % (E,command,status,response)
            Trace.log(e_errors.ERROR, msg)
            return ("ERROR", E, response, "", msg)

        # got response, parse it and put it into the standard form
        answer = string.strip(response[4])
        if string.find(answer, answer_lookfor,0) != 0:
            E=19
            msg = "query server %i: %s => %i,%s, %f" % (E,command,status,response,delta)
            Trace.log(e_errors.ERROR, msg)
            return ("ERROR", E, response, "", msg)
        msg = "%s => %i,%s, %f" % (command,status,answer[0:17],delta)
        Trace.log(e_errors.INFO, msg)
        return (e_errors.OK, 0, msg, "", "")

    query_server = query_robot  #Backward compatiblity. (Still needed?)

    def listDrives(self, ticket):

        # build the command, and what to look for in the response
        command = "query drive ALL"
        #answer_lookfor = "query drive ALL"

        # execute the command and read the response
        # FIXME - what if this hangs?
        # efb (dec 22, 2005) - up timeout from 10 to 60 as the queries are hanging
        #status,response, delta = self.timed_command(command,4,10)
        status,response, delta = self.timed_command(command,4,60)
        if status != 0:
            E=4
            msg = "QUERY_DRIVE %i: %s => %i,%s" % (E,command,status,response)
            Trace.log(e_errors.ERROR, msg)
	    ticket['status'] = ("ERROR", E, response, "", msg)
	    self.reply_to_caller(ticket)
            return ("ERROR", E, response, "", msg)

        drive_list = []
        for line in response:
	    if line[:2] != "  ":
	        #This is some other information.
	        continue

	    name = line[2:13].strip()
	    state = line[14:29].strip()
	    status = line[30:41].strip()
	    volume = line[42:52].strip()
	    drive_type = line[53:].strip()
	    
	    drive_list.append({"name" : name.replace(" ", ""),
			       "state" : state,
			       "status" : status,
			       "volume" : volume,
			       "type" : drive_type,
			       })

	ticket['drive_list'] = drive_list
	return (e_errors.OK, 0, None, "", "")
        """
	ticket['status'] = (e_errors.OK, 0, "")
	self.reply_to_caller(ticket)
	"""

    def listVolumes2(self, ticket):
        ticket['work'] = "list_volumes" #Use old method for STK now too.
	ticket['function'] = "listVolumes"
        return self.listVolumes(ticket)

    def listVolumes(self, ticket):
	
        acsls_cmd = "query volume all"
	#acsls_look_for = "query volume all"
	
        command = "(echo %s;echo logoff)|/export/home/ACSSS/bin/cmd_proc 2>&1"\
		  % (acsls_cmd,)
        cmd_lookfor = "ACSSA> %s" % (acsls_cmd,)

	args = [self.acls_host, '-l', self.acls_uname, command]

	try:
	    lv_proc = subprocess.Popen(args, executable = "/usr/bin/rsh",
				       stdin = None,
				       stdout = subprocess.PIPE,
				       stderr = subprocess.STDOUT,
				       shell = False)
	    ticket['status'] = (e_errors.OK, 0, None)
        except:
	    ticket['status'] = (e_errors.OSERROR, 0, str(sys.exc_info()[1]))

	#Tell the client over udp that we are about to connect using TCP.
	reply = copy.copy(ticket)
	self.reply_to_caller(reply)
	if not e_errors.is_ok(ticket['status'][0]):
	    return ticket['status']

        ticket['no_reply'] = 1 #Tell WorkDone() not to send the ticket again.
        reply = ticket.copy() #Make a copy to keep things clean.  But why?

       	#Connect using TCP.
	try:
	    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.connect(ticket['callback_addr'])
        except (socket.error), msg:
            Trace.handle_error()
            Trace.log(e_errors.ERROR,
		      "Callback address %s" % (ticket['callback_addr'],))

	    #Close opened sockets.
	    lv_proc.stdout.close()
	    return (e_errors.NET_ERROR, 0, str(msg), "", "")


	#We need to skip the header here.  Normally, timed_command() will
	# skip this for us, but since we are not using it due to the
	#performance problems, we need to do this ourselves.
	try:
		line = -1
		while line:
		    line = lv_proc.stdout.readline()
		    if line.find(cmd_lookfor) > -1:
			break
	except:
		#Close opened sockets.
		lv_proc.stdout.close()
		sock.close()
		return
	    	    
	line = -1
	err = 0
	volume_list = []
	while line:
	    line = lv_proc.stdout.readline()

	    if line.find("ACSSA") >= 0 or line.find("Volume Status") >= 0 \
		   or line.find("Identifier") >= 0 or len(line) == 0:
	        #This is some other information.
		continue

	    volume = line[1:13].strip()
	    state = line[13:29].strip()
	    location = line[31:45].strip()
	    media_type = line[47:].strip()

	    volume_list.append({"volume" : volume,
				"state" : state,
				"location" : location,
				"type" : media_type,
				})
	#Put the list of volumes into the reply ticket.
	reply['volume_list'] = volume_list
	reply['status'] = (e_errors.OK, 0, None)
	try:
	    err = callback.write_tcp_obj(sock, reply)
            if err:
               Trace.log(e_errors.ERROR,
			 "Error calling write_tcp_obj. Callback addr. %s"
			 % (ticket['callback_addr'],))
        except:
            Trace.handle_error()
            Trace.log(e_errors.ERROR,
		      "Callback address %s" % (ticket['callback_addr'],))

	    E=6
	    reply['status'] =  ("ERROR", E, str(sys.exc_info()[1]), "", "")
	
	#Don't forget to close the sockets and FIFOs.
	lv_proc.stdout.close()
	sock.close()
	#sys.exit(0)  #Remember we are the child here.
	return (e_errors.OK, 0, None, "", "")

    def listSlots(self, ticket):
        # build the command, and what to look for in the response
        command = "query lsm all"
        #answer_lookfor = "query lsm all"

        # execute the command and read the response
        # FIXME - what if this hangs?
        # efb (dec 22, 2005) - up timeout from 10 to 60 as the queries are hanging

        #status,response, delta = self.timed_command(command,4,10)
        status, response, delta = self.timed_command(command,4,60)
        if status != 0:
            E=4
            msg = "QUERY_VOLUME %i: %s => %i,%s" % (E,command,status,response)
            Trace.log(e_errors.ERROR, msg)
	    ticket['status'] = ("ERROR", E, response, "", msg)
	    self.reply_to_caller(ticket)
            return ("ERROR", E, response, "", msg)

        slot_list = []
        for line in response:
	    if line.find("ACSSA") >= 0 or line.find("LSM Status") >= 0 or \
		   line.find("Identifier") >= 0 or line.find("Count") >= 0 \
		   or len(line) == 0:
	        #This is some other information.
	        continue

	    lsm = line[:13].strip().replace(" ", "")
	    free = int(line[31:42].strip())

	    slot_list.append({"location" : lsm,
			      "media_type" : "all",
			      "total" : "0",
			      "free" : free,
			      "used" : "0",
			      "disabled" : "0",
			      })

	    #Obtain specific full cell/slot count.
	    command2 = "display cell %s,*,*,* -status full -c" % lsm
	    #answer_lookfor2 = "display cell"
	    status2, response2, delta2 = self.timed_command(command2, 4, 60)
	    if status == 0:
	        for line2 in response2:
		    if line2.find("ACSSA") >= 0 or \
		       line2.find("display cell") >= 0 or \
		       line2.find("Display Cell") >= 0 or \
		       line2.find("Number of cells selected") >= 0 \
		       or len(line2) == 0:
		        #This is some other information.
			continue

		    try:
		        used = int(line2)
			slot_list[-1]['used'] = used
			break
		    except (TypeError, ValueError):
			pass

	    #Obtain specific total cell/slot count.
	    command2 = "display cell %s,*,*,* -c" % lsm
	    #answer_lookfor2 = "display cell"
	    status2, response2, delta2 = self.timed_command(command2, 4, 60)
	    if status == 0:
	        for line2 in response2:
		    if line2.find("ACSSA") >= 0 or \
		       line2.find("display cell") >= 0 or \
		       line2.find("Display Cell") >= 0 or \
		       line2.find("Number of cells selected") >= 0 \
		       or len(line2) == 0:
		        #This is some other information.
			continue

		    try:
		        total = int(line2)
			slot_list[-1]['total'] = total
			break
		    except TypeError:
			pass

	    #Obtain specific inaccessable/disabled cell/slot count.
	    command2 = "display cell %s,*,*,* -status inaccessible -c" % lsm
	    #answer_lookfor2 = "display cell"
	    status2, response2, delta2 = self.timed_command(command2, 4, 60)
	    if status == 0:
	        for line2 in response2:
		    if line2.find("ACSSA") >= 0 or \
		       line2.find("display cell") >= 0 or \
		       line2.find("Display Cell") >= 0 or \
		       line2.find("Number of cells selected") >= 0 \
		       or len(line2) == 0:
		        #This is some other information.
			continue

		    try:
		        inaccessible = int(line2)
			#This value is added to the reserved count.
			break
		    except TypeError:
			pass

	    #Obtain specific inaccessable/disabled cell/slot count.
	    command2 = "display cell %s,*,*,* -status reserved -c" % lsm
	    #answer_lookfor2 = "display cell"
	    status2, response2, delta2 = self.timed_command(command2, 4, 60)
	    if status == 0:
	        for line2 in response2:
		    if line2.find("ACSSA") >= 0 or \
		       line2.find("display cell") >= 0 or \
		       line2.find("Display Cell") >= 0 or \
		       line2.find("Number of cells selected") >= 0 \
		       or len(line2) == 0:
		        #This is some other information.
			continue

		    try:
		        reserved = int(line2)
			break
		    except TypeError:
			pass

	    #Sum these two values for the disabled count.
	    slot_list[-1]['disabled'] = reserved + inaccessible

        ticket['slot_list'] = slot_list
	return (e_errors.OK, 0, None, "", "")
        """
	ticket['status'] = (e_errors.OK, 0, "")
	self.reply_to_caller(ticket)
	"""

    def listClean(self, ticket):
        # build the command, and what to look for in the response
        command = "query clean all"
        #answer_lookfor = "query clean all"

	clean_list = []

        #Send reply and Establish the connection first.
	ticket['status'] = (e_errors.OK, 0, None, "", "")
	reply = copy.copy(ticket)
	self.reply_to_caller(reply)
        try:
		sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
		sock.connect(ticket['callback_addr'])
	except:
	    Trace.handle_error()
            Trace.log(e_errors.ERROR,
		      "Callback address %s" % (ticket['callback_addr'],))

	    E=6
	    return ("ERROR", E, str(sys.exc_info()[1]), "", "")

        ticket['no_reply'] = 1 #Tell WorkDone() not to send the ticket again.
        reply = ticket.copy() #Make a copy to keep things clean.  But why?
    
        # execute the command and read the response
        # FIXME - what if this hangs?
        # efb (dec 22, 2005) - up timeout from 10 to 60 as the queries are hanging
        #status,response, delta = self.timed_command(command,4,10)
        status, response, delta = self.timed_command(command,4,60)
        if status != 0:
            E=4
            msg = "QUERY_CLEAN %i: %s => %i,%s" % (E,command,status,response)
            Trace.log(e_errors.ERROR, msg)
	    return ("ERROR", E, response, "", msg)
        else:
	    #Get the information from the robot.
	    for line in response:
	        if line.find("ACSSA") >= 0 or \
		       line.find("Cleaning Cartridge Status") >= 0 or \
		       line.find("Identifier") >= 0 \
		       or len(line) == 0:
		    #This is some other information.
		    continue

	        volume = line[1:13].strip()
		location = line[13:29].strip()
		max_usage = int(line[30:39].strip())
		current_usage = int(line[41:55].strip())
		status = line[56:66].strip()
		media_type = line[67:].strip()

		remaining_usage = max_usage - current_usage #AML2 compatibility
		clean_list.append({"volume" : volume,
				   "location" : location,
				   "max_usage" : max_usage,
				   "current_usage" : current_usage,
				   "remaining_usage" : remaining_usage,
				   "status" : status,
				   "type" : media_type,
				   })

	    #Put the list of cleaning tapes into the reply ticket.
	    reply['clean_list'] = clean_list

	#Send the information.  (success or failure)
	try:
            r = callback.write_tcp_obj(sock, reply)
            sock.close()
            if r:
               Trace.log(e_errors.ERROR,
			 "Error calling write_tcp_obj. Callback addr. %s"
			 % (ticket['callback_addr'],))
        except:
            Trace.handle_error()
            Trace.log(e_errors.ERROR,
		      "Callback address %s" % (ticket['callback_addr'],))

	    E=6
	    return ("ERROR", E, str(sys.exc_info()[1]), "", "")

	return (e_errors.OK, 0, None, "", "")

    #########################################################################
    # These functions are internal functions specific to STK media changer.
    #########################################################################

    #Query a volume.
    def query(self, volume, media_type=""):
        __pychecker__ = "unusednames=media_type"

        # build the command, and what to look for in the response
        command = "query vol %s" % (volume,)
        answer_lookfor = "%s " % (volume,)

        # execute the command and read the response
        # efb (dec 22, 2005) - up timeout from 10 to 60 as the queries are hanging
        #status,response, delta = self.timed_command(command,4,10)
        status,response, delta = self.timed_command(command,4,60)
        if status != 0:
            E=1
            msg = "QUERY %i: %s => %i,%s" % (E,command,status,response)
            Trace.log(e_errors.ERROR, msg)
            return ("ERROR", E, response, '', msg)

        # got response, parse it and put it into the standard form
        answer = string.strip(response[3])
        if string.find(answer, answer_lookfor, 0) != 0:
            E=2
            msg = "QUERY %i: %s => %i,%s" % (E,command,status,response)
            Trace.log(e_errors.ERROR, msg)
            return ("ERROR", E, response, '', msg)
        elif string.find(answer,' home ') != -1:
            msg = "%s => %i,%s" % (command,status,answer)
            Trace.log(e_errors.INFO, msg)
            return (e_errors.OK,0,answer, 'O', msg) # occupied
        elif string.find(answer,' in drive ') != -1:
            msg = "%s => %i,%s" % (command,status,answer)
            Trace.log(e_errors.INFO, msg)
            return (e_errors.OK,0,answer, 'M', msg) # mounted
        elif string.find(answer,' in transit ') != -1:
            msg = "%s => %i,%s" % (command,status,answer)
            Trace.log(e_errors.INFO, msg)
            return (e_errors.OK,0,answer, 'T', msg) # transit
        else:
            E=3
            msg = "QUERY %i: %s => %i,%s" % (E,command,status,response)
            Trace.log(e_errors.ERROR, msg)
            return ("ERROR", E, answer, '', msg)

    def query_drive(self,drive):

        # build the command, and what to look for in the response
        command = "query drive %s" % (drive,)
        answer_lookfor = "%s " % (drive,)

        # execute the command and read the response
        # FIXME - what if this hangs?
        # efb (dec 22, 2005) - up timeout from 10 to 60 as the queries are hanging
        #status,response, delta = self.timed_command(command,4,10)
        status,response, delta = self.timed_command(command,4,60)
        if status != 0:
            E=4
            msg = "QUERY_DRIVE %i: %s => %i,%s" % (E,command,status,response)
            Trace.log(e_errors.ERROR, msg)
            return ("ERROR", E, response, '', msg)


        # got response, parse it and put it into the standard form
        answer = string.strip(response[3])
        answer = string.replace(answer,', ',',') # easier to part drive id
        if string.find(answer, answer_lookfor,0) != 0:
            E=5
            msg = "QUERY_DRIVE %i: %s => %i,%s" % (E,command,status,answer)
            Trace.log(e_errors.ERROR, msg)
            return ("ERROR", E, answer, '', msg)
        elif string.find(answer,' online ') == -1:
            E=6
            msg = "QUERY_DRIVE %i: %s => %i,%s" % (E,command,status,answer)
            Trace.log(e_errors.ERROR, msg)
            return ("ERROR", E, answer, '', msg)
        elif string.find(answer,' available ') != -1:
            msg = "%s => %i,%s" % (command,status,answer)
            Trace.log(e_errors.INFO, msg)
            return (e_errors.OK,0,answer, '', msg) # empty
        elif string.find(answer,' in use ') != -1:
            loc = string.find(answer,' in use ')
            volume = string.split(answer[loc+8:])[0]
            msg = "%s => %i,%s" % (command,status,answer)
            Trace.log(e_errors.INFO, msg)
            return (e_errors.OK,0,answer, volume, msg) # mounted and in use
        else:
            E=7
            msg = "QUERY_DRIVE %i: %s => %i,%s" % (E,command,status,answer)
            Trace.log(e_errors.ERROR, msg)
            return ("ERROR", E, answer, '', msg)

    def mount(self, volume, drive, media_type="", view_first=1, ticket = {}):

        #############################################################
        # ok, this is a test only - see if we can mount readonly for
	# 9840 and 9940 tapes
	if media_type in ('9840', '9940', '9940B'):
		vol_ticket = ticket.get('vol_ticket', {})
		si = vol_ticket.get('system_inhibit', ('none', 'none'))
		ui = vol_ticket.get('user_inhibit', ('none', 'none'))

		if enstore_functions2.is_readonly_state(si[1]) or \
		   enstore_functions2.is_readonly_state(ui[1]):
			readonly = 1
		else:
			readonly = 0
	else:
		readonly = 0
        #############################################################
		

        # build the command, and what to look for in the response
        command = "mount %s %s" % (volume,drive)
	if readonly:
		command = command + " readonly"
        answer_lookfor = "Mount: %s mounted on " % (volume,)

        # check if tape is in the storage location or somewhere else
        if view_first:
            status,stat,response,attrib,com_sent = self.query(volume, media_type)

            if stat!=0:
                E=e_errors.MC_FAILCHKVOL
                msg = "MOUNT %i: %s => %i,%s" % (E,command,stat,response)
                Trace.log(e_errors.ERROR, msg)
                return ("ERROR", E, response, "", msg)
            if attrib != "O": # look for tape in tower (occupied="O")
                E=e_errors.MC_VOLNOTHOME
                msg = "MOUNT %i: Tape is not in home position. %s => %s,%s" % (E,command,status,response)
                Trace.log(e_errors.ERROR, msg)
                return ("ERROR", E, response, "", msg)

        # check if any tape is mounted in this drive
            status,stat,response,volser,com_sent = self.query_drive(drive)
            if stat!=0:
                E=e_errors.MC_FAILCHKDRV
                msg = "MOUNT %i: %s => %i,%s" % (E,command,stat,response)
                Trace.log(e_errors.ERROR, msg)
                return ("ERROR", E, response, "", msg)
            if volser != "": # look for any tape mounted in this drive
                E=e_errors.MC_DRVNOTEMPTY
                msg = "MOUNT %i: Drive %s is not empty =>. %s => %s,%s" % (E,drive,command,status,response)
                Trace.log(e_errors.ERROR, msg)
                return ("ERROR", E, response, "", msg)

        # execute the command and read the response
        status,response, delta = self.timed_command(command,2,60*10)
        if status != 0:
            E=12
            msg = "MOUNT %i: %s => %i,%s" % (E,command,status,response)
            Trace.log(e_errors.ERROR, msg)
            return ("ERROR", E, response, "", msg)

        # got response, parse it and put it into the standard form
        answer = string.strip(response[1])
        if string.find(answer, answer_lookfor,0) != 0:
            # during cap operations acsls returns an error message containing the information that the volume was actually mounted
            # if  this is a case, process it
            compared = 0
            try:
	        Trace.log(e_errors.INFO, "Ckecking ASCLS message %s %s"%(response, answer_lookfor)) # remove after debugging AM
			  
                for l in response:
                    if answer_lookfor in l:
                        # ok the volume is actually mounted
                        # but in what drive?
                        requeseted_drive=drive.split(',')
                        l=l.replace(',',' ')
                        ar=l.split()
			Trace.log(e_errors.INFO, "Requested Drive %s. Comparing to %s"%(requeseted_drive, ar)) # remove after debugging AM
                        same_drive = 0
                        for i in range(len(requeseted_drive)):
                            if int(requeseted_drive[-(i+1)]) != int(ar[-(i+1)]):
                                break
                        else:
                            same_drive = 1
                        if same_drive:
                          compared = 1
                          Trace.log(e_errors.INFO, "The error was false: %s"%(response,))
                          break
                else:
                    compared = 0
            except:
                Trace.handle_error()
                
            if compared == 0:
                E=13
                msg = "MOUNT %i: %s => %i,%s" % (E,command,status,answer)
                Trace.log(e_errors.ERROR, msg)
                return ("ERROR", E, response, "", msg)
        msg = "%s => %i,%s" % (command,status,answer)
        Trace.log(e_errors.INFO, msg)
        return (e_errors.OK, 0, msg, "", "")


    def dismount(self,volume, drive, media_type="", view_first=1):
        __pychecker__ = "unusednames=media_type"

        # build the command, and what to look for in the response
        command = "dismount VOLUME %s force" % (drive,)
        answer_lookfor = "Dismount: Forced dismount of "

        # check if any tape is mounted in this drive
        if view_first:
            status,stat,response,volser,com_sent = self.query_drive(drive)
            if stat!=0:
                E=e_errors.MC_FAILCHKDRV
                msg = "DISMOUNT %i: %s => %i,%s" % (E,command,stat,response)
                Trace.log(e_errors.ERROR, msg)
                return ("ERROR", E, response, "", msg)

            if volser == "": # look for any tape mounted in this drive
                if volume!="Unknown":
                    #FIXME - this should be a real error. mover needs to know which tape it has.
                    E=14
                    msg = "Dismount %i ignored: Drive %s is empty. Thought %s was there =>. %s => %s,%s" % (E,drive,volume,command,status,response)
                    Trace.log(e_errors.INFO, msg)
                    return (e_errors.OK, 0, response, "", msg)
                else: #don't know the volume on startup
                    E=15
                    msg = "Dismount %i ignored: Drive %s is empty. Thought %s was there =>. %s => %s,%s" % (E,drive,volume,command,status,response)
                    Trace.log(e_errors.INFO, msg)
                    return (e_errors.OK, 0, response, "", msg)

        # execute the command and read the response
        status,response,delta = self.timed_command(command,2,60*10)
        if status != 0:
            E=16
            msg = "DISMOUNT %i: %s => %i,%s" % (E,command,status,response)
            Trace.log(e_errors.ERROR, msg)
            return ("ERROR", E, response, "", msg)

        # got response, parse it and put it into the standard form
        answer = string.strip(response[1])
        if string.find(answer, answer_lookfor,0) != 0:
            # during cap operations acsls returns an error message containing the information that the volume was actually mounted
            # if  this is a case, process it
            compared = 0
            try:
                for l in response:
                    if answer_lookfor in l:
                        # ok the volume is actually mounted
                        # but in what drive?
                        requeseted_drive=drive.split(',')
                        l=l.replace(',',' ')
                        ar=l.split()
			Trace.log(e_errors.INFO, "Requested Drive %s. Comparing to %s"%(requeseted_drive, ar)) # remove after debugging AM
                        same_drive = 0
                        for i in range(len(requeseted_drive)):
                            if int(requeseted_drive[-(i+1)]) != int(ar[-(i+1)]):
                                break
                        else:
                            same_drive = 1
                        if same_drive:
                          compared = 1
                          Trace.log(e_errors.INFO, "The error was false: %s"%(response,))
                          break
                else:
                    compared = 0
            except:
                Trace.handle_error()
                
            if compared == 0:
                E=17
                msg = "DISMOUNT %i: %s => %i,%s" % (E,command,status,answer)
                Trace.log(e_errors.ERROR, msg)
                return ("ERROR", E, response, "", msg)
        msg = "%s => %i,%s" % (command,status,answer)
        Trace.log(e_errors.INFO, msg)
        return (e_errors.OK, 0, msg, "", "")


#########################################################################
#
# manual media changer
#
#########################################################################
class Manual_MediaLoader(MediaLoaderMethods):
    def __init__(self, medch, max_work=7, csc=None):
        MediaLoaderMethods.__init__(self,medch,max_work,csc)
        if self.mc_config.has_key('DriveCleanTime'):   # error if DriveCleanTime assignments not in config
            self.driveCleanTime = self.mc_config['DriveCleanTime']
        else:
            self.driveCleanTime = None
	self.media_changer_test = self.mc_config.get("test", None)

    #########################################################################
    # These functions are overridden from the generic class.
    #########################################################################

    def cleanCycle(self, inTicket):
        __pychecker__ = "unusednames=i"
	
        #do drive cleaning cycle
        Trace.log(e_errors.INFO, 'mc: ticket='+repr(inTicket))
        #classTicket = { 'mcSelf' : self }
        try:
            drive = inTicket['moverConfig']['mc_device']
        except KeyError:
            Trace.log(e_errors.ERROR, 'mc: no device field found in ticket.')
            status = 37
            return e_errors.DOESNOTEXIST, status, "no device field found in ticket"

        driveType = drive[:2]  # ... need device type, not actual device
        try:
            if self.driveCleanTime:
                cleanTime = self.driveCleanTime[driveType][0]  # clean time in seconds
                driveCleanCycles = self.driveCleanTime[driveType][1]  # number of cleaning cycles
            else:
                cleanTime = 60
                driveCleanCycles = 1
        except KeyError:
            cleanTime = 60
            driveCleanCycles = 1

        vcc = volume_clerk_client.VolumeClerkClient(self.csc)
        min_remaining_bytes = 1
        vol_veto_list = []
        first_found = 0
        libraryManagers = inTicket['moverConfig']['library']
        if type(libraryManagers) == types.StringType:
            lm = libraryManagers
            library = string.split(libraryManagers,".")[0]
        elif type(libraryManagers) == types.ListType:
            lm = libraryManagers[0]
            library = string.split(libraryManagers[0],".")[0]
        else:
            Trace.log(e_errors.ERROR, 'mc: library_manager field not found in ticket.')
            status = 37
            return e_errors.DOESNOTEXIST, status, "no library_manager field found in ticket"
        lm_info = self.csc.get(lm)
        if not lm_info.has_key('CleanTapeVolumeFamily'):
            Trace.log(e_errors.ERROR, 'mc: no CleanTapeVolumeFamily field found in ticket.')
            status = 37
            return e_errors.DOESNOTEXIST, status, "no CleanTapeVolumeFamily field found in ticket"

        cleanTapeVolumeFamily = lm_info['CleanTapeVolumeFamily']
        v = vcc.next_write_volume(library,
                                  min_remaining_bytes, cleanTapeVolumeFamily,
                                  vol_veto_list, first_found, exact_match=1)  # get which volume to use
        if v["status"][0] != e_errors.OK:
            Trace.log(e_errors.ERROR,"error getting cleaning volume:%s %s"%
                      (v["status"][0],v["status"][1]))
            status = 37
            return v["status"][0], 0, v["status"][1]

        for i in range(driveCleanCycles):
            Trace.log(e_errors.INFO, "clean drive %s, vol. %s"%(drive,v['external_label']))
            t = {'vol_ticket':v,'drive_id':drive}
            rt = self.loadvol(t)
	    if not e_errors.is_ok(rt[0]):
	       return rt
            time.sleep(cleanTime)  # wait cleanTime seconds
            rt = self.unloadvol(t)
	    if not e_errors.is_ok(rt[0]):
	       return rt
        retTicket = vcc.get_remaining_bytes(v['external_label'])
        remaining_bytes = retTicket['remaining_bytes']-1
        vcc.set_remaining_bytes(v['external_label'],remaining_bytes,'\0', None)
        return (e_errors.OK, 0, None)

    def getVolState(self, ticket):
        __pychecker__ = "no-argsused"
        return (e_errors.NOT_SUPPORTED, 0,
                            "Manual media changer has no robot to query.")

    def getDriveState(self, ticket):
        __pychecker__ = "no-argsused"
        return (e_errors.NOT_SUPPORTED, 0,
                            "Manual media changer has no robot to query.")

    def query_robot(self, ticket):
        __pychecker__ = "no-argsused"
        return (e_errors.NOT_SUPPORTED, 0,
                            "Manual media changer has no robot to query.")

    def listDrives(self, ticket):
        __pychecker__ = "no-argsused"
        return (e_errors.NOT_SUPPORTED, 0,
                            "Manual media changer has no robot to query.")

    def listVolumes(self, ticket):
        __pychecker__ = "no-argsused"
        return (e_errors.NOT_SUPPORTED, 0,
                            "Manual media changer has no robot to query.")

    def listVolumes2(self, ticket):
        __pychecker__ = "no-argsused"
        return (e_errors.NOT_SUPPORTED, 0,
                            "Manual media changer has no robot to query.")

    def listClean(self, ticket):
        __pychecker__ = "no-argsused"
        return (e_errors.NOT_SUPPORTED, 0,
                            "Manual media changer has no robot to query.")

    def listSlots(self, ticket):
        __pychecker__ = "no-argsused"
        return (e_errors.NOT_SUPPORTED, 0,
                            "Manual media changer has no robot to query.")

    #########################################################################
    # These functions are internal functions specific to Manual media changer.
    #########################################################################

    # load volume into the drive; default overridden for other media changers
    def load(self, ticket):
        drive = ticket['drive_id']
	external_label = ticket['vol_ticket']['external_label']

	if external_label:
	    if self.media_changer_test:
	        mc_popup = "mc_popup_test"
	    else:
	        mc_popup = "mc_popup"
		
            rt = os.system("%s 'Please load %s into %s'" % \
			   (mc_popup, external_label, drive))
	    if rt:
	        return (e_errors.UNKNOWN, 0, str(rt))
	
        return (e_errors.OK, 0, None)

    # unload volume from the drive; default overridden for other media changers
    def unload(self, ticket):
        drive = ticket['drive_id']
	external_label = ticket['vol_ticket']['external_label']

	if external_label:
	    if self.media_changer_test:
	        mc_popup = "mc_popup_test"
	    else:
	        mc_popup = "mc_popup"
		
            rt = os.system("%s 'Please unload %s from %s'" % \
			   (mc_popup, external_label, drive))
	    if rt:
	        return (e_errors.UNKNOWN, 0, str(rt))
	
        return (e_errors.OK, 0, None)


#########################################################################
#
# Raw Disk and stand alone tape media server
#
#########################################################################
class RDD_MediaLoader(MediaLoaderMethods):
    def __init__(self, medch, max_work=1, csc=None):
        MediaLoaderMethods.__init__(self,medch,max_work,csc)

    #########################################################################
    # These functions are overridden from the generic class.
    #########################################################################

    def getVolState(self, ticket):
        __pychecker__ = "no-argsused"
        return (e_errors.NOT_SUPPORTED, 0,
                            "NULL media changer has no robot to query.")

    def getDriveState(self, ticket):
        __pychecker__ = "no-argsused"
        return (e_errors.NOT_SUPPORTED, 0,
                            "NULL media changer has no robot to query.")

    def query_robot(self, ticket):
        __pychecker__ = "no-argsused"
        return (e_errors.NOT_SUPPORTED, 0,
                            "NULL media changer has no robot to query.")

    def listDrives(self, ticket):
        __pychecker__ = "no-argsused"
        return (e_errors.NOT_SUPPORTED, 0,
                            "NULL media changer has no robot to query.")

    def listVolumes(self, ticket):
        __pychecker__ = "no-argsused"
        return (e_errors.NOT_SUPPORTED, 0,
                            "NULL media changer has no robot to query.")

    def listVolumes2(self, ticket):
        __pychecker__ = "no-argsused"
        return (e_errors.NOT_SUPPORTED, 0,
                            "NULL media changer has no robot to query.")

    def listClean(self, ticket):
        __pychecker__ = "no-argsused"
        return (e_errors.NOT_SUPPORTED, 0,
                            "NULL media changer has no robot to query.")

    def listSlots(self, ticket):
        __pychecker__ = "no-argsused"
        return (e_errors.NOT_SUPPORTED, 0,
                            "NULL media changer has no robot to query.")

    #########################################################################
    # These functions are internal functions specific to NULL media changer.
    #########################################################################

    # load volume into the drive; default, overridden for other media changers
    def load(self, ticket):
        drive = ticket['drive_id']
	external_label = ticket['vol_ticket']['external_label']
        if 'delay' in self.mc_config.keys() and self.mc_config['delay']:
            # YES, THIS BLOCK IS FOR THE DEVELOPMENT ENVIRONMENT AND THE
            # OUTPUT OF THE PRINTS GO TO THE TERMINAL
            print "make sure tape %s in in drive %s" % (external_label, drive)
            time.sleep( self.mc_config['delay'] )
            print 'continuing with reply'
        return (e_errors.OK, 0, None)

    # unload volume from the drive; default overridden for other media changers
    def unload(self, ticket):
        drive = ticket['drive_id']
	external_label = ticket['vol_ticket']['external_label']
        if 'delay' in self.mc_config.keys() and self.mc_config['delay']:
	    message = "remove tape %s from drive %s" % (external_label, drive)
            Trace.log(e_errors.INFO, message)
            time.sleep( self.mc_config['delay'] )
        return (e_errors.OK, 0, None)


    """
      Reserving tape drives for the exclusive use of the Enstore-media_changer
      can be done by establishing an OCS Authorization Group inwhich the sole
      user is the enstore_userid and tape drive list consists soley of the
      enstore reserved drives. These drives and the enstore_userid must not be
      listed in any other Authorization Group as well. Section 7.3.2 of the
      OCS Installation/Administration Guide, Version 3.1, details this
      mechanism.
    """

"""
#########################################################################
#
# "Shelf" manual media server - interfaces with OCS
#
#########################################################################
class Shelf_MediaLoader(MediaLoaderMethods):
    status_message_dict = {
      'OK':        (e_errors.OK, "request successful"),
      'ERRCfgHst': (e_errors.NOACCESS, "mc:Shlf config OCShost incorrect"),
      'ERRNoLoHN': (e_errors.NOACCESS, "mc:Shlf local hostname not accessable"),
      'ERRPipe':   (e_errors.NOACCESS, "mc:Shlf no pipeObj"),
      'ERRHoNoRe': (e_errors.NOACCESS, "mc:Shlf remote host not responding"),
      'ERRHoCmd':  (e_errors.NOACCESS, "mc:Shlf remote host command unsuccessful"),
      'ERROCSCmd': (e_errors.NOACCESS, "mc:Shlf OCS not responding"),
      'ERRHoNamM': (e_errors.NOACCESS, "mc:Shlf remote host name match"),
      'ERRAloPip': (e_errors.MOUNTFAILED, "mc:Shlf allocate no pipeObj"),
      'ERRAloCmd': (e_errors.MOUNTFAILED, "mc:Shlf allocate failed"),
      'ERRAloDrv': (e_errors.MOUNTFAILED, "mc:Shlf allocate drive not available"),
      'ERRAloRsh': (e_errors.MOUNTFAILED, "mc:Shlf allocate rsh error"),
      'ERRReqPip': (e_errors.MOUNTFAILED, "mc:Shlf request no pipeObj"),
      'ERRReqCmd': (e_errors.MOUNTFAILED, "mc:Shlf request failed"),
      'ERRReqRsh': (e_errors.MOUNTFAILED, "mc:Shlf request rsh error"),
      'ERRDeaPip': (e_errors.DISMOUNTFAILED, "mc:Shlf deallocate no pipeObj"),
      'ERRDeaCmd': (e_errors.DISMOUNTFAILED, "mc:Shlf deallocate failed"),
      'ERRDeaRsh': (e_errors.DISMOUNTFAILED, "mc:Shlf deallocate rsh error"),
      'ERRDsmPip': (e_errors.DISMOUNTFAILED, "mc:Shlf dismount no pipeObj"),
      'ERRDsmCmd': (e_errors.DISMOUNTFAILED, "mc:Shlf dismount failed"),
      'ERRDsmRsh': (e_errors.DISMOUNTFAILED, "mc:Shlf dismount rsh error")
      }

    def status_message(self, s):
        if s in self.status_message_dict.keys():
            return self.status_message_dict[s][1]
        else:
            return s

    def status_code(self, s):
        if s in self.status_message_dict.keys():
            return self.status_message_dict[s][0]
        else:
            return e_errors.ERROR


    def __init__(self, medch, max_work=1, csc=None): #Note: max_work may need to be changed, tgj
        MediaLoaderMethods.__init__(self,medch,max_work,csc)
        self.prepare=self.unload #override prepare with dismount and deallocate

        fnstatusO = self.getOCSHost()
        fnstatus = self.getLocalHost()
        Trace.trace(e_errors.INFO,"Shelf init localHost=%s OCSHost=%s" % (self.localHost, self.ocsHost))
        if fnstatus == 'OK' and fnstatusO == 'OK' :
            index = string.find(self.localHost,self.ocsHost)
            if index > -1 :
                self.cmdPrefix = ""
                self.cmdSuffix = ""
            else :
                self.cmdPrefix = "enrsh " + self.ocsHost + " '"
                self.cmdSuffix = "'"
                fnstatus = self.checkRemoteConnection()
                if fnstatus != 'OK' :
                    Trace.log(e_errors.ERROR, "ERROR:Shelf init %s %s" %
                              (fnstatus, self.status_message(fnstatus)))
                    return
        else :
            ## XXX fnstatusR not defined at this point...
            #Trace.log(e_errors.ERROR, "ERROR:Shelf init %s %s" %
            # (fnstatusR, self.status_message(fnstatusR))
            Trace.log(e_errors.ERROR, "ERROR:Shelf init %s %s" %
                      (fnstatus, self.status_message(fnstatus)))
            return
        fnstatus = self.checkOCSalive()
        if fnstatus != 'OK' :
             Trace.log(e_errors.ERROR, "ERROR:Shelf init %s %s" %
                       (fnstatus, self.status_message(fnstatus)))
             return
        #fnstatus = self.deallocateOCSdrive("AllTheTapeDrives")
        #if fnstatus != 'OK' :
        #     Trace.log(e_errors.ERROR, "ERROR:Shelf init %s %s" %
        #                   (fnstatus, self.status_message(fnstatus)))
        #     return
        Trace.log(e_errors.INFO, "Shelf init %s %s" % (fnstatus, self.status_message(fnstatus)))
        return

    def getOCSHost(self):
        "get the hostname of the OCS machine from the config server"
        fnstatus = 'OK'
        self.ocsHost = string.strip(self.mc_config['OCSclient'])
        index = string.find(self.ocsHost,".")
        if index == 0 :
            fnstatus = 'ERRCfgHst'
        return fnstatus

    def getLocalHost(self):
        "get the hostname of the local machine"
        fnstatus = 'OK'
        result = hostaddr.gethostinfo()
        self.localHost = result[0]
        return fnstatus

    def checkRemoteConnection(self):
        "check to see if remote host is there"
        fnstatus = 'OK'
        command = self.cmdPrefix + "echo $(hostname) ; echo $?" + self.cmdSuffix
        Trace.log(e_errors.INFO, "Shelf cRC Cmd=%s" % (command, ))
        pipeObj = popen2.Popen3(command, 0, 0)
        if pipeObj is None:
            fnstatus = 'ERRPipe'
            return fnstatus
        stat = pipeObj.wait()
        result = pipeObj.fromchild.readlines()  # result has returned string
        Trace.log(e_errors.INFO, "Shelf cRC enrsh return strings=%s stat=%s" % (result, stat))
        if stat == 0:
            retval = result[len(result)-1][0]
            if retval != '0':
                fnstatus = 'ERRHoCmd'
                return fnstatus
        else :
            fnstatus = 'ERRHoNoRe'
            return fnstatus
        return fnstatus

    def checkOCSalive(self):
        "check to see if OCS is alive"
        fnstatus = 'OK'
        command = self.cmdPrefix + "ocs_left_allocated -l 0 ; echo $?"  + self.cmdSuffix
        Trace.log(e_errors.INFO, "Shelf cOa Cmd=%s" % (command,) )
        pipeObj = popen2.Popen3(command, 0, 0)
        if pipeObj is None:
            fnstatus = 'ERRPipe'
            return fnstatus
        stat = pipeObj.wait()
        result = pipeObj.fromchild.readlines()  # result has returned string
        Trace.log(e_errors.INFO, "Shelf cOa enrsh return strings=%s stat=%s" % (result, stat))
        if stat == 0:
            retval = result[len(result)-1][0]
            if retval != '0':
                fnstatus = 'ERROCSCmd'
                return fnstatus
        else :
            fnstatus = 'ERRHoNoRe'
            return fnstatus
        return fnstatus

    def allocateOCSdrive(self, drive):
        "allocate an OCS managed drive"
        fnstatus = 'OK'
        command = self.cmdPrefix + "ocs_allocate -T " + drive + " ; echo $?" + self.cmdSuffix
        Trace.log(e_errors.INFO, "Shelf aOd Cmd=%s" % (command,) )
        pipeObj = popen2.Popen3(command, 0, 0)
        if pipeObj is None:
            fnstatus = 'ERRAloPip'
            return fnstatus
        stat = pipeObj.wait()
        result = pipeObj.fromchild.readlines()  # result has returned string
        Trace.log(e_errors.INFO, "Shelf aOd enrsh return strings=%s stat=%s" % (result, stat))
        if stat == 0:
            retval = result[len(result)-1][0]
            if retval != '0':
                fnstatus = 'ERRAloCmd'
                return fnstatus
            else :   # check if OCS allocated a different drive
                retstring = result[0]
                pos=string.find(retstring," "+drive)
                if pos == -1 :  # different drive was allocated
                    fnstatus = 'ERRAloDrv'
                    pos=string.find(retstring," ")
                    if pos != -1 :
                        wrongdrive=string.strip(retstring[pos+1:])
                        Trace.log(e_errors.ERROR, "ERROR:Shelf aOd enrsh wrongdrive=%s" % (wrongdrive,) )
                    fnstatusR = self.deallocateOCSdrive(drive)
                    return fnstatus
        else :
            fnstatus = 'ERRAloRsh'
            return fnstatus
        return fnstatus

    def mountOCSdrive(self, external_label, drive):
        "request an OCS managed tape"
        fnstatus = 'OK'
        command = self.cmdPrefix + "ocs_request -t " + drive + \
                  " -v " + external_label + " ; echo $?" + self.cmdSuffix
        Trace.log(e_errors.INFO, "Shelf mOd Cmd=%s" % (command,) )
        pipeObj = popen2.Popen3(command, 0, 0)
        if pipeObj is None:
            fnstatus = 'ERRReqPip'
            fnstatusR = self.deallocateOCSdrive(drive)
            return fnstatus
        stat = pipeObj.wait()
        result = pipeObj.fromchild.readlines()  # result has returned string
        Trace.log(e_errors.INFO, "Shelf mOd enrsh return strings=%s stat=%s" % (result, stat))
        if stat == 0:
            retval = result[len(result)-1][0]
            if retval != '0':
                fnstatus = 'ERRReqCmd'
                fnstatusR = self.deallocateOCSdrive(drive)
                return fnstatus
        else :
            fnstatus = 'ERRReqRsh'
            fnstatusR = self.deallocateOCSdrive(drive)
            return fnstatus
        return fnstatus

    def deallocateOCSdrive(self, drive):
        "deallocate an OCS managed drive"
        fnstatus = 'OK'
        if "AllTheTapeDrives" == drive :
            command = self.cmdPrefix + "ocs_deallocate -a " + \
                      " ; echo $?" + self.cmdSuffix
        else :
            command = self.cmdPrefix + "ocs_deallocate -t " + drive + \
                      " ; echo $?" + self.cmdSuffix
        Trace.log(e_errors.INFO, "Shelf dOd Cmd=%s" % (command,) )
        pipeObj = popen2.Popen3(command, 0, 0)
        if pipeObj is None:
            fnstatus = 'ERRDeaPip'
            return fnstatus
        stat = pipeObj.wait()
        result = pipeObj.fromchild.readlines()  # result has returned string
        Trace.log(e_errors.INFO, "Shelf dOd enrsh return strings=%s stat=%s" % (result, stat))
        if stat == 0:
            retval = result[len(result)-1][0]
            if retval != '0': #check if drive already deallocated (not an error)
                retstring = result[0]
                pos=string.find(retstring,"drive is already deallocated")
                if pos == -1 :  # really an error
                    fnstatus = 'ERRDeaCmd'
                    return fnstatus
        else :
            fnstatus = 'ERRDeaRsh'
            return fnstatus
        return fnstatus

    def unmountOCSdrive(self, drive):
        "dismount an OCS managed tape"
        fnstatus = 'OK'
        command = self.cmdPrefix + "ocs_dismount -t " + drive + \
                  " ; echo $?" + self.cmdSuffix
        Trace.log(e_errors.INFO, "Shelf uOd Cmd=%s" % (command,) )
        pipeObj = popen2.Popen3(command, 0, 0)
        if pipeObj is None:
            fnstat = 'ERRDsmPip'
            return fnstatus
        stat = pipeObj.wait()
        result = pipeObj.fromchild.readlines()  # result has returned string
        Trace.log(e_errors.INFO, "Shelf uOd enrsh return strings=%s stat=%s" % (result, stat))
        if stat == 0:
            retval = result[len(result)-1][0]
            if retval != '0':
                fnstatus = 'ERRDsmCmd'
                return fnstatus
        else :
            fnstatus = 'ERRDsmRsh'
            return fnstatus
        return fnstatus

    def load(self, external_label, drive, media_type):
        "load a tape"
        fnstatus = self.allocateOCSdrive(drive)
        if fnstatus == 'OK' :
            fnstatus = self.mountOCSdrive(external_label, drive)
        if fnstatus == 'OK' :
            status = 0
        else :
            status = 1
            Trace.log(e_errors.ERROR, "ERROR:Shelf load exit fnst=%s %s %s" %
                      (status, fnstatus, self.status_message(fnstatus)))
        return self.status_code(fnstatus), status, self.status_message(fnstatus)

    def unload(self, external_label, drive, media_type):
        "unload a tape"
        fnstatusTmp = self.unmountOCSdrive(drive)
        fnstatus = self.deallocateOCSdrive(drive)
        Trace.log(e_errors.INFO, "Shelf unload deallocate exit fnstatus=%s" % (fnstatus,))
        if fnstatusTmp != 'OK' :
            Trace.log(e_errors.ERROR, "ERROR:Shelf unload deall exit fnst= %s %s" %
                      (fnstatus, self.status_message(fnstatus)))
            fnstatus = fnstatusTmp
        if fnstatus == 'OK' :
            status = 0
        else :
            status = 1
            Trace.log(e_errors.ERROR, "ERROR:Shelf unload exit fnst= %s %s" %
                      (fnstatus, self.status_message(fnstatus)))
        return self.status_code(fnstatus), status, self.status_message(fnstatus)

    def getNretry(self):
        numberOfRetries = 1
        return numberOfRetries
""" #End definition of OCS class.

# This method tries to execute function f with arguments a in time t.
# The return values are first an int 0 for completion and -1 for
# failure to complete in the allotted time.  The second return value
# is either a tupple of values which depend on what f returns if f
# completed, or the string 'timeout error' if f didn't return in the
# allotted time.
def return_by(f, a, t):

    q = Queue.Queue()
    e = threading.Event()
    h = threading.Thread(target = execute_and_set, \
                         args   = (f, a, e, q))
    h.start()
    e.wait(t)
    if q.empty():
        return -1, 'timeout error'
    else:
        return 0, q.get()

# This method executes function f with arguments a, puts the result in
# queue q and triggers the Event e
def execute_and_set(f, a, e, q):

    q.put(apply(f, a))
    e.set()
    return

#########################################################################
#
# mtx robot loader server for Overland stackers
#
#########################################################################
class MTX_MediaLoader(MediaLoaderMethods):

    def __init__(self, medch, max_work=1, csc=None):

        MediaLoaderMethods.__init__(self,medch,max_work,csc)
        
        # Mark our cached status info as invalid
        self.status_valid = 0;
        
        # Read the device name to use.
        if self.mc_config.has_key('device_name'):
            self.device_name = self.mc_config['device_name']
        else:
            self.device_name = '/dev/sgb' #best guess
            Trace.log(e_errors.ERROR,
                      'mtx: no device specified.  Guessing /dev/sgb')
            
        # Read the value for the timeout on status commands.
        if self.mc_config.has_key('status_timeout'):
            self.status_timeout = self.mc_config['status_timeout']
        else:
            self.status_timeout = 5 #best guess
            Trace.log(e_errors.ERROR,
                      'mtx no status timeout specified.  Using 5 seconds')

        # Read the value for the timeout on mount commands.
        if self.mc_config.has_key('mount_timeout'):
            self.mount_timeout = self.mc_config['mount_timeout']
        else:
            self.mount_timeout = 120 #best guess
            Trace.log(e_errors.ERROR,
                      'mtx no mount timeout specified.  Using 120 seconds')

        Trace.log(e_errors.INFO, ('MTX_MediaLoader initialized with device: ', \
                  self.device_name, ' status time limit: ', self.status_timeout, \
                  ' mount time limit: ', self.mount_timeout))

        Trace.log(e_errors.INFO, 'MTX_MediaLoader initialized with device: %s status time limit: %s mount time limit: %s '%(self.device_name, self.status_timeout, self.mount_timeout))
	
    #########################################################################
    # These functions are overridden from the generic class.
    #########################################################################
    
    # load volume into the drive;
    def load(self, ticket):
        """
	external_label,    # volume external label
	drive,             # drive id
	media_type):       # media type
	"""
        drive = ticket['drive_id']
	external_label = ticket['vol_ticket']['external_label']
	media_type = ticket['vol_ticket']['media_type']
        Trace.log(e_errors.INFO, 'MTX_MediaLoader: request to load %s of type %s into drive %s'%(external_label, media_type, drive))
        return self.retry_function(self.mtx_mount, external_label,
				   drive, media_type)
    
    # unload volume from the drive
    def unload(self, ticket):
        """
	external_label,  # volume external label
	drive,           # drive id
	media_type):     # media type
	"""
        drive = ticket['drive_id']
	external_label = ticket['vol_ticket']['external_label']
	media_type = ticket['vol_ticket']['media_type']
        Trace.log(e_errors.INFO, 'MTX_MediaLoader: request to unload %s of type %s from drive %s'%(external_label, media_type, drive))
        return self.retry_function(self.mtx_dismount, external_label,
				   drive, media_type)

    #########################################################################
    # These functions are internal functions specific to MTX media changer.
    #########################################################################

    # Find the tape and mount it in the drive.
    def mtx_mount(self,volume, drive, media_type="", view_first=1):
        __pychecker__ = "unusednames=media_type,view_first"
	
        try:
            dr = int(drive)
        except:
            Trace.log(e_errors.ERROR, 'mtx_mount unrecognized drive: %s'%(drive))
            return ('ERROR', e_errors.ERROR, [],'' ,\
                    'mtx_mount unrecognized drive: %s'%(drive))

        s,d = self.locate_volume(volume)

        if -1 == s:
            if -1 == d:
                Trace.log(e_errors.ERROR,
                          ' mtx cant mount tape. Not in library')
                return ('ERROR', e_errors.ERROR, [],'' ,\
                        ' mtx cant mount tape. Not in library')
            else:
                Trace.log(e_errors.ERROR,
                          ' mtx cant mount tape. Already in drive %d'%(d))
                return ('ERROR', e_errors.ERROR, [],'' ,\
                        ' mtx cant mount tape. Already in drive %d'%(d))

        Trace.log(e_errors.INFO, 'found %s in slot %s ...mounting'%(volume, s))
        a, b = return_by(self.load_local, (s, dr), self.mount_timeout)

        self.status_valid = 0;

        if -1 == a:
            Trace.log(e_errors.ERROR, ' mtx mount timeout')
            return ('ERROR', e_errors.ERROR, [],'' ,' mtx mount timeout')
        else:
            return b
    
    # Find a free slot and unmount the tape from the drive.
    def mtx_dismount(self,volume, drive, media_type="", view_first=1):
        __pychecker__ = "unusednames=media_type,view_first"
	    
        try:
            dr = int(drive)
        except:
            Trace.log(e_errors.ERROR, 'mtx_mount unrecognized drive: %s'%(drive))
            return ('ERROR', e_errors.ERROR, [],'' ,\
                    'mtx_mount unrecognized drive: %s'%(drive))

        s,ignore = self.locate_volume('empty')

        if -1 == s:
            Trace.log(e_errors.ERROR, ' mtx unload: No free slots')
            return ('ERROR', e_errors.ERROR, [],'' ,\
                    ' mtx unload: No free slots')

        ignore,d = self.locate_volume(volume)

        if dr != d:
            Trace.log(e_errors.ERROR, ' mtx unload: %s is in %d, not %d'%
                      (volume, d, dr))
            return ('ERROR', e_errors.ERROR, [],'' ,\
                    ' mtx unload: %s is not in %d'%
                    (volume, dr))


        Trace.log(e_errors.INFO, ('found ', volume, ' in drive ', d, \
                  '...dismounting'))
        a,b = return_by(self.unload_local, (s, dr), self.mount_timeout)

        self.status_valid = 0;

        if -1 == a:
            Trace.log(e_errors.ERROR, ' mtx unmount timeout')
            return ('ERROR', e_errors.ERROR, [],'' ,' mtx dismount timeout')
        else:
            return b

    # This method indicates where the tape is located within the
    # library by returning two numbers.  The first number is the slot
    # number containing the tape or negative one if the tape is not in
    # a slot.  The second number is the drive number the tape is in or
    # negative one if the tape is not in a drive.  (slots and drives
    # are both indexted starting at zero.)  If both numbers are
    # negative one then the tape is not in the library.  If both
    # numbers are not negative one then there is either a bug in this
    # function or multiple tapes that have the same label in the
    # library.
    def locate_volume(self, vol):

        Trace.log(e_errors.INFO, ' looking for volume %s'%(vol))
        if 0 == self.status_valid:
            a, b = return_by(self.status_local, (), self.status_timeout)
            if -1 == a:
                Trace.log(e_errors.ERROR, ' mtx status request timeout')
                return -1, -1
            self.status_valid = 1
        found = 0
        idx_drive = 0
        for i in self.drives:
            if vol == i:
                found = 1;
                break
            idx_drive = idx_drive + 1
            
        if 0 == found:
            idx_drive = -1

        found = 0
        idx_slot = 0
        for i in self.slots:
            if vol == i:
                found = 1;
                break
            idx_slot = idx_slot + 1
            
        if 0 == found:
            idx_slot = -1

        return idx_slot, idx_drive
    
    #  This method tries to have device 'device' load the tape in slot
    #  number 'slot' into drive number 'drive' The return value is
    #  anything that MTX printed to stderr.  If mtx hangs, this method
    #  will never return.
    def load_local(self, slot, drive):

        Trace.log(e_errors.INFO, 'Invoking the following command: sudo mtx -f %s load %d %d'%(self.device_name, slot + 1, drive))
        processIO = popen2.popen3('sudo mtx -f %s load %d %d'%(self.device_name,
                                                          slot + 1, drive))
        Trace.log(e_errors.INFO, 'The following command completed: sudo mtx -f %s load %d %d'%(self.device_name, slot + 1, drive))
        line = processIO[2].readline();
        errorString = ''
        while '' != line:
            errorString = errorString + line
            line = processIO[2].readline();
            
        processIO[2].close()
            
        if '' != errorString:
            Trace.log(e_errors.ERROR,
                      ' mtx load returned this message %s'%(errorString))

        if '' == errorString:
            return (e_errors.OK, 0, None, "", "")
        else:
            return ('ERROR', e_errors.ERROR, [], "", errorString)
        
    #  This method tries to have device 'device' unload the tape in
    #  drive number drive back into slot number 'slot'.  The return
    #  value is anything that MTX printed to stderr.  If mtx hangs,
    #  this method will never return.
    def unload_local(self, slot, drive):
        
        Trace.log(e_errors.INFO, 'Invoking the following command: sudo mtx -f %s unload %d %d'%(self.device_name, slot + 1, drive))
        processIO = popen2.popen3('sudo mtx -f %s unload %d %d'%(self.device_name,
                                                            slot + 1, drive))
        Trace.log(e_errors.INFO, 'The following command completed: sudo mtx -f %s unload %d %d'%(self.device_name, slot + 1, drive))
        line = processIO[2].readline();
        errorString = ''
        while '' != line:
            errorString = errorString + line
            line = processIO[2].readline();

        processIO[2].close()

        if '' != errorString:
            Trace.log(e_errors.ERROR,
                      ' mtx unload returned this message %s'%(errorString))

        if '' == errorString:
            return (e_errors.OK, 0, None, "", "")
        else:
            return ('ERROR', e_errors.ERROR, [], "",errorString)

    # This method blocks while it returns the status of the media
    # changer at the specified device.  The first return value is a
    # list of barcodes for the tapes in the drives, the second return
    # value is a list of the barcodes for the tapes in the slots, the
    # third return value are any messages that mtx printed to stderr.
    # If mtx hangs, this method will never return.
    def status_local(self):

        Trace.log(e_errors.INFO, 'Invoking the following command: sudo mtx -f %s status'%(self.device_name))
        processIO = popen2.popen3('sudo mtx -f %s status'%(self.device_name))
        Trace.log(e_errors.INFO, 'The following command completed: sudo mtx -f %s status'%(self.device_name))
        
        self.drives = []
        self.slots  = []

        counter = 1
        line = processIO[0].readline()
        while '' != line:
            line = string.strip(line)
            if string.find(line, 'Data Transfer Element') != -1:
                if string.find(line, 'Empty') > 0:
                    self.drives.append('empty');
                elif string.find(line, 'VolumeTag') != -1:
                    i1 = string.find(line, '=') + 1
                    i2 = len(line)
                    self.drives.append(string.strip(line[i1:i2]))
                else:
                    self.drives.append('unlabelled')
            elif string.find(line, 'Storage Element') != -1:
                if string.find(line, 'Empty') > 0:
                    self.slots.append('empty')
                elif string.find(line, 'VolumeTag') != -1:
                    i1 = string.find(line, '=') + 1
                    i2 = len(line)
                    self.slots.append(string.strip(line[i1:i2]))
                else:
                    self.slots.append('unlabelled')
                
            line = processIO[0].readline()
            counter = counter + 1
            
        processIO[0].close()
                
        line = processIO[2].readline();
        errorString = ''
        while '' != line:
            errorString = errorString + line
            line = processIO[2].readline();
        
        processIO[2].close()

        if '' != errorString:
            Trace.log(e_errors.ERROR,
                  ' mtx status returned this message %s'%(errorString))

        return errorString

#########################################################################
#
# IBM robot media loader
#
#########################################################################
class IBM_3584_MediaLoader(MediaLoaderMethods):

    def __init__(self, medch, max_work=7, csc=None):
        MediaLoaderMethods.__init__(self,medch,max_work,csc)
        self.prepare = self.unload
        self.DEBUG = 0
	#self.driveCleanTime = self.mc_config.get('DriveCleanTime',{'9840':[60,1],'9940':[60,1]})
	self.device = self.mc_config.get('device','Unknown')
	self.rmchost = self.mc_config.get('rmchost', 'Unknown')
        print "IBM 3584 MediaLoader initialized"

    # retry function call
    def retry_function(self,function,*args):
        count = self.getNretry()
        sts=("",0,"")
        # retry every error
        while count > 0 and sts[0] != e_errors.OK:
            try:
                sts=apply(function,args)
                if sts[1] != 0:
                   if self.logdetail:
                      Trace.log(e_errors.ERROR, 'retry_function: function %s  %s  sts[1] %s  sts[2] %s  count %s'%(repr(function),args,sts[1],sts[2],count))
                   if function==self.mount:
                       time.sleep(60)
                       fixsts=apply(self.dismount,args)
                       Trace.log(e_errors.INFO, 'Tried %s %s  status=%s %s  Desperation dismount  status %s %s'%(repr(function),args,sts[1],sts[2],fixsts[1],fixsts[2]))
                   time.sleep(60)
                   count = count - 1
                else:
                    break
            except:
                exc,val,tb = Trace.handle_error()
                return str(exc),0,""
        return sts

    # simple elapsed timer
    def delta_t(self,begin):
            (ut, st,cut, cst,now) = os.times()
            return (now-begin, now)

    # execute a stk cmd_proc command, but don't wait forever for it to complete
    #mostly stolen from Demo/tkinter/guido/ShellWindow.py - spawn function
    def timed_command(self,cmd,min_response_length=0,timeout=60):

        message = ""
        blanks=0
        nread=0

        now=timeofday.tod()
        p2cread, p2cwrite = os.pipe()
        c2pread, c2pwrite = os.pipe()
        command = cmd
        cmd_lookfor = ""

        # can not use dispatching work fork because we are already child.
        # need to kill explictly and children can't kill
        (dum,mark) = self.delta_t(0)
        pid = os.fork()

        if pid == 0:
            # Child
            for i in 0, 1, 2:
                try:
                    os.close(i)
                except os.error:
                    pass
            if os.dup(p2cread) <> 0:
                print 'ERROR: timed_command pc2cread bad read dup'
                Trace.log(e_errors.ERROR, 'timed_command pc2cread bad read dup')
            if os.dup(c2pwrite) <> 1:
                print 'ERROR: timed_command c2pwrite bad write dup'
                Trace.log(e_errors.ERROR, 'timed_command c2pwrite bad write dup')
            if os.dup(c2pwrite) <> 2:
                print 'ERROR: timed_command c2pwrite bad error dup'
                Trace.log(e_errors.ERROR, 'timed_command c2pwrite bad error dup')
            MAXFD = 100 # Max number of file descriptors (os.getdtablesize()???)
            for i in range(3, MAXFD):
                try:
                    os.close(i)
                except:
                    pass
            try:
                #I know this is hard-coded and inflexible. That is what I want so as to
                #prevent any possible security problem.

                os.execv("/bin/bash", ["bash", "-c", command])
            finally:
                exc, msg, tb = sys.exc_info()
                Trace.log(e_errors.ERROR, "timed_command execv failed:  %s %s %s"% (exc, msg, traceback.format_tb(tb)))
                os._exit(1)

        os.close(p2cread)
        os.close(c2pwrite)
        os.close(p2cwrite)


        #wait for child to complete, or kill it
        start = time.time()
        if self.DEBUG:
            print timeofday.tod(),cmd
            Trace.trace(e_errors.INFO,"%s" %(cmd,))
        active=0
        (p,r) = (0,0)
        try:
            while active<timeout:
                p,r = os.waitpid(pid,os.WNOHANG)
                if p!=0:
                    break
	        #We need to start reading this now for really long responses.
		# Otherwise, the buffer fills up with the child waiting
		# for the parent to read something from the full buffer.
		# And the parent waits for the child to finish.
	        msg=os.read(c2pread,2000)
		if msg:
		    if self.DEBUG:
		        print msg,
		    message = message+msg
		    #Need to reset the timeout period.
		    start = time.time()
		    active = 0
		else:
		    if msg == '':
		        blanks = blanks+1
		    active = time.time() - start
		    time.sleep(1)
            else:
                msg="killing %d => %s" % (pid,cmd)
                print timeofday.tod(),msg
                Trace.trace(e_errors.INFO,msg)
                os.kill(pid,signal.SIGTERM)
                time.sleep(1)
                p,r = os.waitpid(pid,os.WNOHANG)
                if p==0:
                    msg="kill -9ing %d => %s" % (pid,cmd)
                    print timeofday.tod(),msg
                    Trace.trace(e_errors.INFO,msg)
                    os.kill(pid,signal.SIGKILL)
                    time.sleep(2)
                    p,r = os.waitpid(pid,os.WNOHANG)
        except:
            exc, msg, tb = sys.exc_info()
            Trace.log(e_errors.ERROR, "timed_command wait for child failed:  %s %s %s"% (exc, msg, traceback.format_tb(tb)))
	    os.close(c2pread)
            return -1,[], self.delta_t(mark)[0]

        if p==0:
	    os.close(c2pread)
            return -2,[], self.delta_t(mark)[0]

        # now read response from the pipe (Some of
	if string.find(cmd,'mount') != -1:  # this is a mount or a dismount command
	    maxread=100  # quick response on queries
	else:
	    maxread=10000 # slow respone on mount/dismounts

	nlines=0
	ntries=0
	jonflag=0
        # async message start with a date:  2001-12-20 07:33:17     0    Drive   0, 0,10,12: Cleaned.
        # unfortunately, not just async messages start with a date.  Alas, each message has to be parsed.
        async_date=re.compile("20\d\d-\d\d-\d\d \d\d:\d\d:\d\d")  
        while nlines<4 and ntries<3:
	  ntries=ntries+1
          #while blanks<2 and nread<maxread:
	  while nread<maxread:
            msg=os.read(c2pread,2000)
	    message = message + msg
	    if msg:
	        if self.DEBUG:
		    print msg,
            nread = nread+1
            if msg == '':
                blanks = blanks+1
#	    if self.DEBUG:
#	        nl=0
#		ml=string.split(msg,'\012')
#		for l in ml:
#                   nl=nl+1
#		   print "nread=",nread, "line=",nl, l
          response = []
          resp = string.split(message,'\012')
	  nl=0
	  for l in resp:
            if async_date.match(l):
              if string.find(l,'Place cartridges in CAP') != -1 or \
                 string.find(l,'Remove cartridges from CAP') != -1 or \
                 string.find(l,'Library error, LSM offline') != -1 or \
                 string.find(l,'Library error, Transport failure') != -1 or \
                 string.find(l,'Library error, LMU failure') != -1 or \
                 string.find(l,'LMU Recovery Complete') != -1 or \
                 string.find(l,': Offline.') != -1 or \
                 string.find(l,': Online.') != -1 or \
                 string.find(l,': Enter operation ') != -1 or \
                 string.find(l,'Clean drive') != -1 or \
                 string.find(l,'Cleaned') != -1:
                if self.DEBUG:
                  print "DELETED:", l
                jonflag=1
                continue
	    if self.DEBUG:
              print    "response line =",nl, l
            response.append(l)
	    nl=nl+1
          nlines=len(response)

	  nl=0
	  if jonflag and self.DEBUG:
	       for l in response:
		  print    "parsed lines =",nl, l
		  nl=nl+1

	os.close(c2pread)
        size = len(response)
        #if size <= 19:
        #    return -3,[], self.delta_t(mark)[0]
        status = 0
        for look in range(0,size): # 1st part of response is STK copyright information
            if string.find(response[look], cmd_lookfor, 0) == 0:
                break
        if look == size:
            status = -4
            look = 0
        else:
            if len(response[look:]) < min_response_length:
                status = -5
        if self.DEBUG:
            rightnow = timeofday.tod() # the times on fntt are not necessarily right, allows us to correlate log time
            rsp = [now,response[look:],rightnow]
            pprint.pprint(rsp)

        return status,response[look:], self.delta_t(mark)[0]

    #########################################################################
    # These functions are overridden from the generic class.
    #########################################################################

    # load volume into the drive;
    def load(self, ticket):
        drive = ticket['drive_id']
	external_label = ticket['vol_ticket']['external_label']
	media_type = ticket['vol_ticket']['media_type']
        return self.retry_function(self.mount, external_label,
				   drive, media_type)

    # unload volume from the drive
    def unload(self, ticket):
        drive = ticket['drive_id']
	external_label = ticket['vol_ticket']['external_label']
	media_type = ticket['vol_ticket']['media_type']
        return self.retry_function(self.dismount, external_label,
				   drive, media_type)

    #FIXME - what the devil is this?
    def getVolState(self, ticket):
        external_label = ticket['external_label']
        media_type = ticket['media_type']
        rt = self.retry_function(self.query,external_label,media_type)
        Trace.trace(11, "getVolState returned %s"%(rt,))
        if rt[3] == '\000':
            state=''
        else :
            state = rt[3]
            if not state and rt[2]:  # volumes not in the robot
                state = rt[2]
	#Return the correct media type.
	try:
	    ticket['media_type'] = rt[2].split()[-1]
	except (IndexError, ValueError, TypeError, AttributeError):
	    pass

        return (rt[0], rt[1], rt[2], state)

    def getDriveState(self, ticket):
	drive = ticket['drive']
	rt = self.retry_function(self.query_drive, drive)
	#Update the ticket with additional information.
        info = rt[2].split()
	drive_info = {}
	drive_info['state'] = info[0].strip()
	drive_info['status'] = "N/A"
	drive_info['volume'] = info[3].strip()
	drive_info['type'] = "LTO3"
	ticket['drive_info'] = drive_info
	return rt[0], rt[1], rt[3], rt[4]

    def cleanCycle(self, inTicket):
        __pychecker__ = "no-argsused" # When fixed remove this pychecker line.
        return (e_errors.NOT_SUPPORTED, 0,
		"IBM media changer does not suppor this operation.")
        # It is possible that the following code does work.  However, the
	# error messages should be changed from STK to IBM if that is
	# the case.
        """
	__pychecker__ = "unusednames=i"
	
        #do drive cleaning cycle
        Trace.log(e_errors.INFO, 'mc:ticket='+repr(inTicket))
        classTicket = { 'mcSelf' : self }
        try:
            drive = inTicket['moverConfig']['mc_device']
        except KeyError:
            Trace.log(e_errors.ERROR, 'mc:no device field found in ticket.')
            status = 37
            return e_errors.DOESNOTEXIST, status, "no device field found in ticket"

        driveType = drive[:2]  # ... need device type, not actual device
        try:
            if self.driveCleanTime:
                cleanTime = self.driveCleanTime[driveType][0]  # clean time in seconds
                driveCleanCycles = self.driveCleanTime[driveType][1]  # number of cleaning cycles
            else:
                cleanTime = 60
                driveCleanCycles = 1
        except KeyError:
            cleanTime = 60
            driveCleanCycles = 1

        vcc = volume_clerk_client.VolumeClerkClient(self.csc)
        min_remaining_bytes = 1
        vol_veto_list = []
        first_found = 0
        libraryManagers = inTicket['moverConfig']['library']
        if type(libraryManagers) == types.StringType:
            lm = libraryManagers
            library = string.split(libraryManagers,".")[0]
        elif type(libraryManagers) == types.ListType:
            lm = libraryManagers[0]
            library = string.split(libraryManagers[0],".")[0]
        else:
            Trace.log(e_errors.ERROR, 'mc: library_manager field not found in ticket.')
            status = 37
            return e_errors.DOESNOTEXIST, status, "no library_manager field found in ticket"
        lm_info = self.csc.get(lm)
        if not lm_info.has_key('CleanTapeVolumeFamily'):
            Trace.log(e_errors.ERROR, 'mc: no CleanTapeVolumeFamily field found in ticket.')
            status = 37
            return e_errors.DOESNOTEXIST, status, "no CleanTapeVolumeFamily field found in ticket"
        cleanTapeVolumeFamily = lm_info['CleanTapeVolumeFamily']
        v = vcc.next_write_volume(library,
                                  min_remaining_bytes, cleanTapeVolumeFamily,
                                  vol_veto_list, first_found, exact_match=1)  # get which volume to use
        if v["status"][0] != e_errors.OK:
            Trace.log(e_errors.ERROR,"error getting cleaning volume:%s %s"%
                      (v["status"][0],v["status"][1]))
            status = 37
            return v["status"][0], 0, v["status"][1]

        for i in range(driveCleanCycles):
            Trace.log(e_errors.INFO, "STK clean drive %s, vol. %s"%(drive,v['external_label']))
            #rt = self.load(v['external_label'], drive, v['media_type'])
	    rt = self.retry_function(self.mount, v['external_label'],
	                             drive, v['media_type'])
            status = rt[0]
            if status != e_errors.OK:      # mount returned error
                return status, 0, None

            time.sleep(cleanTime)  # wait cleanTime seconds
            #rt = self.unload(v['external_label'], drive, v['media_type'])
	    rt = self.retry_function(self.dismount, v['external_label'],
	                             drive, v['media_type'])
            status = rt[0]
	    if status != e_errors.OK:
                return status, 0, None
            Trace.log(e_errors.INFO,"STK Clean returned %s"%(rt,))

        retTicket = vcc.get_remaining_bytes(v['external_label'])
        remaining_bytes = retTicket['remaining_bytes']-1
        vcc.set_remaining_bytes(v['external_label'],remaining_bytes,'\0', None)
        return (e_errors.OK, 0, None)
	"""

    def query_robot(self, ticket):
        __pychecker__ = "no-argsused" # When fixed remove this pychecker line.
        return (e_errors.NOT_SUPPORTED, 0,
		"IBM media changer does not suppor this operation.")

    def listDrives(self, ticket):
        # build the command, and what to look for in the response
        command = "/usr/bin/smc -h %s -l %s -q D" % (self.rmchost, self.device,)
        #answer_lookfor = ""

        # execute the command and read the response
        # FIXME - what if this hangs?
        # efb (dec 22, 2005) - up timeout from 10 to 60 as the queries are hanging
        #status,response, delta = self.timed_command(command,4,10)
        status,response, delta = self.timed_command(command,2,60)
        if status != 0:
            E=4
            msg = "QUERY_DRIVE %i: %s => %i,%s" % (E,command,status,response)
            Trace.log(e_errors.ERROR, msg)
            return ("ERROR", E, response, "", msg)

        drive_list = []
        for line in response:
            if len(line) > 1:
               rc = line.split()
  
               name = rc[0]
               state = "N/A"
               status = rc[2]
               if status.find("loaded") != -1:
   	          volume = rc[3]
               else:
                  volume = ""
	       drive_type = "LTO3"
	    
	       drive_list.append({"name" : name,
	   		          "state" : state,
			          "status" : status,
			          "volume" : volume,
			          "type" : drive_type,
			          })

	ticket['drive_list'] = drive_list
	return (e_errors.OK, 0, None, "", "")

    def listVolumes(self, ticket):
        #When implementing this function, remember to set ticket['no_reply']
	# to 1 to prevent WorkDone() from sending the reponse again.
        __pychecker__ = "no-argsused" # When fixed remove this pychecker line.
        return (e_errors.NOT_SUPPORTED, 0,
		"IBM media changer does not support this operation.")

    def list_volumes2(self, ticket):
        ticket['work'] = "list_volumes" #Use old method for IBM.
	ticket['function'] = "listVolume"
        return self.listVolumes(ticket)
	
    def listClean(self, ticket):
        #When implementing this function, remember to set ticket['no_reply']
	# to 1 to prevent WorkDone() from sending the reponse again.
        __pychecker__ = "no-argsused" # When fixed remove this pychecker line.
        return (e_errors.NOT_SUPPORTED, 0,
		"IBM media changer does not support this operation.")

    def listSlots(self, ticket):
        __pychecker__ = "no-argsused" # When fixed remove this pychecker line.
        return (e_errors.NOT_SUPPORTED, 0,
		"IBM media changer does not support this operation.")

    #########################################################################
    # These functions are internal functions specific to IBM media changer.
    #########################################################################

    def query(self, volume, media_type=""):
        __pychecker__ = "unusednames=media_type"

        # build the command, and what to look for in the response
        #command = "query vol %s" % (volume,)
        #answer_lookfor = "%s " % (volume,)
	command = "/usr/bin/smc -h %s -l %s -q V -V '%s'" % (self.rmchost,self.device,volume,)
	answer_lookfor = "%s" % (volume,)

        # execute the command and read the response
        # efb (dec 22, 2005) - up timeout from 10 to 60 as the queries are hanging
        #status,response, delta = self.timed_command(command,4,10)
        status,response, delta = self.timed_command(command,1,60)
        if status != 0:
            E=1
            msg = "QUERY %i: %s => %i,%s" % (E,command,status,response)
            Trace.log(e_errors.ERROR, msg)
            return ("ERROR", E, response, '', msg)

        # got response, parse it and put it into the standard form
        answer = string.strip(response[0])
        if string.find(answer, answer_lookfor,0) != 0:
            E=2
            msg = "QUERY %i: %s => %i,%s" % (E,command,status,response)
            Trace.log(e_errors.ERROR, msg)
            return ("ERROR", E, response, '', msg)
        elif string.find(answer,'slot') != -1:
            msg = "%s => %i,%s" % (command,status,answer)
            Trace.log(e_errors.INFO, msg)
            return (e_errors.OK,0,answer, 'O', msg) # occupied
        elif string.find(answer,'drive') != -1:
            msg = "%s => %i,%s" % (command,status,answer)
            Trace.log(e_errors.INFO, msg)
            return (e_errors.OK,0,answer, 'M', msg) # mounted
        else:
            E=3
            msg = "QUERY %i: %s => %i,%s" % (E,command,status,response)
            Trace.log(e_errors.ERROR, msg)
            return ("ERROR", E, answer, '', msg)

    def query_drive(self,drive):

        # build the command, and what to look for in the response
        #command = "query drive %s" % (drive,)
        #answer_lookfor = "%s " % (drive,)
	command = "/usr/bin/smc -h %s -l %s -q D -D %s" % (self.rmchost, self.device, drive,)
        answer_lookfor = "%s" % (drive,)

        # execute the command and read the response
        # FIXME - what if this hangs?
        # efb (dec 22, 2005) - up timeout from 10 to 60 as the queries are hanging
        #status,response, delta = self.timed_command(command,4,10)
        status,response, delta = self.timed_command(command,1,60)
        if status != 0:
            E=4
            msg = "QUERY_DRIVE %i: %s => %i,%s" % (E,command,status,response)
            Trace.log(e_errors.ERROR, msg)
            return ("ERROR", E, response, '', msg)


        # got response, parse it and put it into the standard form
        answer = string.strip(response[0])
        answer = string.replace(answer,', ',',') # easier to part drive id
        if string.find(answer, answer_lookfor,0) != 0:
            E=5
            msg = "QUERY_DRIVE %i: %s => %i,%s" % (E,command,status,answer)
            Trace.log(e_errors.ERROR, msg)
            return ("ERROR", E, answer, '', msg)
#        elif string.find(answer,' online ') == -1:
#            E=6
#            msg = "QUERY_DRIVE %i: %s => %i,%s" % (E,command,status,answer)
#            Trace.log(e_errors.ERROR, msg)
#            return ("ERROR", E, answer, '', msg)
        elif string.find(answer,'free') != -1:
            msg = "%s => %i,%s" % (command,status,answer)
            Trace.log(e_errors.INFO, msg)
            return (e_errors.OK,0,answer, '', msg) # empty
        elif string.find(answer,'loaded') != -1:
            loc = string.find(answer,'loaded')
            volume = string.split(answer[loc+7:])[0]
            msg = "%s => %i,%s" % (command,status,answer)
            Trace.log(e_errors.INFO, msg)
            return (e_errors.OK,0,answer, volume, msg) # mounted 
        else:
            E=7
            msg = "QUERY_DRIVE %i: %s => %i,%s" % (E,command,status,answer)
            Trace.log(e_errors.ERROR, msg)
            return ("ERROR", E, answer, '', msg)

    def mount(self,volume, drive, media_type="",view_first=1):

        # build the command, and what to look for in the response
	# smc command is mute on success, and only says something on failure
        command = "/usr/bin/smc -h %s -l %s -m -D %s -V %s" % \
		  (self.rmchost, self.device, drive, volume)

        # check if tape is in the storage location or somewhere else
        if view_first:
            status,stat,response,attrib,com_sent = self.query(volume, media_type)

            if stat!=0:
                E=e_errors.MC_FAILCHKVOL
                msg = "MOUNT %i: %s => %i,%s" % (E,command,stat,response)
                Trace.log(e_errors.ERROR, msg)
                return ("ERROR", E, response, "", msg)
            if attrib != "O": # look for tape in tower (occupied="O")
                E=e_errors.MC_VOLNOTHOME
                msg = "MOUNT %i: Tape is not in home position. %s => %s,%s" % (E,command,status,response)
                Trace.log(e_errors.ERROR, msg)
                return ("ERROR", E, response, "", msg)

        # check if any tape is mounted in this drive
            status,stat,response,volser,com_sent = self.query_drive(drive)
            if stat!=0:
                E=e_errors.MC_FAILCHKDRV
                msg = "MOUNT %i: %s => %i,%s" % (E,command,stat,response)
                Trace.log(e_errors.ERROR, msg)
                return ("ERROR", E, response, "", msg)
            if volser != "": # look for any tape mounted in this drive
                E=e_errors.MC_DRVNOTEMPTY
                msg = "MOUNT %i: Drive %s is not empty =>. %s => %s,%s" % (E,drive,command,status,response)
                Trace.log(e_errors.ERROR, msg)
                return ("ERROR", E, response, "", msg)

        # execute the command and read the response
        status,response, delta = self.timed_command(command,1,60*10)
        if status != 0:
            E=12
            msg = "MOUNT %i: %s => %i,%s" % (E,command,status,response)
            Trace.log(e_errors.ERROR, msg)
            return ("ERROR", E, response, "", msg)

        # got response, parse it and put it into the standard form
        answer = string.strip(response[0])
        if string.find(answer, " " ,0) != -1:
            E=13
            msg = "MOUNT %i: %s => %i,%s" % (E,command,status,answer)
            Trace.log(e_errors.ERROR, msg)
            return ("ERROR", E, response, "", msg)
        msg = "%s => %i,%s" % (command,status,answer)
        Trace.log(e_errors.INFO, msg)
        return (e_errors.OK, 0, msg, "", "")


    def dismount(self,volume, drive, media_type="", view_first=1):
        __pychecker__ = "unusednames=media_type"

        # build the command, and what to look for in the response
        command = "/usr/bin/smc -h %s -l %s -d -D %s -V %s" % (self.rmchost, self.device, drive, volume)

        #answer_lookfor = "Dismount: Forced dismount of "

        # check if any tape is mounted in this drive
        if view_first:
            status,stat,response,volser,com_sent = self.query_drive(drive)
            if stat!=0:
                E=e_errors.MC_FAILCHKDRV
                msg = "DISMOUNT %i: %s => %i,%s" % (E,command,stat,response)
                Trace.log(e_errors.ERROR, msg)
                return ("ERROR", E, response, "", msg)

            if volser == "": # look for any tape mounted in this drive
                if volume!="Unknown":
                    #FIXME - this should be a real error. mover needs to know which tape it has.
                    E=14
                    msg = "Dismount %i ignored: Drive %s is empty. Thought %s was there =>. %s => %s,%s" % (E,drive,volume,command,status,response)
                    Trace.log(e_errors.INFO, msg)
                    return (e_errors.OK, 0, response, "", msg)
                else: #don't know the volume on startup
                    E=15
                    msg = "Dismount %i ignored: Drive %s is empty. Thought %s was there =>. %s => %s,%s" % (E,drive,volume,command,status,response)
                    Trace.log(e_errors.INFO, msg)
                    return (e_errors.OK, 0, response, "", msg)

        # execute the command and read the response
        status,response,delta = self.timed_command(command,1,60*10)
        if status != 0:
            E=16
            msg = "DISMOUNT %i: %s => %i,%s" % (E,command,status,response)
            Trace.log(e_errors.ERROR, msg)
            return ("ERROR", E, response, "", msg)

        # got response, parse it and put it into the standard form
        answer = string.strip(response[0])
        if string.find(answer, " ",0) != -1:
            E=17
            msg = "DISMOUNT %i: %s => %i,%s" % (E,command,status,answer)
            Trace.log(e_errors.ERROR, msg)
            return ("ERROR", E, response, "", msg)
        msg = "%s => %i,%s" % (command,status,answer)
        Trace.log(e_errors.INFO, msg)
        return (e_errors.OK, 0, msg, "", "")

#########################################################################
# The command line interface class.
#########################################################################
class MediaLoaderInterface(generic_server.GenericServerInterface):

    def __init__(self):
        # fill in the defaults for possible options
        self.max_work=7
        generic_server.GenericServerInterface.__init__(self)

    media_options = {
	    option.LOG:{option.HELP_STRING:"",
			option.VALUE_USAGE:option.REQUIRED,
			option.VALUE_TYPE:option.STRING,
			option.USER_LEVEL:option.ADMIN
			},
	    option.MAX_WORK:{option.HELP_STRING:"",
			     option.VALUE_USAGE:option.REQUIRED,
			     option.VALUE_TYPE:option.INTEGER,
			     option.USER_LEVEL:option.ADMIN
			     },
	    }

    def valid_dictionaries(self):
	    return (self.media_options,) + \
		 generic_server.GenericServerInterface.valid_dictionaries(self)

    # parse the options like normal but make sure we have a media changer
    def parse_options(self):
        option.Interface.parse_options(self)
        # bomb out if we don't have a media_changer
        if len(self.args) < 1 :
            self.missing_parameter(self.parameters())
            self.print_help()
            sys.exit(1)
        else:
            self.name = self.args[0]


if __name__ == "__main__" :
    Trace.init("MEDCHANGER")
    Trace.trace(6, "media changer called with args: %s"%(sys.argv,) )

    # get an interface
    intf = MediaLoaderInterface()

    csc  = configuration_client.ConfigurationClient((intf.config_host,
                                                     intf.config_port) )
    keys = csc.get(intf.name)
    try:
        mc_type = keys['type']
    except:
        exc,msg,tb=sys.exc_info()
        Trace.log(e_errors.ERROR, "MC Error %s %s"%(exc,msg))
        sys.exit(1)
    if keys.has_key('max_work'):
       intf.max_work = int(keys['max_work']) 

    import __main__
    constructor=getattr(__main__, mc_type)
    mc = constructor(intf.name, intf.max_work, (intf.config_host, intf.config_port))

    mc.handle_generic_commands(intf)

    while 1:
        try:
            Trace.log(e_errors.INFO, "Media Changer %s (re) starting"%(intf.name,))
            mc.serve_forever()
        except SystemExit, exit_code:
            sys.exit(exit_code)
        except:
            mc.serve_forever_error("media changer")
            continue
    Trace.log(e_errors.ERROR,"Media Changer finished (impossible)")
