#!/usr/bin/env python

import uuid

# enstore imports
import e_errors

class EnqMessage():
    """ Base class for enstore cache messages
    """
    def __init__(self, message_type=None, *args, **kwargs):
        # This is a hack
        # message type must come as first argument
        # but sometimes it comes as 'message_type' in kwargs
        # or as 'mtype' in kwargs
        if not message_type and kwargs:
            message_type = kwargs.get('message_type')
            if not message_type:
                message_type = kwargs.get('mtype')
        if kwargs:
            self.correlation_id = kwargs.get('correlation_id')
        if message_type is None:
            raise e_errors.EnstoreError(
                None, "message type undefined", e_errors.WRONGPARAMETER)

        # self.correlation_id can be set in base class Message through **kwargs.
        # set correlation_id here if it has not been set in Message constructor
        if not hasattr(self, 'correlation_id') or self.correlation_id is None:
            self.correlation_id = str(uuid.uuid4())  # make a random UUID
        if not hasattr(self, 'properties') or self.properties is None:
            self.properties = {}
#     enstore message protocol version:
#       major is placed into properties (messaging protocol compatibility)
# minor is not in the header (all messages with the same major a
# compatible)
        self.properties["version"] = 2
        if "reply_to" in kwargs:
            self.reply_to = kwargs['reply_to']
        self.properties["en_type"] = message_type
        self.content = kwargs
