#!/usr/bin/env python

###############################################################################
#
# $Id$
#
###############################################################################

# Alternate implementation of Trace, which does not use shared memory,
# semaphores, circular queues, or sys.setprofile.  Less powerful but more
# foolproof.

#Implements the functions:
# trace, init, on,  mode, log, alarm,
# set_alarm_func, set_log_func

# system imports
import sys				
import traceback
import os				
import pwd				
import time
#import socket
import types
import threading

# enstore modules
#import enstore_constants
import event_relay_messages
import event_relay_client
import e_errors

if __name__== '__main__':
    try:
        sys.exit.stderr("No unit test, sorry\n")
        sys.stderr.flush()
    except IOError:
        pass
    sys.exit(-1)

# message types.  a message type will be appended to every message so that
# identifying which message is which will be easier.  messages logged without
# a message type will have MSG_DEFAULT appended.
MSG_TYPE = "MSG_TYPE="
MSG_DEFAULT = ""
MSG_ALARM = "%sALARM "%(MSG_TYPE,)
MSG_ENCP_XFER = "%sENCP_XFER "%(MSG_TYPE,)
MSG_MC_LOAD_REQ = "%sMC_LOAD_REQ "%(MSG_TYPE,)
MSG_MC_LOAD_DONE = "%sMC_LOAD_DONE "%(MSG_TYPE,)
MSG_ADD_TO_LMQ = "%sADD_TO_LMQ "%(MSG_TYPE,)
MSG_EVENT_RELAY = "%sEVENT_RELAY "%(MSG_TYPE,)

logname = ""
alarm_func = None
log_func = None

print_levels = {}
log_levels = {}
alarm_levels = {}
message_levels = {}

thread_name = None

# stuff added by efb for new event_relay_client
erc = None

def notify(msg):
    global erc
    if not erc:
	erc = event_relay_client.EventRelayClient()
    if type(msg) == types.StringType:
	# we must convert the message into a message instance
	msg = event_relay_messages.decode(msg)
    erc.send(msg)

# end of stuff added by efb

def trunc(x):
    if type(x) != type(""):
        x = str(x)
    if len(x)>=4096:
        x=x[:4080] + "(trunc. %s)"%(len(x),)
    return x

def do_print(levels):
    if type(levels) != type([]):
        levels = [levels]
    for level in levels:
        print_levels[level]=1

def dont_print(levels):
    if type(levels) != type([]):
        levels = [levels]
    for level in levels:
        if print_levels.has_key(level):
            del print_levels[level]

def do_log(levels):
    if type(levels) != type([]):
        levels = [levels]
    for level in levels:
        log_levels[level]=1

def dont_log(levels):
    if type(levels) != type([]):
        levels = [levels]
    for level in levels:
        if level<5:
            pass
        if log_levels.has_key(level):
            del log_levels[level]

def do_alarm(levels):
    if type(levels) != type([]):
        levels = [levels]
    for level in levels:
        alarm_levels[level]=1
    
def dont_alarm(levels):
    if type(levels) != type([]):
        levels = [levels]
    for level in levels:
        if level==0:
            #raise e_errors.NOT_ALWD_EXCEPTION
            raise ValueError("alarm level 0 can not be turned off")
        if alarm_levels.has_key(level):
            del alarm_levels[level]

def do_message(levels):
    if type(levels) != type([]):
        levels = [levels]
    for level in levels:
        message_levels[level]=1
    
def dont_message(levels):
    if type(levels) != type([]):
        levels = [levels]
    for level in levels:
        if level==0:
            #raise e_errors.NOT_ALWD_EXCEPTION
            raise ValueError("message level 0 can not be turned off")
        if message_levels.has_key(level):
            del message_levels[level]

def init(name, include_thread_name=''):
    global logname,thread_name 
    logname=name
    thread_name = include_thread_name

def log(severity, msg, msg_type=MSG_DEFAULT, doprint=1):
    global logname, thread_name
    msg = trunc(msg)
    if  log_func:
        try:
	    # build up message
            if  msg_type != MSG_DEFAULT:
                new_msg = "%s %s" % (msg_type, msg)
            else:
                new_msg = msg
	    # check for no logname
	    if logname == "":
		logname = "UNKNOWN"
            if thread_name:
                thread = threading.currentThread()
                if thread:
                    th_name = thread.getName()
                else:
                    th_name = ''
            else:
                th_name = ''
                    
            if th_name:
               new_msg = "%s Thread %s"%(new_msg, th_name) 
            log_func(time.time(), os.getpid(), logname, (severity, new_msg))
        except (KeyboardInterrupt, SystemExit):
            raise sys.exc_info()[0], sys.exc_info()[1], sys.exc_info()[2]
        except:
            exc, detail = sys.exc_info()[:2]
            try:
                sys.stderr.write("Failure writing message to log %s %s\n" %
                                 (msg, detail))
                sys.stderr.flush()
            except IOError:
                pass
        
    if doprint and print_levels.has_key(severity):
        try:
            print msg
            sys.stdout.flush()
        except (KeyboardInterrupt, SystemExit):
            raise sys.exc_info()[0], sys.exc_info()[1], sys.exc_info()[2]
        except:
            pass
        
