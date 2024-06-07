#!/usr/bin/env python

from __future__ import print_function
import sys
import accounting_client
import option

if __name__ == "__main__":   # pragma: no cover

    if len(sys.argv) < 2:
        # quit with error yet quiet
        sys.exit(1)

    intf = option.Interface()
    acc = accounting_client.accClient((intf.config_host, intf.config_port))
    tag = acc.log_start_event(sys.argv[1])
    print(tag)
