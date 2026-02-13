#!/usr/bin/env python

'''
    MW - Enstore File Cache Migration worker core functionality implementation

    implements everything what can work and be tested without full enstore installation
'''
from __future__ import print_function

# system imports

import sys
import time

from multiprocessing import Pool, Process
import threading
import logging

# amqp
import pika
import queue

# enstore imports
import e_errors
import enstore_constants

# enstore cache imports
import rabbitmq_cache.errors as cache_errors
import rabbitmq_cache.messaging.client as cmc
import rabbitmq_cache.messaging.mw_client as mwc

from rabbitmq_cache.messaging.messages import MSG_TYPES as mt

debug = True
MAX_PROCESSES = 5  # @todo configurable

# @todo define it here for now. move to common file


class MigrationWorker(object):
    '''
    Migration Worker core functionality implementation
    '''

# def __init__(self, amq_broker=("localhost",5672), myaddr="mw",
# target="pe", auto_ack=True ):
    def __init__(self, name, conf):
        '''
        @type name: str
        @param name: name - migration worker name
        @type conf: dict
        @param conf: configuration dictionary (partial) received from Configuration Server or else

        conf["server"] - configuration of this server
        conf["amqp"] - configuration of amqp, such as broker, else
        conf["file_clerk"]
        '''
        self.shutdown = False
        self.finished = False
        self.suspended = False
        self.auto_ack = True  # auto ack incoming messages
        self.command_receiver_started = False  # start flag for command receiver

        self.work_dict = {}
        #logging.basicConfig(level=logging.DEBUG, filename='bbb.out')
        self.log = logging.getLogger('log.encache.%s' % name)
        self.log.setLevel(logging.INFO)
        self.trace = logging.getLogger('trace.encache.%s' % name)
        self.trace.setLevel(logging.DEBUG)
        print("LOGGER", self.log)
        print("TRACER", self.trace)
        print("START {}".format(name))
        self.log.info("LLLLL starting")
        self.trace.debug("extract configuration")
        try:
            self.name = name

            self.trace.debug("name=%s, conf=%s", name, conf)

            cfb = conf['amqp']['broker']
            cfs = conf['server']
            amq_broker = (cfb['host'], cfb['port'])
            self.queue_in = cfs['queue_in']
            queue_work = cfs['queue_work']
            w_exch = cfs.get('exchange_work')
            queue_reply = cfs['queue_reply']
            r_exch = cfs.get('exchange_reply')
        except BaseException:
            self.trace.exception(
                "got exception when extracting configuration form dictionary")
            # @todo - configuraion error, raise exception

        self.trace.debug("create clients")
        self.amq_client = cmc.EnAMQPClient(amq_broker,
                                           my_queue=queue_work,
                                           my_exchange=w_exch,
                                           target_queue=queue_reply,
                                           target_exchange=r_exch,
                                           authentication=cfb.get('sasl-mechanism'))
        self.trace.debug("amq_client: %s", dir(self.amq_client))
        self.trace.debug(
            "reading commands from '%s', replying to '%s'",
            queue_work,
            queue_reply)
        print("reading commands from {}, replying to {}".format(queue_work, queue_reply))
        # start it here
        # self.start()
        # XXX self.amq_client.add_receiver("work",queue_work)

        # self.pool = Pool(processes=MAX_PROCESSES) # pool of worker processes

    def set_handler(self, message_type, handler_method):
        self.trace.debug("set_handler %s" % (handler_method,))
        self.trace.debug("set_handler handlers before %s" % (self.handlers,))
        if message_type in self.handlers.keys():
            self.handlers[message_type] = handler_method
        else:
            raise e_errors.EnstoreError(
                None, "Worker is not defined", e_errors.WRONGPARAMETER)
        self.trace.debug("set_handler handlesrs after %s" % (self.handlers,))

    def _fetch_message(self, receiver):
        rc = None
        try:
            rc = self.amq_client.rcv_default.fetch()
            #rc = receiver.fetch()
            if rc:
                self.trace.debug("fetch_message: returning %s" % (rc,))
        except queue.Empty:
            self.trace.debug("fetch_message: queue empty")
        except Exception as e:
            self.log.error("fetch_message() exception %s", e)
        return rc

    def _ack_message(self, msg):
        # self.amq_client.ssn.acknowledge(msg)
        try:
            self.trace.debug("_ack_message(): sending acknowledge %s", msg)
            # self.amq_client.ssn.acknowledge(msg) # no ack is needed as it gets acked automatically in client.py implementation???? Check if this is true.
        except BaseException:
            exc, emsg = sys.exc_info()[:2]
            self.trace.debug(
                "_ack_message(): Can not send auto acknowledge for the message. Exception e=%s msg=%s",
                str(exc),
                str(emsg))
            self.trace.exception("_ack_message(): stack dump follows")
            pass

    def _send_reply(self, m):
        self.amq_client.snd_default.send(m)

