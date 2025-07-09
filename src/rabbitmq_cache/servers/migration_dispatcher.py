#!/usr/bin/env python

"""
Sends SFA migration lists to corresponding queues to get processed by migrators.
Receives migrator responds on the return queues and processes them.
"""
from __future__ import print_function

# system imports
import sys
import time
import types
from multiprocessing import Pool, Process
import threading
import logging

# amqp
import queue

# enstore imports
import e_errors
import enstore_constants
import configuration_client
import Trace

# enstore cache imports
import file_cache_status
import rabbitmq_cache.errors
# import cache.messaging.client2 as cmc
import rabbitmq_cache.messaging.client as cmc

import rabbitmq_cache.messaging.file_list as file_list
import rabbitmq_cache.messaging.mw_client as mw_client

from rabbitmq_cache.messaging.messages import MSG_TYPES as mt
import rabbitmq_cache.en_logging.en_logging as en_logging

debug = True
MAX_PROCESSES = 5  # @todo configurable

# @todo define it here for now. move to common file


class MigrationList:
    def __init__(self, f_list=None, id=None, state=None, expected_reply=None):
        self.list_object = f_list  # file list according to file_list.py class description
        self.status_requestor = None
        self.id = id  # MigrationList id
        self.state = state  # state of the file list from file_list.py
        self.expected_reply = expected_reply  # reply expected for this file list

    def __str__(self):
        return "id %s list: %s" % (self.id, self.list_object)


