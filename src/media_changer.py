#########################################################################
#                                                                       #
# Media Changer server.                                                 #
# Media Changer is an abstract object representing a physical device or #
# operator who performs mounts / dismounts of tapes on tape drives.     #
# At startup the media changer process takes its argument from the      #
# command line and cofigures based on the dictionary entry in the       #
# Configuration Server for this type of Media Changer.                  #
# It accepts then requests from its clients and performs tape mounts    #
# and dismounts                                                         #
#                                                                       #
#########################################################################
#  $Id$

import os
import SocketServer
import configuration_client
import dispatching_worker
import generic_server
import log_client
import string

list = 0
# media loader template class
class MediaLoaderMethods(dispatching_worker.DispatchingWorker) :

    # load volume into the drive
    def load(self,
             external_label,    # volume external label
             drive) :           # drive id
        self.reply_to_caller({'status' : 'ok'})

    # unload volume from the drive
    def unload(self,
               external_label,  # volume external label
               drive) :         # drive id
        self.reply_to_caller({'status' : 'ok'})

    # wrapper method for client - server communication
    def loadvol(self,
                ticket):        # associative array containing volume and\
                                # drive id
        return self.load(ticket['external_label'], ticket['drive_id'])

    # wrapper method for client - server communication
    def unloadvol(self, ticket):
        return self.unload(ticket['external_label'], ticket['drive_id'])

# IBM3494 robot class
class IBM3494_MediaLoaderMethods(MediaLoaderMethods) :

    # load volume into the drive
    def load(self, external_label, drive) :
        print 'I am load function and my type is IBM3494'
        self.reply_to_caller({'status' : 'ok'})

    # unload volume from the drive
    def unload(self, external_label, drive) :
        print 'I am unload function and my type is IBM3494'
        self.reply_to_caller({'status' : 'ok'})

# FTT tape drives with no robot
class FTT_MediaLoaderMethods(MediaLoaderMethods) :

    # assumes volume is in drive
    def load(self, external_label, drive) :
        os.system("mt -t " + drive + " rewind")
        self.reply_to_caller({'status' : 'ok'})

    # assumes volume is in drive and leave it there for testing
    def unload(self, external_label, drive) :
        os.system("mt -t " + drive + " rewind")
        self.reply_to_caller({'status' : 'ok'})

# STK robot class
class STK_MediaLoaderMethods(MediaLoaderMethods) :

    # load volume into the drive
    def load(self, external_label, tape_drive) :
        # form mount command to be executed
        stk_mount_command = "rsh " + keys['acls_host'] + " -l " + \
                            keys['acls_uname'] + " 'echo mount " + \
                            external_label + " " + tape_drive + \
                            " | /export/home/ACSSS/bin/cmd_proc 2>>/tmp/garb'"

        print 'mount command is:',stk_mount_command

        # call mount command
        returned_message = os.popen(stk_mount_command, "r").readlines()
        out_ticket = {"status" : "mount_failed"}

        # analize the retrun message
        for line in returned_message:
            if list: print line
            if string.find(line, "mounted") != -1 :
                out_ticket = {"status" : "ok"}
                break
        # send reply to caller
        print out_ticket
        self.reply_to_caller(out_ticket)
        print "mount status " + out_ticket["status"]

    # unload volume from the drive
    def unload(self, external_label, tape_drive) :

        # form dismount command to be executed
        stk_mount_command = "rsh " + keys['acls_host'] + " -l " +\
                            keys['acls_uname'] + " 'echo dismount " +\
                            external_label + " " + tape_drive + " force" +\
                            " | /export/home/ACSSS/bin/cmd_proc 2>>/tmp/garb'"

        # call dismount command
        print 'dismount command is:',stk_mount_command
        returned_message = os.popen(stk_mount_command, "r").readlines()
        out_ticket = {"status" : "dismount_failed"}

        # analize the retrun message
        for line in returned_message:
            if list: print line
            if string.find(line, "dismount") != -1 :
                out_ticket = {"status" : "ok"}
                break
        self.reply_to_caller(out_ticket)
        print "dism status " + out_ticket["status"]

# STK media loader server
class STK_MediaLoader(STK_MediaLoaderMethods,
                      generic_server.GenericServer,
                      SocketServer.UDPServer) :
    pass

# Raw Disk media loaded server
class RDD_MediaLoader(MediaLoaderMethods,
                      generic_server.GenericServer,
                      SocketServer.UDPServer) :
    pass

# Raw Disk media loaded server
class FTT_MediaLoader(FTT_MediaLoaderMethods,
                      generic_server.GenericServer,
                      SocketServer.UDPServer) :
    pass

if __name__ == "__main__" :
    import sys
    import getopt
    import socket
    import time
    import timeofday

    # defaults
    #config_host = "localhost"
    (config_host,ca,ci) = socket.gethostbyaddr(socket.gethostname())
    config_port = "7500"
    config_file = ""
    config_list = 0

    # see what the user has specified. bomb out if wrong options specified
    options = ["config_host=","config_port=","config_file="\
               ,"config_list","list","help"]
    optlist,args=getopt.getopt(sys.argv[1:],'',options)
    for (opt,value) in optlist :
        if opt == "--config_host" :
            config_host = value
        elif opt == "--config_port" :
            config_port = value
        elif opt == "--config_list" :
            config_list = 1
        elif opt == "--list" :
            list = 1
        elif opt == "--help" :
            print "python ",sys.argv[0], options, "media changer"
            print "   do not forget the '--' in front of each option"
            sys.exit(0)

    # bomb out if can't translate host
    ip = socket.gethostbyname(config_host)

    # bomb out if port isn't numeric
    config_port = string.atoi(config_port)

    # bomb out if we don't have a media changer
    if len(args) < 1 :
        print "python ",sys.argv[0], options, "media changer"
        print "   do not forget the '--' in front of each option"
        sys.exit(1)

    if config_list :
        print "Connecting to configuration server at ",config_host,config_port
    csc = configuration_client.configuration_client(config_host,config_port)

    keys = csc.get(args[0])


    # here we need to define what is the class of the media changer
    # and create an object of that class based on the value of args[0]
    # for now there is just one possibility

    # THIS NEEDS TO BE FIXED -- WE CAN'T BE CHECKING FOR EACH KIND!!!
    if args[0] == 'STK.media_changer' :
        mc =  STK_MediaLoader((keys['host'], keys['port']),
                               STK_MediaLoaderMethods)
    elif args[0] == 'FTT.media_changer' :
        mc =  FTT_MediaLoader((keys['host'], keys['port']),
                               FTT_MediaLoaderMethods)
    else :
        mc =  RDD_MediaLoader((keys['host'], keys['port']),
                               MediaLoaderMethods)
    mc.set_csc(csc)

    # create a log client
    logc = log_client.LoggerClient(csc, keys["logname"], 'logserver', 0)
    mc.set_logc(logc)

    while 1:
        try:
            logc.send(log_client.INFO, "Media Changer"+args[0]+"(re) starting")
            mc.serve_forever()
        except:
            format = timeofday.tod()+" "+\
                     str(sys.argv)+" "+\
                     str(sys.exc_info()[0])+" "+\
                     str(sys.exc_info()[1])+" "+\
                     "media changer serve_forever continuing"
            print format
            logc.send(log_client.INFO,format)
            continue
