#!/usr/bin/env python

###############################################################################
#
# $Id$
#
###############################################################################

# system imports
import string
import errno
import sys
import socket
#import select
import os

# enstore imports
import generic_client
import option
import backup_client
#import callback
import hostaddr
import Trace
import e_errors
import pprint
import volume_clerk_client
import volume_family
import pnfs
import info_client
import enstore_constants
import file_utils
from en_eval import en_eval

MY_NAME = enstore_constants.FILE_CLERK_CLIENT   #"FILE_C_CLIENT"
MY_SERVER = enstore_constants.FILE_CLERK        #"file_clerk"
RCV_TIMEOUT = 10
RCV_TRIES = 5

# union(list_of_sets)
def union(s):
    res = []
    for i in s:
        for j in i:
            if not j in res:
                res.append(j)
    return res

class FileClient(info_client.fileInfoMethods, #generic_client.GenericClient, 
                 backup_client.BackupClient):

    def __init__( self, csc, bfid=0, server_address=None, flags=0, logc=None,
                  alarmc=None, rcv_timeout=RCV_TIMEOUT, rcv_tries=RCV_TRIES,
                  #Timeout and tries are for backward compatibility.
                  timeout=None, tries=None):
        ###For backward compatibility.
        if timeout != None:
            rcv_timeout = timeout
        if tries != None:
            rcv_tries = tries
        ###
            
        #generic_client.GenericClient.__init__(self,csc,MY_NAME,server_address,
        #                                      flags=flags, logc=logc,
        #                                      alarmc=alarmc,
        #                                      rcv_timeout=rcv_timeout,
        #                                      rcv_tries=rcv_tries,
        #                                      server_name = MY_SERVER)
        info_client.fileInfoMethods.__init__(self,csc,MY_NAME,server_address,
                                             flags=flags, logc=logc,
                                             alarmc=alarmc,
                                             rcv_timeout=rcv_timeout,
                                             rcv_tries=rcv_tries,
                                             server_name = MY_SERVER)
        
	self.bfid = bfid
	#if self.server_address == None:
        #    self.server_address = self.get_server_address(
        #        MY_SERVER, rcv_timeout, rcv_tries)

    # create a bit file using complete metadata -- bypassing all
    def create_bit_file(self, file):
        # file is a structure without bfid
        ticket = {"fc":{}}
        ticket["fc"]["external_label"] = str(file["external_label"])
        ticket["fc"]["location_cookie"] = str(file["location_cookie"])
        ticket["fc"]["size"] = long(file["size"])
        ticket["fc"]["sanity_cookie"] = file["sanity_cookie"]
        ticket["fc"]["complete_crc"]  = long(file["complete_crc"])
        ticket["fc"]["pnfsid"] = str(file["pnfsid"])
        ticket["fc"]["pnfs_name0"] = str(file["pnfs_name0"])
        ticket["fc"]["drive"] = str(file["drive"])
        # handle uid and gid
        if file.has_key("uid"):
            ticket["fc"]["uid"] = file["uid"]
        if file.has_key("gid"):
            ticket["fc"]["gid"] = file["gid"]
        ticket = self.new_bit_file(ticket)
        if ticket["status"][0] == e_errors.OK:
            ticket = self.set_pnfsid(ticket)
        return ticket

    def new_bit_file(self, ticket):
        ticket['work'] = "new_bit_file"
        r = self.send(ticket)
        return r

    def show_state(self):
        return self.send({'work':'show_state'})

    def set_pnfsid(self, ticket):
        ticket['work'] = "set_pnfsid"
        r = self.send(ticket)
        return r

    def get_brand(self, timeout=0, retry=0):
        ticket = {'work': 'get_brand'}
        r = self.send(ticket, timeout, retry)
        if r['status'][0] == e_errors.OK:
            return r['brand']
        else:
            return None

    # find_copies(bfid) -- find the first generation of copies
    def find_copies(self, bfid, timeout=0, retry=0):
        ticket = {'work': 'find_copies',
                  'bfid': bfid}
        return self.send(ticket, timeout, retry)

    # find_all_copies(bfid) -- find all copies from this file
    # This is done on the client side
    def find_all_copies(self, bfid):
        res = self.find_copies(bfid)
        if res["status"][0] == e_errors.OK:
            copies = union([[bfid], res["copies"]])
            for i in res["copies"]:
                res2 = self.find_all_copies(i)
                if res2["status"][0] == e_errors.OK:
                    copies = union([copies, res2["copies"]])
                else:
                    return res2
            res["copies"] = copies
        return res 

    # find_original(bfid) -- find the immidiate original
    def find_original(self, bfid, timeout=0, retry=0):
        ticket = {'work': 'find_original',
                  'bfid': bfid}
        if bfid:
            ticket = self.send(ticket, timeout, retry)
        else:
            ticket['status'] = (e_errors.OK, None)
        return ticket

    # find_the_original(bfid) -- find the altimate original of this file
    # This is done on the client side
    def find_the_original(self, bfid):
        res = self.find_original(bfid)
        if res['status'][0] == e_errors.OK:
            if res['original']:
                res2 = self.find_the_original(res['original'])
                return res2
            # this is actually the else part
            res['original'] = bfid
        return res

    # find_duplicates(bfid) -- find all original/copies of this file
    # This is done on the client side
    def find_duplicates(self, bfid):
        res = self.find_the_original(bfid)
        if res['status'][0] == e_errors.OK:
            return self.find_all_copies(res['original'])
        return res

    # get all pairs of bfids relating to migration/duplication of
    # the specified bfid
    def find_migrated(self, bfid):
        r = self.send({"work" : "find_migrated", "bfid" : bfid})
        if r.has_key('work'):
            del r['work']
        return r

    # def set_delete(self, ticket):
    #     #Is this really set_deleted or set_delete?
    #     ticket['work'] = "set_deleted"
    #     r = self.send(ticket)
    #     return r

    """
    def get_bfids(self, external_label):
        host, port, listen_socket = callback.get_callback()
        listen_socket.listen(4)
        ticket = {"work"          : "get_bfids",
                  "callback_addr" : (host, port),
                  "external_label": external_label}
        # send the work ticket to the file clerk
        ticket = self.send(ticket)
        if ticket['status'][0] != e_errors.OK:
            return ticket

        r, w, x = select.select([listen_socket], [], [], 60)
        if not r:
            listen_socket.close()
            raise errno.errorcode[errno.ETIMEDOUT], "timeout waiting for file clerk callback"
        control_socket, address = listen_socket.accept()
        if not hostaddr.allow(address):
            listen_socket.close()
            control_socket.close()
            raise errno.errorcode[errno.EPROTO], "address %s not allowed" %(address,)

        ticket = callback.read_tcp_obj(control_socket)
        listen_socket.close()
        
        if ticket["status"][0] != e_errors.OK:
            return ticket
        
        data_path_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        data_path_socket.connect(ticket['file_clerk_callback_addr'])
  
        ticket= callback.read_tcp_obj(data_path_socket)
        list = callback.read_tcp_obj_new(data_path_socket)
        ticket['bfids'] = list
        data_path_socket.close()

        # Work has been read - wait for final dialog with file clerk
        done_ticket = callback.read_tcp_obj(control_socket)
        control_socket.close()
        if done_ticket["status"][0] != e_errors.OK:
            return done_ticket

        return ticket
    """

    """
    def list_active(self,external_label):
        host, port, listen_socket = callback.get_callback()
        listen_socket.listen(4)
        ticket = {"work"          : "list_active2",
                  "callback_addr" : (host, port),
                  "external_label": external_label}
        # send the work ticket to the file clerk
        ticket = self.send(ticket)
        if ticket['status'][0] != e_errors.OK:
            return ticket

        r, w, x = select.select([listen_socket], [], [], 60)
        if not r:
            listen_socket.close()
            raise errno.errorcode[errno.ETIMEDOUT], "timeout waiting for file clerk callback"
        control_socket, address = listen_socket.accept()
        if not hostaddr.allow(address):
            listen_socket.close()
            control_socket.close()
            raise errno.errorcode[errno.EPROTO], "address %s not allowed" %(address,)

        ticket = callback.read_tcp_obj(control_socket)
        listen_socket.close()
        
        if ticket["status"][0] != e_errors.OK:
            return ticket
        
        data_path_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        data_path_socket.connect(ticket['file_clerk_callback_addr'])
  
        ticket= callback.read_tcp_obj(data_path_socket)
        list = callback.read_tcp_obj_new(data_path_socket)
        # Work has been read - wait for final dialog with file clerk
        done_ticket = callback.read_tcp_obj(control_socket)
        control_socket.close()
        if done_ticket["status"][0] != e_errors.OK:
            return done_ticket

        ticket['active_list'] = []
        for i in list:
            ticket['active_list'].append(i[0])
        data_path_socket.close()

        return ticket
    """

    """
    def tape_list(self,external_label):
        host, port, listen_socket = callback.get_callback()
        listen_socket.listen(4)
        ticket = {"work"          : "tape_list2",
                  "callback_addr" : (host, port),
                  "external_label": external_label}
        # send the work ticket to the file clerk
        ticket = self.send(ticket)
        if ticket['status'][0] != e_errors.OK:
            return ticket

        r, w, x = select.select([listen_socket], [], [], 60)
        if not r:
            listen_socket.close()
            raise errno.errorcode[errno.ETIMEDOUT], "timeout waiting for file clerk callback"
        control_socket, address = listen_socket.accept()
        if not hostaddr.allow(address):
            listen_socket.close()
            control_socket.close()
            raise errno.errorcode[errno.EPROTO], "address %s not allowed" %(address,)

        ticket = callback.read_tcp_obj(control_socket)
        listen_socket.close()
        
        if ticket["status"][0] != e_errors.OK:
            return ticket
        
        data_path_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        data_path_socket.connect(ticket['file_clerk_callback_addr'])
  
        ticket= callback.read_tcp_obj(data_path_socket)
        vol = callback.read_tcp_obj_new(data_path_socket)
        data_path_socket.close()

        # Work has been read - wait for final dialog with file clerk
        done_ticket = callback.read_tcp_obj(control_socket)
        control_socket.close()
        if done_ticket["status"][0] != e_errors.OK:
            return done_ticket

        # convert to external format
        ticket['tape_list'] = []
        for s in vol:
            if s['deleted'] == 'y':
                deleted = 'yes'
            elif s['deleted'] == 'n':
                deleted = 'no'
            else:
                deleted = 'unknown'

            if s['sanity_size'] == -1:
                sanity_size = None
            else:
                sanity_size = s['sanity_size']

            if s['sanity_crc'] == -1:
                sanity_crc = None
            else:
                sanity_crc = s['sanity_crc']

            if s['crc'] == -1:
                crc = None
            else:
                crc = s['crc']

            record = {
                'bfid': s['bfid'],
                'complete_crc': crc,
                'deleted': deleted,
                'drive': s['drive'],
                'external_label': s['label'],
                'location_cookie': s['location_cookie'],
                'pnfs_name0': s['pnfs_path'],
                'pnfsid': s['pnfs_id'],
                'sanity_cookie': (sanity_size, sanity_crc),
                'size': s['size']
            }

            if s.has_key('uid'):
                record['uid'] = s['uid']
            if s.has_key('gid'):
                record['gid'] = s['gid']
            ticket['tape_list'].append(record)

        return ticket
    """

    def mark_bad(self, path, specified_bfid = None):
        # get the full absolute path
        a_path = os.path.abspath(path)
        dirname, filename = os.path.split(a_path)

	# does it exist?
        if not os.access(path, os.F_OK):
            msg = "%s does not exist!" % (path)
            return {'status': (e_errors.FILE_CLERK_ERROR, msg)}

        # check premission
        if not os.access(dirname, os.W_OK):
            msg = "not enough privilege to rename %s" % (path)
            return {'status': (e_errors.FILE_CLERK_ERROR, msg)}

        # get bfid
        bfid_file = os.path.join(dirname, '.(use)(1)(%s)' % (filename))
        f = open(bfid_file)
        bfid = string.strip(f.readline())
        f.close()

        #Detect if the suplied bfid is a multiple copy of the primary bfid.
        is_multiple_copy = False
        if specified_bfid:
            copy_dict = self.find_all_copies(bfid)
            if e_errors.is_ok(copy_dict):
                copy_bfids = copy_dict['copies']
            else:
                return copy_dict
            try:
                #Remove the primary bfid from the list.  file_copies()
                # can miss copies of copies, so we don't want to use that.
                del copy_bfids[copy_bfids.index(bfid)]
            except IndexError:
                pass
            #If the bfid is in the list, we have a valid mupltiple copy.
            if specified_bfid in copy_bfids:
                bfid = specified_bfid
                is_multiple_copy = True
            else:
                msg = "%s bfid is not a copy of %s" % (specified_bfid, path)
                return {'status': (e_errors.FILE_CLERK_ERROR, msg)}

        if len(bfid) < 12:
            msg = "can not find bfid for %s"%(path)
            return {'status': (e_errors.FILE_CLERK_ERROR, msg)}

        record = self.bfid_info(bfid)
        if record['status'][0] != e_errors.OK:
            return record

        if is_multiple_copy:
            bad_file = path
        else:
            bad_file = os.path.join(dirname, ".bad." + filename)
            # rename it
            try:
                os.rename(a_path, bad_file)
            except:
                msg = "failed to rename %s to %s"%(a_path, bad_file)
                return {'status': (e_errors.FILE_CLERK_ERROR, msg)}

        # log it in the bad_file table of the database
        ticket = {'work': 'mark_bad', 'bfid': bfid, 'path': bad_file};
        ticket = self.send(ticket)
        if ticket['status'][0] == e_errors.OK:
            print bfid, a_path, "->", bad_file
        return ticket

    def unmark_bad(self, path, specified_bfid = None):
        # get the full absolute path
        a_path = os.path.abspath(path)
        dirname, filename = os.path.split(a_path)

	# does it exist?
        if not os.access(path, os.F_OK):
            msg = "%s does not exist!" % (path)
            return {'status': (e_errors.FILE_CLERK_ERROR, msg)}

        # check premission
        if not os.access(dirname, os.W_OK):
            msg = "not enough privilege to rename %s" % (path)
            return {'status': (e_errors.FILE_CLERK_ERROR, msg)}

        # get bfid
        bfid_file = os.path.join(dirname, '.(use)(1)(%s)' % (filename))
        f = open(bfid_file)
        bfid = string.strip(f.readline())
        f.close()
        if len(bfid) < 12:
            msg = "can not find bfid for %s"%(path)
            return {'status': (e_errors.FILE_CLERK_ERROR, msg)}

        #Detect if the suplied bfid is a multiple copy of the primary bfid.
        is_multiple_copy = False
        if specified_bfid:
            copy_dict = self.find_all_copies(bfid)
            if e_errors.is_ok(copy_dict):
                copy_bfids = copy_dict['copies']
            else:
                return copy_dict
            try:
                #Remove the primary bfid from the list.  file_copies()
                # can miss copies of copies, so we don't want to use that.
                del copy_bfids[copy_bfids.index(bfid)]
            except IndexError:
                pass
            if specified_bfid in copy_bfids:
                bfid = specified_bfid
                is_multiple_copy = True
            else:
                msg = "%s bfid is not a copy of %s" % (specified_bfid, path)
                return {'status': (e_errors.FILE_CLERK_ERROR, msg)}

        # is it a "bad" file?
	if filename[:5] != ".bad." and not is_multiple_copy:
            msg = "%s is not officially a bad file"%(path)
            return {'status': (e_errors.FILE_CLERK_ERROR, msg)}

        record = self.bfid_info(bfid)
        if record['status'][0] != e_errors.OK:
            return record

        if is_multiple_copy:
            good_file = path
        else:
            good_file = os.path.join(dirname, filename[5:])
            # rename it
            try:
                os.rename(a_path, good_file)
            except:
                msg = "failed to rename %s to %s"%(a_path, good_file)
                return {'status': (e_errors.FILE_CLERK_ERROR, msg)}

        # log it
        ticket = {'work': 'unmark_bad', 'bfid': bfid}
        ticket = self.send(ticket)
        if ticket['status'][0] == e_errors.OK:
            print bfid, a_path, "->", good_file
        return ticket


    """
    def show_bad(self):
        host, port, listen_socket = callback.get_callback()
        listen_socket.listen(4)
        ticket = {"work"          : "show_bad",
                  "callback_addr" : (host, port)}
        # send the work ticket to the file clerk
        ticket = self.send(ticket)
        if ticket['status'][0] != e_errors.OK:
            return ticket

        r, w, x = select.select([listen_socket], [], [], 60)
        if not r:
            listen_socket.close()
            raise errno.errorcode[errno.ETIMEDOUT], "timeout waiting for file clerk callback"
        control_socket, address = listen_socket.accept()
        if not hostaddr.allow(address):
            listen_socket.close()
            control_socket.close()
            raise errno.errorcode[errno.EPROTO], "address %s not allowed" %(address,)

        ticket = callback.read_tcp_obj(control_socket)
        listen_socket.close()
        
        if ticket["status"][0] != e_errors.OK:
            return ticket
        
        data_path_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        data_path_socket.connect(ticket['file_clerk_callback_addr'])
  
        ticket= callback.read_tcp_obj(data_path_socket)
        bad_files = callback.read_tcp_obj_new(data_path_socket)
        ticket['bad_files'] = bad_files
        data_path_socket.close()

        # Work has been read - wait for final dialog with file clerk
        done_ticket = callback.read_tcp_obj(control_socket)
        control_socket.close()
        if done_ticket["status"][0] != e_errors.OK:
            return done_ticket

        return ticket
    """

    def bfid_info(self, bfid = None, timeout=0, retry=0):
        if not bfid:
            bfid = self.bfid
        r = self.send({"work" : "bfid_info",
                       "bfid" : bfid }, timeout, retry)

        if r.has_key("work"):
            del r['work']

        return r

    # This is only to be used internally
    def exist_bfids(self, bfids = []):
        if bfids == None:
            bfids = self.bfid
        r = self.send({"work" : "exist_bfids",
                       "bfids": bfids} )
        return r['result']

    # This is a retrofit for bfid
    def set_deleted(self, deleted, restore_dir="no", bfid = None):
        if bfid == None:
            bfid = self.bfid
        r = self.send({"work"        : "set_deleted",
                       "bfid"        : bfid,
                       "deleted"     : deleted,
		       "restore_dir" : restore_dir } )
        return r


    def get_crcs(self, bfid):
        r = self.send({"work"        : "get_crcs",
                       "bfid"        : bfid})
        return r

    def set_crcs(self, bfid, sanity_cookie, complete_crc):
        r = self.send({"work"        : "set_crcs",
                       "bfid"        : bfid,
                       "sanity_cookie": sanity_cookie,
                       "complete_crc": complete_crc})
        return r
        
    # delete a volume

    def delete_volume(self, vol):
        r = self.send({"work"           : "delete_volume",
		       "external_label" : vol } )
	return r

    # erase a volume

    def erase_volume(self, vol):
        r = self.send({"work"           : "erase_volume",
		       "external_label" : vol } )
	return r

    # does the volume contain any undeleted file?

    def has_undeleted_file(self, vol):
        r = self.send({"work"           : "has_undeleted_file",
		       "external_label" : vol } )
	return r

    def restore(self, bfid, uid = None, gid = None, force = None):
        # get the file information from the file clerk
        bit_file = self.bfid_info(bfid)
        if bit_file['status'][0] != e_errors.OK:
            return bit_file
        del bit_file['status']

        # take care of uid and gid
        if not uid:
            uid = bit_file['uid']
        if not gid:
            gid = bit_file['gid']

	# try its best to set uid and gid
        try:
            os.setregid(gid, gid)
            os.setreuid(uid, uid)
        except:
            pass

        # check if the volume is deleted
        if bit_file["external_label"][-8:] == '.deleted':
            message = "volume %s is deleted" % (bit_file["external_label"],)
            return {'status': (e_errors.FILE_CLERK_ERROR, message)}

        # make sure the file has to be deleted (if --force was specified,
        # allow for the restore to update the file)
        if bit_file['deleted'] != 'yes' and force == None:
            message = "%s is not deleted" % (bfid,)
            return {'status': (e_errors.FILE_CLERK_ERROR, message)}

        # find out file_family
        vcc = volume_clerk_client.VolumeClerkClient(self.csc)
        vol = vcc.inquire_vol(bit_file['external_label'])
        if vol['status'][0] != e_errors.OK:
            return vol
        file_family = volume_family.extract_file_family(vol['volume_family'])
        del vcc

        # check if the path is a valid pnfs path
        #if bit_file['pnfs_name0'][:5] != '/pnfs':
        if not pnfs.is_pnfs_path(bit_file['pnfs_name0'], check_name_only = 1):
            message = "%s is not a valid pnfs path" % (bit_file['pnfs_name0'],)
            return {'status': (e_errors.FILE_CLERK_ERROR, message)}

        # its directory has to exist
        p_p, p_f = os.path.split(bit_file['pnfs_name0'])
        rtn_code2 = file_utils.e_access(p_p, os.F_OK)
        if not rtn_code2:
            message = "can not write in directory %s" % (p_p,)
            return {'status': (e_errors.FILE_CLERK_ERROR, message)}

        # check if the file has already existed (if --force was specified,
        # allow for the restore to update the file)
        rtn_code = file_utils.e_access(bit_file['pnfs_name0'], os.F_OK)
        if rtn_code and force == None: # file exists
            message = "%s exists" % (bit_file['pnfs_name0'],)
            return {'status': (e_errors.FILE_CLERK_ERROR, message)}
        if rtn_code and force != None:
            #check if any file has the same pnfs_id
            pnfs_id = pnfs.get_pnfsid(bit_file['pnfs_name0'])
            if pnfs_id != bit_file['pnfsid']:
                message = "file pnfs id (%s) does not match database pnfs id (%s)"\
                          % (bit_file['pnfs_name0'], pnfs_id)
                return {'status': (e_errors.FILE_CLERK_ERROR, message)}


        #Setup the File class to do the update.
        bit_file['file_family'] = file_family
        pf = pnfs.File(bit_file)
        # pf.show()

        # Now create/update it; catch any error
        if not rtn_code:  #DOES NOT EXIST
            # Has it already existed?
            if pf.exists() and force == None:
                message = "%s already exists" % (bit_file['pnfs_name0'],)
                return {'status': (e_errors.FILE_CLERK_ERROR, message)}
            
            try:
                pf.create()
            except:
                message = "can not create %s" % (pf.path,)
                return {'status': (e_errors.FILE_CLERK_ERROR, message)}
            
            pnfs_id = pf.get_pnfs_id()
            if pnfs_id != pf.pnfs_id:
                # update file record
                return self.modify({'bfid': bfid, 'pnfsid':pnfs_id,
                                    'deleted':'no'})
        else: #DOES EXIST
            try:
                pf.update()
            except:
                message = "can not update %s: %s" % (pf.path,
                                                     sys.exc_info()[1])
                return {'status': (e_errors.FILE_CLERK_ERROR, message)}

        return {'status':(e_errors.OK, None)}

            

    # rebuild pnfs file entry
    def rebuild_pnfs_file(self, bfid, file_family = None):
        ticket = {"work": "restore_file2",
                  "bfid": bfid,
                  "check": 0}
        if file_family:
            ticket['file_family'] = file_family
        return self.send(ticket)

    # get volume map name for given bfid
    def get_volmap_name(self, bfid = None):
        if not bfid:
            bfid = self.bfid
        r = self.send({"work"           : "get_volmap_name",
                       "bfid"           : bfid} )
	return r

    # delete bitfile
    def del_bfid(self, bfid = None):
        if not bfid:
            bfid = self.bfid
        r = self.send({"work"           : "del_bfid",
                       "bfid"           : bfid} )
	return r

    # create file record
    def add(self, ticket):
        ticket['work'] = 'add_file_record'
        return self.send(ticket)

    # modify file record
    def modify(self, ticket):
        ticket['work'] = 'modify_file_record'
        return self.send(ticket)

