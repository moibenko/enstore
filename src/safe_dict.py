# this class provides a way to handle dictionaries without having to do a
# dict.has_key or a dict.get for every element.  it supports dictionaries
# contained within dictionaries too.

from UserDict import UserDict


class SafeDict(UserDict):

    def __init__(self, d):
        UserDict.__init__(self)
        for k, v in list(d.items()):
            if isinstance(v, type({})):
                v = SafeDict(v)
            self[k] = v

    def __getitem__(self, key):
        if key in self.data:
            return self.data[key]
        else:
            return SafeDict({})

    def __bool__(self):
        return len(list(self.data.keys()))
