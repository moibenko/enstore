#!/usr/bin/env python

##############################################################################
# src/$RCSfile$   $Revision$
#
# system import
import sys
import os
import time
import string
import socket
import select
import pprint

# enstore imports
import setpath
import traceback
import callback
# import volume_clerk_client
import dispatching_worker
import generic_server
import event_relay_client
import monitored_server
import enstore_constants
import db
import bfid_db
import Trace
import e_errors
import configuration_client
import hostaddr
import pnfs

MY_NAME = "file_clerk"

class FileClerkMethods(dispatching_worker.DispatchingWorker):

    def __init__(self, csc):
        dispatching_worker.DispatchingWorker.__init__(self, csc)
        self.dict = None
        self.bfid_db = None
        return

    # set_brand(brand) -- set brand

    def set_brand(self, brand):
        self.brand = brand
        return

    # we need a new bit field id for each new file in the system
    def new_bit_file(self, ticket):
        # input ticket is a file clerk part of the main ticket
        # create empty record and control what goes into database
        # do not pass ticket, for example to the database!
        record = {}
        record["external_label"]   = ticket["fc"]["external_label"]
        record["location_cookie"]  = ticket["fc"]["location_cookie"]
        record["size"]             = ticket["fc"]["size"]
        record["sanity_cookie"]    = ticket["fc"]["sanity_cookie"]
        record["complete_crc"]     = ticket["fc"]["complete_crc"]
        
        # get a new bit file id
        bfid = self.unique_bit_file_id()
        record["bfid"] = bfid
        # record it to the database
        self.dict[bfid] = record 
        
        ticket["fc"]["bfid"] = bfid
        ticket["status"] = (e_errors.OK, None)
        self.reply_to_caller(ticket)
        Trace.trace(10,'new_bit_file bfid=%s'%(bfid,))
        return

    # update the database entry for this file - add the pnfs file id
    def set_pnfsid(self, ticket):
        try:
            bfid = ticket["fc"]["bfid"]
        except KeyError, detail:
            msg =  "File Clerk: key %s is missing"  % (detail,)
            ticket["status"] = (e_errors.KEYERROR, msg)
            Trace.log(e_errors.ERROR, msg)
            self.reply_to_caller(ticket)
            return

        # also need new pnfsid - make sure we have this
        try:
            pnfsid = ticket["fc"]["pnfsid"]
        except KeyError, detail:
            msg =  "File Clerk: key %s is missing"  % (detail,)
            ticket["status"] = (e_errors.KEYERROR, msg)
            Trace.log(e_errors.ERROR, msg)
            self.reply_to_caller(ticket)
            return

        # temporary workaround - sam doesn't want to update encp too often
        pnfsvid = ticket["fc"].get("pnfsvid")
        pnfs_name0 = ticket["fc"].get("pnfs_name0")
        pnfs_mapname = ticket["fc"].get("pnfs_mapname")

        # start (10/18/00) adding which drive we used to write the file
        drive = ticket["fc"].get("drive","unknown:unknown")

        # look up in our dictionary the request bit field id
        try:
            record = self.dict[bfid] 
        except KeyError, detail:
            "File Clerk: bfid %s not found"%(detail,)
            ticket["status"] = (e_errors.KEYERROR, msg)
            Trace.log(e_errors.ERROR, msg)
            self.reply_to_caller(ticket)
            return

        # add the pnfsid
        record["pnfsid"] = pnfsid
        record["drive"] = drive
        # temporary workaround - see above
        if pnfsvid != None:
            record["pnfsvid"] = pnfsvid
        if pnfs_name0 != None:
            record["pnfs_name0"] = pnfs_name0
        if pnfs_mapname != None:
            record["pnfs_mapname"] = pnfs_mapname
        record["deleted"] = "no"

        # record our changes
        self.dict[bfid] = record 
        ticket["status"] = (e_errors.OK, None)
        self.reply_to_caller(ticket)
        Trace.trace(12,'set_pnfsid %s'%(ticket,))
        return

    # change the delete state element in the dictionary
    # this method is for private use only
    def set_deleted_priv(self, bfid, deleted, restore_dir="no"):
        try:
            # look up in our dictionary the request bit field id
            try:
                record = self.dict[bfid] 
            except KeyError:
                status = (e_errors.KEYERROR, 
                          "File Clerk: bfid %s not found"%(bfid,))
                Trace.log(e_errors.INFO, "%s"%(status,))
                Trace.trace(10,"set_deleted %s"%(status,))
                return status, None, None


            if 'y' in string.lower(deleted):
                deleted = "yes"
                decr_count = 1
            else:
                deleted = "no"
                decr_count = -1
            # the foolowing fixes a problem with lost 'deleted' entry'
            fix_deleted = 0
            if not record.has_key('deleted'):
                fix_deleted = 1
                record["deleted"] = deleted
                
            if record["deleted"] == deleted:
                # don't return a status error to the user - she needs a 0 status in order to delete
                # the file in the trashcan.  Otherwise we are in a hopeless loop & it makes no sense
                # to try and keep deleting the already deleted file over and over again
                #status = (e_errors.USER_ERROR,
                #                    "%s = %s deleted flag already set to %s - no change." % (bfid,record["pnfs_name0"],record["deleted"]))
                status = (e_errors.OK, None)
                fname=record.get('pnfs_name0','pnfs_name0 is lost')
                Trace.log(e_errors.USER_ERROR, 
                "%s = %s deleted flag already set to %s - no change." % (bfid, fname, record["deleted"]))
                Trace.trace(12,'set_deleted_priv %s'%(status,))
                if fix_deleted:
                    self.dict[bfid] = record
                    Trace.log(e_errors.INFO, 'added missing "deleted" key for bfid %s' % (bfid,))
                return status, None, None

            if deleted == "no":
                # restore pnfs entry
                # import pnfs
                map = pnfs.Pnfs(record["pnfs_mapname"])
                status = map.restore_from_volmap(restore_dir)
                del map
                if status[0] != e_errors.OK:
                    Trace.log(e_errors.ERROR, "restore_from_volmap failed. Status: %s"%(status,))
                    return status, None, None 

            # mod the delete state
            record["deleted"] = deleted

            # do not maintain non_del_files
            #
            # # become a client of the volume clerk and decrement the non-del files on the volume
            # vcc = volume_clerk_client.VolumeClerkClient(self.csc)
            # vticket = vcc.decr_file_count(record['external_label'],decr_count)
            # status = vticket["status"]
            # if status[0] != e_errors.OK: 
            #     Trace.log(e_errors.ERROR, "decr_file_count failed. Status: %s"%(status,))
            #     return status, None, None 

            # record our changes
            self.dict[bfid] = record 

            Trace.log(e_errors.INFO,
                      "%s = %s flagged as deleted:%s  volume=%s   mapfile=%s" %
                      (bfid,record["pnfs_name0"],record["deleted"],
                       record["external_label"], record["pnfs_mapname"]))

            # and return to the caller
            status = (e_errors.OK, None)
            fc = record
            # vc = vticket
            Trace.trace(12,'set_deleted_priv status %s'%(status,))
            # return status, fc, vc
            return status, fc, None

        # if there is an error - log and return it
        except:
            exc, val, tb = Trace.handle_error()
            status = (str(exc), str(val))

    def get_crcs(self, ticket):
        try:
            bfid  =ticket["bfid"]
            record=self.dict[bfid]
            complete_crc=record["complete_crc"]
            sanity_cookie=record["sanity_cookie"]
        except KeyError, detail:
            msg =  "File Clerk: key %s is missing" % (detail,)
            ticket["status"]=(e_errors.KEYERROR, msg)
            Trace.log(e_errors.ERROR, msg)
            self.reply_to_caller(ticket)
            return
        ticket["status"]=(e_errors.OK, None)
        ticket["complete_crc"]=complete_crc
        ticket["sanity_cookie"]=sanity_cookie
        self.reply_to_caller(ticket)

    def set_crcs(self, ticket):
        try:
            bfid  =ticket["bfid"]
            complete_crc=ticket["complete_crc"]
            sanity_cookie=ticket["sanity_cookie"]
            record=self.dict[bfid]
        except KeyError, detail:
            msg = "File Clerk: key %s is missing"%(detail,)
            ticket["status"]=(e_errors.KEYERROR, msg)
            Trace.log(e_errors.ERROR, msg)
            self.reply_to_caller(ticket)
            return
        record["complete_crc"]=complete_crc
        record["sanity_cookie"]=sanity_cookie
        #record our changes to the database
        self.dict[bfid] = record
        ticket["status"]=(e_errors.OK, None)
        #reply to caller with updated database values
        record=self.dict[bfid]
        ticket["complete_crc"]=record["complete_crc"]
        ticket["sanity_cookie"]=record["sanity_cookie"]
        self.reply_to_caller(ticket)


        
    # change the delete state element in the dictionary
    def set_deleted(self, ticket):
        try:
            bfid = ticket["bfid"]
            deleted = ticket["deleted"]
            restore_dir = ticket["restore_dir"]
        except KeyError, detail:
            msg =  "File Clerk: key %s is missing" % (detail,)
            ticket["status"] = (e_errors.KEYERROR, msg)
            Trace.log(e_errors.ERROR, msg)
            self.reply_to_caller(ticket)
            return

        # also need new value of the delete element- make sure we have this
        try:
            deleted = ticket["deleted"]
        except KeyError, detail:
            msg = "File Clerk: key %s is missing" % (detail,)
            ticket["status"] = (e_errors.KEYERROR, msg)
            Trace.log(e_errors.ERROR, msg)
            self.reply_to_caller(ticket)
            return

        status, fc, vc = self.set_deleted_priv(bfid, deleted, restore_dir)
        ticket["status"] = status
        if fc: ticket["fc"] = fc
        if vc: ticket["vc"] = fc
        # look up in our dictionary the request bit field id
        self.reply_to_caller(ticket)
        Trace.trace(12,'set_deleted %s'%(ticket,))
        return

    # restore specified file
    def restore_file(self, ticket):
        try:
            fname = ticket["file_name"]
            restore_dir = ticket["restore_dir"]
        except KeyError, detail:
            msg =  "File Clerk: key %s is missing" % (detail,)
            ticket["status"] = (e_errors.KEYERROR, msg)
            Trace.log(e_errors.ERROR, msg)
            self.reply_to_caller(ticket)
            return
        # find the file in db
        bfid = None
        self.dict.cursor("open")
        key,value=self.dict.cursor("first")
        while key:
            if value["pnfs_name0"] == fname:
                bfid = value["bfid"]
                break
            key,value=self.dict.cursor("next")
        self.dict.cursor("close")
        # file not found
        if not bfid:
            ticket["status"] = "ENOENT", "File %s not found"%(fname,)
            Trace.log(e_errors.INFO, "%s"%(ticket,))
            self.reply_to_caller(ticket)
            Trace.trace(10,"restore_file %s"%(ticket["status"],))
            return

        if string.find(value["external_label"],'deleted') !=-1:
            ticket["status"] = "EACCES", "volume %s is deleted"%(value["external_label"],)
            Trace.log(e_errors.INFO, "%s"%(ticket,))
            self.reply_to_caller(ticket)
            Trace.trace(10,"restore_file %s"%(ticket["status"],))

        status, fc, vc = self.set_deleted_priv(bfid, "no", restore_dir)
        ticket["status"] = status
        if fc: ticket["fc"] = fc
        if vc: ticket["vc"] = fc

        self.reply_to_caller(ticket)
        Trace.trace(12,'restore_file %s'%(ticket,))
        return

    # restore specified file
    #
    # This is a newer version

    def __restore_file(self, bfid):

        try:
            record = self.dict[bfid]
        except:
            msg = "File %s not found"%(bfid)
            Trace.log(e_errors.ERROR, msg)
            return "ENOENT", msg

        if record.has_key('pnfs_name0'):
            if os.access(record['pnfs_name0'], os.F_OK): # file exists
                msg = "%s exists"%(record['pnfs_name0'])
                Trace.log(e_errors.ERROR, msg)
                return "EFEXIST", msg
        else:
            msg = "no pnfs entry for file %s"%(bfid)
            Trace.log(e_errors.ERROR, msg)
            return "ENOPNFSNAME", msg

        if record["external_label"][-8:] == '.deleted':
            msg = "volume %s is deleted"%(record["external_label"])
            Trace.log(e_errors.ERROR, msg)
            return "EACCES", msg

        if record.has_key('deleted'):
            if record['deleted'] != 'yes':
                msg = "File %s is not deleted"%(bfid)
                Trace.log(e_errors.ERROR, msg)
                return "ENOTDELETED", msg

        if record.has_key('pnfs_mapname'):
            map = pnfs.Pnfs(record['pnfs_mapname'])
            status = map.restore_from_volmap('no')
            if status[0] == e_errors.OK:
                # clear the deleted status
                record['deleted'] = 'no'
                self.dict[bfid] = record
                Trace.log(e_errors.INFO, "file %s has been restored"%(bfid))
                # do not maintain non_del_files any more
                # # Take care of non_del_file count
                # vcc = volume_clerk_client.VolumeClerkClient(self.csc)
                # vticket = vcc.decr_file_count(record['external_label'], -1)
                # status = vticket["status"]
                # if status[0] != e_errors.OK: 
                #     Trace.log(e_errors.ERROR, "decr_file_count failed. Status: %s"%(status,))
        else:
            status = (e_errors.ERROR, "file %d does not have volmap entry"%(bfid))

        return status

    # restore specified file
    #
    # This is a newer version

    def restore_file2(self, ticket):
        try:
            bfid = ticket["bfid"]
        except KeyError, detail:
            msg =  "File Clerk: key %s is missing" % (detail,)
            ticket["status"] = (e_errors.KEYERROR, msg)
            Trace.log(e_errors.ERROR, msg)
            self.reply_to_caller(ticket)
            return

        ticket['status'] = self.__restore_file(bfid)
        self.reply_to_caller(ticket)
        return

    def get_user_sockets(self, ticket):
        file_clerk_host, file_clerk_port, listen_socket = callback.get_callback()
        listen_socket.listen(4)
        ticket["file_clerk_callback_addr"] = (file_clerk_host, file_clerk_port)

        self.control_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.control_socket.connect(ticket['callback_addr'])
        callback.write_tcp_obj(self.control_socket, ticket)
        r, w, x = select.select([listen_socket], [], [], 15)
        if not r:
            listen_socket.close()
            return 0
        data_socket, address = listen_socket.accept()
        if not hostaddr.allow(address):
            data_socket.close()
            listen_socket.close()
            return 0
        self.data_socket = data_socket
        listen_socket.close()
        return 1

    # return all info about a certain bfid - this does everything that the
    # read_from_hsm method does, except send the ticket to the library manager
    def bfid_info(self, ticket):
        try:
            bfid = ticket["bfid"]
        except KeyError, detail:
            msg = "File Clerk: key %s is missing"%(detail,)
            ticket["status"] = (e_errors.KEYERROR, msg)
            Trace.log(e_errors.ERROR, msg)
            self.reply_to_caller(ticket)
            return

        # look up in our dictionary the request bit field id
        try:
            finfo = self.dict[bfid] 
        except KeyError, detail:
            ticket["status"] = (e_errors.KEYERROR, 
                                "File Clerk: bfid %s not found"%(bfid,))
            Trace.log(e_errors.INFO, "%s"%(ticket,))
            self.reply_to_caller(ticket)
            Trace.trace(10,"bfid_info %s"%(ticket["status"],))
            return

        # chek if finfo has deleted key and if not fix the record
        if not finfo.has_key('deleted'):
            finfo['deleted'] = 'no'
            Trace.log(e_errors.INFO, 'added missing "deleted" key for bfid %s' % (bfid,))
            self.dict[bfid] = finfo

        #Copy all file information we have to user's ticket.  Copy the info
        # one key at a time to avoid cyclic dictionary references.
        for key in finfo.keys():
            ticket[key] = finfo[key]

        ticket["status"] = (e_errors.OK, None)
        self.reply_to_caller(ticket)
        Trace.trace(10,"bfid_info bfid=%s"%(bfid,))
        return

    # return volume map name for given bfid
    def get_volmap_name(self, ticket):
        try:
            bfid = ticket["bfid"]
        except KeyError, detail:
            msg  = "File Clerk: key %s is missing" % (detail,)
            ticket["status"] = (e_errors.KEYERROR, msg)
            Trace.log(e_errors.INFO, msg)
            self.reply_to_caller(ticket)
            return

        # look up in our dictionary the request bit field id
        try:
            finfo = self.dict[bfid] 
        except KeyError, detail:
            msg = "File Clerk: bfid %s not found"%(detail,)
            ticket["status"] = (e_errors.KEYERROR, msg)
            Trace.log(e_errors.ERROR, msg)
            self.reply_to_caller(ticket)
            return

        # copy all file information we have to user's ticket
        try:
            ticket["pnfs_mapname"] = finfo["pnfs_mapname"]
            ticket["status"] = (e_errors.OK, None)
        except KeyError:
            ticket['status'] = (e_errors.KEYERROR, None)

        self.reply_to_caller(ticket)
        Trace.trace(10,"get_volmap_name %s"%(ticket["status"],))
        return

    # change the delete state element in the dictionary
    def del_bfid(self, ticket):
        try:
            bfid = ticket["bfid"]
        except KeyError, detail:
            msg = "File Clerk: key %s is missing" % (detail,)
            ticket["status"] = (e_errors.KEYERROR, msg)
            Trace.log(e_errors.ERROR, msg)
            self.reply_to_caller(ticket)
            return

        # now just delete the bfid
        del self.dict[bfid]
        Trace.log(e_errors.INFO, "bfid %s has been removed from DB"%(bfid,))

        # and return to the caller
        ticket["status"] = (e_errors.OK, None)
        self.reply_to_caller(ticket)
        Trace.trace(12,'del_bfid %s'%(ticket,))
        return

    # rename volume and volume map
    def rename_volume(self, ticket):
        try:
            bfid = ticket["bfid"]
            label = ticket["external_label"]
            set_deleted = ticket[ "set_deleted"]
            restore_volmap = ticket["restore"]
            restore_dir = ticket["restore_dir"]
        except KeyError, detail:
            msg = "File Clerk: key %s is missing" % (detail,)
            ticket["status"] = (e_errors.KEYERROR, msg)
            Trace.log(e_errors.ERROR, msg)
            self.reply_to_caller(ticket)
            return

        record = self.dict[bfid] 
        # replace old volume name with new one
        record["pnfs_mapname"] = string.replace(record["pnfs_mapname"], 
                                                record["external_label"], 
                                                label)
        ticket["pnfs_mapname"] = record["pnfs_mapname"]
        record["external_label"] = label
        record["deleted"] = set_deleted
        if record["deleted"] == "no" and restore_volmap == "yes":
            # restore pnfs entry
            # import pnfs
            map = pnfs.Pnfs(record["pnfs_mapname"])
            status = map.restore_from_volmap(restore_dir)
            del map
            if status[0] != e_errors.OK:
                ticket["status"] = status
                self.reply_to_caller(ticket)
                Trace.log(e_errors.ERROR,'rename_volume failed %s'%(ticket,))
                return
        self.dict[bfid] = record 
 
        # and return to the caller
        ticket["status"] = (e_errors.OK, None)
        self.reply_to_caller(ticket)
        Trace.log(e_errors.INFO,'volume renamed for %s'%(ticket,))
        return

    # rename volume and volume map
    # this version rename volume for all files in it
    #
    # This only renames the file records. A complete volume renaming
    # requires volume clerk to rename the volume information.
    #
    # Renaming a volume, as far as a file's concern, renames the
    # 'external_label' and 'pnfs_mapname' accordingly.
    #
    # Renaming does involve renaming the volmap path in /pnfs.
    # If it fails, nothing would be done further.

    def __rename_volume(self, old, new):
        Trace.log(e_errors.INFO, 'renaming volume %s -> %s'%(old, new))
        bfids = self.get_all_bfids(old)

        # deal with volmap directory
        # if volmap directory can not be renamed, singal a error and stop

	if len(bfids):
            volmap = self.dict[bfids[0]]["pnfs_mapname"]
            p1, f = os.path.split(volmap)
            p, f1 = os.path.split(p1)
            if old != f1:
                Trace.log(e_errors.ERROR, 'volmap name mismatch. Looking for "%s" but found "%s"'%(old, f1))
                return e_errors.ERROR, 'volmap name mismatch. Looking for "%s" but found "%s"'%(old, f1)
            new_volmap = os.path.join(p, new)
            # can I modify it?
            if not os.access(p, os.W_OK):
		return e_errors.ERROR, 'can not rename %s to %s'%(p, new_volmap)
            try:
                os.rename(p1, new_volmap)
            except:
                return e_errors.ERROR, 'can not rename %s to %s'%(p, new_volmap)
        
        for bfid in bfids:
            record = self.dict[bfid] 
            # replace old volume name with new one
            p1, f = os.path.split(record["pnfs_mapname"])
            p, f1 = os.path.split(p1)
            if old != f1:
                Trace.log(e_errors.ERROR, 'volmap name mismatch. Looking for"%s" but found "%s". Changed anyway.'%(old, f1))
            record["pnfs_mapname"] = os.path.join(p, new, f)
            record["external_label"] = new
            self.dict[bfid] = record 
 
        Trace.log(e_errors.INFO, 'volume %s renamed to %s'%(old, new))
        return e_errors.OK, None

    # rename volume -- server service
    #
    # This is the newer version

    def rename_volume2(self, ticket):
        try:
            old = ticket["external_label"]
            new = ticket[ "new_external_label"]
        except KeyError, detail:
            msg = "File Clerk: key %s is missing" % (detail,)
            ticket["status"] = (e_errors.KEYERROR, msg)
            Trace.log(e_errors.ERROR, msg)
            self.reply_to_caller(ticket)
            return

        # catch any failure
        try:
            ticket["status"] = self.__rename_volume(old, new)
        except:
            ticket["status"] = (e_errors.ERROR, "rename failed")
        # and return to the caller
        self.reply_to_caller(ticket)
        return

    # __erase_volume(self, vol) -- delete all files belonging to vol
    #
    # This is only the file clerk portion of erasing a volume.
    # A complete erasing needs to erase volume information too.
    #
    # This involves removing volmap directory in /pnfs.
    # If it fails, nothing would be done further.

    def __erase_volume(self, vol):
        Trace.log(e_errors.INFO, 'erasing files of volume %s'%(vol))
        bfids = self.get_all_bfids(vol)

        # check to see if volmap can be deleted
        volmap_dir = None
        for bfid in bfids:
            record = self.dict[bfid]
            if record.has_key('pnfs_mapname'):
                if not volmap_dir:
                    volmap_dir, f = os.path.split(record["pnfs_mapname"])
                if not os.access(record["pnfs_mapname"]):
                    error_msg = "no write permission to %s"%(record["pnfs_mapname"])
                    Trace.log(e_errors.ERROR, error_msg)
                    return 'EACCESS', error_msg

        # check to see if volmap directory can be deleted
        if volmap_dir:
            if not os.access(volmap_dir, os.W_OK):
                error_msg = "no write permission to %s"%(volmap_dir)
                Trace.log(e_errors.ERROR, error_msg)
                return 'EACCESS', error_msg
            p, f = os.path.split(volmap_dir)
            if not os.access(p, os.W_OK):
                error_msg = "no write permission to %s"%(p)
                Trace.log(e_errors.ERROR, error_msg)
                return 'EACCESS', error_msg

        # remove file record
        for bfid in bfids:
            record = self.dict[bfid]
            if record.has_key('pnfs_mapname'):
                try:
                    os.remove(record['pnfs_mapname'])
                except:
                    error_msg = "fail to remove %s"%(record['pnfs_mapname'])
                    Trace.log(e_errors.ERROR, error_msg)
                    return 'EACCESS', error_msg
            del self.dict[bfid]

        # remove volmap directory
        if volmap_dir:
            try:
                os.rmdir(volmap_dir)
            except:
                error_msg = "fail to remove directory %s"%(volmap_dir)
                Trace.log(e_errors.ERROR, error_msg)
                return 'EACCESS', error_msg

        Trace.log(e_errors.INFO, 'files of volume %s are erased'%(vol))
        return e_errors.OK, None

    # erase_volume -- server service

    def erase_volume(self, ticket):
        try:
            vol = ticket["external_label"]
        except KeyError, detail:
            msg = "File Clerk: key %s is missing" % (detail,)
            ticket["status"] = (e_errors.KEYERROR, msg)
            Trace.log(e_errors.ERROR, msg)
            self.reply_to_caller(ticket)
            return

        ticket["status"] = (e_errors.OK, None)
        # catch any failure
        try:
            ticket['status'] = self.__erase_volume(vol)
        except:
            ticket["status"] = (e_errors.ERROR, "erase failed")
        # and return to the caller
        self.reply_to_caller(ticket)
        return

    # __delete_volume(self, vol) -- mark all files belonging to vol as deleted
    #
    # Note: this is NOT the counter part of __delete_volume() in
    #       volume clerk, which is simply a renaming to *.deleted

    def __delete_volume(self, vol):
        Trace.log(e_errors.INFO, 'marking files of volume %s as deleted'%(vol))
        bfids = self.get_all_bfids(vol)
        for bfid in bfids:
            record = self.dict[bfid]
            record['deleted'] = 'yes'
            self.dict[bfid] = record
        Trace.log(e_errors.INFO, 'all files of volume %s are marked deleted'%(vol))
        return

    # delete_volume -- server service

    def delete_volume(self, ticket):
        try:
            vol = ticket["external_label"]
        except KeyError, detail:
            msg = "File Clerk: key %s is missing" % (detail,)
            ticket["status"] = (e_errors.KEYERROR, msg)
            Trace.log(e_errors.ERROR, msg)
            self.reply_to_caller(ticket)
            return

        ticket["status"] = (e_errors.OK, None)
        # catch any failure
        try:
            self.__delete_volume(vol)
        except:
            ticket["status"] = (e_errors.ERROR, "delete failed")
        # and return to the caller
        self.reply_to_caller(ticket)
        return

    # __has_undeleted_file(self, vol) -- check if all files are deleted

    def __has_undeleted_file(self, vol):
        Trace.log(e_errors.INFO, 'checking if files of volume %s are deleted'%(vol))
        bfids = self.get_all_bfids(vol)
        for bfid in bfids:
            record = self.dict[bfid]
            if record.has_key('deleted'):
                if record['deleted'] == 'no':
                    return 1
            else:
                # This could happen for very old records
                # record the fact and move on
                Trace.log(e_errors.ERROR, "%s has no 'deleted' field"%(bfid))
        return 0

    # has_undeleted_file -- server service

    def has_undeleted_file(self, ticket):
        try:
            vol = ticket["external_label"]
        except KeyError, detail:
            msg = "File Clerk: key %s is missing" % (detail,)
            ticket["status"] = (e_errors.KEYERROR, msg)
            Trace.log(e_errors.ERROR, msg)
            self.reply_to_caller(ticket)
            return

        ticket["status"] = (e_errors.OK, None)
        # catch any failure
        try:
            result = self.__has_undeleted_file(vol)
            ticket["status"] = (e_errors.OK, result)
        except:
            ticket["status"] = (e_errors.ERROR, "inquire failed")
        # and return to the caller
        self.reply_to_caller(ticket)
        return

    # __restore_volume(self, vol) -- restore according to volmap

    def __restore_volume(self, vol):
        Trace.log(e_errors.INFO, 'restoring files for vol %s'%(vol))
        bfids = self.get_all_bfids(vol)
        msg = ""
        for bfid in bfids:
            status = self.__restore_file(bfid)
            if status[1]:
                msg = msg + '\n' + status[1]
        if msg:
            return e_errors.ERROR, msg
        else:
            return e_errors.OK, None

    # restore_volume -- server service

    def restore_volume(self, ticket):
        try:
            vol = ticket["external_label"]
        except KeyError, detail:
            msg = "File Clerk: key %s is missing" % (detail,)
            ticket["status"] = (e_errors.KEYERROR, msg)
            Trace.log(e_errors.ERROR, msg)
            self.reply_to_caller(ticket)
            return

        ticket["status"] = (e_errors.OK, None)
        # catch any failure
        try:
            ticket['status'] = self.__restore_volume(vol)
        except:
            ticket["status"] = (e_errors.ERROR, "restore failed")
        # and return to the caller
        self.reply_to_caller(ticket)
        return

    # A bit file id is defined to be a 64-bit number whose most significant
    # part is based on the time, and the least significant part is a count
    # to make it unique
    def unique_bit_file_id(self):
        bfid = time.time()
        bfid = long(bfid)*100000
        while self.dict.has_key(self.brand+str(bfid)):
            bfid = bfid + 1
        return self.brand+str(bfid)

    # get_bfids(self, ticket) -- get bfids of a certain volume
    #        This is almost the same as tape_list() yet it does not
    #        retrieve any information from primary file database

    def get_bfids(self, ticket):
        try:
            external_label = ticket["external_label"]
            ticket["status"] = (e_errors.OK, None)
            self.reply_to_caller(ticket)
        except KeyError, detail:
            msg = "File Clerk: key %s is missing"%(detail,)
            ticket["status"] = (e_errors.KEYERROR, msg)
            Trace.log(e_errors.ERROR, msg)
            self.reply_to_caller(ticket)
            return

        # get a user callback
        if not self.get_user_sockets(ticket):
            return
        callback.write_tcp_obj(self.data_socket,ticket)

        bfids = self.get_all_bfids(external_label)
        callback.write_tcp_obj_new(self.data_socket, bfids)
        self.data_socket.close()
        callback.write_tcp_obj(self.control_socket,ticket)
        self.control_socket.close()
        return

    # get_all_bfids(external_label) -- get all bfids of a particular volume

    def get_all_bfids(self, external_label):
        bfids = []
        if self.dict.inx.has_key('external_label'):
            # now get a cursor so we can loop on the database quickly:
            c = self.dict.inx['external_label'].cursor()
            key, pkey = c.set(external_label)
            while key:
                bfids.append(pkey)
                key, pkey = c.nextDup()
            c.close()
        else:  # use bfid_db
            try:
                bfids = self.bfid_db.get_all_bfids(external_label)
            except:
                bfids = None
        return bfids

    def tape_list(self,ticket):
        try:
            external_label = ticket["external_label"]
            ticket["status"] = (e_errors.OK, None)
            self.reply_to_caller(ticket)
        except KeyError, detail:
            msg = "File Clerk: key %s is missing"%(detail,)
            ticket["status"] = (e_errors.KEYERROR, msg)
            Trace.log(e_errors.ERROR, msg)
            self.reply_to_caller(ticket)
            ####XXX client hangs waiting for TCP reply
            return

        # fork as it may take quite a while to get the list
        # if self.fork() != 0:
        #    return

        # get a user callback
        if not self.get_user_sockets(ticket):
            return
        callback.write_tcp_obj(self.data_socket,ticket)

        # if index is available, use index, otherwise use bfid_db to be
        # backward compatible

        vol = {}
        if self.dict.inx.has_key('external_label'):  # use index
            # now get a cursor so we can loop on the database quickly:
            c = self.dict.inx['external_label'].cursor()
            key, pkey = c.set(external_label)
            while key:
                value = self.dict[pkey]
                if value.has_key('deleted'):
                    if value['deleted']=="yes":
                        deleted = "deleted"
                    else:
                        deleted = " active"
                else:
                    deleted = "unknown"
                if not value.has_key('pnfs_name0'):
                    value['pnfs_name0'] = "unknown"
                vol[pkey] = value
                key,pkey = c.nextDup()
            c.close()
        else:  # use bfid_db
            try:
                bfid_list = self.bfid_db.get_all_bfids(external_label)
            except:
                msg = "File Clerk: no entry for volume %s" % external_label
                ticket["status"] = (e_errors.KEYERROR, msg)
                Trace.log(e_errors.ERROR, msg)
                bfid_list = []
            for bfid in bfid_list:
                value = self.dict[bfid]
                if value.has_key('deleted'):
                    if value['deleted']=="yes":
                        deleted = "deleted"
                    else:
                        deleted = " active"
                else:
                    deleted = "unknown"
                if not value.has_key('pnfs_name0'):
                     value['pnfs_name0'] = "unknown"
                vol[bfid] = value

        # finishing up

        callback.write_tcp_obj_new(self.data_socket, vol)
        self.data_socket.close()
        callback.write_tcp_obj(self.control_socket,ticket)
        self.control_socket.close()
        return

    def tape_list_saved(self,ticket):
        try:
            external_label = ticket["external_label"]
            ticket["status"] = (e_errors.OK, None)
            self.reply_to_caller(ticket)
        except KeyError, detail:
            msg = "File Clerk: key %s is missing"%(detail,)
            ticket["status"] = (e_errors.KEYERROR, msg)
            Trace.log(e_errors.ERROR, msg)
            self.reply_to_caller(ticket)
            ####XXX client hangs waiting for TCP reply
            return

        # fork as it may take quite a while to get the list
        # if self.fork() != 0:
        #    return

        # get a user callback
        if not self.get_user_sockets(ticket):
            return
        callback.write_tcp_obj(self.data_socket,ticket)
        msg="     label            bfid       size        location_cookie delflag original_name\n"
        callback.write_tcp_raw(self.data_socket, msg)

        # if index is available, use index, otherwise use bfid_db to be
        # backward compatible

        if self.dict.inx.has_key('external_label'):  # use index
            # now get a cursor so we can loop on the database quickly:
            c = self.dict.inx['external_label'].cursor()
            key, pkey = c.set(external_label)
            while key:
                value = self.dict[pkey]
                if value.has_key('deleted'):
                    if value['deleted']=="yes":
                        deleted = "deleted"
                    else:
                        deleted = " active"
                else:
                    deleted = "unknown"
                if not value.has_key('pnfs_name0'):
                    value['pnfs_name0'] = "unknown"
                msg= "%10s %s %10i %22s %7s %s\n" % (external_label, value['bfid'],
                    value['size'],value['location_cookie'],
                    deleted,value['pnfs_name0'])
                callback.write_tcp_raw(self.data_socket, msg)
                key,pkey = c.nextDup()
            c.close()
        else:  # use bfid_db
            try:
                bfid_list = self.bfid_db.get_all_bfids(external_label)
            except:
                msg = "File Clerk: no entry for volume %s" % external_label
                ticket["status"] = (e_errors.KEYERROR, msg)
                Trace.log(e_errors.ERROR, msg)
                bfid_list = []
            for bfid in bfid_list:
                value = self.dict[bfid]
                if value.has_key('deleted'):
                    if value['deleted']=="yes":
                        deleted = "deleted"
                    else:
                        deleted = " active"
                else:
                    deleted = "unknown"
                if not value.has_key('pnfs_name0'):
                     value['pnfs_name0'] = "unknown"
                msg= "%10s %s %10i %22s %7s %s\n" % (external_label, value['bfid'],
                                                      value['size'],value['location_cookie'],
                                                      deleted,value['pnfs_name0'])
                callback.write_tcp_raw(self.data_socket, msg)

        # finishing up

        callback.write_tcp_raw(self.data_socket, "")
        self.data_socket.close()
        callback.write_tcp_obj(self.control_socket,ticket)
        self.control_socket.close()
        return

    # list_active(self, ticket) -- list the active files on a volume
    #     only the /pnfs path is listed
    #     the purpose is to generate a list for deletion before the
    #     deletion of a volume

    def list_active(self,ticket):
        try:
            external_label = ticket["external_label"]
            ticket["status"] = (e_errors.OK, None)
            self.reply_to_caller(ticket)
        except KeyError, detail:
            msg = "File Clerk: key %s is missing"%(detail,)
            ticket["status"] = (e_errors.KEYERROR, msg)
            Trace.log(e_errors.ERROR, msg)
            self.reply_to_caller(ticket)
            ####XXX client hangs waiting for TCP reply
            return

        # get a user callback
        if not self.get_user_sockets(ticket):
            return
        callback.write_tcp_obj(self.data_socket,ticket)

        # if index is available, use index, otherwise use bfid_db to be
        # backward compatible

        alist = []
        if self.dict.inx.has_key('external_label'):  # use index
            # now get a cursor so we can loop on the database quickly:
            c = self.dict.inx['external_label'].cursor()
            key, pkey = c.set(external_label)
            while key:
                value = self.dict[pkey]
                if not value.has_key('deleted') or value['deleted'] != "yes":
                    if value.has_key('pnfs_name0'):
                        alist.append(value['pnfs_name0'])
                key,pkey = c.nextDup()
            c.close()
        else:  # use bfid_db
            try:
                bfid_list = self.bfid_db.get_all_bfids(external_label)
            except:
                msg = "File Clerk: no entry for volume %s" % external_label
                ticket["status"] = (e_errors.KEYERROR, msg)
                Trace.log(e_errors.ERROR, msg)
                bfid_list = []
            for bfid in bfid_list:
                value = self.dict[bfid]
                if not value.has_key('deleted') or value['deleted'] != "yes":
                    if value.has_key('pnfs_name0'):
                        alist.append(value['pnfs_name0'])

        # finishing up

        callback.write_tcp_obj_new(self.data_socket, alist)
        self.data_socket.close()
        callback.write_tcp_obj(self.control_socket,ticket)
        self.control_socket.close()
        return

    def start_backup(self,ticket):
        try:
            Trace.log(e_errors.INFO,"start_backup")
            self.dict.start_backup()
            self.reply_to_caller({"status"        : (e_errors.OK, None),
                                  "start_backup"  : 'yes' })
        # catch any error and keep going. server needs to be robust
        except:
            exc, msg, tb = sys.exc_info()
            status = str(exc), str(msg)
            Trace.log(e_errors.ERROR,"start_backup %s"%(status,))
            self.reply_to_caller({"status"       : status,
                                  "start_backup" : 'no' })


    def stop_backup(self,ticket):
        try:
            Trace.log(e_errors.INFO,"stop_backup")
            self.dict.stop_backup()
            self.reply_to_caller({"status"       : (e_errors.OK, None),
                                  "stop_backup"  : 'yes' })
        # catch any error and keep going. server needs to be robust
        except:
            exc, msg, tb = sys.exc_info()
            status = str(exc), str(msg)
            Trace.log(e_errors.ERROR,"stop_backup %s"%(status,))
            self.reply_to_caller({"status"       : status,
                                  "stop_backup"  : 'no' })

    def backup(self,ticket):
        try:
            Trace.log(e_errors.INFO,"backup")
            self.dict.backup()
            self.reply_to_caller({"status"       : (e_errors.OK, None),
                                  "backup"  : 'yes' })
        # catch any error and keep going. server needs to be robust
        except:
            exc, msg, tb = sys.exc_info()
            status = str(exc), str(msg)
            Trace.log(e_errors.ERROR,"backup %s"%(status,))
            self.reply_to_caller({"status"       : status,
                                  "backup"  : 'no' })

    # assign_file_record() -- create or modify file record
    #
    # This is very dangerous!

    def assign_file_record(self, ticket):
        # extracting the values 
        try:
            complete_crc = ticket['complete_crc']
            deleted = ticket['deleted']
            drive = ticket['drive']
            external_label = ticket['external_label']
            location_cookie = ticket['location_cookie']
            pnfs_mapname = ticket['pnfs_mapname']
            pnfs_name0 = ticket['pnfs_name0']
            pnfsid = ticket['pnfsid']
            pnfsvid = ticket['pnfsvid']
            sanity_cookie = ticket['sanity_cookie']
            size = ticket['size']
        except KeyError, detail:
            msg =  "File Clerk: assign_file_record() -- key %s is missing" % (detail,)
            ticket["status"] = (e_errors.KEYERROR, msg)
            Trace.log(e_errors.ERROR, msg)
            self.reply_to_caller(ticket)
            return

        if ticket.has_key['bfid']:
            bfid = ticket['bfid']
        else:
            bfid = self.unique_bit_file_id()
            ticket['bfid'] = bfid

        record = {}
        record['bfid'] = bfid
        record['complete_crc'] = complete_crc
        record['deleted'] = deleted
        record['drive'] = drive
        record['external_label'] = external_label
        record['location_cookie'] = location_cookie
        record['pnfs_mapname'] = pnfs_mapname
        record['pnfs_name0'] = pnfs_name0
        record['pnfsid'] = pnfsid
        record['pnfsvid'] = pnfsvid
        record['sanity_cookie'] = sanity_cookie
        record['size'] = size

        # assigning it to database
        self.dict[bfid] = record
        Trace.log(e_errors.INFO, 'assigned: '+`record`)
        ticket['status'] = (e_errors.OK, None)
        self.reply_to_caller(ticket)
        return

