#!/usr/bin/env python
###############################################################################
# src/$RCSfile$   $Revision$
#

import enmv

def do_work():
    # admin mode
    mode = 0

    intf = enmv.EnmvInterface(user_mode=mode)
    if intf:
	enmv.do_work(intf)

if __name__ == "__main__" :

    do_work()