class FileClerkClientInterface(generic_client.GenericClientInterface):

    def __init__(self, args=sys.argv, user_mode=1):
        # fill in the defaults for the possible options
        #self.do_parse = flag
        #self.restricted_opts = opts
        self.list =None 
        self.bfid = 0
        self.bfids = None
        self.backup = 0
        self.deleted = 0
	self.restore = ""
        self.alive_rcv_timeout = 0
        self.alive_retries = 0
        self.get_crcs=None
        self.set_crcs=None
	self.all = 0
        self.ls_active = None
        self.mark_bad = None
        self.unmark_bad = None
        self.show_bad = 0
        self.add = None
        self.modify = None
        self.show_state = None
        self.erase = None
        self.find_copies = None
        self.find_all_copies = None
        self.find_original = None
        self.find_the_original = None
        self.find_duplicates = None
        self.force = None

        generic_client.GenericClientInterface.__init__(self, args=args,
                                                       user_mode=user_mode)


    def valid_dictionaries(self):
        return (self.alive_options, self.help_options, self.trace_options,
                self.file_options)

    file_options = {
        option.ADD:{option.HELP_STRING:
                    "add file record (dangerous! don't try this at home)",
                    option.VALUE_TYPE:option.STRING,
                    option.VALUE_USAGE:option.REQUIRED,
                    option.VALUE_LABEL:"bfid",
                    option.USER_LEVEL:option.ADMIN},
        option.BACKUP:{option.HELP_STRING:
                       "backup file journal -- part of database backup",
                       option.DEFAULT_VALUE:option.DEFAULT,
                       option.DEFAULT_TYPE:option.INTEGER,
                       option.VALUE_USAGE:option.IGNORED,
                       option.USER_LEVEL:option.ADMIN},
        option.BFID:{option.HELP_STRING:"get info of a file",
                     option.VALUE_TYPE:option.STRING,
                     option.VALUE_USAGE:option.REQUIRED,
                     option.USER_LEVEL:option.USER},
        option.BFIDS:{option.HELP_STRING:"list all bfids on a volume",
                      option.VALUE_TYPE:option.STRING,
                      option.VALUE_USAGE:option.REQUIRED,
                      option.VALUE_LABEL:"volume_name",
                      option.USER_LEVEL:option.ADMIN},
        option.DELETED:{option.HELP_STRING:"used with --bfid to mark the file as deleted",
                        option.DEFAULT_TYPE:option.STRING,
                        option.VALUE_USAGE:option.REQUIRED,
                        option.VALUE_LABEL:"yes/no",
                        option.USER_LEVEL:option.ADMIN},
        option.ERASE:{option.HELP_STRING:"permenantly erase a file",
                      option.VALUE_TYPE:option.STRING,
                      option.VALUE_USAGE:option.REQUIRED,
                      option.VALUE_LABEL:"bfid",
                      option.USER_LEVEL:option.HIDDEN},
        option.FIND_COPIES:{option.HELP_STRING:"find the immediate copies of this file",
                     option.VALUE_TYPE:option.STRING,
                     option.VALUE_USAGE:option.REQUIRED,
                     option.VALUE_LABEL:"file",
                     option.USER_LEVEL:option.ADMIN},
        option.FIND_ALL_COPIES:{option.HELP_STRING:"find all copies of this file",
                     option.VALUE_TYPE:option.STRING,
                     option.VALUE_USAGE:option.REQUIRED,
                     option.VALUE_LABEL:"file",
                     option.USER_LEVEL:option.ADMIN},
        option.FIND_ORIGINAL:{option.HELP_STRING:"find the immediate original of this file",
                     option.VALUE_TYPE:option.STRING,
                     option.VALUE_USAGE:option.REQUIRED,
                     option.VALUE_LABEL:"file",
                     option.USER_LEVEL:option.ADMIN},
        option.FIND_THE_ORIGINAL:{option.HELP_STRING:"find the very first original of this file",
                     option.VALUE_TYPE:option.STRING,
                     option.VALUE_USAGE:option.REQUIRED,
                     option.VALUE_LABEL:"file",
                     option.USER_LEVEL:option.ADMIN},
        option.FIND_DUPLICATES:{option.HELP_STRING:"find all duplicates related to this file",
                     option.VALUE_TYPE:option.STRING,
                     option.VALUE_USAGE:option.REQUIRED,
                     option.VALUE_LABEL:"file",
                     option.USER_LEVEL:option.ADMIN},
        option.FORCE:{option.HELP_STRING:
			      "Force restore of file from DB that still exists"
                              " (in some capacity) in PNFS.",
			      option.VALUE_USAGE:option.IGNORED,
			      option.VALUE_TYPE:option.INTEGER,
			      option.USER_LEVEL:option.HIDDEN},
        option.GET_CRCS:{option.HELP_STRING:"get crc of a file",
                         option.VALUE_TYPE:option.STRING,
                         option.VALUE_USAGE:option.REQUIRED,
                         option.VALUE_LABEL:"bfid",
                         option.USER_LEVEL:option.ADMIN},
        option.LIST:{option.HELP_STRING:"list the files in a volume",
                     option.VALUE_TYPE:option.STRING,
                     option.VALUE_USAGE:option.REQUIRED,
                     option.VALUE_LABEL:"volume_name",
                     option.USER_LEVEL:option.USER},
        option.LS_ACTIVE:{option.HELP_STRING:"list active files in a volume",
                          option.VALUE_TYPE:option.STRING,
                          option.VALUE_USAGE:option.REQUIRED,
                          option.VALUE_LABEL:"volume_name",
                          option.USER_LEVEL:option.USER},
        option.MARK_BAD:{option.HELP_STRING:"mark the file bad",
                         option.VALUE_TYPE:option.STRING,
                         option.VALUE_USAGE:option.REQUIRED,
                         option.VALUE_LABEL:"path",
                         option.USER_LEVEL:option.ADMIN,
                         option.EXTRA_VALUES:[{
                              option.VALUE_NAME:"bfid",
                              option.VALUE_LABEL:"bfid",
                              option.VALUE_TYPE:option.STRING,
                              option.VALUE_USAGE:option.OPTIONAL,
                              option.DEFAULT_TYPE:None,
                              option.DEFAULT_VALUE:None,
                              }]
                         },
        option.MODIFY:{option.HELP_STRING:
                    "modify file record (dangerous!)",
                    option.VALUE_TYPE:option.STRING,
                    option.VALUE_USAGE:option.REQUIRED,
                    option.VALUE_LABEL:"bfid",
                    option.USER_LEVEL:option.ADMIN},
        option.RECURSIVE:{option.HELP_STRING:"restore directory",
                          option.DEFAULT_NAME:"restore_dir",
                          option.DEFAULT_VALUE:option.DEFAULT,
                          option.DEFAULT_TYPE:option.INTEGER,
                          option.VALUE_USAGE:option.IGNORED,
                          option.USER_LEVEL:option.ADMIN},
        option.RESTORE:{option.HELP_STRING:"restore a deleted file with optional uid:gid",
                     option.VALUE_TYPE:option.STRING,
                     option.VALUE_USAGE:option.REQUIRED,
                     option.VALUE_LABEL:"bfid",
                     option.USER_LEVEL:option.ADMIN,
                     option.EXTRA_VALUES:[{
                         option.VALUE_NAME:"owner",
                         option.VALUE_LABEL:"uid[:gid]",
                         option.VALUE_TYPE:option.STRING,
                         option.VALUE_USAGE:option.OPTIONAL,
                         option.DEFAULT_TYPE:None,
                         option.DEFAULT_VALUE:None
                         }]
                     },
        option.SET_CRCS:{option.HELP_STRING:"set CRC of a file",
                          option.VALUE_TYPE:option.STRING,
                          option.VALUE_USAGE:option.REQUIRED,
                          option.USER_LEVEL:option.ADMIN},
        option.SHOW_BAD:{option.HELP_STRING:"list all bad files",
                     option.DEFAULT_VALUE:option.DEFAULT,
                     option.DEFAULT_TYPE:option.INTEGER,
                     option.VALUE_USAGE:option.IGNORED,
                     option.USER_LEVEL:option.USER},
        option.SHOW_STATE:{option.HELP_STRING:
                       "show internal state of the server",
                       option.DEFAULT_VALUE:option.DEFAULT,
                       option.DEFAULT_TYPE:option.INTEGER,
                       option.VALUE_USAGE:option.IGNORED,
                       option.USER_LEVEL:option.ADMIN},
        option.UNMARK_BAD:{option.HELP_STRING:"unmark a bad file",
                           option.VALUE_TYPE:option.STRING,
                           option.VALUE_USAGE:option.REQUIRED,
                           option.VALUE_LABEL:"path",
                           option.USER_LEVEL:option.ADMIN,
                           option.EXTRA_VALUES:[{
                              option.VALUE_NAME:"bfid",
                              option.VALUE_LABEL:"bfid",
                              option.VALUE_TYPE:option.STRING,
                              option.VALUE_USAGE:option.OPTIONAL,
                              option.DEFAULT_TYPE:None,
                              option.DEFAULT_VALUE:None,
                              }]},
        }


