#!/usr/bin/env python

##############################################################################
#
# $Id$
# Library Mnager Director
##############################################################################


'''
    LMD - python prototype for Enstore File Cache Library Manager Dispatcher core functionality implementation
'''
from __future__ import print_function

# system imports
import sys

# enstore imports
import e_errors
import enstore_constants
import generic_server
import dispatching_worker
import event_relay_client
import monitored_server
import Trace
import lmd_policy_selector

MY_NAME = enstore_constants.LM_DIRECTOR

class LMD(dispatching_worker.DispatchingWorker,
          generic_server.GenericServer):
    '''
    classdocs
    '''

    def __init__(self, csc, auto_ack=True):
        '''
        Constructor
        '''
        generic_server.GenericServer.__init__(self, csc, MY_NAME,
                                              function=self.handle_er_msg)
        self.shutdown = False
        self.finished = False
        Trace.init(self.log_name, "yes")

        # get all necessary information from configuration
        self.lmd_config = self.csc.get(MY_NAME)

        self.policy_file = self.lmd_config['policy_file']
        try:
            self.policy_selector = lmd_policy_selector.Selector(
                self.policy_file)
        except Exception as detail:
            Trace.log(
                e_errors.ALARM, "Can not create policy selector: %s" %
                (detail,))
            sys.exit(-1)

        self.alive_interval = monitored_server.get_alive_interval(self.csc,
                                                                  MY_NAME,
                                                                  self.lmd_config)

        dispatching_worker.DispatchingWorker.__init__(self, (self.lmd_config['hostip'],
                                                      self.lmd_config['port']))
        self.resubscribe_rate = 300
        self.erc = event_relay_client.EventRelayClient(self)
        self.erc.start_heartbeat(self.name, self.alive_interval)

    ##############################################
    # Configuration related methods
    ##############################################
    # reload policy when this method is called
    # by the request from the client
    def reload_policy(self, ticket):
        try:
            self.policy_selector.read_config()
            ticket['status'] = (e_errors.OK, None)
        except Exception as detail:
            ticket['status'] = (
                e_errors.ERROR, "Error loading policy for LMD: %s" %
                (detail,))
        self.reply_to_caller(ticket)

    # send current policy to client

    def show_policy(self, ticket):
        try:
            ticket['dump'] = self.policy_selector.policydict
            ticket['status'] = (e_errors.OK, None)
            self.send_reply_with_long_answer(ticket)
        except Exception as detail:
            ticket['status'] = (e_errors.ERROR, "Error %s" % (detail,))
            self.reply_to_caller(ticket)

    def get_library_manager(self, ticket):
        result = self.lmd_decision(ticket)
        self.reply_to_caller(result)

    ##########################################################################
    # Ticket Processing logic
    def lmd_decision(self, ticket):
        Trace.trace(10, "lmd_decision")
        if not isinstance(ticket, dict):
            Trace.trace(
                10, "lmd_decision  - ticket is not dictionary type, ticket %s." %
                (ticket,))
            return {'status': (e_errors.LMD_WRONG_TICKET_FORMAT,
                               'LMD: ticket is not dictionary type')}
        result = ticket
        # create a copy of the original library
        try:
            result['original_library'] = result['vc']['library']
        except KeyError:
            result['status'] = (e_errors.MALFORMED, "No library key specified")
            return result
        Trace.trace(10, "lmd_decision1 %s" % (result,))

        try:
            rc, new_library = self.policy_selector.match_found(ticket)
        except BaseException:
            exc, msg, tb = sys.exc_info()
            Trace.handle_error(exc, msg, tb)
            del (tb)
            result['status'] = (e_errors.ERROR, 'See log file')
            return result

        Trace.trace(10, "lmd_decision2 rc=%s lm=%s" % (rc, new_library,))
        if rc:
            result['vc']['library'] = new_library
            # do not allow multiple copies if request was re-directed
            # the copy will be done on a package file
            copies = result['fc'].get("copies", 0)
            if copies:
                result['fc']['copies'] = 0
        result['status'] = (e_errors.OK, None)
        return result

##############################################################################

class LMDInterface(generic_server.GenericServerInterface):
    pass


if __name__ == "__main__":   # pragma: no cover
    # get the interface
    intf = LMDInterface()
    lmd = LMD((intf.config_host, intf.config_port))
    # lmd._do_print({'levels':[10]})
    lmd.handle_generic_commands(intf)

    while True:
        try:
            Trace.log(e_errors.INFO, "Library Manager Director (re)starting")
            lmd.serve_forever()
        except SystemExit as exit_code:
            Trace.log(
                e_errors.INFO, "Library Manager Director Exiting %s" %
                (exit_code,))

    Trace.trace(
        e_errors.ERROR,
        "Library Manager Director finished (impossible)")
