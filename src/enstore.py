#!/usr/bin/env python

###############################################################################
# src/$RCSfile$   $Revision$
#
# in order to add support for a new 'client', add a section to the following
# structures -
#             import the appropriate file
#             server_functions
#             server_options (if this new client can be run by a normal user)


# system imports
#
import sys
import re
import os
import string
import errno

# enstore imports
import setpath

import e_errors
import alarm_client
import configuration_client
import configuration_server
import file_clerk_client
import inquisitor_client
import library_manager_client
import log_client
import media_changer_client
import mover_client
import monitor_client
import volume_clerk_client
import enstore_up_down
import enstore_saag
import dbs
import ratekeeper_client
import pnfs

CMD1 = "%s%s%s"%(dbs.CMDa, "startup", dbs.CMDb)
#CMD1 = "%s%s%s"%(dbs.CMDa, "startup", dbs.CMDc)

DEFAULT_AML2_NODE = "rip10"

server_functions = { "alarm" : [alarm_client.AlarmClientInterface,
                                alarm_client.do_work],
                     "configuration" : [configuration_client.ConfigurationClientInterface,
                                        configuration_client.do_work],
                     "file" : [file_clerk_client.FileClerkClientInterface,
                               file_clerk_client.do_work],
                     "inquisitor" : [inquisitor_client.InquisitorClientInterface,
                                     inquisitor_client.do_work],
                     "library" : [library_manager_client.LibraryManagerClientInterface,
                                  library_manager_client.do_work],
                     "log" : [log_client.LoggerClientInterface,
                              log_client.do_work],
                     "media" : [media_changer_client.MediaChangerClientInterface,
                                media_changer_client.do_work],
                     "monitor" : [monitor_client.MonitorServerClientInterface,
                                monitor_client.do_work],
#                     "mover" : [mover_client.MoverClientInterface,
#                                mover_client.do_work],
                     "up_down" : [enstore_up_down.UpDownInterface,
                                  enstore_up_down.do_work],
                     "system" : [enstore_saag.SaagInterface,
                                 enstore_saag.do_work],
                     "schedule" : [inquisitor_client.InquisitorClientInterface,
                                   inquisitor_client.do_work],
                     "volume" : [volume_clerk_client.VolumeClerkClientInterface,
                                 volume_clerk_client.do_work],
		     "database" : [dbs.Interface,
			           dbs.do_work],
                     "ratekeeper" : [ratekeeper_client.RatekeeperClientInterface,
                                     ratekeeper_client.do_work],
                     }

server_interfaces = {"pnfs":[pnfs.PnfsInterface,
                             pnfs.do_work],
                     "mover" : [mover_client.MoverClientInterface,
                                mover_client.do_work],
                     }

def get_farmlet(default):
    if len(sys.argv) > 1:
        return sys.argv[1]
    else:
        return default

def get_argv2(default=" "):
    if len(sys.argv) > 2:
        return sys.argv[2]
    else:
        return default


local_scripts = {"enstore-start":[("enstore-start", sys.argv[2:])],
                 "start":[("enstore-start", sys.argv[2:])],
                 "enstore-stop":[("enstore-stop", sys.argv[2:])],
                 "stop":[("enstore-stop", sys.argv[2:])],
                 "restart":[("enstore-stop", sys.argv[2:]),
                            ("enstore-start --nocheck", sys.argv[2:])],
                 "ping":[("enstore-ping", sys.argv[2:])],
                 "qping":[("quick-ping", sys.argv[2:])],
                 "backup":[("python $ENSTORE_DIR/src/backup.py",sys.argv[2:])],
                 "aml2":[('enrsh %s "sh -c \'. /usr/local/etc/setups.sh;setup enstore;dasadmin listd2 | grep rip;dasadmin list rip1\'"',
                          [],
                          "self.node"),
                         ],
                 "ps":[("EPS", sys.argv[2:])],
                 }

remote_scripts = {"Estart":[("enstore", "%s enstore-start %s%s" % (CMD1,
                                                get_farmlet("enstore"),
                                                      dbs.CMD2))],
                  "Estop":[("enstore-down",
                            "%s enstore-stop %s%s" % (CMD1,
                                                get_farmlet("enstore-down"),
                                                      dbs.CMD2),
                            "prompt"), ],
                  "Erestart":[("enstore-down",
                               "%s enstore-stop %s%s" % (CMD1,
                                                  get_farmlet("enstore-down"),
                                                         dbs.CMD2)),
                              ("enstore",
                               "%s enstore-start %s%s" % (CMD1, "%s",
                                                          dbs.CMD2),
                               ("get_farmlet('enstore')",))],
                  "EPS":[("enstore",
                          "source /usr/local/etc/setups.sh;setup enstore;EPS"),
                         ],
                  "ls":[("enstore",
                         "ls %s",
                         ("os.getcwd()",),)],
                  }

