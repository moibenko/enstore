#!/usr/bin/env python

##############################################################################
#
# $Id$
#
##############################################################################
import logging

import cache.en_logging.handlers

# set enstore logger and tracer


def set_logging(name):
    # @param - name: name for logger and tracer
    # @return - (logger, tracer)
    # define format as standard enstore format
    logging_fmt = logging.Formatter("%(levelname)s %(message)s")  # for logging
    # logging_fmt = logging.Formatter("%(asctime)s %(name)s %(levelname)s
    # %(message)s") # for logging
    trace_fmt = logging.Formatter(
        # for trace
        "%(levelname)s chan=%(name)s module=%(module)s file=%(filename)s %(lineno)d %(message)s")

    # Log settings
    lh = cache.en_logging.handlers.EnLogHandler(name)
    lh.setFormatter(logging_fmt)

    logger = logging.getLogger('log.encache')
    logger.addHandler(lh)

    # you may raise logging level here, and DEBUG will not reach Trace.log
    # otherwise all messages are sent to trace and filtered there
    #  l_log.setLevel(logging.DEBUG) or else can be called anywhere any time
    # DEBUG is default in EnLogHandler, you may skip it here
    logger.setLevel(logging.INFO)

    # Trace settings are similar
    th = cache.en_logging.handlers.EnTraceHandler(name)
    th.setFormatter(trace_fmt)

    tracer = logging.getLogger('trace.encache')
    tracer.addHandler(th)
    # tracer.setLevel(logging.DEBUG)

    # Qpid
    qpid_fmt = logging.Formatter("%(levelname)s %(message)s")
    # Log settings
    qh = cache.en_logging.handlers.EnLogHandler(name)
    qh.setFormatter(qpid_fmt)

    q_logger = logging.getLogger('qpid')
    q_logger.addHandler(qh)
    # adjust report level here or reset it later
    # can get logger 'qpid.messaging' and adjust its level separately
    q_logger.setLevel(logging.WARNING)

    return logger, tracer
