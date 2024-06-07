###############################################################################
# src/$RCSfile$   $Revision$
#
# enstore imports

from builtins import object
class BackupClient(object):

    def start_backup(self):
        r = self.send({'work': 'start_backup'})
        return r

    def stop_backup(self):
        r = self.send({'work': 'stop_backup'})
        return r

    def backup(self):
        r = self.send({'work': 'backup'})
        return r
