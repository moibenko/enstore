#!/usr/bin/env python

###############################################################################
#
# $Id$
#
###############################################################################

#system imports
import os
import sys
import socket
import select
import string
import time
import threading
import errno
import gc, inspect
import types
import pprint
import signal
import resource
import stat
import math


#enstore imports
import enstore_display
import configuration_client
import enstore_functions2
import enstore_erc_functions
import e_errors
import event_relay_messages
import event_relay_client
import Trace
import generic_client
import option
import delete_at_exit
import host_config
import udp_client


#4-30-2002: For reasons unknown to me the order of the imports matters a lot.
# If the wrong order is done, then the dashed lines are not drawn.
#3-5-2003: Update to previous comment.  Tkinter must be imported after
# importing enstore_display.  I still don't know why this is.
#11-1-2004: Update to previous comment.  The reason enstore_display must
# be imported first is that the tkinter environmental variables are set
# at the top of the file.
import Tkinter

#########################################################################
# Globals
#########################################################################

TEN_MINUTES=600   #600seconds = 10minutes
DEFAULT_BG_COLOR = '#add8e6'   #light blue

#When entv reads from a command file use these as defaults.
DEFAULT_SYSTEM_NAME = "Enstore"
DEFAULT_GEOMETRY = "1200x1600+0+0"
DEFAULT_ANIMATE = 1

#Constants for select looping.
SELECT_TIMEOUT = 5  #In seconds.
MAX_COUNT = int(30.0 / SELECT_TIMEOUT)

#status_threads = None
messages_threads = []

#Should we need to stop (ie. cntl-C) this is the global flag.
stop_now = 0

#For cleanup_objects() to report problems.
old_list = []
old_len  = 0

#For callbacks called from the master window.  This is the list of canvases.
displays = []
#For callbacks called from the master window.  This is the global name of
# the master window frame.
master_windowframe = None

#Trace.message level for generating a messages file for replaying later.
MESSAGES_LEVEL = enstore_display.MESSAGES_LEVEL
#Trace.message level for fixing lock deadlocks.
LOCK_LEVEL = enstore_display.LOCK_LEVEL 

#########################################################################
# common support functions
#########################################################################

def entv_client_version():
    ##this gets changed automatically in {enstore,encp}Cut
    ##You can edit it manually, but do not change the syntax
    version_string = "v0_0  CVS $Revision$ "
    entv_file = globals().get('__file__', "")
    if entv_file: version_string = version_string + entv_file
    return version_string

#Get the ConfigurationClient object for the default enstore system.
get_csc = enstore_display.get_csc

#Re-exec() entv.  It is hosed.
def restart_entv():
    Trace.trace(0, "Starting new entv process.")
    #import traceback
    #traceback.print_stack()
    os.execv(sys.argv[0], sys.argv)

def to_restart_entv_alarm_signal_handler(sig, frame):
    __pychecker__ = "unusednames=frame"

    if sig != signal.SIGALRM:
        return

    for display in displays:
        time_passed = time.time() - display.last_message_processed
        if time_passed > TEN_MINUTES:
            message = "Seconds passed since last message: %s\n" \
                      "Restarting entv." % (time_passed,)
            Trace.trace(0, message, out_fp=sys.stderr)
            restart_entv()
            
    signal.alarm(TEN_MINUTES)

def alarm_signal_handler(sig, frame):
    __pychecker__ = "unusednames=frame"

    if sig != signal.SIGALRM:
        return

    for display in displays:
        time_passed = time.time() - display.last_message_processed
        if time_passed > TEN_MINUTES:
            try:
                sys.stderr.write("Seconds passed since last message: %s\n" %
                                 (time_passed),)
                sys.stderr.flush()
            except IOError:
                pass
            display.reinitialize()
            
    signal.alarm(TEN_MINUTES)

def open_files(message):
    print message,
    os.system("ls -l /proc/`(EPS | grep \"entv\" | head -n 1 | cut -c8-15 | tr -d ' ')`/fd | wc -l")

def endswith(s1,s2):
    return s1[-len(s2):] == s2

def print_object(item):
    if type(item) in [types.FrameType]:
        print type(item), str(item)[:60], item.f_code
    else:
        print type(item), str(item)[:60]

    i = 1
    for lsk in gc.get_referrers(item):
        if lsk == inspect.currentframe():
            continue

        if type(lsk) in [types.FrameType]:
            print "  %d: %s %s" % (i,
                                 str(pprint.pformat(lsk))[:100],
                                 lsk.f_code)
        else:
            print "  %d: %s" % (i, str(pprint.pformat(lsk))[:100])
        i = i + 1
    print

def cleanup_objects():
    #Force garbage collection while the display is off while awaiting
    # initialization.
    gc.collect()
    del gc.garbage[:]
    gc.collect()
    uncollectable_count = len(gc.garbage)
    del gc.garbage[:]

    #First report what the garbage collection algorithm says...
    if uncollectable_count > 0:
        Trace.trace(10, "UNCOLLECTABLE COUNT: %s" % uncollectable_count)

    entv_used_memory = memory_in_use()
    physical_memory = total_memory()

    if entv_used_memory == None or physical_memory == None or \
           entv_used_memory > physical_memory:
        #Something is wrong if we get here.
        return None
        
    percent = (entv_used_memory / float(physical_memory)) * 100
    if percent > 50:
        #If entv is consuming 50% or more of the memory resources,
        # return that we need to start a new entv process.
        Trace.trace(0, "entv consuming %5f%% of system memory" % (percent,))
        return True

    return None

#Report the memery in use by entv.
def memory_in_use():
    if os.uname()[0] == "Linux":
        f = open("/proc/%d/status" % (os.getpid(),), "r")
        proc_info = f.readlines()
        f.close()

        for item in proc_info:
            words = item.split()
            if words[0] == "VmSize:":
                #Since this is in kB, multiple by 1024.
                return int(words[1]) * 1024

        return None #Should never happen.
    else:
        #rss = Resident Set Size
        rss = resource.getrusage(resource.RUSAGE_SELF)[3]
        if rss != 0:
            #Not all OSes, like Linux and Solaris, report valid information.
            # They recommend going to /proc for this information instead.
            return rss
        else:
            return None

#Return total system memory or None if unable to determine.
def total_memory():
    total_mem_in_pages = os.sysconf(os.sysconf_names['SC_PHYS_PAGES'])
    if total_mem_in_pages == -1:
        return None
    
    page_size = os.sysconf(os.sysconf_names['SC_PAGE_SIZE'])
    if page_size == -1:
        return None

    return long(total_mem_in_pages) * long(page_size)

#########################################################################
# .entrc file related functions
#########################################################################

def get_entvrc_filename():
    return os.environ["HOME"] + "/.entvrc"

def get_entvrc_file():
    lines = []

    #Get the file contents.
    try:
        f = open(get_entvrc_filename())
        for line in f.readlines():
            lines.append(line.strip())
        f.close()
    except (OSError, IOError):
        pass
    
    ###Don't remove blank lines and command lines from the output.  This
    ### output is used by the set_entvrc function which will use these
    ### extraneous lines.

    return lines

def get_entvrc(csc=None):

    library_colors = {}
    client_colors = {}
    system_info = {}

    try:
        #if not csc:
        #    csc = get_csc()
        if not csc:
            config_servers = {}
        else:
            config_servers = csc.get('known_config_servers', 3, 3)
            if not e_errors.is_ok(config_servers):
                config_servers = {}
            else:
                try:
                    del config_servers['status']
                except KeyError:
                    pass
        
        #Only need to grab this once.
        entvrc_data = get_entvrc_file()

        for line in entvrc_data:

            #Check the line for problems or things to skip, like comments.
            if len(line) == 0:
                continue
            if line[0] == "#": #Skip comment lines.
                continue
            
            #Split the string and look for problems.
            words = line.strip().split()
            if not words:
                continue

            #If the line gives outline color for movers based on their
            # library manager, pass this information along.
            if words[0] == "library_color":
                try:
                    library_colors[words[1]] = words[2]
                except (IndexError, KeyError, AttributeError, ValueError,
                        TypeError):
                    pass
                continue

            #If the line gives fill color for clients based on their nodename.
            if words[0] == "client_color":
                try:
                    client_colors[words[1]] = words[2]
                except (IndexError, KeyError, AttributeError, ValueError,
                        TypeError):
                    pass
                continue

            #We have a line we belive contains information about an Enstore
            # system.
            try:
                geometry = words[1]
            except IndexError:
                geometry = "1200x1600+0+0"
            try:
                background = words[2]
            except IndexError:
                background = DEFAULT_BG_COLOR
            try:
                if words[3] == "animate":
                    animate = 1
                else:
                    animate = 0
            except IndexError:
                animate = 1

            for system_name, csc_addr in config_servers.items():
                if socket.getfqdn(words[0]) == socket.getfqdn(csc_addr[0]):
                    enstore_system = system_name
                    break
            else:
                enstore_system = words[0]

            try:
                system_info[words[0]] = {'config_host' : words[0],
                                         'geometry' : geometry,
                                         'background' : background, #color
                                         'animate' : animate,
                                         'system_name' : enstore_system,
                                         }
            except (IndexError, KeyError, AttributeError, ValueError,
                    TypeError):
                pass

    except (IOError, IndexError):
        pass

    rtn_dict = {}
    rtn_dict['library_colors'] = library_colors
    rtn_dict['client_colors'] = client_colors
    rtn_dict['system_info'] = system_info

    return rtn_dict

