#!/usr/bin/env python
#
# $Id$
#

import os
import sys
import signal
import Trace

import configuration_client
import file_clerk_client
import enstore_functions2
import e_errors

_deletion_list = []
_deletion_list_bfids = []

def register(filename):
    if filename == '/dev/null':
        return
    if filename not in _deletion_list:
        _deletion_list.append(filename)

def register_bfid(bfid):
    if bfid not in _deletion_list_bfids:
        _deletion_list_bfids.append(bfid)

def unregister(filename):
    if filename == '/dev/null':
        return
    if filename in _deletion_list:
        _deletion_list.remove(filename)

def unregister_bfid(bfid):
    if bfid in _deletion_list_bfids:
        _deletion_list_bfids.remove(bfid)

def delete():
    # Delete registered files.
    for f in _deletion_list:
        Trace.log(e_errors.INFO, "Performing file cleanup for file: %s" % (f,))
        if os.path.exists(f):
            try:
                os.unlink(f)
            except:
                Trace.log(e_errors.ERROR, "Can not delete file %s.\n" % (f,))
                sys.stderr.write("Can not delete file %s.\n" % (f,))

    # get a configuration server and file clerk
    config_host = enstore_functions2.default_host()
    config_port = enstore_functions2.default_port()
    csc = configuration_client.ConfigurationClient((config_host,config_port))

    # Delete registered bfids.
    for b in _deletion_list_bfids:
        Trace.log(e_errors.INFO, "Performing bfid cleanup for: %s" % (b,))
        try:
            fcc = file_clerk_client.FileClient(csc, b)
            fcc.set_deleted("yes")
        except:
            Trace.log(e_errors.ERROR,
                      "Can not delete bfid %s from database.\n" % (b,))
            sys.stderr.write("Can not delete bfid %s from database.\n" % (b,))

            
def signal_handler(sig, frame):

    try:
        if sig not in [signal.SIGTERM, signal.SIGINT, signal.SIGQUIT]:
            sys.stderr.write("Signal caught at: %s line %d\n" %
                             (frame.f_code.co_filename, frame.f_lineno))
            sys.stderr.flush()
    except (OSError, IOError, TypeError):
        exc, msg = sys.exc_info()[:2]
        try:
            sys.stderr.write("%s: %s\n" % (str(exc), str(msg)))
            sys.stderr.flush()
        except IOError:
            pass
    
    try:
        sys.stderr.write("Caught signal %s, exiting.\n" % (sig,))
        sys.stderr.flush()
    except IOError:
        pass

    quit(1)

def setup_signal_handling():
    
    #Handle all signals not in the known skip list.
    for sig in range(1, signal.NSIG):
        if sig not in (signal.SIGTSTP, signal.SIGCONT,
                       signal.SIGCHLD, signal.SIGWINCH):
            try:
                signal.signal(sig, signal_handler)
            except RuntimeError:
                pass
            except (ValueError, TypeError):
                sys.stderr.write("Setting signal %s to %s failed.\n" %
                                 (sig, signal_handler))

def quit(exit_code=1):
    delete()
    os._exit(exit_code)
