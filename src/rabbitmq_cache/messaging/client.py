#!/usr/bin/env python

'''
client.py - Enstore rabbitmq messaging client
'''
from __future__ import print_function
from future.utils import raise_
import pika
import logging
import sys
import multiprocessing
import threading
import queue
import time
import pickle
import uuid

import e_errors
import Trace

# Connection reconnect_timeout in seconds
TO_RECONNECT_INTERVAL = 10
TO_RECONNECT_INTERVAL_MIN = 10
TO_RECONNECT_INTERVAL_MAX = 60
TO_CON_CLOSE = 5  # Connection Close timeout in sec

ALLOWED_SASL_MECHANISM = ('ANONYMOUS', 'PLAIN', 'GSSAPI')
DEFAULT_EXCHANGE = 'encache_default'
debug = False
MAX_QUEUE_SIZE = 200000

class EnAMQPError(Exception):
    """
    Needed to raise EnAMQP specific exceptions.

    """

    def __init__(self, arg):
        Exception.__init__(self, arg)

class Connection(object):
    """
    Create connection to amqp broker
    """
    def __init__(self, connection_parameters):
        """
        Args:
            connection_parameters: pika.ConnectionParameters
        """

        self.connection_parameters = connection_parameters
        self.log = logging.getLogger('log.encache.messaging')
        self.trace = logging.getLogger('trace.encache.messaging')
        self._conn = False
        self.connect()

    def connect(self):
        """
        Create connection
        pika is not thread safe
        so, create connection in each instance to be able to run in thread
        """
        if not self._conn or self._conn.is_closed:
            self._conn = pika.BlockingConnection(self.connection_parameters)
            self.channel = self._conn.channel()


    def close(self):
        """
        Close connection
        """
        if self._conn:
            self._conn.close()

    def __del__(self):
        self.close()

class Sender(Connection):
    """
    rabbitmq sender
    """
    def __init__(self, 
                 connection_parameters, 
                 queue, 
                 exchange='/', 
                 exchange_type='direct', 
                 routing_key=None, 
                 exclusive=False,
                 auto_delete=False
             ):
        """
        Create rabbitmq sender
        Args:
            connection_parameters: pika.ConnectionParameters
            queue (str): queue name
            exchange (str): exchange name
            exchange_type (str): exchange type
            routing_key (str): exchange routing key
            exclusive (bool): exclusive queue
            auto_delete (bool): auto_delete queue
        """
        self.log = logging.getLogger('log.encache.messaging')
        self.trace = logging.getLogger('trace.encache.messaging')
        self.exchange = exchange if exchange not in ('', None) else DEFAULT_EXCHANGE
        self.queue = queue
        self.exclusive = exclusive
        self.auto_delete = auto_delete
        super().__init__(connection_parameters)
        if not routing_key:
            routing_key = queue
        self.routing_key = routing_key
        Trace.log(e_errors.INFO,
                  "CREATING SENDER for queue {} exchange {} type {} routing key {} exclusive {}".format(self.queue,
                                                                                                        self.exchange,
                                                                                                        exchange_type,
                                                                                                        self.routing_key,
                                                                                                        exclusive))
        try:
            self.channel.exchange_declare(exchange=self.exchange,
                                          exchange_type=exchange_type)
            self.channel.queue_declare(queue=self.queue, durable=True, exclusive=self.exclusive, auto_delete=self.auto_delete)
            self.channel.queue_bind(exchange=self.exchange, queue=self.queue, routing_key=self.routing_key)
            self.channel.confirm_delivery()
        except Exception as e:
            Trace.log(e_errors.ERROR, 
                      "Sender Error, exception {} {} queue {} routing key {}".format(sys.exc_info()[0], 
                                                                                     sys.exc_info()[1],
                                                                                     self.queue,
                                                                                     self.routing_key))
            raise_(e)

    def _publish(self, msg, routing_key=None):
        """
        Publish message 
        Args:
          msg (obj): mesage to send
          routing_key (str): send using routing_key
        """
 
        routing_key = routing_key if routing_key else self.routing_key

        """
        self.channel.queue_declare(queue=routing_key, 
                                   durable=True, 
                                   exclusive=self.exclusive, 
                                   auto_delete=self.auto_delete)
        self.channel.queue_bind(exchange=self.exchange, queue=routing_key, routing_key=routing_key)
        """
        Trace.trace(10, "_publish {} {} {}".format(self.exchange, routing_key, msg))
        data = pickle.dumps(msg)
        try:
            self.channel.basic_publish(exchange=self.exchange,
                                       routing_key=self.routing_key,
                                       body=data,
                                       properties=pika.BasicProperties(
                                           delivery_mode = 2, # make message persistent                             
                                       ))
        except Exception as e:
            raise(e)

        Trace.trace(10, 'message sent: {} {}'.format(self.queue, msg))

    def send(self, msg, routing_key=None):
        """Publish msg, reconnecting if necessary."""
        routing_key = routing_key if routing_key else self.routing_key
        self._publish(msg)