def set_entvrc(display, address):
    
    #If there isn't geometry don't do anything.
    master_geometry = getattr(display, "master_geometry", None)
    if master_geometry == None:
        return

    try:
        #Do this now to save the time to do the conversion for every line.
        if type(address) == types.TupleType and len(address) >= 2:
            csc_server_name = socket.getfqdn(address[0])
        elif type(address) == types.StringType:
            csc_server_name = socket.getfqdn(address)
        else:
            csc_server_name = None

        #Get the current .entvrc file data if possible.
        try:
            data = get_entvrc_file()
        except (OSError, IOError), msg:
            #If the file exists but still failed to open (ie permissions)
            # then skip this step.
            if msg.errno != errno.ENOENT:
                Trace.trace(1, "Unable to open .entvrc file: %s" % (str(msg),),
                            out_fp=sys.stderr)
                return
            #But if it simply did not exist, then prepare to create it.
            else:
                data = []

        #use a temporary file incase something goes wrong.
        tmp_filename = get_entvrc_filename() + "." + str(os.getpid()) + ".tmp"
        tmp_file = open(tmp_filename, "w")

        #Make sure this gets written to file if not already there.
        new_line_written = 0

        #Loop through any existing data from the file.
        getfqdn = socket.getfqdn  #Speed up lookups.
        for line in data:
            #Split the line into its individual words.
            words = line.split()

            #If the line is empty, write an empty line and continue.
            if not words:
                tmp_file.write("\n")   #Skip empty lines.
                continue

            if words[0] == "client_color" or words[0] == "library_color" \
               or line[0] == "#":
                tmp_file.write("%s\n" % (line,))

                #The reason for looking for client_color, library_color
                # and comment lines is to avoid calling (socket.)getfqdn().
                # It really slows things down.

            #If this is the correct line to update; update it.
            elif getfqdn(words[0]) == csc_server_name:
                #We can't assume a user that puts together there own
                # .entvrc file will do it correctly.
                try:
                    background = words[2]
                except IndexError:
                    background = DEFAULT_BG_COLOR
                try:
                    if display.master.entv_do_animation.get():
                        animate = str("animate")
                    else:
                        animate = str("still")
                except AttributeError:
                    animate = str("animate")
                #Write the new geometry to the .entvrc file.
                tmp_file.write("%-25s %-20s %-10s %-7s\n" %
                               (csc_server_name, master_geometry,
                                background, animate))

                new_line_written = 1
            else:
                tmp_file.write("%s\n" % (line,))

        #If the enstore system entv display is not found, add it at the end.
        if not new_line_written:
            tmp_file.write("%-25s %-20s %-10s\n" %
                         (csc_server_name, master_geometry, DEFAULT_BG_COLOR))
            
        tmp_file.close()

        entv_file = open(get_entvrc_filename(), "a")
        os.unlink(get_entvrc_filename())
        os.link(tmp_filename, get_entvrc_filename())
        os.unlink(tmp_filename)
        entv_file.close()
                  
    except (IOError, IndexError, OSError), msg:
        Trace.trace(1, "Error writing .entvrc file: %s" % (str(msg),),
                    out_fp=sys.stderr)
        pass #If the line isn't there to begin with don't change anything.

#Return the system_info dictionary that correlates to the currently
# configured system.  Takes the  Tk() instance object and the return
# value from get_entvrc() as parameters.  If system_name is set,
# return the values for that system.
def get_system_info_from_entvrc(tk, entvrc_dict, system_name=None):
    #Create the default information.
    entvrc_info = {'geometry' : DEFAULT_GEOMETRY,
                   'background' : DEFAULT_BG_COLOR,
                   'animate' : 1,
                   }

    #If a particular system is specified return that systems info.
    if system_name:
        for config_host, tmp_entvrc_info in \
                entvrc_dict.get('system_info', {}).items():
            if system_name == tmp_entvrc_info['system_name']:
                entvrc_info = tmp_entvrc_info
                break
            elif system_name == tmp_entvrc_info['config_host']:
                entvrc_info = tmp_entvrc_info
                break
    
    #If the number of enabled systems is one, set the geometry from its
    # configuration information.  This allows a long running entv process
    # to pick up new entvrc information with a reinitialization.
    elif systems_enabled_statistics(tk)[0] == 1:
        for current_system_name in configurated_systems(tk):
            if is_system_enabled(current_system_name, tk):
                for config_host, tmp_entvrc_info in \
                        entvrc_dict.get('system_info', {}).items():
                    if current_system_name == tmp_entvrc_info['system_name']:
                        entvrc_info = tmp_entvrc_info
                        #Don't return here so we can test if the window
                        # already exists.
                        break
                    elif system_name == tmp_entvrc_info['config_host']:
                        entvrc_info = tmp_entvrc_info
                        #Don't return here so we can test if the window
                        # already exists.
                        break

    if tk.state() in  ["normal", "iconic", "icon"]:
        #In all cases, if the window already exists, use the existing
        # window geometry.  The only other state is "withdrawn', which means
        # that the window is not realized.
        entvrc_info['geometry'] = tk.geometry()

    return entvrc_info

#########################################################################
# entv functions
#########################################################################

#Wrapper around csc.get_library_managers2().
def get_library_managers(system_name):
    libraries_config_info = []
    count = 0
    while libraries_config_info == [] and count < 3:
        try:
            csc = get_csc(system_name)
            libraries_config_info = csc.get_library_managers2(3, 3)
        except KeyError:
            #Place a limit on how many times to try.
            count = count + 1
        
    return libraries_config_info

#Wrapper around csc.get_movers2().
def get_movers(system_name):
    movers_config_info = []
    count = 0
    while movers_config_info == [] and count < 3:
        try:
            csc = get_csc(system_name)
            movers_config_info = csc.get_movers2(None, 3, 3)
        except KeyError:
            #Place a limit on how many times to try.
            count = count + 1
    
    return movers_config_info

ignored_movers = {} #cache for ignore_mover_by_library
allowed_movers = {}
#Return True if the mover, which must have the form name.mover@system should
# be dropped.  False otherwise.
#
# mover_name: String name of the mover: 9940B_1@gccen or 9940B_1.mover@gccen
# intf: EntvInterface instance
# mover_config:  Configuration for the "mover_name" mover.
# library_configs:  Returned value from get_library_mangers().
def ignore_mover_by_library(mover_name, intf, mover_config=None,
                            library_configs=None):
    global ignored_movers
    global allowed_movers
    
    if intf and intf.messages_file:
        #Let --generate-messages-file filter out the contents for us
        # on creation of the messages file.
        return False

    #Obtain the mover name that will be in the configuration.
    alt_mover_name, enstore_system = mover_name.split("@")
    short_mover_name = alt_mover_name.split(".")[0]
    full_mover_name = short_mover_name + ".mover"
    full_entv_mover_name = "%s@%s" % (full_mover_name, enstore_system)

    #If we have already cached this movers library information.
    if full_entv_mover_name in ignored_movers.keys():
        return True
    if full_entv_mover_name in allowed_movers.keys():
        return False

    #Get the mover's configuration information.
    if mover_config == None:
        csc = get_csc(enstore_system)
        mover_config_info = csc.get(full_mover_name, 3, 3)
        if not e_errors.is_ok(mover_config_info):
            #One known source of getting here is if a mover is scheduled
            # down then removed from the configuration.  Since it is still
            # in the scheduled down list it is included in the response
            # from the inquisitor, but csc.get() will fail.
            message = "Failed to get %s (%s) configuration information: %s" % \
                 (full_mover_name, enstore_system, mover_config_info['status'])
            Trace.trace(1, message, out_fp=sys.stderr)
            return False
    else:
        mover_config_info = mover_config
    #Get the libraries' configuration information.
    if library_configs == None:
        libraries_config_info = get_library_managers(enstore_system)
    else:
        libraries_config_info = library_configs

    #Extract the library information.  There might be more than one, so
    # lets put everything into a list.
    if type(mover_config_info['library']) == types.ListType:
        libraries = mover_config_info['library']
    else:
        libraries = [mover_config_info['library']]

    #Pull out all the libraries in the configuration and put just the
    # names in a list.
    valid_libraries = []
    for lib in libraries_config_info:
        valid_libraries.append(lib['library_manager'])

    #Split the comma seperated libraries to ignore.
    skip_library_list = string.split(intf.dont_show, ",")

    #Report True or False if the mover is to be igored or not.
    for library in libraries:
        use_library = library[:-16] #remove trailing ".library_manager"
        if use_library not in valid_libraries:
            # We found a library that is not in the configuration.
            ignored_movers["%s@%s" % (full_mover_name, enstore_system)] = libraries
            return True
        if use_library not in skip_library_list:
            # We found a library not in this movers list of libraries.
            #
            # We don't ingore a mover if only one library is ignored.  If
            # a test library is ignored, we don't want to ignore any
            # production movers that have the production and test libraries
            # in their configuration.
            allowed_movers["%s@%s" % (full_mover_name, enstore_system)] = libraries
            return False

    #cache the miss
    ignored_movers["%s@%s" % (full_mover_name, enstore_system)] = libraries
    return True

