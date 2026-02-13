#!/usr/bin/env python
import types


def normalize_ticket(obj):
    """Normalize content of enstore ticket received from rabbit-mq  by converting lists to tuples
    """
    if isinstance(obj, (type(None), str, bytes, int, bool, float)):
        return obj
    elif isinstance(obj, dict):
        d = {}
        for k, v in obj.items():
            # self.trace.debug(" k,v %s,%s",k,v )
            d[normalize_ticket(k)] = normalize_ticket(v)
        return d
    elif type(obj) in [list, tuple]:
        return tuple(map(normalize_ticket, obj))

    return obj