##############################################################################
# Message Processing logic
#

# Message handlers:
# - handler processes message m
# - handler "consumes" message, if it returns None - I'll ack the message to sender
#   if handler returns not None, it is handler's responsibility to ack message. AMQP broker will resent message if the message is not acked.
# - redelivered message have property redelivered = True
# - sender supposed to set correlation_id unique for the message
#
# Normal course of action:
#    check args, start message processing, drop correlation_id on heap and return None
#
    def worker_purge(self, correlation_id=None):
        # @todo access to dictionary must be synchronized
        try:
            self.trace.debug(
                "working on %s, correlation_id=%s",
                mt.MWC_PURGE,
                correlation_id)
            m = self.work_dict[correlation_id]
            time.sleep(2)
            # @todo - use original list, put something for now
            l = ["file1", "file2"]
            self.trace.debug("WORKER m=%s", m)
            self.trace.debug("WORKER l=%s", l)
            reply = mwc.MWRPurged(orig_msg=m, content=l)
            self.trace.debug("WORKER reply=%s", reply)
            try:
                self._send_reply(reply)
                self.trace.debug("worker_purge() reply sent, reply=%s", reply)
            except Exception as e:
                self.trace.exception(
                    "worker_purge(), sending reply, exception")
        except BaseException:
            self.trace.exception(
                "worker %s, correlation_id=%s",
                mt.MWC_PURGE,
                correlation_id)
        finally:
            # @todo delete it in main, or do periodic cleanup
            del self.work_dict[correlation_id]

    # work messages
    def handler_purge(self, m):
        self.trace.debug("process %s message %s", mt.MWC_PURGE, m)
        # @todo - use named tuple
        self.work_dict[m.correlation_id] = (m, "more info related to worker")
        # start processing
        kw = {"correlation_id": m.correlation_id}
        t = threading.Thread(target=self.worker_purge, kwargs=kw)
        t.start()
        self.trace.debug("processing thread started %s,args=%s", t, kw)

    # def handler_archive(self, m):
    def handler_archive(self, m):
        self.trace.debug("handler_archive:message %s %s", m, self.work_dict)
        self.trace.debug("handler_archive: content %s", m.content)

    def handler_stage(self, m):
        self.trace.debug("process %s message %s", mt.MWC_STAGE, m)

    # direct messages:
    def handler_status(self, m):
        self.trace.debug("process %s message %s", mt.MWC_STATUS, m)

    # map message type to processor

    handlers = {mt.MWC_PURGE: handler_purge,
                mt.MWC_ARCHIVE: handler_archive,
                mt.MWC_STAGE: handler_stage,
                mt.MWC_STATUS: handler_status,
                }

    def handle_message(self, m):
        #self.trace.debug(
        #    "handle message called %s %s",
        #    m.correlation_id,
        #    m.redelivered)
        self.trace.debug(
            "handle message called %s",
            m.correlation_id)

        # ack message here
        # retries are hadled at the higher level
        # of piers transaction
        self._ack_message(m)
        # @todo : check "type" present and is string or unicode
        cmd_type = m.properties["en_type"]
        try:
            h = self.handlers[cmd_type]
        except KeyError:
            raise cache_errors.errors.EnCacheWrongCommand(cmd_type)

        self.trace.debug("handle message - type,handle=%s,%s", cmd_type, h)
        # can use these to exclude redelivered messages
        correlation_id = m.correlation_id
        # redelivered = m.redelivered # did not find this flag in rabbitmq
        redelivered = False
        # @todo check if message is on heap for processing
        if redelivered:
            if correlation_id in self.work_dict:
                return False

        try:
            # ret = h(self,m)
            self.trace.debug("handle message - calling%s", h)
            ret = h(m)
        except Exception as e:
            self.trace.exception("handle message - exception %s", e)
            # Message processing has failed.
            # Allow to re-process it
            del (self.work_dict[correlation_id])
            ret = False

        self.trace.debug("handle message - returning %s", ret)
        return ret

    def serve_amq(self, receiver):
        """
        read amq messages from queue
        """
        print("serve AMQ. Receiver {}".format(receiver))
        try:
            while not self.shutdown:
                if self.suspended:
                    time.sleep(2)
                    continue

                # Fetch message from queue
                message = self._fetch_message(receiver)
                if not message:
                    continue
                self.trace.debug("got message {} {} {} {} {}".format(message, type(message), dir(message), message.correlation_id, message.properties))

                # debug HACK to use spout messages
                try:
                    message.correlation_id = message.properties["spout-id"]
                    self.trace.info(
                        "correlation_id is not set, setting it to spout-id %s",
                        message.correlation_id)
                except BaseException:
                    pass
                # end DEBUG hack

                do_ack = False
                try:
                    rc = self.handle_message(message)
                    # do_ack = rc # according to suggested protocol
                    # message gets acked before starting handler
                    # to avoid unnecessary repeats
                    # due to timeout expiration
                    self.trace.debug(
                        "message processed correlation_id=%s, do_ack=%s",
                        message.correlation_id,
                        do_ack)
                except Exception as e:
                    # @todo - print exception type cleanly
                    self.log.error(
                        "can not process message. Exception %s. Original message = %s", e, message)

                # Acknowledge ORIGINAL ticket thus we will not get it again
                if do_ack:
                    self._ack_message(message)

        # try / while
        finally:
            self.amq_client.stop()

    def start(self):
        self.amq_client.start()
        # add receiver for Migration Dispatcher commands
        self.amq_command_receiver = self.amq_client.add_receiver(
            "mw_interface", self.queue_in)

        # start servers in separate threads
        """
        self.srv_thread = threading.Thread(
            target=self.serve_amq, name="Request Server", args=[
                self.amq_client.rcv_default])
        self.srv_thread.start()
        """
        self.cmd_srv_thread = threading.Thread(
            target=self.serve_amq, name="MD Commmand Server", args=[
                self.amq_command_receiver])
        self.cmd_srv_thread.start()

    def stop(self):
        # tell serving thread to stop and wait until it finish
        self.shutdown = True

        self.amq_client.stop()
        self.srv_thread.join()
        self.cmd_srv_thread.join()