#The parameters fullnames and with_system determine what strings are
# appended to each mover name.  Assume short mover name test01.  This
# is what would be returned if fullnames and with_system are python false.
#fullnames true -> test01.mover
#with_system true -> test01@test01
def get_mover_list(system_name, intf, fullnames=None, with_system=None):

    if intf and intf.messages_file:
        #We build the mover list as we go in this case.
        return []

    #Get the list of movers for this enstore system.
    csc = get_csc(system_name)
    if csc == None or csc.server_address == None:
        mover_list = []
    else:
        mover_list = get_movers(system_name)
        library_list = get_library_managers(system_name)

    allowed_mover_list = []
    for mover_dict in mover_list:
        #mover_dict['name'] is the fullname; mover_dict['mover'] would
        # contain the short mover name if we wanted it.
        short_name = mover_dict['mover']
        #full_name = mover_dict['name']
        entv_full_mover_name = "%s@%s" % (mover_dict['name'], system_name)

        #Determine if it is allowed to be shone.
        if not ignore_mover_by_library(entv_full_mover_name, intf,
                                       mover_config=mover_dict,
                                       library_configs=library_list):
            #Return the format of the mover name with the requested format.
            use_mover_name = short_name
            if fullnames:
                use_mover_name = "%s.mover" % (use_mover_name,)
            if with_system:
                use_mover_name = "%s@%s" % (use_mover_name, system_name)
            allowed_mover_list.append(use_mover_name)

    allowed_mover_list.sort()
    return allowed_mover_list
    

#Takes the name of the mover and the status dictionary.  Returns the
# list of display commands to update the display to show the mover in
# its current state.
def handle_status(mover, status):
    if mover == "inquisitor":
        offline_dict = status.get('offline', {})
        outage_dict = status.get('outage', {})
        send_error_list = {}  #Really a dictionary.
        for mover_name, outage in outage_dict.items():
            if not enstore_functions2.is_mover(mover_name):
                #This isn't a scheduled down mover.
                continue
            send_error_list[mover_name] = "error %s %s" % \
                                          (mover_name.split(".")[0], outage)
        for mover_name, reason in offline_dict.items():
            if not enstore_functions2.is_mover(mover_name):
                #This isn't a scheduled down mover.
                continue
            send_error_list[mover_name] = "error %s %s" % \
                                          (mover_name.split(".")[0], reason)
        return send_error_list.values()
    
    state = status.get('state','Unknown')
    time_in_state = status.get('time_in_state', '0')
    mover_state = "state %s %s %s" % (mover, state, time_in_state)
    volume = status.get('current_volume', None)
    client = status.get('client', "Unknown")
    connect = "connect %s %s" % (mover, client)
    #For error, see if a reason is mentioned in the second status field [1],
    # otherwise just go with the first field [0].
    _error_status = status.get('status', ('Unknown', None))
    if _error_status[1]:
        error_status = _error_status[1]
    else:
        error_status = _error_status[0]
    if not volume:
        return [mover_state]
    if state in ['ACTIVE', 'SEEK', 'SETUP']:
        loaded = "loaded %s %s" % (mover, volume)
        return [loaded, mover_state, connect]
    if state in ['HAVE_BOUND', 'DISMOUNT_WAIT']:
        loaded = "loaded %s %s" % (mover, volume)
        return [loaded, mover_state]
    if state in ['MOUNT_WAIT']:
        loading = "loading %s %s" %(mover, volume)
        return [loading, mover_state, connect]
    if state in ['ERROR']:
        error = "error %s %s" %(mover, error_status)
        return [mover_state, error]

    return [mover_state]


#########################################################################
# The following functions initialize or destroy the display panels.
#########################################################################

#Returns a list of the display panels.  If the empty list is returned,
# then an error occured and the caller should try again later.
def make_display_panels(master, entvrc_dict,
                        mover_display, intf):
    #Set the size of the window.
    set_geometry(master, entvrc_dict)

    display_list = []
    for system_name in configurated_systems(master):
        if not is_system_enabled(system_name, master):
            continue

        try:
            new_display_panel = make_display_panel(master, system_name,
                                                   mover_display, intf)
        except:
            #Note: KeyboardInterrupt and SystemExit are handled below.
            
            #Make sure that any display panels that did get created get
            # destroyed before we return.
            try:
                for display in display_list:
                    destroy_display_panel(display)
            finally:
                del display_list[:] #Make sure these are gone.

            exc, msg = sys.exc_info()[:2]
            if isinstance(exc, KeyboardInterrupt) or \
               isinstance(msg, SystemExit):
                raise sys.exc_info()[0], sys.exc_info()[1], sys.exc_info()[2]
            else:
                import traceback
                traceback.print_tb(sys.exc_info()[2])
                #Report on the error.
                try:
                    message = "Destroying display failed unexpectedly: (%s, %s)\n"
                    sys.stderr.write(message % (str(exc), str(msg)))
                    sys.stderr.flush()
                except IOError:
                    pass
                
                #Give up.  By return an empty list we tell the caller to try
                # again later.
                return []

        if new_display_panel:
            display_list.append(new_display_panel)
        
    return display_list

#Return a display panel object.  On error raise an exception.
def make_display_panel(master, system_name,
                       mover_display, intf, entvrc_dict=None):
    Trace.trace(1, "creating display for %s" % (system_name,))

    #Get the entvrc file info.
    if not entvrc_dict:
        entvrc_dict = get_entvrc(csc=None)

    #Determine the size of the panel in the display.
    if intf and intf.messages_file:
        #When --messages-file is used.
        entvrc_info = get_system_info_from_entvrc(master, entvrc_dict)
    else:
        #Extract the system_info dictionary that correlates to the currently
        # configured system.
        entvrc_info = get_system_info_from_entvrc(master, entvrc_dict,
                                                  system_name)

    use_geometry = entvrc_info.get('geometry', DEFAULT_GEOMETRY)
    size = use_geometry.split("+")[0]
    sizes = size.split("x")
    #Determine width, which is width of window divided by number of systems
    # to display.
    count = 0
    for value in master.enstore_systems_enabled:
        if value:
            count = count + 1
    width = int(sizes[0]) / count
    #Now determine the height.
    height = int(sizes[1])

    #Create the object that will be drawn in the window.
    display = enstore_display.Display(entvrc_dict, system_name,
                                      master = master,
                                      width = width,
                                      height = height,
                                      mover_display = mover_display,
                         background = entvrc_info.get('background', None))
    display.pack(side = Tkinter.LEFT, fill = Tkinter.BOTH,
                 expand = Tkinter.YES)

    Trace.trace(1, "created display for %s" % (system_name,))

    return display

#Return true, means that this is a reinit and that the caller should
# make new display panels and keep working.  Return false, indicates
# that entv should proceed to exit cleanly.
def destroy_display_panels():
    global displays

    continue_working = 0
    for display in displays:
        #Determine if this is a reinitialization (True) or not (False).
        continue_working = continue_working + display.attempt_reinit()

        try:
            destroy_display_panel(display)
        except (KeyboardInterrupt, SystemExit):
            raise sys.exc_info()[0], sys.exc_info()[1], sys.exc_info()[2]
        except Tkinter.TclError:
            pass
        except:
            exc, msg = sys.exc_info()[:2]
            import traceback
            traceback.print_tb(sys.exc_info()[2])
            #Report on the error.
            try:
                message = "Destroying display failed unexpectedly: (%s, %s)\n"
                sys.stderr.write(message % (str(exc), str(msg)))
                sys.stderr.flush()
            except IOError:
                pass

    try:
        del displays[:]
    except:
        displays = []
    return continue_working

def destroy_display_panel(display):

    #We need to remove the associated detailed mover display window,
    # if present.
    if display.mover_display:
        try:
            display.mover_display.destroy()
        except Tkinter.TclError:
            #It might already be destroyed (i.e. window closed by user).
            pass
        try:
            del display.mover_display
        except AttributeError:
            pass
        display.mover_display = None
    
    try:
        
        display.cleanup_display()
        display.shutdown()
        #Forces cleanup of objects that would not happen otherwise.  As
        # part of the destroy call Tkinter does generate a Destroy event
        # that results in window_killed() being called.  Skipping a
        # destroy() function call would result in a huge memory leak.
        try:
            display.destroy()
        except Tkinter.TclError:
            #It might already be destroyed (i.e. window closed by user).
            pass
    except (KeyboardInterrupt, SystemExit):
        raise sys.exc_info()[0], sys.exc_info()[1], sys.exc_info()[2]
    except:
        exc, msg = sys.exc_info()[:2]
        import traceback
        traceback.print_tb(sys.exc_info()[2])
        #Report on the error.
        try:
            message = "Destroying display failed unexpectedly: (%s, %s)\n"
            sys.stderr.write(message % (str(exc), str(msg)))
            sys.stderr.flush()
        except IOError:
            pass