class Receiver(Connection):
    def __init__(self, 
                 connection_parameters, 
                 queue, exchange='/', 
                 exchange_type='direct', 
                 exclusive=False,
                 auto_delete=False
             ):
        self.log = logging.getLogger('log.encache.messaging')
        self.trace = logging.getLogger('trace.encache.messaging')
        Trace.log(e_errors.INFO,
                  "CREATING RECEIVER for queue {} exchange {} type {} routing key {} exclusive {}".format(queue,
                                                                                                          exchange,
                                                                                                          exchange_type,
                                                                                                          queue,
                                                                                                          exclusive))
        self.exchange = exchange
        self.queue = queue
        super().__init__(connection_parameters)

        self.buff = multiprocessing.Queue(MAX_QUEUE_SIZE) # messages go here
        try:
            self.channel.exchange_declare(exchange=exchange,
                                         exchange_type=exchange_type)
            self.channel.queue_declare(queue=queue, durable=True, exclusive=exclusive, auto_delete=auto_delete)
            self.channel.queue_bind(exchange=exchange, queue=queue, routing_key=queue)
            self.channel.basic_qos(prefetch_count=1) 
            self.channel.confirm_delivery()
        except:
            Trace.log(e_errors.ERROR,
                      "Sender Error, exception %s %s", sys.exc_info()[0], sys.exc_info()[1])
    
    def __str__(self):
        return "Receiver. Queue {}, exchange {}".format(self.queue, self.exchange)

    def callback(self, ch, method, properties, message):
        msg = pickle.loads(message)
        Trace.trace(10, f" [x] Received Method={method} properties {properties} message {msg}")
        self.buff.put_nowait(msg)
    
    def start_receiver(self):
        Trace.log(e_errors.INFO, "START COSUMING queue={} exchange={}".format(self.queue, self.exchange))
        try:
            self.channel.basic_consume(queue=self.queue, on_message_callback=self.callback, auto_ack=True)
            self.channel.start_consuming()
        except Exception as e:
            Trace.log(e_errors.ERROR,
                      "exception starting receiver. queue={} exchange={} {}".format(self.queue, self.exchange, e))
            raise(e)

    def start(self):
        Trace.log(e_errors.INFO, "START RECEIVER queue={} exchange={}".format(self.queue, self.exchange))
        rec_thread = threading.Thread(target=self.start_receiver)
        rec_thread.start()

    def fetch(self):
        msg = ''
        if not self.buff.empty():
            msg = self.buff.get_nowait()
            Trace.trace(10, "FETCH {}".format(msg))
        return msg