class MigrationDispatcher():
    """
    Migration dispatcher.
    Dispatches migration requests to migrators via corresponding queues.
    Monitors submitted requests.

    """

    def __init__(self,
                 name,
                 broker,
                 queue_write,
                 queue_read,
                 queue_purge,
                 queue_reply,
                 lock,
                 migration_pool,
                 purge_pool,
                 cache_written_pool,
                 fcc,
                 clustered_configuration=None):
        '''

        :type name: :obj:`str`
        :arg name: migration dispatcher name
        :type broker: :obj:`dict`
        :arg broker: ({'host':amqp_broker_host, 'port':amqp_broker_port})
        :type queue_write: :obj:`str`
        :arg queue_write: queue for migration dispatcher write requests
        :type queue_read: :obj:`str`
        :arg queue_read: queue for migration dispatcher read requests
        :type queue_purge: :obj:`str`
        :arg queue_purge: queue for migration dispatcher purge requests
        :type queue_reply: :obj:`str`
        :arg queue_reply: replies from migrators are sent to this queue
        :type migration_pool: :obj:`str`
        :arg migration_pool: pool where PE Server part puts lists to get served by Migration Dispatcher
        :type purge_pool: :obj:`str`
        :arg purge_pool: purge pool where PE Server part puts lists to get served by Migration Dispatcher
        :type cache_written_pool: :obj:`str`
        :arg cache_written_pool: pool where write event from file clerk are kept
        :type fcc: :class:`file_clerk_client.FileClient`
        :arg fcc: file clerk client
        :type clustered_configuration: :obj:`bool`
        :arg clustered_configuration: - indicates that clustered configuration is used or not
       '''

        self.shutdown = False
        self.finished = False
        self.auto_ack = True  # auto ack incoming messages
        self.lock = lock
        self.migration_pool = migration_pool
        self.purge_pool = purge_pool
        self.cache_written_pool = cache_written_pool
        self.fcc = fcc

        
        self.log, self.trace = en_logging.set_logging(name)

        self.name = name

        self.reply_to = None
        self.stop_status_loop = None
        self.expected_status_reply = None
        self.clustered_configuration = clustered_configuration  # see dispatcher.__init__()

        amq_broker = (broker['host'], broker['port'])
        self.queue_write = queue_write
        self.queue_read = queue_read
        self.queue_purge = queue_purge
        # Each type of request has its own queue
        if self.clustered_configuration:
            # And its own exchange for clustered configuration.
            # We assume that format is 'queue.exchange'
            # and do not check here just split
            exch_wr, q_wr = queue_write.split('.')
            #exch_type = 'topic'
            exch_type = 'direct'
            #q_wr = "%s; {create:always,node:{type:topic,x-declare:{type:direct}}}" % (queue_write,)
            exch_rd, q_rd = queue_read.split('.')
            #q_rd = "%s; {create:always,node:{type:topic,x-declare:{type:direct}}}" % (queue_read,)
            exch_p, q_p = queue_write.split('.')
            #q_p = "%s; {create:always,node:{type:topic,x-declare:{type:direct}}}" % (queue_purge,)
        else:
            q_wr = queue_write
            q_rd = queue_read
            q_p = queue_purge
            exch_wr = exch_rd = exch_p = 'encache'
            #exch_type = 'topic'
            exch_type ='direct'
        q_r = queue_reply

        Trace.log(e_errors.INFO, "CREATE EnAMQPClient {} {} {} {}".format(q_r, q_wr, exch_wr, exch_type))
        self.amq_client_write = cmc.EnAMQPClient(amq_broker,
                                                 my_queue=q_r,
                                                 #target_queue=q_wr,
                                                 target_queue=None,
                                                 target_exchange=exch_wr,
                                                 target_exchange_type=exch_type,
                                                 authentication=broker.get('sasl-mechanism'))
        
        """
        Trace.log(e_errors.INFO, "CREATE EnAMQPClient 2 {} {} {}".format(q_rd, exch_rd, exch_type))
        self.amq_client_read = cmc.EnAMQPClient(amq_broker,
                                                my_queue=None,
                                                target_queue=q_rd,
                                                target_exchange=exch_rd,
                                                target_exchange_type=exch_type,
                                                authentication=broker.get('sasl-mechanism'))

        Trace.log(e_errors.INFO, "CREATE EnAMQPClient 3 {} {} {}".format(q_p, exch_p, exch_type))
        self.amq_client_purge = cmc.EnAMQPClient(amq_broker,
                                                 my_queue=None,
                                                 target_queue=q_p,
                                                 target_exchange=exch_p,
                                                 target_exchange_type=exch_type,
                                                 authentication=broker.get('sasl-mechanism'))
        self.amq_client_read.start()
        self.amq_client_purge.start()
        """

        self.amq_client = self.amq_client_write
        Trace.log(e_errors.INFO, "EnAMQPClients created")
        # start it here
        self.start()

    def _fetch_message(self):
        try:
            msg = self.amq_client.rcv_default.fetch()
            if msg:
                Trace.trace(10, "FETCH returned {}".format(msg))
            return msg
        except queue.Empty:
            return None
        except Exception as e:
            Trace.log(e_errors.ERROR, "fetch_message() exception {}".format(e))
            return None

    def _ack_message(self, msg):
        # ack not needed in rabbitmq
        # but leave here commented
        """
        try:
            self.trace.debug("_ack_message(): sending acknowledge")
            self.amq_client.ssn.acknowledge(msg)
        except BaseException:
            exc, emsg = sys.exc_info()[:2]
            self.trace.debug(
                "_ack_message(): Can not send auto acknowledge for the message. Exception e=%s msg=%s",
                str(exc),
                str(emsg))
            pass
        """
        pass

    def _create_sender(self, client, queue, routing_key):
        # Routing key is valuable only for clustered configuration
        # and is defined by disk library manager.
        # The routing key is not enough for separate queues based on the type of request.
        # Each request type has its own message queue defined by request type and disk library:
        #
        #
        #                           |--- read_LIB1
        #   exchange for cluster 1: |--- write_LIB1
        #                           |--- purge_LIB1
        #
        #                           |--- read_LIB2
        #   exchange for cluster 2: |--- write_LIB2
        #                           |--- purge_LIB2
        #

        key = "_".join((queue, routing_key))
        Trace.trace(10, "_create_sender for {} {} {}".format(key, client.target_exchange, client.target_exchange_type))
        try:
            snd = client.ssn.sender(key, client.target_exchange, client.target_exchange_type)
        except Exception as e:
            Trace.trace(10, "exception in _create_sender: {}".format(e))
            return None
        Trace.trace(10, "_create_sender, sender created: {}".format(snd))
        return snd

    def send_status_request(self):
        Trace.trace(10, "Starting send_status_request")
        status_cmd = mw_client.MWCStatus(request_id=0)

        while True:
            for pool in (self.migration_pool, self.purge_pool):

                if self.stop_status_loop:
                    break
                for key in pool.keys():
                    try:
                        if pool[key].status_requestor:
                            # If status requestor exist
                            # dispatcher had already received confirmation from
                            # migrator.
                            # Send status request to it
                            status_cmd = mw_client.MWCStatus(
                                request_id=0, correlation_id=key)
                            Trace.trace(10, 
                                        "send_status_request sending {}".format(status_cmd))
                            pool[key].status_requestor.send(status_cmd)
                    except KeyError:
                        Trace.handle_error()
                        Trace.log(e_errors.INFO,
                                  "error in send_status_request KeyError {} keys {}".format(key, pool.keys()))
            time.sleep(600)

    def refill_cache_written_pool(self, mig_list):
        """
        Refill cache written pool.

        :type mig_list: :class:`MigrationList`
        :arg mig_list: file list
        """
        f_list = mig_list.list_object
        Trace.trace(10, "refill_cache_written_pool list: {}".format(f_list))
        # identify policy corresponding to this list
        policy = f_list.list_name
        for f in f_list.file_list:
            bfid_info = self.fcc.bfid_info(f['bfid'])
            if bfid_info and bfid_info['archive_status'] is None:
                # this will go into the list to migrate
                # check if the file list exists
                if not policy in self.cache_written_pool:
                    # Create list
                    new_f_list = file_list.FileListWithCRC(id=("%s-%s" % (mig_list.id, "MDREFILL")),
                                                           list_type=f_list.list_type,
                                                           list_name=policy,
                                                           minimal_data_size=f_list.minimal_data_size,
                                                           maximal_file_count=f_list.maximal_file_count,
                                                           max_time_in_list=f_list.max_time_in_list,
                                                           disk_library=f_list.disk_library)
                    self.cache_written_pool[policy] = new_f_list

                list_element = file_list.FileListItemWithCRC(bfid=bfid_info['bfid'],
                                                             nsid=f['nsid'],
                                                             path=f['path'],
                                                             libraries=f['libraries'],
                                                             crc=f['complete_crc'])
                l_id = self.cache_written_pool[policy].list_id
                self.lock.acquire()
                self.cache_written_pool[policy].append(
                    list_element, bfid_info['size'])
                migrate_list = False
                if self.cache_written_pool[policy].full:
                    # pass this list to Migration Dispatcher
                    Trace.trace(10, 
                                "refill_cache_written_pool passing to migration dispatcher id {}".format(l_id))
                    self.cache_written_pool[policy].creation_time = time.time()
                    try:
                        self.migration_pool[l_id] = self.MigrationList(new_f_list,
                                                                       l_id,
                                                                       file_list.FILLED)
                        del (self.cache_written_pool[policy])
                        migrate_list = True
                    except Exception as detail:
                        Trace.log(e_errors.ERROR, 
                                  "Error moving to migration pool: {}".format(detail))
                self.lock.release()
                if migrate_list:
                    self.start_migration(self.migration_pool, l_id)

    def handle_message(self, m):
        # @todo : check "type" present and is string or unicode
        msg_type = m.properties["en_type"]
        Trace.trace(10, "handle_message {} type {} properties {} all {}".format(m, msg_type, m.properties, dir(m)))
        Trace.trace(10, "migration pool {}".format(self.migration_pool))
        Trace.trace(10, "correlation id {}".format(m.correlation_id))
        # can use these to exclude redelivered messages
        correlation_id = m.correlation_id
        # redelivered = m.redelivered # not needed? Anyway rabbitmq does not seem to have this in messages
        redelivered = False
        Trace.trace(10, "handle_message:redelivered {}".format(redelivered))

        # @todo check if message is on heap for processing
        if redelivered:
            # this may require additional processing
            pass
        client = self.amq_client    
        if m.correlation_id in self.migration_pool:
            Trace.trace(10, 
                        "handle_message:in migration pool {}".format(self.migration_pool[m.correlation_id]))
            pool = self.migration_pool
            if self.migration_pool[m.correlation_id].list_object.list_type == mt.CACHE_MISSED:
                send_queue = self.queue_read
                #client = self.amq_client_read
            else:
                send_queue = self.queue_write
                #client = self.amq_client_write
        elif m.correlation_id in self.purge_pool:
            pool = self.purge_pool
            send_queue = self.queue_purge
            #client = self.amq_client_purge
        else:
            # Dispatcher must have been restarted and does not have
            # a record with this correlation id.
            return
        Trace.trace(10, "handle_message:in pool {}".format(pool[m.correlation_id]))

        if msg_type == mt.MWR_CONFIRMATION:
            # Received the confirmation from migrator
            # create sender on the queue declared in m.reply_to.
            # Correlation id is propagated for all mesaages related to the same request
            # first find which pool is the confirnmation for

            if not pool[m.correlation_id].status_requestor:
                self.lock.acquire()
                try:
                    pool[m.correlation_id].status_requestor = self.amq_client.add_sender(
                        "mw_amqp_interface", m.reply_to)
                except BaseException:
                    pass  # for now
                self.lock.release()

        if msg_type in (mt.MWR_ARCHIVED, mt.MWR_PURGED, mt.MWR_STAGED):
            if m.correlation_id in pool:
                self.lock.acquire()
                try:
                    del (pool[m.correlation_id])
                except BaseException:
                    pass
                self.lock.release()
            Trace.trace(10, "handle_message:After {}".format(pool,))

        if msg_type == mt.MWR_STATUS:
            # This message type can be received only as a result
            # status request sent from this migration dispatcher,
            # which means that the addressed migrator is doing work
            # for migration dispatcher

            Trace.trace(10,
                        "handle_message: MWR_STATUS recieved {} {}".format(m.content, m.correlation_id))
            Trace.trace(10, "handle_message: MPOOL {}".format(pool))
            if m.content['content']['migrator_status'] is None or m.content['content']['migrator_status'] == mt.FAILED:
                # Migrator restarted, but before restart it was doing
                # some work which could have failed.
                # in this case the request needs to be re-sent
                if m.correlation_id in pool:
                    Trace.trace(10, 
                                "handle_message: Migrator replied with status {}".format(m.content['content']['migrator_status']))
                    if m.content['content']['migrator_status'] == mt.FAILED:
                        if "detail" in m.content['content'] and m.content['content']['detail'] == "REBUILD PACKAGE":
                            # migrator failed to write package
                            # delete corresponding migration_pool record
                            # so that it can be rebuilt later
                            self.refill_cache_written_pool(
                                pool[m.correlation_id])
                            del (pool[m.correlation_id])
                            Trace.trace(10, "deleted from migration pool to get rebuilt")
                        elif "No such file or directory" in m.content['content']['detail']:
                            Trace.alarm(e_errors.ERROR, "Please investigate. Receceived {}".format(m.content['content']['detail']))
                            del (pool[m.correlation_id])

                    if m.correlation_id in pool:
                        Trace.trace(10, "handle_message: reposting request")
                        pool[m.correlation_id].state = file_list.FILLED
                        disk_library = pool[m.correlation_id].list_object.disk_library
                        # sender = self._create_sender(self.queue_work, disk_library)
                        sender = self._create_sender(
                            client, send_queue, disk_library)

                        self.migrate_list(pool[m.correlation_id], sender)
            else:
                if correlation_id in pool:
                    if m.content['content']['migrator_status'] == pool[m.correlation_id].expected_reply:
                        # expected reply is announced in the corresponding
                        # migration pool entry
                        # keyed by the correlation id
                        # all messages for a given action have the same
                        # correlation id.
                        Trace.trace(10, "handle_message: received expected status reply")
                        del (pool[m.correlation_id])

                    else:
                        Trace.trace(10, 
                                    "handle_message: received %s expected %s".format(m.content['content']['migrator_status'],
                                                                                     self.pool[m.correlation_id].expected_reply))
        return True

    def serve_amqp(self):
        """
        read amqp messages from queue
        """
        self.amq_client.start()
        Trace.log(e_errors.INFO, "AMQP client started. Shutdown = {}".format(self.shutdown))

        try:
            while not self.shutdown:
                # Fetch message from amqp queue
                message = self._fetch_message()
                if not message:
                    continue

                # debug HACK to use spout messages
                Trace.trace(10, "got amqp message {}", message)
                try:
                    if "spout-id" in message.properties:
                        message.correlation_id = message.properties["spout-id"]
                        Trace.trace(10,
                                    "correlation_id is not set, setting it to spout-id {}".format(message.correlation_id))
                except BaseException:
                    Trace.trace(10,
                                "exception setting it to spout-id {}".format(message.correlation_id))
                    pass
                # end DEBUG hack

                do_ack = False
                try:
                    Trace.trace(10, "MSG {} {}".format(type(message), message.content))
                    do_ack = self.handle_message(message)
                    Trace.trace(10,
                                "message processed correlation_id={}, do_ack={}".format(message.correlation_id,
                                                                                        do_ack))
                except Exception as e:
                    # @todo - print exception type cleanly
                    Trace.handle_error()
                    Trace.log(e_errors.ERROR,
                              "can not process message. Exception {}. Original message = {}".format(e, message))
                    do_ack = True  # to not hold message in the queue

                # Acknowledge ORIGINAL ticket thus we will not get it again
                Trace.trace(10, "serve_amqp doack {}".format(do_ack))
                if do_ack:
                    self._ack_message(message)

        # try / while
        finally:
            self.amq_client.stop()

    def start(self):
        # start server in separate thread
        self.amqp_srv_thread = threading.Thread(target=self.serve_amqp)
        self.amqp_srv_thread.start()
        self.status_thread = threading.Thread(
            target=self.send_status_request, name="Status")
        self.status_thread.start()

    def stop(self):
        # tell serving thread to stop and wait until it finish
        self.shutdown = True

        self.amq_client.stop()
        self.srv_thread.join()
        self.status_thread.join()

    def migrate_list(self, migration_list, send_client):
        if migration_list.state != file_list.ACTIVE:
            # send list to migration dispatcher queue
            if migration_list.list_object.list_type == mt.CACHE_WRITTEN:
                command = mw_client.MWCArchive(migration_list.list_object.file_list,
                                               correlation_id=migration_list.id)
                migration_list.expected_reply = mt.ARCHIVED
            elif migration_list.list_object.list_type == mt.CACHE_MISSED:
                command = mw_client.MWCStage(
                    migration_list.list_object.file_list,
                    correlation_id=migration_list.id)
                migration_list.expected_reply = mt.CACHED
            elif migration_list.list_object.list_type == mt.MDC_PURGE:
                command = mw_client.MWCPurge(
                    migration_list.list_object.file_list,
                    correlation_id=migration_list.id)
                migration_list.expected_reply = mt.PURGED
            try:
                # send command to the queue defined in send_client
                # and set corresponding list state to ACTIVE
                # for monitoring of execution
                Trace.trace(10, "migrate_list sending {}".format(command))
                send_client.send(command)

                migration_list.state = file_list.ACTIVE
            except BaseException:
                Trace.handle_error()

    def start_migration(self, pool, key):
        Trace.trace(10, "start_migration pool {} key {}".format(pool, key))

        try:
            item = pool[key]
        except KeyError as detail:
            Trace.log(
                e_errors.ERROR, "Error adding to list. No such key {}".format(key))
            return
        client = self.amq_client
        if item.list_object.list_type == mt.CACHE_MISSED:
            send_queue = self.queue_read
            #client = self.amq_client_read
        elif item.list_object.list_type == mt.MDC_PURGE:
            send_queue = self.queue_purge
            #client = self.amq_client_purge
        elif item.list_object.list_type == mt.CACHE_WRITTEN:
            time.sleep(15)
            send_queue = self.queue_write
            #client = self.amq_client_write
        else:
            Trace.alarm(e_errors.WARNING, "Unknown message type {}".format(item))
            return

        sender = self._create_sender(
            client, send_queue, item.list_object.disk_library)
        self.migrate_list(item, sender)
