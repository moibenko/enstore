#!/usr/bin/env python
import os

def get_ports():
    """
    Get range of port to use for communications.
    Useful with firewall
    """

    port_range = None
    ports = os.getenv('ENSTORE_CLIENT_PORTS')
    if ports:
        port_range = []
        portl, portm = ports.split(',')
        port_range.append(int(portl))
        port_range.append(int(portm))
    return port_range