def alarm(severity, root_error, rest={},
          condition=None, remedy_type=None):
    #log(severity, root_error, MSG_ALARM)
    if alarm_func:
        alarm_func(time.time(), os.getpid(), logname, root_error, severity,
		   condition, remedy_type, rest)
    if print_levels.has_key(severity):
        try:
            print root_error
            sys.stdout.flush()
        except:
            pass

def trace(severity, msg):
    global thread_name
    ## There is no need to waste time on creating a message, if it will not
    ## be sent.  Truncate all messages sent over the network, but not the
    ## messages to be printed to standard out.
    if (log_levels.has_key(severity) or
        alarm_levels.has_key(severity)):
        msg_truncated = trunc(msg)
    else:
        if not print_levels.has_key(severity):
            return
    if print_levels.has_key(severity):
        try:
            t=time.time()
            dp=("%3.2f"%(t-int(t),)).split('.')[1]
            a=time.ctime(t).split(" ")
            b="."
            c=b.join((a[4],dp))
            a[4]=c
            b=" "
            tm=b.join(a)
            new_msg = msg
            if thread_name:
                thread = threading.currentThread()
                if thread:
                    th_name = thread.getName()
                else:
                    th_name = ''
            else:
                th_name = ''
                    
            if th_name:
               new_msg = "%s Thread %s"%(new_msg, th_name) 
            
            print severity, tm, new_msg
	    # the following line will output the memory usage of the process
	    #os.system("a=`ps -ef |grep '/inq'|grep -v grep|xargs echo|cut -f2 -d' '`;ps -el|grep $a|grep python")
	    #print "================================="  # a usefull divider
            sys.stdout.flush()
        except (KeyboardInterrupt, SystemExit):
            raise sys.exc_info()[0], sys.exc_info()[1], sys.exc_info()[2]
        except:
            pass
    if log_levels.has_key(severity):
        log(severity, msg_truncated, doprint=0)
    if alarm_levels.has_key(severity):
        alarm(severity, msg_truncated)

def message(severity, msg):
    msg = trunc(msg)
    if message_levels.has_key(severity):
        try:
            print msg
            sys.stdout.flush()
        except (KeyboardInterrupt, SystemExit):
            raise sys.exc_info()[0], sys.exc_info()[1], sys.exc_info()[2]
        except:
            pass

def set_alarm_func(func):
    global alarm_func
    alarm_func=func

def set_log_func(func):
    global log_func
    log_func = func

# defaults (templates) -- called from trace

def default_alarm_func(timestamp, pid, name, root_error, severity,
                       condition, remedy_type, args):
    __pychecker__ = "unusednames=timestamp,pid,name,root_error,severity," \
                    "condition,remedy_type,args"
    print "default_alarm_func:", args
    #lvl = args[0]
    #msg = args[1]
    return None

set_alarm_func(default_alarm_func)

#pid = os.getpid()
try:
    usr = pwd.getpwuid(os.getuid())[0]
except:
    usr = "unknown"

def default_log_func( timestamp, pid, name, args ):
    #Even though this implimentation of log_func() does not use the time
    # parameter, others will.
    __pychecker__ = "unusednames=time"
    
    severity = args[0]
    msg = args[1]
    if severity > e_errors.MISC: severity = e_errors.MISC
    print '%s %.6d %.8s %s %s  %s' % (time.ctime(timestamp), pid,usr,e_errors.sevdict[severity],name,msg)
    return None

set_log_func(default_log_func)

# log traceback info
def handle_error(exc=None, value=None, tb=None, msg_type=MSG_DEFAULT):

    # store traceback info
    locally_obtained = False
    if not exc:
        locally_obtained = True
	exc, value, tb = sys.exc_info()
        
    # log it
    for l in traceback.format_exception( exc, value, tb ):
	log( e_errors.ERROR, l, msg_type, "TRACEBACK")

    if not locally_obtained:
        return exc, value, tb
    else:
        #Avoid a cyclic reference.
        del tb
        return sys.exc_info()


#log the current stack trace
# Normally, severity is e_errors.INFO, e_errors.ERROR, et. al.  Here, we
# jst want it to go to the DEBUGLOG, not the normal log; so we use 99 as
# the default.
def log_stack_trace(severity = 99, msg_type = MSG_DEFAULT):
    # log it
    for l in traceback.format_stack():
	log(severity, l, msg_type, "STACKTRACE")
