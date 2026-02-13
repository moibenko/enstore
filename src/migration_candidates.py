#!/usr/bin/env python

###############################################################################
# queries all volumes, finds volumes with deleted to total ratio above
# specified threshold and sends to stdout
#
###############################################################################


# system imports
import os
import sys
import traceback

import edb
import configuration_client
import Trace
import e_errors
import option

if __name__ == "__main__":   # pragma: no cover

    upper_limit = 80.
    if len(sys.argv) > 1:
        upper_limit = float(sys.argv[1])
        
    success = True
    csc = configuration_client.ConfigurationClient((os.environ['ENSTORE_CONFIG_HOST'], int(os.environ['ENSTORE_CONFIG_PORT'])))
    dbInfo = csc.get('database')
    volumedb_dict = edb.VolumeDB(host=dbInfo.get('db_host'),
                                 port=dbInfo.get('db_port'),
                                 user=dbInfo.get('dbuser'),
                                 database=dbInfo.get('dbname'),
                                 auto_journal=0,
                                 max_connections=20,
                                  max_idle=5)
    q = "select  label as vol, deleted_files as del, active_files as active, \
    trunc(deleted_files/(active_files+deleted_files)::numeric*100,2) as p_del \
    from volume where label not like '%.deleted' and deleted_files!=0 and trunc(deleted_files/(active_files+deleted_files)::numeric*100,2) > {}\
    order by p_del desc \
    ".format(upper_limit)
    res = volumedb_dict.query_getresult(q)
    if len(res) > 0:
        print("label    active deleted  percent_deleted")
        for row in res: 
            print("{:8s} {:06d} {:06d}   {:05.1f}".format(row[0], row[1], row[2], row[3]))
        print("==================")
        print("Total volumes: {}".format(len(res)))