def do_work(intf):
    # now get a file clerk client
    fcc = FileClient((intf.config_host, intf.config_port), intf.bfid, None, intf.alive_rcv_timeout, intf.alive_retries)
    Trace.init(fcc.get_name(MY_NAME))

    ifc = info_client.infoClient(fcc.csc)

    ticket = fcc.handle_generic_commands(MY_SERVER, intf)
    if ticket:
        pass

    elif intf.backup:
        ticket = fcc.start_backup()
        ticket = fcc.backup()
        ticket = fcc.stop_backup()

    elif intf.show_state:
        ticket = fcc.show_state()
        w = 0
        for i in ticket['state'].keys():
            if len(i) > w:
                w = len(i)
        fmt = "%%%ds = %%s"%(w)
	for i in ticket['state'].keys():
            print fmt%(i, ticket['state'][i])

    elif intf.deleted and intf.bfid:
	try:
	    if intf.restore_dir:
                do_dir = "yes"
	except AttributeError:
	    do_dir = "no"
        ticket = fcc.set_deleted(intf.deleted, do_dir)
        Trace.trace(13, str(ticket))

    elif intf.list:
        ticket = ifc.tape_list(intf.list)
        if ticket['status'][0] == e_errors.OK:
            output_format = "%%-%ds %%-20s %%10s %%-22s %%-7s %%s" \
                            % (len(intf.list))
            print output_format \
                  % ("label", "bfid", "size", "location_cookie", "delflag",
                     "original_name")
            print
            tape = ticket['tape_list']
            for record in tape:
                if record['deleted'] == 'yes':
                    deleted = 'deleted'
                elif record['deleted'] == 'no':
                    deleted = 'active'
                else:
                    deleted = 'unknown'
                print output_format % (intf.list,
                    record['bfid'], record['size'],
                    record['location_cookie'], deleted,
                    record['pnfs_name0'])

    elif intf.mark_bad:
        ticket = fcc.mark_bad(intf.mark_bad, intf.bfid)

    elif intf.unmark_bad:
        ticket = fcc.unmark_bad(intf.unmark_bad, intf.bfid)

    elif intf.show_bad:
        ticket = ifc.show_bad()
        if ticket['status'][0] == e_errors.OK:
            for f in ticket['bad_files']:
                print f['label'], f['bfid'], f['size'], f['path']

    elif intf.ls_active:
        ticket = ifc.list_active(intf.ls_active)
        if ticket['status'][0] == e_errors.OK:
            for i in ticket['active_list']:
                print i
    elif intf.bfids:
        ticket  = ifc.get_bfids(intf.bfids)
        if ticket['status'][0] == e_errors.OK:
            for i in ticket['bfids']:
                print i
            # print `ticket['bfids']`
    elif intf.bfid:
        ticket = ifc.bfid_info(intf.bfid)
	if ticket['status'][0] ==  e_errors.OK:
	    #print ticket['fc'] #old encp-file clerk format
	    #print ticket['vc']
            status = ticket['status']
            del ticket['status']
	    pprint.pprint(ticket)
            ticket['status'] = status
    elif intf.restore:
        uid = None
        gid = None
        if intf.owner:
            owner = string.split(intf.owner, ':')
            uid = int(owner[0])
            if len(owner) > 1:
                gid = int(owner[1])
        ticket = fcc.restore(intf.restore, uid=uid, gid=gid,
                             force = intf.force)

    elif intf.add:
        d={}
        for s in intf.args:
            k,v=string.split(s,'=')
            try:
                v=en_eval(v) #numeric args
            except:
                pass #yuk...
            d[k]=v
        if intf.add != "None":
            d['bfid']=intf.add # bfid
        ticket = fcc.add(d)
        print "bfid =", ticket['bfid']
    elif intf.modify:
        d={}
        for s in intf.args:
            k,v=string.split(s,'=')
            if k != 'bfid': # nice try, can not modify bfid
                try:
                    v=en_eval(v) #numeric args
                except:
                    pass #yuk...
                d[k]=v
        d['bfid']=intf.modify
        ticket = fcc.modify(d)
        if ticket['status'][0] == e_errors.OK:
            print "bfid =", ticket['bfid']
    elif intf.find_copies:
        ticket = fcc.find_copies(intf.find_copies)
        if ticket['status'][0] == e_errors.OK:
            for i in ticket['copies']:
                print i
    elif intf.find_all_copies:
        ticket = fcc.find_all_copies(intf.find_all_copies)
        if ticket['status'][0] == e_errors.OK:
            for i in ticket['copies']:
                print i
    elif intf.find_original:
        ticket = fcc.find_original(intf.find_original)
        if ticket['status'][0] == e_errors.OK:
            print ticket['original']
    elif intf.find_the_original:
        ticket = fcc.find_the_original(intf.find_the_original)
        if ticket['status'][0] == e_errors.OK:
            print ticket['original']
    elif intf.find_duplicates:
        ticket = fcc.find_duplicates(intf.find_duplicates)
        if ticket['status'][0] == e_errors.OK:
            for i in ticket['copies']:
                print i
    elif intf.erase:
        # Make this a hidden option -- this is too dangerous otherwise
        ALLOW_ERASE = True
        if ALLOW_ERASE:
            ticket = fcc.del_bfid(intf.erase)
        else:
            ticket = {}
            ticket['status'] = (e_errors.NOT_SUPPORTED, None)
    elif intf.get_crcs:
        bfid=intf.get_crcs
        ticket = fcc.get_crcs(bfid)
        print "bfid %s: sanity_cookie %s, complete_crc %s"%(`bfid`,ticket["sanity_cookie"],
                                                 `ticket["complete_crc"]`) #keep L suffix
    elif intf.set_crcs:
        bfid,sanity_size,sanity_crc,complete_crc=string.split(intf.set_crcs,',')
        sanity_crc=en_eval(sanity_crc)
        sanity_size=en_eval(sanity_size)
        complete_crc=en_eval(complete_crc)
        sanity_cookie=(sanity_size,sanity_crc)
        ticket=fcc.set_crcs(bfid,sanity_cookie,complete_crc)
        sanity_cookie = ticket['sanity_cookie']
        complete_crc = ticket['complete_crc']
        print "bfid %s: sanity_cookie %s, complete_crc %s"%(`bfid`,ticket["sanity_cookie"],
                                                            `ticket["complete_crc"]`) #keep L suffix
        
    else:
	intf.print_help()
        sys.exit(0)

    fcc.check_ticket(ticket)


if __name__ == "__main__" :
    Trace.init(MY_NAME)
    Trace.trace(6,"fcc called with args %s"%(sys.argv,))

    # fill in interface
    intf = FileClerkClientInterface(user_mode=0)

    do_work(intf)
