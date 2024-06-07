#!/usr/bin/env python

###############################################################################
#
# $Id$
#
###############################################################################

#
# client_1_1_2_3.py , the frozen verision of client.py in process of refactoring
# Will become onsolete when udp2amq.py is checked to work with client2.py which is used by all other servers.
# Formerly client.py, last version with that name:
# $Id$

from __future__ import print_function
import optparse
import sys
import traceback

import qpid.messaging
import qpid.util
import qpid.log
# from qpid.util import URL
# from qpid.log import enable, DEBUG, WARN
import cache.messaging.constants as cmsc

debug = False


class EnQpidClient:
    def __init__(self, host_port, myaddr=None, target=None):

        (h, p) = host_port
        self.br_host = h          # broker url
        self.br_port = p or cmsc.EN_AMQP_PORT

        # @todo
        hp = "%s:%s" % (self.br_host, self.br_port)
        # host,port portion not used
        self.url = qpid.util.URL("localhost:5672")
        self.url.user = "guest"
        self.url.password = "guest"

        if debug:
            print(
                "DEBUG EnQpidClient URL init: %s %s " %
                (self.br_host, self.br_port))
        self.myaddr = myaddr    # my address to be used in reply receiver
        self.target = target    # destination address to be used in sender

    def configure(self):
        # override this method to talk to configuration server if needed to get
        # broker url, etc.
        pass

    def start(self):
        # @todo
        # print "DEBUG EnQpidClient URL start:" + self.url
        print(
            "DEBUG EnQpidClient br host, port: %s %s" %
            (self.br_host, self.br_port))
        self.conn = qpid.messaging.Connection(host=self.br_host, port=self.br_port,
                                              username=self.url.user, password=self.url.password)
        self.conn.reconnect = True
        self.conn.open()
        self.ssn = self.conn.session()

        # sender "snd" sends messages to target
        self.snd = self.ssn.sender(self.target)

        if not self.myaddr:
            # set reply queue
            # create exclusive queue with unique name for replies
            self.myaddr = "reply_to:" + self.ssn.name
            self.ssn.queue_declare(queue=self.myaddr, exclusive=True)
            # @todo fix exchange name
            self.ssn.exchange_bind(
                exchange="amq.direct",
                queue=self.myaddr,
                binding_key=self.myaddr)
        # else:
        # do nothing - assume queue exists and bound, or the address contain
        # option to create queue

        # receiver "rcv" receives messages sent to us at myaddr
        self.rcv = self.ssn.receiver(self.myaddr)

    def receiver(self, addr, name):
        """
        create additional receiver to read "addr" queue
        """
        self.r[name] = (addr, self.ssn.receiver(addr))
        return self.r[name]

    def sender(self, addr, name):
        """
        create additional sender for target addr'
        """
        self.s[name] = (addr, self.ssn.sender(addr))
        return self.s[name]

    def stop(self):
        # @todo: We do not acknowledge whatever is left in the queue - it is not processed.
        self.started = False
        try:
            self.conn.close()
        except BaseException:
            print("Can not close qpid connection ", self.conn)

    # @todo block/async
    def send(self, msg, *args, **kwargs):
        try:
            self.snd.send(msg, *args, **kwargs)
        except BaseException:
            pass

    def fetch(self, *args, **kwargs):
        try:
            msg = self.rcv.fetch(*args, **kwargs)
        except BaseException:
            pass
        return msg