#########################################################################
# The following functions start functions in new threads.
#########################################################################

#Wrapper function called from start_messages_thread() that allows for
# thread tracebacks to be reported.
def __func_smt_wrapper(function, args):
    try:
        apply(function, args)
    except (KeyboardInterrupt, SystemExit):
        raise sys.exc_info()[0], sys.exc_info()[1], sys.exc_info()[2]
    except:
        exc, msg = sys.exc_info()[:2]
        import traceback
        traceback.print_tb(sys.exc_info()[2])
        #Report on the error.
        try:
            message = "Error in network thread for %s: (%s, %s)\n"
            sys.stderr.write(message % (args[1], str(exc), str(msg)))
            sys.stderr.flush()
        except IOError:
            pass

def start_messages_thread(system_name, intf):
    global messages_threads

    __pychecker__ = "unusednames=i"

    for i in range(0, 5):
        try:
            Trace.trace(1, "Creating thread for %s." % (system_name,))
            sys.stdout.flush()
            new_thread = threading.Thread(
                target = __func_smt_wrapper,
                args = (handle_messages, (system_name, intf)),
                name = system_name,
                )
            new_thread.start()
            Trace.trace(1, "Started thread for %s." % (system_name,))
        except (KeyboardInterrupt, SystemExit):
            raise sys.exc_info()[0], sys.exc_info()[1], sys.exc_info()[2]
        except:
            exc, msg = sys.exc_info()[:2]
            import traceback
            traceback.print_tb(sys.exc_info()[2])
            #Report on the error.
            try:
                message = "Failed to start network thread for %s: (%s, %s)\n"
                sys.stderr.write(message % (system_name, str(exc), str(msg)))
                sys.stderr.flush()
            except IOError:
                pass

        if new_thread in threading.enumerate():
            sys.stdout.flush()
            #We succeded in starting the thread.
            messages_threads.append(new_thread)
            break

        time.sleep(1)
        #If we get here go back to the top of the loop and try again.

    else:
        #We kept on failing to start the thread.
        try:
            sys.stderr.write("Failed to start network thread for %s.\n" %
                             (system_name,))
            sys.stderr.flush()
        except IOError:
            pass
            
    return

def stop_messages_threads():
    global messages_threads

    __pychecker__ = "unusednames=i"

    for i in range(len(messages_threads)):
        messages_threads[0].join(5) #Wait 5 seconds before giving up.
        del messages_threads[0]

    del messages_threads[:]
    messages_threads = []

    return

#########################################################################
# The following functions run in their own thread.
#########################################################################


##send_mover_request(), send_sched_request(), send_all_requests() and
## stop_waiting_all_requests() control obtaining status information from
## the movers and the inquisitor.

def send_mover_request(csc, send_request_dict, mover_name, u, count = 0):
    mover_name = mover_name.split("@")[0].split(".")[0]
    mover_name = mover_name + ".mover"
    
    #Get the message, mover name and mover network address
    # for sending the status request.
    mover_conf_dict = csc.get(mover_name, timeout=5, retry=6)
    m_addr = mover_conf_dict.get('hostip', None)
    m_port = mover_conf_dict.get('port', None)
    if not m_addr or not m_port:
        return

    message = {'work' : 'status'}
    mover_system_name = mover_name.split(".")[0]
    try:
        tx_id = u.send_deferred(message, (m_addr, m_port))
    except (socket.error, socket.gaierror, socket.herror), msg:
        Trace.trace(0, "Failed to send message to %s at (%s, %s):  %s" % \
                    (mover_name, m_addr, m_port, str(msg)))
        return
    Trace.trace(1, "Sent ID %s to %s." % (tx_id, mover_name))
    send_request_dict[tx_id] = {}
    send_request_dict[tx_id]['name']  = mover_system_name
    send_request_dict[tx_id]['time']  = time.time()
    send_request_dict[tx_id]['count'] = count

def send_sched_request(csc, send_request_dict, u, count = 0):

    #Get the address for sending the scheduled down information request.
    inquisitor_conf_dict = csc.get('inquisitor', timeout=5, retry=6)
    i_addr = inquisitor_conf_dict.get('hostip', None)
    i_port = inquisitor_conf_dict.get('port', None)
    if not i_addr or not i_port:
        return

    message = {'work' : 'show'}
    try:
        tx_id = u.send_deferred(message, (i_addr, i_port))
    except (socket.error, socket.gaierror, socket.herror), msg:
        Trace.trace(0, "Failed to send message to %s at (%s, %s):  %s" % \
                    ("inquisitor", i_addr, i_port, str(msg)))
        return
    Trace.trace(1, "Sent ID %s to inquisitor %s." % (tx_id, (i_addr, i_port)))
    send_request_dict[tx_id] = {}
    send_request_dict[tx_id]['name']  = 'inquisitor'
    send_request_dict[tx_id]['time']  = time.time()
    send_request_dict[tx_id]['count'] = count

#Send any status requests to the movers or the inquisitor.  This only
# sends these requests, it does not wait for responses here.
def send_all_status_requests(csc, send_request_dict, enstore_system, u):
    mover_name = True
    name_sent_list = []  #use this to avoid sending duplicates.
    while mover_name:
        mover_name = enstore_display.request_queue.get_queue(enstore_system)
        if mover_name in name_sent_list:
            continue  #Already covered this time around.
        if mover_name != None:
            name_sent_list.append(mover_name)
            
        if mover_name == 'inquisitor':
            send_sched_request(csc, send_request_dict, u)
        elif mover_name:
            send_mover_request(csc, send_request_dict, mover_name, u)

#Remove items that are in the queue without having received a response,
# and resend requests that possibly have been dropped.
def drop_stale_status_requests(send_request_dict, u):
    for tx_id in send_request_dict.keys():
        if time.time() - send_request_dict[tx_id]['time'] > \
           MAX_COUNT * SELECT_TIMEOUT:
            #If there has not been any response after 30 seconds
            # (5 x 6) then give up.
            Trace.trace(1, "Removing %s (%s) from status query list." % \
                        (send_request_dict[tx_id]['name'], tx_id))
            try:
                del send_request_dict[tx_id]
            except KeyError:
                pass
        elif time.time() - send_request_dict[tx_id]['time'] > \
                 send_request_dict[tx_id]['count'] * SELECT_TIMEOUT:
            #If there hasn't been a response resend the request.
            u.repeat_deferred(tx_id)

