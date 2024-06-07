#
# system import

# enstore imports
from builtins import object
import Trace
import e_errors

# alarm state
CLEARED = 0
SET = 1
RAISED = 2


class GenericAlarm(object):

    def __init__(self):
        self.clear()

    def set(self, error_code, severity, info):
        self.error_code = error_code
        self.severity = severity
        self.info = info
        self.state = SET

    def GAraise(self):
        # this method needs to get overridden to do something.
        pass

    def clear(self):
        # clear the alarm
        self.severity = 0
        self.state = CLEARED
        self.error_code = e_errors.OK
        self.info = {}
