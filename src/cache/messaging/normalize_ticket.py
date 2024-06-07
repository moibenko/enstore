#!/usr/bin/env python
import types


def normalize_ticket(obj):
    """Normalize content of enstore ticket received from qpid by convering unicode to ascii and lists to tuples
    """
    if type(obj) in [type(None), str, int, bool, float]:
        return obj
    elif isinstance(obj, unicode):
        return obj.encode('ascii', 'replace')
    elif isinstance(obj, dict):
        d = {}
        for k, v in obj.items():
            # self.trace.debug(" k,v %s,%s",k,v )
            d[normalize_ticket(k)] = normalize_ticket(v)
        return d
    elif type(obj) in [list, tuple]:
        return tuple(map(normalize_ticket, obj))

    return obj
