#!/usr/bin/env python

###############################################################################
#
# $Id: delfile_chimera.py,v 1.7 2013/10/02 18:34:20 litvinse Exp $
#
# Equivalent of delfile for chimera
# relies on configuration entry that looks like this:
#
# configdict['namespace']    = {
#    'cms' : {'dbname' : 'chimera',
#             'dbhost' : 'dmsdca03',
#             'dbport' : 5432,
#             'dbuser' : 'enstore' },
#    }
#
#  The key in dictionary ('cms') is just a name
#
# how it works:
# loops over all chimera databases and extract bfid and pnfsid from
# t_locationinfo_trash table. Loop over each entry and mark file as
# deleted in file table, then remove entry from  t_locationinfo_trash
# if error occurs tries to rollback deletion and change delete flag
# in file table
#
###############################################################################


# system imports
from __future__ import print_function
from future import standard_library
standard_library.install_aliases()
from builtins import str
import os
import sys
import traceback
import urllib.parse

import psycopg2
import psycopg2.extras

import dbutils.pooled_db as PooledDB

import Trace
import alarm_client
import e_errors
import file_clerk_client
import info_client
import option


def delete_trash_record(db, pnfsid, itype):
    """
    delete record in trash table
    """
    delete_cursor = None
    success = True
    try:
        delete_cursor = db.cursor()
        #
        # we are removing only TAPE files (itype=0) DISK files (itype=1) are handled by dCache
        # cleaner
        #
        cmd = "delete from t_locationinfo_trash where ipnfsid='{}' and itype={}".format(pnfsid, itype)
        delete_cursor.execute(cmd)
        db.commit()
    except psycopg2.Error as msg:
        success = False
        try:
            if db:
                db.rollback()
        except psycopg2.Error as msg:
            sys.stderr.write("Failed to rollback delete of pnfsid {} from t_localinfo_trash, {} \n".format(pnfsid, msg))
    finally:
        if delete_cursor:
            try:
                delete_cursor.close()
            except BaseException:
                pass
            delete_cursor = None
    return success

