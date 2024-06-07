from __future__ import print_function
from future.utils import raise_
__version__ = '$Id$'
from HTMLgen import *
from HTMLcolors import *
from HTMLutil import *
import cgi
import sys
import tempfile
import traceback


def _fstodict(fs):
    d = {}
    for tok in list(fs.keys()):
        alist = []
        if isinstance(fs[tok], list):
            for val in fs[tok]:
                if val.value:
                    alist.append(val.value)
        elif fs[tok].file:
            alist = (fs[tok].filename, fs[tok].file)
        else:
            if fs[tok].value:
                alist = fs[tok].value
        if alist:
            d[tok] = alist
    return d


class CGI(Document):
    def __init__(self, **kw):
        Document.__init__(self)
        self._tempfile = tempfile.mktemp()

        self.active = 1
        self.logfile = '/home/httpd/logs/cgi_log'
        self.script_url = ''
        self.source = ''

        self.valid = {'_no_function': _no_function}
        self.function = '_no_function'

        self.form = {}
        self.form_ok = 1
        self.form_defaults = {}
        self.form_errors = {}
        self.form_messages = []

        self.http = {'Content-type': 'text/html'}
        for item in list(kw.keys()):
            if item in self.__dict__:
                self.__dict__[item] = kw[item]
            else:
                raise_(KeyError,
                       repr(item) + ' not a valid parameter of the CGI class')

    def get_form(self):
        self.form = _fstodict(cgi.FieldStorage())
        if 'function' in self.form:
            f = self.form['function']
            if f in list(self.valid.keys()):
                self.function = f

    def verify(self):
        for tok in list(self.form_defaults.keys()):
            if tok not in self.form:
                self.form[tok] = self.form_defaults[tok]
        for tok in list(self.form_errors.keys()):
            if tok not in self.form:
                self.form_messages.append(self.form_errors[tok])
                self.form_ok = 0

    def run(self, cont=0):
        # Print HTTP messages
        for key in list(self.http.keys()):
            print('%s: %s' % (key, self.http[key]))
        print()

        # Redirect stderr
        sys.stderr = open(self._tempfile, 'w')

        # Grab query string
        self.get_form()

        # Function handling
        if not self.active:
            ret = _not_active(self)
            print(self)
            sys.exit(0)
        elif not '_no_function' in list(self.valid.keys()):
            self.valid['_no_function'] = _no_function
        if not self.function or self.function not in list(self.valid.keys()):
            self.function = '_no_function'
        try:
            ret = self.valid[self.function](self)
        except BaseException:
            traceback.print_exc()
            sys.stderr.flush()
            f = open(self._tempfile, 'r')
            self.title = 'CGI Error Occured'
            self.append(Pre(f.read()))
            f.close()

        # Print Document object
        print(self)
        if not cont:
            sys.exit(0)  # Provide a speedy exit


class MinimalCGI(MinimalDocument, CGI):
    __init__ = CGI.__init__


# For backward compatibility
CGIApp = CGI


def _not_active(cgi):
    cgi.title = 'Script Inactive!'
    cgi.subtitle = 'Please Try Later'
    cgi.append(Paragraph("""
            This script is being service or is otherwise unavailable.
            Please try again later or contact the author with any
            questions or comments.
            """))
    return 0


def _no_function(cgi):
    cgi.title = 'Error!'
    cgi.subtitle = 'No Action'
    cgi.append(Paragraph("""
            No action was defined or the action was not
            in the list of valid actions. Please send
            feedback to the author."""))
    return 0