#handle_messages() reads event relay messages from the specified event
# relay.  It is called within a new thread (one for each event relay).
#
#intf is an instance of the EntvInterface class.
def handle_messages(system_name, intf):
    #Use this like a lamda function inside handle_messages().
    def should_stop(system_name):
        global stop_now
        global displays

        if stop_now:
            return True
        for display in displays:
            if display.system_name == system_name:
                if display.stopped:
                    #Found display, but it is supposed to be stopped.
                    return True
                else:
                    return False
        else:
            #Did not find this enstore system in the list, return True
            # to trigger thread exit.
            return True

        return False  #Should never get here.
    #### End of should_stop().

    threading.currentThread().setName("MESSAGES-%s" % (system_name,))

    #Prevent the main thread from queuing status requests.
    enstore_display.acquire(enstore_display.startup_lock, "startup_lock")

    #This is a time hack to get a clean output file.
    if intf.generate_messages_file:
        timeout_time = time.time() + intf.capture_timeout
    else:
        timeout_time = None

    send_request_dict = {}

    u = udp_client.UDPClient()
    
    # we will get all of the info from the event relay.
    if intf.messages_file:
        messages_file = open(intf.messages_file, "r")
        
        last_timestamp = -1 #Used to space the commands in real time.
    else:
        csc = get_csc(system_name)

        er_dict = None
        while er_dict == None or not e_errors.is_ok(er_dict):
            #If the user said it needs to die, then die.  Don't wait for all of
            # the movers to be contacted.  If there is a known problem then
            # this could possibly take a while to time out with each of the
            # movers.
            if should_stop(system_name):
                enstore_display.startup_lock.release()  #Avoid resource leak.
                Trace.trace(1, "Detected stop flag in %s messages thread." %
                            (system_name,))
                return

            if csc == None:
                
                #We can't find the Enstore system.  We need to wait, but
                # first lets release the lock to allow other message
                # threads to startup.
                enstore_display.release(enstore_display.startup_lock,
                                        "startup_lock")  #Avoid resource leak.
                time.sleep(60)
                enstore_display.acquire(enstore_display.startup_lock,
                                        "startup_lock")
                csc = get_csc(system_name)
                continue
            else:
                #As long as we are reinitializing, make sure we pick up any
                # new configuration changes.  It is possible that the
                # reinialization is happening because a NEWCONFIGFILE message
                # was received; among other reasons.
                try:
                    rtn_config = csc.dump_and_save(timeout = 3, retry = 3)

                    if not e_errors.is_ok(rtn_config):
                        raise ValueError("Loop back to top.")
                except (KeyboardInterrupt, SystemExit):
                    raise sys.exc_info()[0], sys.exc_info()[1], \
                          sys.exc_info()[2]
                except:
                    #We can't find the Enstore system.  We need to wait, but
                    # first lets release the lock to allow other message
                    # threads to startup.
                    enstore_display.release(enstore_display.startup_lock,
                                            "startup_lock")  #Avoid resource leak.
                    time.sleep(60)
                    enstore_display.acquire(enstore_display.startup_lock,
                                            "startup_lock")
                    continue

            
            try:
                er_dict = csc.get('event_relay', 3, 3)
            except (KeyboardInterrupt, SystemExit), msg:
                enstore_display.startup_lock.release()  #Avoid resource leak.
                raise msg
            except:
                pass

            #If the user said it needs to die, then die.  Don't wait for all of
            # the movers to be contacted.  If there is a known problem then
            # this could possibly take a while to time out with each of the
            # movers.
            if should_stop(system_name):
                enstore_display.startup_lock.release()  #Avoid resource leak.
                Trace.trace(1, "Detected stop flag in %s messages thread." %
                            (system_name,))
                return

            if er_dict == None or e_errors.is_timedout(er_dict):
                #We can't find the Enstore system.  We need to wait, but
                # first lets release the lock to allow other message
                # threads to startup.
                enstore_display.release(enstore_display.startup_lock,
                                        "startup_lock")  #Avoid resource leak.
                time.sleep(60)
                enstore_display.acquire(enstore_display.startup_lock,
                                        "startup_lock")
                continue

            if not e_errors.is_ok(er_dict):
                enstore_display.message_queue.put_queue("reinit",
                                                        system_name)
                enstore_display.startup_lock.release()  #Avoid resource leak.
                Trace.trace(0, "ER config info: %s" % (er_dict,),
                            out_fp=sys.stderr)
                return

            er_addr = (er_dict.get('hostip', None), er_dict.get('port', None))
            erc = event_relay_client.EventRelayClient(
                event_relay_host = er_addr[0], event_relay_port = er_addr[1])
            retval = erc.start([event_relay_messages.ALL])
            if retval == erc.ERROR:
                Trace.trace(0, "Could not contact event relay.",
                            out_fp=sys.stderr)

            put_func = enstore_display.message_queue.put_queue #Shortcut.

            #Inform the display the names of all the movers.
            mover_list = get_mover_list(system_name, intf, with_system=1)
            mover_list = ["movers"] + mover_list
            movers_command = string.join(mover_list, " ")
            put_func(movers_command, system_name)
            
            #If we want a clean commands file, we need to set the inital movers
            # state to idle.
            if intf and intf.generate_messages_file:
                for mover in mover_list:
                    idle_command = string.join(["state", mover, "IDLE"], " ")
                    put_func(idle_command, system_name)
            
            #Get the list of movers that we need to send status requests to.
            movers = get_mover_list(system_name, intf, fullnames=1)
            #Queue status request for the mover.
            for mover_name in movers:
                send_mover_request(csc, send_request_dict, mover_name, u)
                
        #If the client fails to initialize then wait a minute and start over.
        # The largest known error to occur is that socket.socket() fails
        # to return a file descriptor because to many files are open.
        if should_stop(system_name):
            enstore_display.release(enstore_display.startup_lock,
                                    "startup_lock")  #Avoid resource leak.
            Trace.trace(1, "Detected stop flag in %s messages thread." %
                            (system_name,))
            return

    start = time.time()
    count = 0
    
    #Allow the main thread to queue status requests.
    enstore_display.release(enstore_display.startup_lock, "startup_lock")
    
    while not should_stop(system_name):
        # If commands are listed, use 'canned' version of entv.
        if intf.messages_file:
            try:
                #Get the next line from the commands list file.
                line = messages_file.readline()
                if not line:
                    try:
                        position = messages_file.tell()
                        size = os.fstat(messages_file.fileno())[stat.ST_SIZE]
                    except (OSError, IOError), msg:
                        Trace.trace(0,
                                    "Error accessing messages file: %s" %
                                    (str(msg),),
                                     out_fp=sys.stderr)
                        sys.exit(1)
                    if position == size:
                        messages_file.seek(0, 0) #Position at beginning of file.
                        last_timestamp = -1  #Reset this too.
                        
                #For each line strip off the timestamp information from
                # the espion.py.
                words = line.split()
                recorded_time = string.join(words[:5])
                command = string.join(words[5:])
                if not command:
                    continue
                    #break  #Is this correct to break here?
                #Store the command into the list (in this case of 1).
                commands = [command]
            except (OSError, IOError, TypeError, ValueError,
                    KeyError, IndexError):
                messages_file.seek(0, 0) #Position at beginning of file.
                last_timestamp = -1  #Reset this too.
                continue

            try:
                timestamp = time.mktime(time.strptime(recorded_time))
            except ValueError:
                #Other content.
                continue
            #Don't overwhelm the display thread.  This code attempts to wait
            # the same amount of time as it happended the first time.
            if last_timestamp != -1:
                now = time.time()
                sleep_duration = timestamp - last_timestamp - (1 - math.modf(now)[0])
                time.sleep(max(sleep_duration, 0))
            last_timestamp = timestamp
        else:
            #Send any status requests to the movers or the inquisitor.  This
            # only sends these requests, it does not wait for responses here.
            send_all_status_requests(csc, send_request_dict, system_name, u)

            #Test whether there is a command or status response ready to read,
            # timeout in 5 seconds.
            try:
                readable, unused, unused = select.select(
                    [erc.sock, u.get_tsd().socket], [], [], SELECT_TIMEOUT)
            except (socket.error, select.error), msg:
                if msg.args[0] != errno.EINTR:
                    erc.unsubscribe()
                    erc.sock.close()
                    try:
                        sys.stderr.write("Exiting early.\n")
                        sys.stderr.flush()
                    except IOError:
                        pass
                    sys.exit(1)

            #Update counts and do it again if there is nothing going on.
            if not readable:
                #Since we don't have much going on, let us take a moment
                # to clear out stale status requests that we don't appear
                # to ever be getting reponses to.
                drop_stale_status_requests(send_request_dict, u)
                
                if count > MAX_COUNT:
                    #If nothing received for 30 seconds, resubscribe.
                    erc.subscribe()
                    count = 0
                else:
                    #If nothing received for 5 seconds, up the count and
                    # try again.
                    count = count + 1

                # If the display/main thread hasn't done anything in 10
                # minutes, let us restart entv.
                if enstore_display.message_queue.get_time <= \
                       time.time() - TEN_MINUTES:
                    message = "Display is stuck.  Restarting entv. [1]"
                    Trace.trace(0, message, out_fp=sys.stderr)
                    restart_entv()

                continue

            # If the display/main thread hasn't done anything in 10
            # minutes, let us restart entv.
            if enstore_display.message_queue.len_queue(system_name) > 0 and \
                   enstore_display.message_queue.last_get_time() <= \
                   time.time() - TEN_MINUTES:
                message = "Display is stuck.  Restarting entv. [2]"
                Trace.trace(0, message, out_fp=sys.stderr)
                restart_entv()
                
            commands = []

            #Read any status responses from movers or the inquisitor.
            if u.get_tsd().socket in readable:
                for tx_id in send_request_dict.keys():
                    try:
                        mstatus = u.recv_deferred(tx_id, 0.0)
                        if mstatus.has_key('time_in_state'):
                            #We have a mover response.  Since the status
                            # field might be for an error, we need to
                            # avoid using is_ok() here, so that the error
                            # gets displayed instead of getting the
                            # response ignored.
                            pass
                        else:
                            #We have an inquisitor response.
                            if not e_errors.is_ok(mstatus):
                                del send_request_dict[tx_id]
                                continue

                        commands = commands + handle_status(
                            send_request_dict[tx_id]['name'], mstatus)

                        del send_request_dict[tx_id]

                        if mstatus.get('work', None) == "show":
                            Trace.trace(1, "Recieved ID %s from inquisitor." \
                                        % (tx_id,))
                        else:
                            Trace.trace(1, "Recieved ID %s from mover." \
                                        % (tx_id,))
                    except (socket.error, select.error,
                            e_errors.EnstoreError):
                        pass
                    except errno.errorcode[errno.ETIMEDOUT]:
                        pass
                else:
                    #Make sure to read any messages that finally arrived
                    # after the record of them being sent was purged from
                    # send_request_dict.
                    try:
                        u.recv_deferred([], 0.0)
                    except (socket.error, select.error,
                            e_errors.EnstoreError), msg:
                        if msg.args[0] not in [errno.ETIMEDOUT]:
                            Trace.log(0,
                                 "Error reading socket: %s" % (str(msg),))

            #Remove items that are in the queue without having received a
            # response.
            else:
                drop_stale_status_requests(send_request_dict, u)

            #Read the next message from the event relay.
            if erc.sock in readable:
                try:
                    msg = enstore_erc_functions.read_erc(erc)
                except SyntaxError:
                    exc, msg = sys.exc_info()[:2]
                    import traceback
                    traceback.print_tb(sys.exc_info()[2])
                    #Report on the error.
                    try:
                        message = "Failed to read erc message: (%s, %s)\n"
                        sys.stderr.write(message % (str(exc), str(msg)))
                        sys.stderr.flush()
                    except IOError:
                        pass

                if msg and not getattr(msg, 'status', None):
                    #Take the message from event relay.
                    commands = commands + ["%s %s" % (msg.type,
                                                      msg.extra_info)]

                ##If read_erc is valid it is a EventRelayMessage instance. If
                # it gets here it is a dictionary with a status field error.
                elif getattr(msg, "status", None):
                    Trace.trace(1, "Event relay error: %s" % (str(msg),),
                                out_fp=sys.stderr)

            if not commands:
                continue

        #Those commands that use mover names need to have the system name
        # appended to the name.
        for i in range(len(commands)):
            words = commands[i].split(" ")
            if words[0] in ("connect", "disconnect", "loaded", "loading",
                            "state", "unload", "transfer", "error"):
                
                if len(words[1].split("@")) == 1:
                    full_entv_mover_name = words[1] + "@" + system_name
                    #If the name already has the enstore_system appended to
                    # the end (from messages_file) then don't do this step.
                    commands[i] = "%s %s %s" % (words[0],
                                                full_entv_mover_name,
                                                string.join(words[2:], " "))
                else:
                    #Input is from the messages file.
                    full_entv_mover_name = words[1]

                #If the mover belongs to a library that we don't care
                # about, skip it.
                if ignore_mover_by_library(full_entv_mover_name, intf):
                    commands[i] = ""
                    continue

                #Output this if --generate-messages-file was used.
                now = time.time()
                if timeout_time and timeout_time > now:
                    #Building this string is resource expensive, only build it
                    # if necessary.
                    Trace.message(MESSAGES_LEVEL,
                                  string.join((time.ctime(now),
                                               commands[i]), " "))
                elif timeout_time: #timeout expired.
                    try:
                        if displays[0].movers[full_entv_mover_name].state \
                               not in ("IDLE", "Unknown", "HAVE_BOUND"):
                            #Keep outputing until the mover is done.
                            Trace.message(MESSAGES_LEVEL,
                                          string.join((time.ctime(now),
                                                       commands[i]), " "))
                    except (KeyError, IndexError):
                        pass
                        

        put_func = enstore_display.message_queue.put_queue #Shortcut.
        for command in commands:
            if command:
                #For normal use put everything into the queue.
                put_func(command, system_name)
            
            
        #If necessary, handle resubscribing.
        if not intf.messages_file:
            now = time.time()
            if now - start > TEN_MINUTES:
                # resubscribe
                erc.subscribe()
                start = now

    #End nicely.
    if not intf.messages_file:
        #Tell the event relay to stop sending us information.
        erc.unsubscribe()

        #Remove all of the routes that were set up to all of the movers.
        for mover_name in movers:
            try:
                m_addr = csc.get(mover_name, {}).get('hostip', None)
                #If we added a route to the mover, we should remove it.
                # Most clients would prefer to leave such routes in place,
                # but entv is not your normal client.  It talks to many
                # movers that makes the routing table huge.
                host_config.unset_route(m_addr)
                pass
            except (socket.error, OSError):
                pass
            except TypeError:
                # mov.server_address is equal to None
                pass

    Trace.trace(1, "Detected stop flag in %s messages thread." %
                (system_name,))
    return

