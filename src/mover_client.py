###############################################################################
# src/$RCSfile$   $Revision$
#
#########################################################################
#                                                                       #
# Mover client.                                                         #
# Mover access methods                                                  #
#                                                                       #
#########################################################################

# system imports
import sys
import string

#enstore imports
import udp_client
import interface
import generic_client
import Trace

class MoverClient(generic_client.GenericClient):
    def __init__(self, csc, name=""):
        self.mover=name
        self.log_name = "C_"+string.upper(name)
        generic_client.GenericClient.__init__(self, csc, self.log_name)
        self.u = udp_client.UDPClient()

    def status(self, rcv_timeout=0, tries=0):
	return self.send({"work" : "status"}, rcv_timeout, tries)

    def local_mover(self, enable, rcv_timeout=0, tries=0):
	return self.send({"work" : "local_mover",
                          "enable" : enable}, rcv_timeout, tries)

    def start_draining(self, rcv_timeout=0, tries=0):
	return self.send({"work" : "start_draining"}, rcv_timeout, tries)

    def stop_draining(self, rcv_timeout=0, tries=0):
	return self.send({"work" : "stop_draining"}, rcv_timeout, tries)

    def send (self, ticket, rcv_timeout=0, tries=0) :
        vticket = self.csc.get(self.mover)
        return self.u.send(ticket, (vticket['hostip'], vticket['port']), \
	                rcv_timeout, tries)

class MoverClientInterface(generic_client.GenericClientInterface):
    def __init__(self, flag=1, opts=[]):
        self.do_parse = flag
        self.restricted_opts = opts
        self.alive_rcv_timeout = 0
        self.alive_retries = 0
        self.mover = ""
        self.local_mover = 0
        self.enable = 0
	self.status = 0
        self.start_draining = 0
        self.stop_draining = 0
        generic_client.GenericClientInterface.__init__(self)

    # define the command line options that are valid
    def options(self):
        if self.restricted_opts:
            return self.restricted_opts
        else:
            return self.client_options()+["status", "local_mover=", "start_draining", "stop_draining"]

    #  define our specific help
    def parameters(self):
        return "mover"

    # parse the options like normal but make sure we have a mover name
    def parse_options(self):
        interface.Interface.parse_options(self)
        # bomb out if we don't have a mover
        if len(self.args) < 1 :
	    self.missing_parameter(self.parameters())
            self.print_help()
            sys.exit(1)
        else:
            self.mover = self.args[0]


def do_work(intf):
    # get a mover client
    movc = MoverClient((intf.config_host, intf.config_port), intf.mover)
    Trace.init(movc.get_name(movc.log_name))

    ticket = {}
    msg_id = None

    if intf.alive:
        ticket = movc.alive(intf.mover, intf.alive_rcv_timeout,
                            intf.alive_retries)
    elif intf.status:
        ticket = movc.status(intf.alive_rcv_timeout,intf.alive_retries)
	print repr(ticket)
    elif intf.local_mover:
        ticket = movc.local_mover(intf.enable, intf.alive_rcv_timeout,
                                  intf.alive_retries)
    elif intf.start_draining:
        ticket = movc.start_draining(intf.mover, intf.alive_rcv_timeout,
                                     intf.alive_retries)
    elif intf.stop_draining:
        ticket = movc.stop_draining(intf.mover, intf.alive_rcv_timeout,
                                     intf.alive_retries)
    else:
	intf.print_help()
        sys.exit(0)

    del movc.csc.u
    del movc.u		# del now, otherwise get name exception (just for python v1.5???)

    movc.check_ticket(ticket)

if __name__ == "__main__" :
    Trace.init("MOVER_CLI")
    Trace.trace(6,"movc called with args "+repr(sys.argv))

    # fill in the interface
    intf = MoverClientInterface()

    do_work(intf)