# these general functions perform various system functions
def call_function(executable, argv):
    # pull out the arguments from argv and create a string that can be
    # passed to os.system.
    str = executable
    for arg in argv:
        str = "%s %s"%(str, arg)
    return os.system(str)>>8


def prompt_user(command="", node=""):
    sys.stdout.write("Please confirm: %s enstore on %s [y/n def:n] : "%(command, 
									node))
    return sys.stdin.readline()

def no_argv_num(num):
    if len(sys.argv) < num:
	return 1
    else:
	return None

def no_argv2():
    return no_argv_num(2)

def no_argv3():
    return no_argv_num(3)

def do_rgang_command(fdefault, command):
    farmlet = get_farmlet(fdefault)
    print 'rgang %s \"%s\"'%(farmlet, command)
    return os.system('rgang %s \"%s\"'%(farmlet, command))




class EnstoreInterface:

    def __init__(self, user_mode):
        self.user_mode = user_mode
        self.match_server()
        #self.match_script()

    #server_intfs = {}

    # get a new server interface and store it to use later if needed
    def get_server_intf(self, skey, flag):
        functions = server_functions.get(skey, None)
        if functions:
            self.server_intf = functions[0](flag,)

            return self.server_intf
        else:
            return None

    # return a list of the allowed options given the command key (server)
    def get_options(self, skey):
        opts = self.server_options.get(skey, [])
        if opts:
            opts = opts + GenericUserOptions.get_options(self)
        return opts

    def get_valid_options(self, skey):
        if self.user_mode:
            opts = self.get_options(skey)
        else:
            #intf = self.get_server_intf(skey, 1)
            intf = server_functions[skey][0]()
            if type(intf.options) == type({}):
                opts = intf.options.keys()
            elif not intf is None:
                opts = intf.options()
            else:
                # this was not a valid server key
                opts = []
        return opts

    def get_valid_servers(self):
        if self.user_mode:
            # user mode
            servers = self.server_options.keys()
            servers.sort()
        else:
            # admin mode, all are allowed
            servers = server_functions.keys()
            servers.sort()
        return servers

    # figure out if the passed key is a valid server key
    def is_valid_server(self, skey):
        if self.user_mode:
            return self.server_options.has_key(skey)
        else:
            return 1


    def match_server(self):
        # the user can enter the least amount of text that uniquely
        # identifies the desired server. (e.g. - i for inquisitor).  so get
        # the full server name here.
        all_servers = self.get_valid_servers() + local_scripts.keys() + \
                      remote_scripts.keys() + server_interfaces.keys()
        total_matches = self.find_server_match(all_servers)
        if total_matches > 1:
            # not enough info was entered and we matched more than
            # once.  in any case, print help & exit
            self.print_valid_servers()
        elif total_matches == 1:
            # look through the command line and verify that it only consists of
            # allowed options.
            # remove the 'enstore' name from sys.argv
            del sys.argv[0]
            
            # call the servers' interface, since we pass in a list of valid
            # options, we do not have to validate them, getopts does it
            self.server_intf = self.get_server_intf(self.matched_server, 1)

        else:
            # we did not match anything.  if this is user_mode, check if the
            # entered server is a real one, just not a valid one.  if so, print
            # a list of the valid servers, else print full help
            if self.user_mode:
                servers = server_functions.keys()
                total_matches = self.find_server_match(servers)
                if total_matches == 0:
                    # nope, this is a bogus first arg, we don't know what was
                    # meant, print all the help
                    #self.print_help()
                    pass
                else:
                    # this was an existing but invalid server, print the valid
                    # ones
                    #self.print_valid_servers()
                    pass
            else:
                # we were allowed access to all servers but did not match on
                # any of them, so we don't know what was meant, print all help
                #self.print_help()
                pass
            self.server_intf = None
            self.matched_server = ""

    def find_server_match(self, servers):
        total_matches = 0
        try:
            pattern = "^%s"%(sys.argv[1],)
            for server in servers:
                match = re.match(pattern, server, re.I)
                if not match is None:
                    total_matches = total_matches + 1
                    self.matched_server = server
            return total_matches
        except (TypeError, IndexError):
            return 0  #total_matches = 0 

    def print_valid_servers(self):
        servers = self.get_valid_servers()
        print "\nERROR: Allowed servers/commands are : "
        for server in servers:
            print "\t%s"%(server,)

    def print_valid_options(self, server):
        opts = self.get_valid_options()
        print "\nERROR: Allowed options for %s are : "
        for opt in opts:
            print "\t%s"%(opt,)

    def print_usage_line(self, server, intf):
        if self.user_mode:
            # only print the options we support
            intf.print_usage_line(self.get_valid_options(server))
        else:
            intf.print_usage_line()

    def get_usage_line(self, server, intf):
        if self.user_mode:
            # only print the options we support
            return intf.get_usage_line(self.get_valid_options(server))
        else:
            return intf.get_usage_line()
            
            
    def print_help(self):
        cmd = "enstore"
        if not self.user_mode:
            call_function("pnfsa", "")
            print "\n%s start   [--just server --ping --asynch --nocheck]"%(cmd,)
            print "%s stop    [--just server --xterm server]"%(cmd,)
            print "%s restart [--just server --xterm server]"%(cmd,)
            print "%s ping    [timeout-seconds]"%(cmd,)
            print "%s qping   [timeout-seconds]"%(cmd,)
            print "%s ps                 (list enstore related processes)"%(cmd,)
            print "\n%s Estart   farmlet   (global Enstore start on all farmlet nodes)"%(cmd,)
            print "%s Estop    farmlet   (global Enstore stop on all farmlet nodes)"%(cmd,)
            print "%s Erestart farmlet   (global Enstore restart on all farmlet nodes)"%(cmd,)
            print "\n%s EPS      farmlet   (global Enstore-associated ps on all farmlet nodes)"%(cmd,)
            print "\n%s aml2               (lists current mount state & queue list on aml2 robot)"%(cmd,)
        else:
            call_function("pnfs", "")
        print "\n"
        servers = self.get_valid_servers()
        for server in servers:
            # print the usage line for each server
            print
            print "%s %s "%(cmd, server),
            intf = self.get_server_intf(server, 0)
            if intf:
                print self.get_usage_line(server, intf),
            print " "