#########################################################################
# The following function sets the window geometry and related window
# frame attributes.
#########################################################################

#tk is the toplevel window.
def set_geometry(tk, entvrc_dict):

    #Don't draw the window until all geometry issues have been worked out.
    #tk.withdraw()

    #Extract the system_info dictionary that correlates to the currently
    # configured system.
    entvrc_info = get_system_info_from_entvrc(tk, entvrc_dict)

    geometry = entvrc_info.get('geometry', DEFAULT_GEOMETRY)
    window_width = entvrc_info.get('window_width', None)
    window_height = entvrc_info.get('window_height', None)
    x_position = entvrc_info.get('x_position', None)
    y_position = entvrc_info.get('y_position', None)
    
    #Use the geometry argument first.
    if geometry != None:
        window_width, window_height, x_position, y_position = \
                      enstore_display.split_geometry(geometry)

    #If the initial size is larger than the screen size, use the
    #  screen size.
    if window_width != None and window_height != None:
        window_width = min(tk.winfo_screenwidth(), window_width)
        window_height= min(tk.winfo_screenheight(), window_height)
    else:
        window_width = 0
        window_height = 0
    if x_position != None and y_position != None:
        x_position = max(min(tk.winfo_screenwidth(), x_position), 0)
        y_position = max(min(tk.winfo_screenheight(), y_position), 0)
    else:
        x_position = 0
        y_position = 0

    #Formulate the size and location of the window.
    geometry = "%sx%s+%s+%s" % (window_width, window_height,
                                x_position, y_position)
    #Set the geometry.
    tk.geometry(geometry)
    #Force the update.  Without this the window frame is not considered in
    # the geometry on reinitializations.  The effect without this is
    # that the window appears to migrate upward without human intervention.
    tk.update()

def resize(event = None):
    global displays

    __pychecker__ = "no-argsused"

    #Recalculating this for each display is not efficent.
    if len(displays) > 0:
        size = displays[0].master.geometry().split("+")[0]
        sizes = size.split("x")
        width = int(sizes[0]) / len(displays)
        height = int(sizes[1])

    for display in displays:
        #Get the height and width info.  We do end up getting everything...
        try:
            conf_dict = display.configure()
        except Tkinter.TclError:
            continue

        try:
            #Index 4 is the location in each of these tuples for the value
            # to make these comparisons.
            if conf_dict['height'][4] != height and \
                   conf_dict['width'][4] != width:
                display.configure(height = height, width = width)
            elif conf_dict['height'][4] != height:
                display.configure(height = height)
            elif conf_dict['width'][4] != width:
                display.configure(width = width)
        except Tkinter.TclError:
            pass

def set_title(master, intf):
    #We need to update the title if the user selected or deselected
    # an enstore system from the list.
    if intf.messages_file:
        title_name = "%s: %s" % ("entv", DEFAULT_SYSTEM_NAME)
    else:
        title_list = []
        for system_name in configurated_systems(master):
            if not is_system_enabled(system_name, master):
                continue
            else:
                title_list.append(system_name)
        if len(title_list) == 1:
            title_name = "%s: %s" % ("entv", title_list[0])
        elif len(title_list) > 1:
            title_name = "%s: %s" % ("entv", str(title_list))
        else:
            title_name = "entv"

    #(re)set the title of the window.
    master.title(title_name)
    
#########################################################################
#  Create and manage menubar 
#########################################################################