if __name__ == "__main__":   # pragma: no cover

    # Test Unit
    import rabbitmq_cache.en_logging.config_test_unit

    def set_logging(name):
        lh = logging.StreamHandler()
        #    fmt = logging.Formatter("%(asctime)s - %(name)s - %(levelname)s - %(message)s")
        # %(pathname)s
        fmt = logging.Formatter("%(filename)s %(lineno)d :: %(name)s :: %(module)s :: %(levelname)s :: %(message)s")

        l_log = logging.getLogger('log.encache.{}'.format(name))
        l_trace = logging.getLogger('trace.encache.{}'.format(name))
        #add formatter to lh
        lh.setFormatter(fmt)
        l_log.addHandler(lh)
        l_trace.addHandler(lh)

        l_log.setLevel(logging.DEBUG)
        l_trace.setLevel(logging.DEBUG)

    #set_logging()

    # cache.en_logging.config_test_unit.set_logging_console()

    #rabbitmq_cache.en_logging.config_test_unit.set_logging_enstore(name="MW_UNIT_TEST")
    
    #trace = logging.getLogger('trace.encache.messaging')
    #trace.debug("starting")
    name = "mw_123"
    set_logging(name)
    #rabbitmq_cache.en_logging.config_test_unit.set_logging_enstore(name=name)
    trace = logging.getLogger('trace.encache.{}'.format(name))
    trace.debug("starting")
    conf = {"amqp": {
        "broker": {
            "host": "dvl-es-hd02.jinr.ru",
            "port": 5672,
            'sasl-mechanism': 'PLAIN',
        },
    },
        "server": {
        # all workers get job from common Migration Worker queue
        "queue_work": "migrator",
        # queue name for messages sent directly to this worker, like MDW_STATUS
        # worker automatically create queue if it does not exist
        # and deletes on exit
            "queue_in": "mw_123",
            
            #                      "queue_out" : "md",            # MW reply to Migration Dispatcher queue
            "queue_reply": "md_replies",            # MW reply to Migration Dispatcher queue
    }
    }

    l_trace = logging.getLogger('trace.encache.%s' % name)
    l_trace.debug("start unit test")

    try:
        # instantiate MigrationWorker server
        mw = MigrationWorker(name, conf)
        # it starts in constructor
        mw.start()
    except BaseException as e:
        l_trace.debug("Can't instantiate MigrationWorker: {}, exiting".format(e))
        sys.exit(1)

    # stop mw server if there was keyboard interrupt
    while not mw.finished:
        try:
            time.sleep(1)
        except KeyboardInterrupt:
            print("Keyboard interrupt at main thread")
            mw.stop()
            break

    del mw
    print("mw finished")