class FileClerk(FileClerkMethods, generic_server.GenericServer):

    def __init__(self, csc):
        generic_server.GenericServer.__init__(self, csc, MY_NAME)
        Trace.init(self.log_name)
        #   pretend that we are the test system
        #   remember, in a system, there is only one bfs
        #   get our port and host from the name server
        #   exit if the host is not this machine
        keys = self.csc.get(MY_NAME)
        self.alive_interval = monitored_server.get_alive_interval(self.csc,
                                                                  MY_NAME,
                                                                  keys)
        FileClerkMethods.__init__(self, (keys['hostip'], keys['port']))
        # start our heartbeat to the event relay process
        self.erc.start_heartbeat(enstore_constants.FILE_CLERK, 
                                 self.alive_interval)
        self.brand = ""


class FileClerkInterface(generic_server.GenericServerInterface):
    pass

if __name__ == "__main__":
    Trace.init(string.upper(MY_NAME))

    # get the interface
    intf = FileClerkInterface()

    # get a file clerk
    fc = FileClerk((intf.config_host, intf.config_port))
    fc.handle_generic_commands(intf)
    Trace.log(e_errors.INFO, '%s' % (sys.argv,))

    # find the brand

    Trace.log(e_errors.INFO,"find the brand")
    try:
        brand = configuration_client.ConfigurationClient(
                (intf.config_host, intf.config_port)).get('file_clerk')['brand']
        Trace.log(e_errors.INFO,"The brand is %s"%(brand))
    except:
        brand = string.upper(string.split(os.uname()[1], ".")[0][:2])+'MS'
        Trace.log(e_errors.INFO,"No brand is found, using '%s'"%(brand))

    fc.set_brand(brand)

    Trace.log(e_errors.INFO,"determine dbHome and jouHome")
    try:
        dbInfo = configuration_client.ConfigurationClient(
                (intf.config_host, intf.config_port)).get('database')
        dbHome = dbInfo['db_dir']
        try:  # backward compatible
            jouHome = dbInfo['jou_dir']
        except:
            jouHome = dbHome
    except:
        dbHome = os.environ['ENSTORE_DIR']
        jouHome = dbHome

    Trace.log(e_errors.INFO,"opening file database using DbTable")
    # see if there is an index file
    if os.access(os.path.join(dbHome, 'file.external_label.index'), os.F_OK):
        print "open with index"
        fc.dict = db.DbTable("file", dbHome, jouHome, ['external_label']) 
    else:
        print "open with no index"
        fc.dict = db.DbTable("file", dbHome, jouHome) 
    fc.bfid_db = bfid_db.BfidDb(dbHome)
    Trace.log(e_errors.INFO,"hurrah, file database is open")
    
    while 1:
        try:
            Trace.log(e_errors.INFO, "File Clerk (re)starting")
            fc.serve_forever()
        except SystemExit, exit_code:
            fc.dict.close()
            sys.exit(exit_code)
        except:
            fc.serve_forever_error(fc.log_name)
            continue
    Trace.trace(e_errors.ERROR,"File Clerk finished (impossible)")