def create_menubar(menu_defaults, system_defaults, master, intf):
    if not master:
        return
    
    #Menubar attributes.
    master.entv_menubar = Tkinter.Menu(master = master)
    #Options menu.
    master.entv_option_menu = Tkinter.Menu(tearoff = 0)
    #List of Enstore systems.
    master.enstore_systems_menu = Tkinter.Menu(tearoff = 0)

    #Create the animate check button and set animate accordingly.
    master.entv_do_animation = Tkinter.BooleanVar()
    #By default animation is off.  If we need to turn animation, do so now.
    #if menu_defaults['animate'] == enstore_display.ANIMATE:
    master.entv_do_animation.set(menu_defaults['animate'])

    #By default the connection lines match the color of the client outlines.
    master.connection_color = Tkinter.IntVar()
    master.connection_color.set(menu_defaults['connection_color'])
    
    #By default show the movers in columns.  The other choice is circular
    # which does not look good for large number of movers.
    master.layout = Tkinter.IntVar()
    master.layout.set(enstore_display.LINEAR)

    #By default do not show "greyed" out clients that are waiting in
    # their LM queue.
    master.show_waiting_clients = Tkinter.BooleanVar()
    master.show_waiting_clients.set(enstore_display.CONNECTED)
                                
    #Add the checkbutton to the menu.
    ## Note: There is no way to obtain the actual checkbutton object.
    ## This would make accessing it internally do-able.
    ## 
    ## The only way to have the check in the checkbutton turned on
    ## by default is to have the BooleanVar variable be a member
    ## of the class.  Having it as a local variable does not want to
    ## work (though I don't know why that would be).
    master.entv_option_menu.add_checkbutton(
        label = "Animate",
        indicatoron = Tkinter.TRUE,
        onvalue = enstore_display.ANIMATE,
        offvalue = enstore_display.STILL,
        variable = master.entv_do_animation,
        command = toggle_animation,
        )
    master.entv_option_menu.add_separator()
    master.entv_option_menu.add_radiobutton(
        label = "Connections use client color",
        indicatoron = Tkinter.TRUE,
        value = enstore_display.CLIENT_COLOR,
        variable = master.connection_color,
        command = toggle_connection_color,
        )
    master.entv_option_menu.add_radiobutton(
        label = "Connections use library color",
        indicatoron = Tkinter.TRUE,
        value = enstore_display.LIBRARY_COLOR,
        variable = master.connection_color,
        command = toggle_connection_color,
        )
    master.entv_option_menu.add_separator()
    master.entv_option_menu.add_radiobutton(
        label = "Linear layout",
        indicatoron = Tkinter.TRUE,
        value = enstore_display.LINEAR,
        variable = master.layout,
        command = toggle_layout,
        )
    master.entv_option_menu.add_radiobutton(
        label = "Circular layout",
        indicatoron = Tkinter.TRUE,
        value = enstore_display.CIRCULAR,
        variable = master.layout,
        command = toggle_layout,
        )
    master.entv_option_menu.add_separator()
    master.entv_option_menu.add_checkbutton(
        label = "Show Waiting Clients",
        indicatoron = Tkinter.TRUE,
        onvalue = enstore_display.WAITING,
        offvalue = enstore_display.CONNECTED,
        variable = master.show_waiting_clients,
        command = toggle_clients,
        )

    master.enstore_systems_enabled = {}
    for system_name, on_off in system_defaults.items():
        master.enstore_systems_enabled[system_name] = Tkinter.BooleanVar()
        master.enstore_systems_enabled[system_name].set(on_off)
        master.enstore_systems_menu.add_checkbutton(
            label = system_name,
            indicatoron = Tkinter.TRUE,
            onvalue = Tkinter.TRUE,
            offvalue = Tkinter.FALSE,
            variable = master.enstore_systems_enabled[system_name],
            command = toggle_systems_enabled,
            )
        
    #Added the menus to there respective parent widgets.
    master.entv_menubar.add_cascade(label = "options",
                                    menu = master.entv_option_menu)
    if not intf.messages_file and not intf.generate_messages_file:
        #Only add the list of valid systems if showing live data.  If
        # replaying past information from the messages file don't allow
        # this feature.
        #
        #Only one enstore system can be used with --generate-messages-file
        # or with espion.py at a time, so removing these options does
        # not limit any functionality under those situations.
        master.entv_menubar.add_cascade(label = "systems",
                                        menu = master.enstore_systems_menu)
    master.config(menu = master.entv_menubar)

def is_system_enabled(system_name, master):
    ese = getattr(master, "enstore_systems_enabled", {})
    tmp = ese.get(system_name, None)
    if tmp == None:
        return False
    return bool(tmp.get())

#Return triple of the number of Enstore systems enabled for display,
# disabled for display and the total number.
def systems_enabled_statistics(master):
    ese = getattr(master, "enstore_systems_enabled", {})
    enabled = 0
    disabled = 0
    for boolean in ese.values():
        if boolean.get():
            enabled = enabled + 1
        else:
            disabled = disabled + 1

    return (enabled, disabled, len(ese.keys()))

def configurated_systems(master):
    ese = getattr(master, "enstore_systems_enabled", {})
    return ese.keys()

def toggle_animation():
    global displays

    for display in displays:
        if display.master.entv_do_animation.get() == enstore_display.ANIMATE:
            if not display.after_smooth_animation_id:
                display.after_smooth_animation_id = display.after(
                    enstore_display.ANIMATE_TIME, display.smooth_animation)
        else: #enstore_display.STILL
            if display.after_smooth_animation_id:
                display.after_cancel(display.after_smooth_animation_id)
                display.after_smooth_animation_id = None
                

def toggle_connection_color():
    global displays
    
    #Update the colors for the connections all at once.  The other way to
    # do this would be to poll the value of
    # display.master.connection_color.get() for every frame of animation.
    # that would be a big waste of CPU.
    for display in displays:
        cc = display.master.connection_color.get()
        for connection in display.connections.values():
            connection.update_color(cc)

def toggle_layout():
    global displays
    
    #Relocate where each mover is shown on the screen.  Either in the
    # LINEAR (default) or CIRCULAR patterns.
    for display in displays:
        display.reposition_canvas(force=1)

def toggle_clients():
    global displays
    
    #Reserved for future use.

    #This function could be used to show or hide all known waiting clients
    # at once, instead of letting them slowly build up over time.

def toggle_systems_enabled():
    global displays
    global master_windowframe
    global intf_of_entv

    #Hopefully, we can create and destroy display panels without needing
    # to destroy and create all of them.
    for system_name, enabled in \
            master_windowframe.enstore_systems_enabled.items():
        if is_system_enabled(system_name, master_windowframe):
            for display in displays:
                if display.system_name == system_name:
                    break  #System already enabled.
            else:
                #Need to add display.
                new_display = make_display_panel(master_windowframe,
                                                 system_name,
                                                 None, intf_of_entv)
                displays.append(new_display)
                start_messages_thread(system_name, intf_of_entv)
        else:
            for display in displays:
                if display.system_name == system_name:
                    destroy_display_panel(display)
                    displays.remove(display)
                    #Need to destroy messages thread for this system.
                    break

    #Resize the displays to account for the change in the number of displays.
    resize()
    #Need to retitle the main window with the new list of Enstore systems.
    set_title(master_windowframe, intf_of_entv)

#########################################################################
#  Interface class
#########################################################################

class EntvClientInterface(generic_client.GenericClientInterface):

    def __init__(self, args=sys.argv, user_mode=1):
        self.verbose = 0
        generic_client.GenericClientInterface.__init__(self, args=args,
                                                       user_mode=user_mode)

    def valid_dictionaries(self):
        return (self.help_options, self.entv_options)
    
    # parse the options like normal but make sure we have other args
    def parse_options(self):
        self.capture_timeout = 120  #seconds for capture.
        self.dont_show = ""
        self.verbose = 0
        self.display = os.environ.get("DISPLAY", ":0.0")
        self.generate_messages_file = 0
        self.messages_file = ""
        self.profile = 0
        self.version = 0
        self.timeout = 3
        self.retries = 3
        generic_client.GenericClientInterface.parse_options(self)

    entv_options = {
        option.CAPTURE_TIMEOUT:{option.HELP_STRING:"Duration (in seconds) that"
                                " --generate-messages-file should display"
                                " new transfers. (default 120 seconds.)",
                                option.VALUE_USAGE:option.REQUIRED,
                                option.VALUE_TYPE:option.INTEGER,
                                option.USER_LEVEL:option.USER,},
        option.DISPLAY:{option.HELP_STRING:"Specify the screen entv should"
                                           " display to.",
                        option.VALUE_USAGE:option.REQUIRED,
                        option.VALUE_TYPE:option.STRING,
                        option.USER_LEVEL:option.USER,},
        option.DONT_SHOW:{option.HELP_STRING:"Don't display the movers that"
                          " belong to the specified library manager(s).",
                          option.VALUE_USAGE:option.REQUIRED,
                          option.VALUE_TYPE:option.STRING,
                          option.VALUE_LABEL:"LM short name,...",
                          option.USER_LEVEL:option.USER,},
        option.GENERATE_MESSAGES_FILE:{option.HELP_STRING:
                                     "Output to standard output the sequence"
                                     " of messages that create the display."
                                     "  This is done in a visually clean way.",
                                     option.VALUE_USAGE:option.IGNORED,
                                     option.USER_LEVEL:option.ADMIN,},
        option.MESSAGES_FILE:{option.HELP_STRING:
                              "Use 'canned' version of entv.",
                              option.VALUE_USAGE:option.REQUIRED,
                              option.VALUE_TYPE:option.STRING,
                              option.VALUE_LABEL:"messages_file",
                              option.USER_LEVEL:option.ADMIN,},
        option.PROFILE:{option.HELP_STRING:"Display profile info on exit.",
                            option.VALUE_USAGE:option.IGNORED,
                            option.USER_LEVEL:option.ADMIN,},
        option.RETRIES:{option.HELP_STRING:"Number of times to wait " \
                        "for an answer.",
                        option.VALUE_USAGE:option.REQUIRED,
                        option.VALUE_TYPE:option.INTEGER,
                        option.USER_LEVEL:option.USER,},
        option.TIMEOUT:{option.HELP_STRING:"Number of seconds to wait " \
                        "for an answer.  If value is negative, wait forever.",
                        option.VALUE_USAGE:option.REQUIRED,
                        option.VALUE_TYPE:option.INTEGER,
                        option.USER_LEVEL:option.USER,},
        option.VERBOSE:{option.HELP_STRING:"Print out information.",
                        option.VALUE_USAGE:option.REQUIRED,
                        option.VALUE_TYPE:option.INTEGER,
                        option.USER_LEVEL:option.USER,},
        option.VERSION:{option.HELP_STRING:
                        "Display entv version information.",
                        option.DEFAULT_TYPE:option.INTEGER,
                        option.DEFAULT_VALUE:1,
                        option.USER_LEVEL:option.USER,},
        }

#########################################################################
#  main
#########################################################################

