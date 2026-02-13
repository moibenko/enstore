#!/usr/bin/env python

"""
Keeps the system configuration information and provides it to the rest of the system.
"""
from __future__ import print_function

# system imports
from future import standard_library
standard_library.install_aliases()
from builtins import str
from builtins import range
from builtins import object
from future.utils import raise_
import sys
import types
import os
import traceback
import socket
import time
import copy
import threading
import errno
import smtplib
import pwd
import queue

# enstore imports
# import setpath
import dispatching_worker
import generic_server
import event_relay_client
import event_relay_messages
import enstore_constants
import enstore_functions2
import option
import Trace
import e_errors
import hostaddr
import callback
import udp_client
import host_config
import delete_at_exit
import ports_to_use

MY_NAME = enstore_constants.CONFIGURATION_SERVER  # "CONFIG_SERVER"
SEQUENTIAL_QUEUE_SIZE = enstore_constants.SEQUENTIAL_QUEUE_SIZE
PARALLEL_QUEUE_SIZE = enstore_constants.PARALLEL_QUEUE_SIZE
MAX_THREADS = enstore_constants.MAX_THREADS

configdict = {} # define as global, otherwise exec in Pyhton 3 does not work

class ConfigurationDict(object):
    """
    Loads, updates configuration dictionary and provides configuration helper methods.
    """

    def __init__(self):
        self.serverlist = {}
        self.config_load_timestamp = None
        self.use_thread = 1
        self.system_name = None  # Cache return value from _get_system_name().
        self.cached_domains = None  # Cache return value from _get_domains().
        # The average dump2() execution time, in seconds, for these three
        # copy levels are (n = 9, for each):
        # deepcopy: 0.017653094397633334
        # copy: 0.0063026481204566673
        # direct reference: 0.0062727663252077782
        # We are going with copy, since it is just as fast as a direct
        # reference and the way self.configdict is assigned in read_config(),
        # there should be no possible way for any sub-ticket values to
        # be shared between a new and old configdict.
        self.do_copies = 1  # 2=deepcopy, 1=copy, 0=object reference

        # To keep the code as clean as possible, only ConfigurationDict
        # functions use these locks.  ConfigurationServer class functions use
        # wrapper functions that access these locks in a thread safe manner.
        self.config_lock = threading.Lock()
        self.member_lock = threading.Lock()

    ####################################################################
    # read_config(), verify_and_update_config() and load_config()
    # are the three functions used to read in the configuration file.

    def read_config(self, configfile):
        """
        Read configuration from the configuration file.

        :type configfile: :obj:`str`
        :arg configfile: configuration file name
        :rtype: :obj:`tuple` (:obj:`str` - error code, :obj:`str` - details)
        """

        global configdict
        try:
            f = open(configfile, 'r')
        except (OSError, IOError) as msg:
            if msg.args[0] in [errno.ENOENT]:
                status = (e_errors.DOESNOTEXIST,
                      "Configuration Server: read_config %s: does not exist"
                          % (configfile,))
            else:
                status = (e_errors.OSERROR,
                          "Configuration Server: read_config %s: %s"
                          % (configfile, str(msg)))
            Trace.log(e_errors.ERROR, status[1])
            return status
        code = ''.join(f.readlines())
        # Lint hack, otherwise lint can't see where configdict is defined.
        configdict = {}
        #del configdict
        #configdict = {}

        try:
            exec(code, globals())
            # I would like to do this in a restricted namespace, but
            # the dict uses modules like e_errors, which it does not import
        except:
            exc, msg, tb = sys.exc_info()
            fmt = traceback.format_exception(exc, msg, tb)[2:]
            # report the name of the config file in the traceback instead of
            # "<string>"
            fmt[0] = fmt[0].replace("<string>", configfile)
            message = "Configuration Server: " + ''.join(fmt)
            Trace.log(e_errors.ERROR, message)
            os._exit(-1)
        # ok, we read entire file - now set it to real dictionary
        self.configdict = configdict
        return (e_errors.OK, None)

    def verify_and_update_config(self):
        """
        Verifies that configuration file is syntactically correct and has no conflicts.
        If no errors were detected updates current configuration.

        :rtype: :obj:`tuple` (:obj:`str` - error code, :obj:`str` - details)
        """

        self.serverlist = {}
        conflict = 0
        for key in list(self.configdict.keys()):
            if 'status' not in self.configdict[key]:
                self.configdict[key]['status'] = (e_errors.OK, None)
            for insidekey in list(self.configdict[key].keys()):
                if insidekey == 'host':
                    if 'hostip' not in self.configdict[key]:
                        self.configdict[key]['hostip'] = \
                            hostaddr.name_to_address(
                            self.configdict[key]['host'])
                    if 'port' not in self.configdict[key]:
                        self.configdict[key]['port'] = -1
                    # check if server is already configured
                    for configured_key in list(self.serverlist.keys()):
                        if (self.serverlist[configured_key][1] ==
                            self.configdict[key]['hostip'] and
                            self.serverlist[configured_key][2] ==
                            self.configdict[key]['port'] and
                            self.configdict[key]['port'] != -1):
                            message = "Configuration Conflict detected "\
                                  "for hostip " +\
                                  repr(self.configdict[key]['hostip']) + \
                                  "and port " + \
                                  repr(self.configdict[key]['port'])
                            Trace.log(10, message)
                            conflict = 1
                            break
                    if not conflict:
                        self.serverlist[key] = (
                            self.configdict[key]['host'],
                            self.configdict[key]['hostip'],
                            self.configdict[key]['port'])
                    break

        if conflict:
            return (e_errors.CONFLICT, "Configuration conflict detected. "
                   "Check configuration file")

        return (e_errors.OK, None)

    def load_config(self, configfile):
        """
        Load configuration file.

        :type configfile: :obj:`str`
        :arg configfile: configuration file name
        :rtype: :obj:`tuple` (:obj:`str` - error code, :obj:`str` - details)
        """

        # Check if config file is newer, than currently loaded
        config_file_mod_time = os.path.getmtime(configfile)
        if self.config_load_timestamp and self.config_load_timestamp >= config_file_mod_time:
            return (e_errors.ERROR, 'Configuration file is up to date')
        try:
            self.config_lock.acquire()

            # Since we are loading a new configuration file,
            # 'known_config_servers' could change.  Set, system_name to None
            # so the next call to _get_system_name() resets this value.
            self.system_name = None
            self.cached_domains = None

            status = self.read_config(configfile)
            if not e_errors.is_ok(status):
                self.config_lock.release()  # Avoid deadlocks!
                return status

            status = self.verify_and_update_config()
            if not e_errors.is_ok(status):
                self.config_lock.release()  # Avoid deadlocks!
                return status

            # We have successfully loaded the config file.
            self.config_load_timestamp = time.time()

            self.config_lock.release()  # Avoid deadlocks!
            return (e_errors.OK, None)

        # even if there is an error - respond to caller so he can process it
        except:
            exc, msg, tb = sys.exc_info()
            Trace.handle_error(exc, msg, tb)
            del tb  # Avoid resource leaks!
            self.config_lock.release()  # Avoid deadlocks!
            return (e_errors.UNKNOWN, (str((str(exc), str(msg)))))

    ####################################################################

    # get_dict_entry(), get_server_list(), get_config_keys() and
    # get_config_dict():
    # These are internal functions that pull information out of the
    # configuration in a thread safe manner.  All other functions should
    # use these functions instead of accessing self.configdict directly.

    # __get_config_value() is an internal function used by, get_dict_entry(),
    # get_server_list(), et. al.  The calling function should hold the
    # appropriate lock, self.config_lock or self.member_lock, before
    # calling this function.
    def __get_config_value(self, value, copy_level):
        try:
            t0 = time.time()
            if copy_level >= 2:
                copied_value = copy.deepcopy(value)
            elif copy_level == 1:
                copied_value = copy.copy(value)
            else:
                copied_value = value
            message = "__get_config_value: extract time: %f" \
                      % (time.time() - t0,)
            Trace.trace(25, message)
        except:
            raise_(sys.exc_info()[0], sys.exc_info()[1], sys.exc_info()[2])

        return copied_value

    def get_dict_entry(self, skeyValue):
        copy_level = self.get_copy_level()  # Avoid holding both locks at once.
        self.config_lock.acquire()
        try:
            value = self.__get_config_value(self.configdict[skeyValue],
                                            copy_level)
        except:
            self.config_lock.release()
            raise_(sys.exc_info()[0], sys.exc_info()[1], sys.exc_info()[2])
        self.config_lock.release()
        return value

    def get_config_keys(self):
        copy_level = self.get_copy_level()  #Avoid holding both locks at once.
        self.config_lock.acquire()
        try:
            key_list = self.__get_config_value(list(self.configdict.keys()),
                                               copy_level)
        except:
            self.config_lock.release()
            raise_(sys.exc_info()[0], sys.exc_info()[1], sys.exc_info()[2])
        self.config_lock.release()
        return key_list

    def get_config_dict(self):
        copy_level = self.get_copy_level()  #Avoid holding both locks at once.
        self.config_lock.acquire()
        try:
            configdict = self.__get_config_value(self.configdict, copy_level)
        except:
            self.config_lock.release()
            raise_(sys.exc_info()[0], sys.exc_info()[1], sys.exc_info()[2])
        self.config_lock.release()
        return configdict

    ## The following should use member_lock, but use config_lock to avoid
    ## need to lock two locks to safely update the data member.

    def get_server_list(self):
        copy_level = self.get_copy_level()  #Avoid holding both locks at once.
        self.config_lock.acquire()
        try:
            slist = self.__get_config_value(self.serverlist, copy_level)
        except:
            self.config_lock.release()
            raise_(sys.exc_info()[0], sys.exc_info()[1], sys.exc_info()[2])
        self.config_lock.release()
        return slist

    ## The following use member_lock instead of config_lock.

    def get_config_load_timestamp(self):
        copy_level = self.get_copy_level()  #Avoid holding both locks at once.
        self.member_lock.acquire()
        try:
            clt = self.__get_config_value(self.config_load_timestamp,
                                          copy_level)
        except:
            self.member_lock.release()
            raise_(sys.exc_info()[0], sys.exc_info()[1], sys.exc_info()[2])
        self.member_lock.release()
        return clt

    def get_threaded_imp(self):
        copy_level = self.get_copy_level()  #Avoid holding both locks at once.
        self.member_lock.acquire()
        try:
            use_thread = self.__get_config_value(self.use_thread, copy_level)
        except:
            self.member_lock.release()
            raise_(sys.exc_info()[0], sys.exc_info()[1], sys.exc_info()[2])
        self.member_lock.release()
        return use_thread

    def set_threaded_imp(self, new_value):
        self.member_lock.acquire()
        try:
            self.use_thread = new_value
        except:
            self.member_lock.release()
            raise_(sys.exc_info()[0], sys.exc_info()[1], sys.exc_info()[2])
        self.member_lock.release()
        return

    def get_copy_level(self):
        self.member_lock.acquire()
        try:
            copy_level = self.__get_config_value(self.do_copies, self.do_copies)
        except:
            self.member_lock.release()
            raise_(sys.exc_info()[0], sys.exc_info()[1], sys.exc_info()[2])
        self.member_lock.release()
        return copy_level


    def set_copy_level(self, new_value):
        self.member_lock.acquire()
        try:
            self.do_copies = new_value
        except:
            self.member_lock.release()
            raise_(sys.exc_info()[0], sys.exc_info()[1], sys.exc_info()[2])
        self.member_lock.release()
        return

    ####################################################################

    def get_movers_internal(self, ticket):
        ret = []
        if 'library' in ticket:
            # search for the appearance of this library manager
            # in all configured movers
            for srv in self.get_config_keys():
                if srv.find (".mover") != -1:
                    item = self.get_dict_entry(srv)
                    if not ticket['library']:
                        #If no library was specified, return all movers.
                        mv = {'mover' : srv,
                              'address' : (item['hostip'],
                                           item['port'])
                              }
                        ret.append(mv)
                        continue
                    for key in ('library', 'libraries'):
                        if key in item:
                            if type(item[key]) == list:
                                for i in item[key]:
                                    if i == ticket['library']:
                                        mv = {'mover' : srv,
                                              'address' : (item['hostip'],
                                                          item['port'])
                                              }
                                        ret.append(mv)
                            else:
                                if item[key] == ticket['library']:
                                    mv = {'mover' : srv,
                                          'address' : (item['hostip'],
                                                       item['port'])
                                          }
                                    ret.append(mv)
        return ret

    #This function returns the key in the 'known_config_servers' sub-ticket
    # that corresponds to this system.  If it is not there then a default
    # based on the system name is returned.
    #
    # system_name is a variable where this is cached during the
    # first time the function is called.
    #
    # This function should only be called from _get_domain(), where the
    # thread safe locking is done.
    def __get_system_name(self):

        if self.system_name == None:
            try:
                kcs = self.get_dict_entry('known_config_servers')
            except:
                kcs = {}
            server_address = os.environ.get('ENSTORE_CONFIG_HOST', "default2")

            for item in list(kcs.items()):
                if socket.getfqdn(item[1][0]) == \
                       socket.getfqdn(server_address):
                    return item[0]

            self.system_name = socket.getfqdn(server_address).split(".")[0]

        return self.system_name

    #Return the domains information in the configuration dictionary.
    # Append to the valid_domains
    def get_domains(self):

        self.member_lock.acquire()
        if getattr(self, "cached_domains", None) == None:
            should_set_now = True
        else:
            should_set_now = False
        #Release member_lock to prevent another thread from locking
        # config_lock and allowing for the possibility of a deadlock.
        self.member_lock.release()

        if should_set_now:
            t0 = time.time()
            try:
                domains = self.get_dict_entry('domains')
            except:
                #domains = None # Some error.
                domains = {}

            if type(domains) == dict:
                #Add an empty list where we expect it if there isn't one.
                if 'valid_domains' not in domains:
                    domains['valid_domains'] = []

                cached_domains = {}
                #Put the domains into the reply ticket.
                cached_domains['domains'] = domains
                #We need to insert the configuration servers domain into
                # the list.  Otherwise, the client will not have the
                # configuration server's domain in the valid_domains list.
                try:
                    cached_domains['domains']['valid_domains'].append(hostaddr.getdomainaddr())
                except KeyError:
                    pass

                #Don't call __get_system_name() while member_lock is locked.
                # It calls get_dict_entry() which locks config_lock and
                # could cause a deadlock between threads.
                cached_domains['domains']['system_name'] = self.__get_system_name()

                self.member_lock.acquire()
                self.cached_domains = cached_domains
                self.member_lock.release()
            elif domains:
                #If domains is python true, but not a dictionary, make a
                # log entry.
                message = "excpected 'domains' in the configuration to be" \
                          " a dictionary not %s" % (type(domains),)
                Trace.log(e_errors.ERROR, message)

            Trace.trace(25, "get_domains: extract time: %f" % (time.time() - t0,))

        return self.cached_domains

    def update_domains(self):
        """
        Called whenever a new configuration is loaded.
        """

        # The other servers call the generic_server.__init__() function
        # to get hostaddr.update_domains function called.  The configuration
        # server does not use the generic_server.__init__() function, so
        # this must be done explicitely (after the configfile is loaded).
        domains = self.get_domains()
        if domains == None:
            domains = {}
        domains = domains.get('domains', {})
        hostaddr.update_domains(domains)

    def get_keys(self, ticket):
        """
        Reply with a list of the dictionary keys.

        :type ticket: :obj:`dict`
        :arg ticket: request containing "get_keys" work
        """

        __pychecker__ = "unusednames=ticket"

        skeys = self.get_config_keys()
        skeys.sort()
        ticket['get_keys'] = (skeys)
        ticket['status'] = (e_errors.OK, None)
        self.send_reply(ticket)


    def make_dump(self, ticket):

        Trace.trace(15, 'DUMP: \n' + str(ticket))

        ticket['status'] = (e_errors.OK, None)

        #We need to copy the original ticket.  This is to keep it short
        # enough so that it will not be too long for reply_to_caller()
        # to handle.  dump2() could handle it either way, but dump()
        # can not.
        reply=ticket.copy()
        reply['dump'] = self.get_config_dict()
        #The following section places into the udp reply ticket information
        # to prevent the configuration_client from having to pull it
        # down separately.
        reply['config_load_timestamp'] = self.get_config_load_timestamp()
        domains = self.get_domains()['domains']
        if domains != None:
            reply['domains'] = domains

        # Determine on what IP type to communicate depending on the address type of the client.
        my_address_family = socket.getaddrinfo(socket.gethostname(), None)[0][0]
        if (len(ticket['r_a'][0][0].split('.'))) == 4 and (my_address_family == socket.AF_INET6):
            # convert all 'hostip' to IPV4
            for key in reply['dump']:
                if 'host' in reply['dump'][key]:
                    server_ipv4 = None
                    hostinfo = socket.getaddrinfo(reply['dump'][key]['host'],
                                                  reply['dump'][key]['port'],
                                                  socket.AF_INET)
                    for e in hostinfo:
                        if e[0] == socket.AF_INET:
                            server_ipv4 = e[4][0] # see python socket module documentation.
                            break
                    if server_ipv4:
                        # make a copy to not back-affect configuration
                        reply['dump'][key] = copy.copy(reply['dump'][key])
                        reply['dump'][key]['hostip'] = server_ipv4
        return reply

    def dump(self, ticket):
        """
        Reply with a dump of the configuration dictionary

        :type ticket: :obj:`dict`
        :arg ticket: request containing "dump" work
        """

        if not hostaddr.allow(ticket['callback_addr']):
            return None
        reply = self.make_dump(ticket)
        if reply == None:
            return
        self.reply_to_caller(ticket)
        addr = ticket['callback_addr']
        address_family = socket.getaddrinfo(addr[0], None)[0][0]
        sock = socket.socket(address_family, socket.SOCK_STREAM)
        try:
            sock.connect(addr)
            r = callback.write_tcp_obj(sock, reply)
            sock.close()
            if r:
                Trace.log(e_errors.ERROR,"Error calling write_tcp_obj. Callback addr. %s"%(addr,))

        except:
            Trace.handle_error()
            Trace.log(e_errors.ERROR,"Callback address %s"%(addr,))
        return

    def dump2(self, ticket):
        """
        Reply with a dump of the configuration dictionary.
        Another implementation.

        :type ticket: :obj:`dict`
        :arg ticket: request containing "dump2" work
        """
        reply = self.make_dump(ticket)
        return reply

    def get_media_changer(self, ticket):
        """
        Reply with media changer configuration.

        :type ticket: :obj:`dict`
        :arg ticket: request containing "get_media_changer" work
        """
        #__pychecker__ = "unusednames=ticket"

        movers = self.get_movers_internal(ticket)
        ret = ''
        for m in movers:
            mv_name = m['mover']
            ret =  self.get_dict_entry(mv_name).get('media_changer','')
            if ret:
            # handle TFF1-AB variety
                mc = self.get_dict_entry(ret)
                if mc and mc.get('remote_media_changer'):
                    ret = mc.get('remote_media_changer')
                break
        ticket['media_changer'] = ret
        return ticket

    def get_library_managers(self, ticket):
        """
        Reply with list of library managers in configuration.

        :type ticket: :obj:`dict`
        :arg ticket: request containing "get_library_managers" work
        """

        __pychecker__ = "unusednames=ticket"

        ret = {}
        for key in self.get_config_keys():
            index = key.find (".library_manager")
            if index != -1:
                library_name = key[:index]
                item = self.get_dict_entry(key)
                ret[library_name] = {'address':(item['host'],item['port']),
                                     'name': key}
        ticket['library_managers'] = ret
        ticket['status'] = (e_errors.OK, None)
        return ticket

    def get_media_changers(self, ticket):
        """
        Reply with list of media changers in configuration.

        :type ticket: :obj:`dict`
        :arg ticket: request containing "get_media_changers" work
        """

        __pychecker__ = "unusednames=ticket"

        ret = {}
        for key in self.get_config_keys():
            index = key.find (".media_changer")
            if index != -1:
                media_changer_name = key[:index]
                item = self.get_dict_entry(key)
                ret[media_changer_name] = {'address':(item['host'],
                                                      item['port']),
                                           'name': key}
        ticket['media_changers'] = ret
        ticket['status'] = (e_errors.OK, None)
        return ticket

    def get_migrators(self, ticket):
        """
        Reply with list of migrators in configuration.

        :type ticket: :obj:`dict`
        :arg ticket: request containing "get_migrators" work
        """

        __pychecker__ = "unusednames=ticket"

        ret = {}
        for key in self.get_config_keys():
            index = key.find (".migrator")
            if index != -1:
                migrator = key[:index]
                item = self.get_dict_entry(key)
                ret[migrator] = {'address':(item['host'],item['port']),
                                     'name': key}
        ticket['migrators'] = ret
        ticket['status'] = (e_errors.OK, None)
        return ticket

    def reply_serverlist( self, ticket):
        """
        Reply with list of servers in configuration.

        :type ticket: :obj:`dict`
        :arg ticket: request containing "reply_serverlist" work
        """

        __pychecker__ = "unusednames=ticket"

        try:
            ticket['server_list'] = self.get_server_list()
            ticket['status'] = (e_errors.OK, None)
        except:
            ticket['status'] = (e_errors.UNKNOWN, str(sys.exc_info()[1]))

        return ticket

    def get_dict_element(self, ticket):
        """
        Reply with configuration element defined by key "value" in request ticket.

        :type ticket: :obj:`dict`
        :arg ticket: request containing "get_dict_element" work
        """
        try:
            ticket['value'] = self.get_dict_entry(ticket['keyValue'])
            ticket['status'] = (e_errors.OK, None)
        except:
            ticket['status'] = (e_errors.UNKNOWN, str(sys.exc_info()[1]))
        return ticket

    def copy_level(self, ticket):
        """
        Turn on / off threaded implementation.

        :type ticket: :obj:`dict`
        :arg ticket: request containing "copy_level" work
        """
        key = ticket.get('copy_level', 2)
        if key:
            key=int(key)
            if key >= 2:
                key = 2
            elif key <= 0:
                key = 0
        self.set_copy_level(key)
        ticket['status'] = (e_errors.OK,
                            "copy level set to %s" % (self.get_copy_level()))
        return ticket

