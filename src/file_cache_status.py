#!/usr/bin/env python
##############################################################################
#
# $Id$
#
##############################################################################

from __future__ import print_function


from builtins import object
class CacheStatus(object):
    CREATED = "CREATED"
    PURGING = "PURGING"
    PURGED = "PURGED"
    STAGING = "STAGING"
    STAGED = "STAGED"
    CACHED = "CACHED"
    STAGING_REQUESTED = "STAGING_REQUESTED"
    PURGING_REQUESTED = "PURGING_REQUESTED"
    FAILED = "FAILED"


class ArchiveStatus(object):
    ARCHIVING = "ARCHIVING"
    ARCHIVED = "ARCHIVED"
    FAILED = "FAILED"


if __name__ == "__main__":   # pragma: no cover
    print(CacheStatus.CREATED)
    print(ArchiveStatus.ARCHIVED)