def main(intf):
    global stop_now
    global displays
    global master_windowframe

    #Setup trace levels with thread names.
    threading.currentThread().setName("MAIN")
    Trace.init("ENTV", True)
    for x in xrange(0, intf.verbose + 1):
        Trace.do_print(x)
    if intf.generate_messages_file:
        Trace.do_message(MESSAGES_LEVEL)

    #Trace.do_print(LOCK_LEVEL)

    #Switch --generate-messages-file has a restriction, only one enstore
    # system at a time.
    if len(intf.args) > 1 and intf.generate_messages_file:
        print intf.args
        try:
            sys.stderr.write("--generate-messages-file cannot be specified"
                             " with multiple enstore systems.\n")
            sys.stderr.flush()
        except IOError:
            pass
        sys.exit(1)

    #Pointer to alternate window that shows detailed statistics about one
    # mover at a time.
    mover_display = None

    #Get the main window.
    master = Tkinter.Tk(screenName = intf.display)
    master_windowframe = master #Global name for callbacks to use.
    master.withdraw()
    master.title("entv")
    master.bind('<Configure>', resize)
    menu_defaults = {'animate' : enstore_display.STILL,
                     'connection_color' : enstore_display.CLIENT_COLOR }

    #Get the information from the configuration server or fake it if
    # reading from messages file.
    if intf.messages_file:
        csc = None

        system_name = DEFAULT_SYSTEM_NAME

        cscs = {}
    else:
        # get a configuration client
        csc = get_csc()

        if csc == None:
            cscs = {}
        else:
            cscs = enstore_display.get_all_systems(csc=csc)
            if cscs == None:
                cscs = {}

    #Configure the menubar.
    system_defaults = {}
    if intf.messages_file:
        system_defaults[system_name] = 1
    elif len(cscs) > 0:
        #If we have a response from the configuration server, we use that.
        for system_name, current_csc in cscs.items():
            if intf.args and system_name in intf.args:
                system_defaults[system_name] = 1  #Enable this system.
            elif not intf.args and \
                     current_csc.server_address == csc.server_address:
                system_defaults[system_name] = 1  #Enable this system.
            else:
                system_defaults[system_name] = 0  #Disable this system.
    else:
        #If we don't have a response from the configuration server, let's
        # fallback to using saved information in the .entvrc file.
        entvrc_dict = get_entvrc(csc=None)
        for config_hostname in entvrc_dict['system_info'].keys():
            if intf.args and config_hostname in intf.args:
                system_defaults[config_hostname] = 1  #Enable this system.
            else:
                system_defaults[config_hostname] = 0  #Disable this system.
        
    create_menubar(menu_defaults, system_defaults, master, intf)

    #Variables that control the stopping or starting of entv.
    continue_working = 1
    restart_entv = False
    while continue_working:

        #We need to update the title if the user selected or deselected
        # an enstore system from the list.
        set_title(master, intf)

        #Set this to not stop.
        stop_now = 0

        #Get the entvrc file information.  Get this every time so that
        # if something changes, then we can pick up the changes.
        entvrc_dict = get_entvrc(csc=csc)

        #If we hang, making the display panels, try and catch this situation
        # and restart the entv process.  It has been observed that
        # enstore_display.get_font() can hang, because of the
        # tkFont.Font.metrics() call; there probably are others.
        signal.signal(signal.SIGALRM, to_restart_entv_alarm_signal_handler)
        signal.alarm(TEN_MINUTES) #Start the alarm clock.

        #Obtain the list of display panels.  There will be one for each
        # enstore system requested by the user.
        try:
            displays = make_display_panels(master, entvrc_dict,
                                           mover_display, intf)
        except (KeyboardInterrupt, SystemExit):
            raise sys.exc_info()[0], sys.exc_info()[1], sys.exc_info()[2]
        except:
            exc, msg = sys.exc_info()[:2]
            import traceback
            traceback.print_tb(sys.exc_info()[2])
            #Report on the error.
            try:
                message = "Failed to make panels: (%s, %s)\n"
                sys.stderr.write(message % (str(exc), str(msg)))
                sys.stderr.flush()
            except IOError:
                pass

            displays = []

        signal.alarm(0) #Stop the alarm clock.

        Trace.trace(1, "starting message threads")
        
        #On average collecting the status of all the movers takes 10-15
        # seconds.  We don't want to wait that long.  This can be done
        # in parallel to displaying live data.

        #First acquire the startup lock.  This will delay the other threads
        # from consuming resources that would be better spent on this
        # thread at the moment.  This lock is released inside of
        # enstore_display.mainloop().
        enstore_display.acquire(enstore_display.startup_lock, "startup_lock")

        if intf.messages_file:
            #Read from file the event relay messages to process.
            start_messages_thread("Enstore", intf)
        else:
            #Start a thread for each event relay we should contact.
            for system_name in configurated_systems(master):
                if not is_system_enabled(system_name, master):
                    continue
                
                Trace.trace(1, "starting thread for %s" % (system_name,))
                start_messages_thread(system_name, intf)
                Trace.trace(1, "started thread for %s" % (system_name,))

        #Let the other startup threads go.
        enstore_display.release(enstore_display.startup_lock, "startup_lock")

        Trace.trace(1, "started message threads")

        #Regardless of the window state, we need to call update() so that
        # the window geometry gets updated.  This will allow for the
        # correct geometry to be set so that it does what we want when
        # the user de-iconifies the window.
        master.update()
        #If the window is "normal" (widow is display), "iconic" (user minimized
        # the window or user switched to a different desktop) or an "icon"
        # don't modify the window state.  The window state is only set to
        # "withdrawn" at initialization.
        if master.state() == "withdrawn":
            master.deiconify()
            master.lift()
            master.update()

        # This would be a good time to cleanup before things get hairy.
        gc.collect()
        del gc.garbage[:]

        signal.signal(signal.SIGALRM, to_restart_entv_alarm_signal_handler)
        signal.alarm(TEN_MINUTES) #Start the alarm clock.

        Trace.trace(1, "starting mainloop")

        #Loop until user says don't.
        try:
            master.mainloop()
        except (KeyboardInterrupt, SystemExit):
            raise sys.exc_info()[0], sys.exc_info()[1], sys.exc_info()[2]
        except:
            exc, msg = sys.exc_info()[:2]
            import traceback
            traceback.print_tb(sys.exc_info()[2])
            #Report on the error.
            try:
                message = "Exited mainloop unexpectedly: (%s, %s)\n"
                sys.stderr.write(message % (str(exc), str(msg)))
                sys.stderr.flush()
            except IOError:
                pass

        Trace.trace(1, "left mainloop")

        #When we exec() a new process due to memory consumed, stop the alarm
        # because the alarm will still be scheduled for the same process ID.
        signal.alarm(0) #Stop the alarm clock.

        #Tell other thread(s) to stop.
        stop_now = 1

        #Set the geometry of the .entvrc file (if necessary).
        if not intf.messages_file and \
               systems_enabled_statistics(master)[0] == 1:
            #Find the one Enstore system that is being displayed.
            for system_name, current_csc in cscs.items():
                if is_system_enabled(system_name, master):
                    #Since we know only one display is currently being
                    # displayed, save the geometry.
                    set_entvrc(displays[0], current_csc.server_address)
                    break

        #Cleanup the display.
        continue_working = destroy_display_panels()

        #Wait for the other threads to finish.
        Trace.trace(1, "waiting for threads to stop")
        stop_messages_threads()
        Trace.trace(1, "message threads finished")

        #Reclaim all of display's resources now.
        del displays[:]
        del entvrc_dict
        #del mover_list[:]
        #Don't move the following into threads in enstore_display functions.
        # There are wierd references that prevent them from being reclaimed
        # by the garbage collector.
        enstore_display.message_queue.clear_queues()
        enstore_display.request_queue.clear_queues()

        #Force reclaimation of memory (and other resources) and also
        # report if leaks are occuring.
        do_restart_entv = cleanup_objects()

        ### Do we really want a new entv process?  This has the issue of
        ### creating a new top level window which will be created on the
        ### users current desktop, not the one entv was started on.
        #If entv is consuming 50% or more of physical memory, restart
        # the entv process.
        if continue_working and do_restart_entv:
            #At this point a lot of objects have been unable to be freed.
            # Thus, we should re-exec() the entv process.
            message = "Restarting entv from excessive memory usage."
            Trace.trace(0, message, out_fp=sys.stderr)
            restart_entv()

        if continue_working:
            master.update()
 
if __name__ == "__main__":

    delete_at_exit.setup_signal_handling()

    intf_of_entv = EntvClientInterface(user_mode=0)

    if intf_of_entv.profile:
        #If the user wants to see the profile of entv...
        import profile
        import pstats
        profile.run("main(intf_of_entv)", "/tmp/entv_profile")
        p = pstats.Stats("/tmp/entv_profile")
        p.sort_stats('cumulative').print_stats(100)
    elif intf_of_entv.version:
        #Just print the version of entv.
        print entv_client_version()
    else:
        main(intf_of_entv)
        sys.exit(0)