def main(intf):
    success = True

    if os.geteuid() != 0:
        sys.stderr.write("Must be user root.\n")
        return False
    itype = 0 # tape
    if not intf.vol:
        print("volume not specified")
        return
    if intf.clear:
        itype = 2 # inode
    fcc = file_clerk_client.FileClient((intf.config_host, intf.config_port))
    ifc = info_client.infoClient((intf.config_host, intf.config_port))

    files = ifc.tape_list(intf.vol)
    if not e_errors.is_ok(files):
        return
    pnfsids = []
    for f in files['tape_list']:
        pnfsids.append(f['pnfsid'])

    namespaceDictionary = fcc.csc.get('namespace')

    if not namespaceDictionary:
        sys.stderr.write("No namespace dictionary in configuration root.\n")
        return False

    if not e_errors.is_ok(namespaceDictionary):
        sys.stderr.write(
            "Got error retrieving namespace dictionary from config {}\n".format(namespaceDictionary['status']))
        return False

    del namespaceDictionary['status']

    for key, value in namespaceDictionary.items():
        connectionPool = None
        cursor = None
        db = None

        dbcon = value
        if "master" in value:
            dbcon = value.get("master")

        try:
            connectionPool = PooledDB.PooledDB(psycopg2,
                                               maxconnections=1,
                                               blocking=True,
                                               host=dbcon.get(
                                                   'dbhost', 'localhost'),
                                               port=dbcon.get('dbport', 5432),
                                               user=dbcon.get(
                                                   'dbuser', 'enstore'),
                                               database=dbcon.get('dbname', 'chimera'))
            db = connectionPool.connection()
            cursor = db.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
            #
            # we are looking for only TAPE files (itype=0) DISK files (itype=1) are handled by dCache
            # cleaner
            #
            for e_pnfsid in pnfsids:
                cmd = "select * from t_locationinfo_trash where itype={} and ipnfsid='{}'".format(itype, e_pnfsid)
                cursor.execute(cmd)
                res = cursor.fetchall()

                for row in res:
                    delete_cursor = None
                    pnfsid = row.get('ipnfsid')
                    #
                    # ilocation field is URI like and looks:
                    #   enstore://enstore/?volume=NUL002&location_cookie=0000_000000000_0021154&size=1816&file_family=testers&original_name=/pnfs/fnal.gov/data/testers/NULL/enstore/fstab.16&map_file=&pnfsid_file=0000D05E3A18BB7F4378BB460A066B66B850&pnfsid_map=&bfid=B0MS129054868400000&origdrive=dmsdca03:/dev/null:0&crc=0
                    #
                    ilocation = row.get('ilocation')
                    #
                    # files in /pnfs/fs/usr/Migration will have ilocation set to '\n'
                    #
                    if not ilocation and itype == 2:
                        # try to find bfid
                        finfo = ifc.find_file_by_pnfsid(pnfsid)
                        if e_errors.is_ok(finfo):
                            bfid = finfo.get('bfid')
                            if not intf.check:
                                print('would delete', bfid, pnfsid, '...', end=' ')
                                #result = fcc.set_deleted('yes', bfid=bfid)
                                #if result['status'][0] not in (
                                #        e_errors.OK, e_errors.NO_FILE):
                                #    print(bfid, result['status'][1])
                                #    success = False
                                #else:
                                #    success = delete_trash_record(db, pnfsid, itype)


                    elif ilocation == '\n':
                        print("AAAA")
                        #success = delete_trash_record(db, pnfsid, itype)
                    else:
                        print("BBBB", ilocation, itype)
                        
                        url_dict = urllib.parse.parse_qs(ilocation)
                        if not url_dict or not url_dict.get('bfid', None):
                            print("BBB1")
                            #success = delete_trash_record(db, pnfsid, itype)
                            continue
                        bfid = url_dict.get('bfid')[0]
                        fcc.bfid = bfid
                        active_package_count = fcc.bfid_info().get('active_package_files_count', 0)
                        if active_package_count is None:
                            active_package_count = 0
                        package_id = fcc.bfid_info().get('package_id', None)
                        if package_id is None:
                            package_id = ''
                        if active_package_count > 0 and \
                           package_id == bfid:
                            Trace.log(e_errors.WARNING,
                                      'Skipping non-empy package file %s' % (
                                          bfid,),
                                      fcc.bfid_info().get('pnfs_name0', None))
                            print('skipping non-empty package file', bfid, '...')
                            continue
                        print('deleting', bfid, pnfsid, '...', end=' ')
                        #result = fcc.set_deleted('yes')
                        #if result['status'][0] not in (
                        #        e_errors.OK, e_errors.NO_FILE):
                        #    print(bfid, result['status'][1])
                        #    success = False
                        #else:
                        #    success = delete_trash_record(db, pnfsid, itype)
                        """
                        during SFA testing we encountered many cases where BFID of these file
                        no longer in database. Skip these as not errors.
                        """
                        #if result['status'][0] not in (
                        #        e_errors.OK, e_errors.NO_FILE):
                        #    print(bfid, result['status'][1])
                        #    success = False
                        #else:
                        #    print("BBB2")
                        #    success = delete_trash_record(db, pnfsid, itype)
        except psycopg2.OperationalError as opr:
            Trace.alarm(
                e_errors.ALARM,
                "Delfile failed for namespace {} : {}".format(
                    key,
                    opr.message))
            success = False
        finally:
            for item in [cursor, db, connectionPool]:
                if item:
                    item.close()
    if not success:
        return 1
    return 0


def do_work(intf):
    alarm_client.Trace.init("DELFILE")

    try:
        exit_status = main(intf)
    except (SystemExit, KeyboardInterrupt) as msg:
        Trace.log(e_errors.ERROR, "delfile aborted from: %s" % str(msg))
        sys.exit(1)
    except BaseException:
        # Get the uncaught exception.
        exc, msg, tb = sys.exc_info()
        # Print it to terminal.
        traceback.print_exception(exc, msg, tb)
        # Also, send it to the log file.
        Trace.handle_error(exc, msg, tb)

        del tb  # No cyclic references.
        sys.exit(1)
    sys.exit(exit_status)


class DelfileInterface(option.Interface):
    def __init__(self, args=sys.argv, user_mode=0):
        self.clear = 0
        self.vol = ''
        self.check = False
        option.Interface.__init__(self, args=args, user_mode=user_mode)

    def valid_dictionaries(self):
        return (self.help_options, self.config_options)
    config_options = {
        option.CLEAR: {option.HELP_STRING: "remove files indicated by inode",
                    option.DEFAULT_TYPE: option.INTEGER,
                    option.USER_LEVEL: option.ADMIN
                       },
        option.VOL: {option.HELP_STRING: "get info of a volume",
                     option.VALUE_TYPE: option.STRING,
                     option.VALUE_USAGE: option.REQUIRED,
                     option.VALUE_LABEL: "volume_name",
                     option.USER_LEVEL: option.USER},
        option.CHECK: {option.HELP_STRING: "just check do not remove from table",
                      option.DEFAULT_VALUE: option.DEFAULT,
                      option.DEFAULT_TYPE: option.INTEGER,
                      option.VALUE_USAGE: option.IGNORED,
                      option.USER_LEVEL: option.USER},

    }


if __name__ == "__main__":   # pragma: no cover
    intf_of_delfile = DelfileInterface()
    do_work(intf_of_delfile)
