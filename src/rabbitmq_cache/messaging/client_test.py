#!/usr/bin/env python

'''
client.py - Enstore rabbitmq messaging client
'''
from __future__ import print_function
import sys
import logging
#import client


import rabbitmq_cache.messaging.client as cml

# Connection reconnect_timeout in seconds
TO_RECONNECT_INTERVAL = 10
TO_RECONNECT_INTERVAL_MIN = 10
TO_RECONNECT_INTERVAL_MAX = 60
TO_CON_CLOSE = 5  # Connection Close timeout in sec

ALLOWED_SASL_MECHANISM = ('ANONYMOUS', 'PLAIN', 'GSSAPI')
DEFAULT_EXCHANGE = 'encache'
debug = False
MAX_QUEUE_SIZE = 200000


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

    c = cml.EnAMQPClient(amq_broker, my_queue='t_policy_engine', target_queue='t_migration_dispatcher',
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
                c.send("client2 unit test {}".format(cnt))
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