class Enstore:

    timeout = 2
    retry = 2
    mc_type = ("type", "AML2_MediaLoader")

    def __init__(self, intf):
        self.user_mode = intf.user_mode

        self.server_intf = intf.server_intf
        self.matched_server = intf.matched_server
        self.intf = intf

        # find the node to rsh to.  this node is the one associated with
        # the media changer of type "AML2_MediaLoader"
        #   if the configuration server is running, get the information
        #   from it.  if not, just read the config file pointed to by
        #   $ENSTORE_CONFIG_FILE.  if neither of these works, assume node
        #   in DEFAULT_AML2_NODE.
        if not self.get_config_from_server() and \
           not self.get_config_from_file():
            self.node = DEFAULT_AML2_NODE

    # try to get the configuration information from the config server
    def get_config_from_server(self):
        rtn = 0
        port = os.environ.get('ENSTORE_CONFIG_PORT', 0)
        port = string.atoi(port)
        if port:
            # we have a port
            host = os.environ.get('ENSTORE_CONFIG_HOST', 0)
            if host:
                # we have a host
                csc = configuration_client.ConfigurationClient((host, port))
                try:
                    t = csc.get_dict_entry(self.mc_type, self.timeout,
                                           self.retry)
                    servers = t.get("servers", "")
                    if servers:
                        # there may be more than one, we will use the first
                        t = csc.get(servers[0], self.timeout,
                                    self.retry)
                        # if there is no specified host, use the default
                        self.node = t.get("host", DEFAULT_AML2_NODE)
                    else:
                        # there were no media changers of that type, use the
                        # default node
                        self.node = DEFAULT_AML2_NODE
                    rtn = 1
                except errno.errorcode[errno.ETIMEDOUT]:
                    pass
        return rtn

    # try to get the configuration information from the config file
    def get_config_from_file(self):
        rtn = 0
        # first look to see if $ENSTORE_CONFIG_FILE points to the config file
        cfile = os.environ.get("ENSTORE_CONFIG_FILE", "")
        if cfile:
            dict = configuration_server.ConfigurationDict()
            if dict.read_config(cfile) == (e_errors.OK, None):
                # get the list of media changers of the correct type
                slist = dict.get_dict_entry(self.mc_type)
                if slist:
                    # only use the first one
                    server_dict = dict.configdict[slist[0]]
                    # if there is no specified host use the default
                    self.node = server_dict.get("host", DEFAULT_AML2_NODE)
                    rtn = 1
        return rtn

    # get the node name where the aml2 robot media changer is running
    def get_aml2_node(self):
        pass

    # make sure the user wanted to start d0en nodes while on stken and vice versa
    def verify_node(self,node):
        if len(node)<=3:
            return
        # 1st three letters return the "production" cluster, almost
        gang = node[0:3]
        # there are just 3 clusters we deal with right now... (code this better?)
        clusters = ('stk','d0e','rip')
        if gang in clusters:
            thisnode = os.uname()[1]
            thisgang = thisnode[0:3]
            if thisgang not in clusters:
                return 1
            # if we are trying to execute a command from a node in the same cluster, just do it
            if thisgang == gang:
                return 1
            # rip9 and rip10 are special cases
            if thisgang == 'stk' and node[0:4] == 'rip9':
                    return 1
            if len(node) > 4:
                if thisgang == 'stk' and node[0:5] == 'rip10':
                    return 1
            # need to confirm if user really wanted to do this
            print "You want to execute a command on",node,"but you are running on",thisnode
            print "This doesn't seem right."
            answer = prompt_user("Is this want you want to do - execute ",node)
            if answer[0] == "y" or answer[0] == "Y":
                return 1
            else:
                print 'command canceled'
                return 0
        else:
            return 1

    def prompt(self, command):
        #command is a tuple
        # [0] is the default farmlet
        # [1] is the command to rgang
        # [2] arguments to assign dynamicaly
        # [-1] optionaly contains "prompt" to ask the user for confermation.
        answer = "y"
        try:
            if command[-1] == "prompt":
                if no_argv2():
                    answer = prompt_user(command = "Stopping",
                                         node = "all nodes")
                elif no_argv3():
                    answer = prompt_user(command = "Stopping",
                                node = "farmlet %s" % get_farmlet(command[0]))
        except IndexError:
            pass
        return answer
           

    # this is where all the work gets done
    def do_work(self):
        #        if self.matched_server: #len(sys.argv) > 1:
        arg1 = self.matched_server
        #        else:
        #            # no parameters were entered
        #            arg1 = ''


        #execute local scripts
        if arg1 in local_scripts.keys():
            l_script = local_scripts.get(arg1, None)
            #l_script contains a list of tuples.
            for command in l_script:
                #each tuple in l_script is two items long.
                try:
                    executable = command[0] % command[2:]
                except IndexError, TypeError:
                    executable = command[0]
                rtn = call_function(executable, command[1])

        #handles old interface style
        elif arg1 in server_functions.keys():
            rtn = server_functions[self.matched_server][1](self.server_intf)
        
        
        #handles new interface style
        elif arg1 in server_interfaces.keys():
            intf = server_interfaces[arg1][0](args=sys.argv[:],
                                              user_mode=self.user_mode)
            rtn = server_interfaces[arg1][1](intf)

        #execute remote scripts
        elif arg1 in remote_scripts.keys():
            r_script = remote_scripts.get(arg1, None)
            #r_script contains a list of tuples.
            for command in r_script:
                #each tuple in r_script is two items long.
                farmlet = get_farmlet(command[0])
                if self.verify_node(farmlet):
                    #if command[-1] contains the string "prompt" then it
                    # prompts the user for confermation under some cases.
                    # If no prompt is necessary returns "y".
                    answer = self.prompt(command)

                    try:
                        if command[2] != "prompt":

                            tuple = ()
                            for item in command[2]:
                                tuple = tuple + (eval(item),)
                            executable = command[1] % tuple
                        else:
                            executable = command[1]
                    except IndexError, TypeError:
                        executable = command[1]

                    if answer[0] == "y" or answer[0] == "Y":
                        rtn = do_rgang_command(farmlet, executable)
                    else:
                        rtn = 0
                else:
                    rtn = 0

        # arg1 == "help" or arg1 == "--help" or arg1 == '':
        else:
            rtn = 0
            self.intf.print_help()
            
        sys.exit(rtn)