class _Session(object):
    def __init__(self,
                 host_port,
                 virtual_host='/',
                 user=None,
                 password=None,
                 authentication='PLAIN'):
        """                           
        :type host_port: :obj:`tuple`
        :arg host_port: (:obj:`str` - host name, :obj:`int`- port)
        :type virtual_host: :obj:`str`
        :arg virtual_host: (:obj:`str` - virtual host (rabbitmq))
        :type user: :obj:`str`
        :arg user: client user name
        :type password: :obj:`str`
        :arg password: client user name
        :type authentication: :obj:`str`
        :arg authentication: space separated set of authentication mechanisms. The values can be:
        ANONYMOUS, PLAIN, CRAM-MD5, DIGEST-MD5, GSSAPI
        """
        self.virtual_host = virtual_host
        self.user = user
        self.password = password
        self.authentication = authentication
        if self.authentication not in ALLOWED_SASL_MECHANISM:
            raise EnAMQPError(
                'Declared authentication mechanism %s is not in the list of allowed: %s' %
                (self.authentication, ALLOWED_SASL_MECHANISM,))
        if self.authentication == 'PLAIN' and self.user is None:
            self.user = 'enstore' # TO DO: get this from someweher else or use SASL
            self.password = '12345' # TO DO: get this from someweher else
        credentials = pika.PlainCredentials(username=self.user, password=self.password)

        self.log = logging.getLogger('log.encache.messaging')
        self.trace = logging.getLogger('trace.encache.messaging')

        self.host, self.port = host_port
        self._conn = None
        #self.connection_parameters = pika.ConnectionParameters(self.host, self.port, virtual_host, credentials)
        self.connection_parameters = pika.ConnectionParameters(self.host, self.port, virtual_host, credentials, heartbeat=0)

        self.name = str(uuid.uuid4())

    def sender(self, queue, exchange, exchange_type, exclusive=False, auto_delete=False):
        Trace.log(e_errors.INFO, 'creating sender {} {} {}'.format(queue, exchange, exchange_type))
        sndr = Sender(self.connection_parameters, 
                      queue, 
                      exchange=exchange, 
                      exchange_type=exchange_type, 
                      exclusive=exclusive, 
                      auto_delete=auto_delete)
        return sndr

    def receiver(self, queue, exchange, exchange_type, exclusive=False, auto_delete=False):
        Trace.log(e_errors.INFO, 'creating receiver {} {} {} {}'.format(queue, exchange, exchange_type, auto_delete))
        return Receiver(self.connection_parameters, 
                        queue, 
                        exchange=exchange, 
                        exchange_type=exchange_type, 
                        exclusive=exclusive,
                        auto_delete=auto_delete)
        

