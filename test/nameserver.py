from __future__ import print_function
#
# infinite loop pinging nameserver.  Run test for several hours to see
# the frequency of nameserver lookup errors.
#

from builtins import str
import socket
import sys
import time
import timeofday
import traceback

while 1:
    try:
        socket.gethostbyaddr(socket.gethostname())
        socket.gethostbyaddr("pcfarm4.fnal.gov")
    except BaseException:
        traceback.print_exc()
        format = timeofday.tod() + " " +\
            str(sys.argv) + " " +\
            str(sys.exc_info()[0]) + " " +\
            str(sys.exc_info()[1]) + " " +\
            "nameserver testing continuing"
        print(format)
    time.sleep(1)