class EnAMQPClient(object):
    def __init__(self,
                 host_port,
                 virtual_host='/',
                 my_queue=None,
                 my_exchange='',
                 my_exchange_type='direct',
                 target_queue=None,
                 target_exchange='',
                 target_exchange_type='direct',
                 auto_delete=False,
                 user=None,
                 password=None,
                 authentication='PLAIN'):
        """
        :type host_port: :obj:`tuple`
        :arg host_port: (:obj:`str` - host name, :obj:`int`- port)
        :type virtual_host: :obj:`str`
        :arg virtual_host: (:obj:`str` - virtual host (rabbitmq))                                                   
        :type my_queue: :obj:`str`
        :arg my_queue: input queue
        :type my_exchange: :obj:`str`
        :arg my_exchange: input exchange
        :type my_exchange_type: :obj:`str`
        :arg my_exchange_type: type of input exchange (direct, topic)
        :type target_queue: :obj:`str`
        :arg target_queue: output queue
        :type target_exchange: :obj:`str`
        :arg target_exchange: output exchange
        :type target_exchange_type: :obj:`str`
        :arg target_exchange_type: type of output exchange (direct, topic)
        :type user: :obj:`str`
        :arg user: client user name
        :type password: :obj:`str`
        :arg password: client user name
        :type authentication: :obj:`str`
        :arg authentication: space separated set of authentication mechanisms. The values can be:
        ANONYMOUS, PLAIN, CRAM-MD5, DIGEST-MD5, GSSAPI
        """

        Trace.log(e_errors.INFO,
                  "EnAMQPClient {} {} {} {}".format(my_queue,
                                                    my_exchange,
                                                    target_queue,
                                                    target_exchange))
        self.virtual_host = virtual_host
        self.user = user
        self.password = password
        self.authentication = authentication
        if self.authentication not in ALLOWED_SASL_MECHANISM:
            raise EnAMQPError(
                'Declared authentication mechanism %s is not in the list of allowed: %s' %
                (self.authentication, ALLOWED_SASL_MECHANISM,))
        if self.authentication == 'PLAIN' and self.user is None:
            self.user = 'enstore'
            self.password = '12345'
        credentials = pika.PlainCredentials(username=self.user, password=self.password)

        self.log = logging.getLogger('log.encache.messaging')
        self.trace = logging.getLogger('trace.encache.messaging')

        self.host, self.port = host_port
        self.my_queue = my_queue     # my queue to be used in reply receiver
        self.my_exchange = my_exchange if my_exchange not in ('', None) else DEFAULT_EXCHANGE # my exchange to be used in reply receiver
        self.my_exchange_type = my_exchange_type
        self.target_queue = target_queue    # destination queue to be used in sender
        self.target_exchange = target_exchange if target_exchange != '' else DEFAULT_EXCHANGE
        self.target_exchange_type = target_exchange_type
        self._conn = False
        
    def __str__(self):
        # show all variables in sorted order
        showList = sorted(set(self.__dict__))

        return ("<%s instance at 0x%x>:\n" % (self.__class__.__name__, id(self))) + "\n".join(["  %s: %s"
                % (key.rjust(8), self.__dict__[key]) for key in showList])


    def start(self):
        Trace.log(e_errors.INFO, 
                  "EnAMQPClient broker host, port: {} {}".format(self.host,
                                                                 self.port)
              )

        Trace.log(e_errors.INFO,
                  "CREATING CONNECTION {} {} {} {} {} {} {}".format (self.host,
                                                                     self.port,
                                                                     self.user,
                                                                     self.password,
                                                                     self.virtual_host,
                                                                     self.authentication,
                                                                     True,
                                                                     TO_RECONNECT_INTERVAL))

        self.ssn = _Session((self.host, self.port), 
                              self.virtual_host, 
                              self.user, 
                              self.password, 
                              self.authentication)
        if self.target_queue:
            Trace.log(e_errors.INFO, "creating default sender")
            try:
                self.snd_default = self.ssn.sender(self.target_queue, 
                                                   self.target_exchange, 
                                                   self.target_exchange_type)    # default sender sends messages to target
            except Exception as e:
                Trace.log(e_errors.ERROR, "Exception creating sender {} {}".format(self.target_queue, e))
                raise_(sys.exc_info()[0], sys.exc_info()[1], sys.exc_info()[2])
        auto_delete = False

        if self.my_queue:
            try:
                self.rcv_default = self.ssn.receiver(self.my_queue,
                                                     self.my_exchange,
                                                     self.my_exchange_type,
                                                     auto_delete=auto_delete)
                self.rcv_default.start()

            except Exception as e:
                Trace.log(e_errors.ERROR, "Exception creating receiver {} {}".format(self.my_queue, e))
                raise_(sys.exc_info()[0], sys.exc_info()[1], sys.exc_info()[2])

    def stop(self):
        # @todo: We do not acknowledge whatever is left in the queue - it is not processed.
        self.started = False
        try:
            self.conn.close(TO_CON_CLOSE)
        except :
            Trace.log(e_errors.ERROR, f"amqp client - Can not close connection {self.conn}")

    # @todo block/async

    def send(self, msg, *args, **kwargs ):
        try:
            self.snd_default.send(msg, *args, **kwargs )
        except:
            Trace.trace(10, "client send()")
            raise_(sys.exc_info()[0], sys.exc_info()[1], sys.exc_info()[2])

    def fetch(self, *args, **kwargs ):
        try:
            msg = self.rcv_default.fetch(*args, **kwargs )
            return msg
        except:
            Trace.trace(10, "client fetch()")
            raise_(sys.exc_info()[0], sys.exc_info()[1], sys.exc_info()[2])
            
    # this will work only after client is started (session must be set prior this call)
    def add_receiver(self, name, source, exchange=DEFAULT_EXCHANGE, exchange_type='direct'):
        """
        create additional receiver to read "source" queue
        """
        rec = self.ssn.receiver(source, exchange, exchange_type)
        setattr(self, name, rec)
        rec.start()
        return getattr(self,name)

    # this will work only after client is started (session need to be set)
    def add_sender(self, name, target, exchange=DEFAULT_EXCHANGE, exchange_type='direct'):
        """
        create additional sender 'target' to which messages will be sent
        """
        snd = self.ssn.sender(target, exchange, exchange_type)
        setattr(self, name, snd)
        return getattr(self,name)


if __name__ == "__main__":   # pragma: no cover
    import time
    import optparse

    user = password = None
    parser = optparse.OptionParser()
    parser.add_option("--sasl-mechanism", action="store", type="string", metavar="<mech>", help="SASL mechanism for authentication (ANONYMOUS, PLAIN, GSSAPI)")
    opts, encArgs = parser.parse_args(args=sys.argv)
    if not opts.sasl_mechanism:
        auth = 'ANONYMOUS'
    else:
        auth = opts.sasl_mechanism
    if auth not in ALLOWED_SASL_MECHANISM:
        print("only %s is allowed"%(ALLOWED_SASL_MECHANISM))
        sys.exit(1)
    if auth in ('ANONYMOUS', 'PLAIN'):
        user = 'enstore'
        password = '12345'

    def set_logging():
        lh = logging.StreamHandler()
        #    fmt = logging.Formatter("%(asctime)s - %(name)s - %(levelname)s - %(message)s")
        # %(pathname)s
        fmt = logging.Formatter("%(filename)s %(lineno)d :: %(name)s :: %(module)s :: %(levelname)s :: %(message)s")

        l_log = logging.getLogger('log.encache.messaging')
        l_trace = logging.getLogger('trace.encache.messaging')
        #add formatter to lh
        lh.setFormatter(fmt)
        l_log.addHandler(lh)
        l_trace.addHandler(lh)

        l_log.setLevel(logging.DEBUG)
        l_trace.setLevel(logging.DEBUG)

    set_logging()

    amq_broker=("dvl-es-hd02",5672)
    myaddr="t_policy_engine"
    target="t_migration_dispatcher"
    qr = "t_md_replies"
    qm = "t_migrator"

    c = EnAMQPClient(amq_broker, my_queue='t_policy_engine', target_queue='t_migration_dispatcher',
                     user=user, password=password, authentication='PLAIN')
    print(c)
    c.start()
    print(c)

    r = c.add_receiver("from_md",qr)
    s = c.add_sender("to_mg",qm) # some existing queue
    print(r)
    print(s)
    print(c)

    do_fetch = False
    do_send = True
    do_consume = True

    if do_fetch:
        m = c.fetch()
        if m :
            print(m)
            # ack message, one way of tree below:
            #c.ssn.acknowledge()                # ack all messages in the session
            ###  c.ssn.acknowledge(m)                # ack this message
            #c.ssn.acknowledge(m,sync=False)    # ack this message, do not wait till ack is consumed

    print("To interrupt press ^C")
    cnt = 0
    rdr = c.add_receiver("drain",target)

    while 1:
        try:
            if do_send:
                #c.send("client2 unit test {}".format(cnt))
                d={'cnt':cnt}
                c.send(d)
                cnt += 1

            # consume message we just sent
            #rdr = c.add_receiver("drain",target)
            time.sleep(1)

            mr=c.drain.fetch()
            ### c.ssn.acknowledge(mr)
            print(time.ctime())
            print("MESSAGE RECEIVED", mr)
        except (SystemExit, KeyboardInterrupt):
            break
        except Exception as detail:
            print(detail)
            break
