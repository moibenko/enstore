#!/usr/bin/env python

# $Id$

# python modules
import sys
import os
import threading
import errno
import pprint
import socket
import signal                           
import time                             
import string                           
import select
import exceptions
import traceback

# enstore modules

import setpath
import generic_server
import interface
import dispatching_worker
import volume_clerk_client              
import file_clerk_client                
import media_changer_client             
import callback
import checksum
import e_errors
import udp_client
import socket_ext
import hostaddr
import string_driver

import Trace

"""TODO:

   Create a change_state function, so all state transitions can be logged.
   Find out why --clean doesn't work
   

"""

class MoverError(exceptions.Exception):
    def __init__(self, arg):
        exceptions.Exception.__init__(self,arg)


#states
IDLE, MOUNT_WAIT, SEEK, ACTIVE, HAVE_BOUND, DISMOUNT_WAIT, DRAINING, OFFLINE, CLEANING, ERROR = range(10)

_state_names=['IDLE', 'MOUNT_WAIT', 'SEEK', 'ACTIVE', 'HAVE_BOUND', 'DISMOUNT_WAIT',
             'DRAINING', 'OFFLINE', 'CLEANING', 'ERROR']

##assert len(_state_names)==10

def state_name(state):
    return _state_names[state]

#modes
READ, WRITE = range(2)

def mode_name(mode):
    if mode is None:
        return None
    else:
        return ['READ','WRITE'][mode]

KB=1L<<10
MB=1L<<20
GB=1L<<30

SANITY_SIZE = 65536

class Buffer:
    def __init__(self, blocksize, min_bytes = 0, max_bytes = 1*MB):
        self.blocksize = blocksize
        self.min_bytes = min_bytes
        self.max_bytes = max_bytes
        self.complete_crc = 0L
        self.sanity_crc = 0L
        self.sanity_bytes = 0L
        self.header_size = None
        self.trailer_size = 0L

        self.read_ok = threading.Event()
        self.write_ok = threading.Event()
        
        self._lock = threading.Lock()
        self._buf = []
        self._buf_bytes = 0L
        self._freelist = []
        self._reading_block = None
        self._writing_block = None
        self._read_ptr = 0
        self._write_ptr = 0

    def reset(self):
        self._lock.acquire()

        #notify anybody who is waiting on this? - cgw
        self.read_ok.set()
        self.write_ok.clear()
        
        self._buf = []
        self._freelist = []
        self._buf_bytes = 0
        self._reading_block = None
        self._writing_block = None
        self._read_ptr = 0
        self._write_ptr = 0
        self.complete_crc = 0L
        self.sanity_crc = 0L
        self.sanity_bytes = 0L
        self.header_size = None
        self.trailer_size = 0
        self._lock.release()
        
    def nbytes(self):
        return self._buf_bytes
        
    def full(self):
        return self.nbytes() >= self.max_bytes
    
    def empty(self):
        ## this means that a stream write would fail - we have no data at all to send
        self._lock.acquire()
        r =  len(self._buf) == 0 and not self._writing_block
        self._lock.release()
        return r
    
    def low(self):
        ## this means that either we don't have enough data for a full block,
        ## or we're deferring writes until enough data is buffered (min_bytes)
        self._lock.acquire()
        r = len(self._buf) == 0 or self.nbytes() < self.min_bytes
        self._lock.release()
        return r
    
    def set_min_bytes(self, min_bytes):
        self.min_bytes = min_bytes
        
    def set_blocksize(self, blocksize):
        if blocksize == self.blocksize:
            return
        if self.nbytes() != 0:
            raise "Buffer error: changing blocksize of nonempty buffer"
        self._lock.acquire()
        self._freelist = []
        self.blocksize = blocksize
        self._lock.release()
    
    def push(self, data):
        self._lock.acquire()
        self._buf.append(data)
        self._buf_bytes = self._buf_bytes + len(data)
        self._lock.release()
        
    def pull(self):
        self._lock.acquire()
        data = self._buf.pop(0)
        self._buf_bytes = self._buf_bytes - len(data)
        self._lock.release()
        return data
        
    def nonzero(self):
        return self.nbytes() > 0
    
    def __repr__(self):
        return "Buffer %s  %s  %s" % (self.min_bytes, self._buf_bytes, self.max_bytes)

    def block_read(self, nbytes, driver):
        space = self._getspace()
        bytes_read = driver.read(space, 0, nbytes)
        if bytes_read == nbytes: #normal case
            self.push(space)
        elif bytes_read<=0: #error
            Trace.log(25, "block_read: read %s" % (bytes_read,))
            pass #XXX or raise an exception?
        else: #partial block read
            Trace.trace(25, "partial block (%s/%s) read" % (bytes_read,nbytes))
            partial=space[:bytes_read]
            self.push(partial)
            self._freespace(space)
        Trace.trace(100, "block_read: len(buf)=%s"%(len(self._buf),)) #XXX remove CGW
        return bytes_read
        
    def block_write(self, nbytes, driver):
        data = self.pull() 
        if len(data)!=nbytes:
            raise ValueError, "asked to write %s bytes, buffer has %s" % (nbytes, len(data))
        bytes_written = driver.write(data, 0, nbytes)
        if bytes_written == nbytes: #normal case
            self._freespace(data)
        else: #XXX raise an exception?
            self._freespace(data)
        return bytes_written
        
    def stream_read(self, nbytes, driver):
        do_crc = 1
        if type(driver) is type (""):
            driver = string_driver.StringDriver(driver)
        if isinstance(driver, string_driver.StringDriver):
            do_crc = 0
        if not self._reading_block:
            self._reading_block = self._getspace()
            self._read_ptr = 0
        bytes_to_read = min(self.blocksize - self._read_ptr, nbytes)
        bytes_read = driver.read(self._reading_block, self._read_ptr, bytes_to_read)
        if do_crc:
            self.complete_crc = checksum.adler32_o(self.complete_crc, self._reading_block,
                                                   self._read_ptr, bytes_read)
            if self.sanity_bytes < SANITY_SIZE:
                nbytes = min(SANITY_SIZE-self.sanity_bytes, bytes_read)
                self.sanity_crc = checksum.adler32_o(self.sanity_crc, self._reading_block,
                                                     self._read_ptr, nbytes)
                self.sanity_bytes = self.sanity_bytes + nbytes
        self._read_ptr = self._read_ptr + bytes_read
        if self._read_ptr == self.blocksize: #we filled up  a block
            self.push(self._reading_block)
            self._reading_block = None
            self._read_ptr = 0
        return bytes_read

    def eof_read(self):
        Trace.trace(10, "EOF reached, %s"%(self._read_ptr,))
        if self._reading_block and self._read_ptr:
            data = self._reading_block[:self._read_ptr]
            self.push(data)
            self._reading_block = None
            self._read_ptr = None
    
    def stream_write(self, nbytes, driver):
        if not self._writing_block:
            if self.empty():
                Trace.trace(10, "stream_write: buffer empty")
                return 0
            self._writing_block = self.pull()
            self._write_ptr = 0
        bytes_to_write = min(len(self._writing_block)-self._write_ptr, nbytes)
        if driver:
            bytes_written = driver.write(self._writing_block, self._write_ptr, bytes_to_write)
            self.complete_crc = checksum.adler32_o(self.complete_crc, self._writing_block,
                                                   self._write_ptr, bytes_written)
            if self.sanity_bytes < SANITY_SIZE:
                nbytes = min(SANITY_SIZE-self.sanity_bytes, bytes_written)
                self.sanity_crc = checksum.adler32_o(self.sanity_crc, self._writing_block,
                                                     self._write_ptr, nbytes)
                self.sanity_bytes = self.sanity_bytes + nbytes
        else:
            bytes_written = bytes_to_write #discarding header stuff
        self._write_ptr = self._write_ptr + bytes_written
        if self._write_ptr == len(self._writing_block): #finished sending out this block
            self._freespace(self._writing_block)
            self._writing_block = None
            self._write_ptr = 0
        return bytes_written

    def _getspace(self):
        self._lock.acquire()
        if self._freelist:
            r =  self._freelist.pop(0)
        else:
            r = '\0' * self.blocksize
        self._lock.release()
        return r
    
    def _freespace(self, s):
        if len(s) != self.blocksize:
            return # don't need this partial block around!
        self._lock.acquire()
        self._freelist.append(s)
        self._lock.release()
    
def cookie_to_long(cookie): # cookie is such a silly term, but I guess we're stuck with it :-(
    if type(cookie) is type(0L):
        return cookie
    if type(cookie) is type(0):
        return long(cookie)
    if type(cookie) != type(''):
        raise TypeError, "expected string or integer, got %s %s" % (cookie, type(cookie))
    if '_' in cookie:
        part, block, file = string.split(cookie, '_')
    else:
        file = cookie
    if file[-1]=='L':
        file = file[:-1]
    return long(file)

def loc_to_cookie(loc):
    if type(loc) is type(""):
        loc = cookie_to_long(loc)
    if loc is None:
        loc = 0
    return '%04d_%09d_%07d' % (0, 0, loc)
        
    
class Mover(dispatching_worker.DispatchingWorker,
            generic_server.GenericServer):

    def __init__(self, csc_address, name):
        generic_server.GenericServer.__init__(self, csc_address, name)
        self.name = name

    def start(self):
        name = self.name
        self.t0 = time.time()
        self.config = self.csc.get(name)
        if self.config['status'][0] != 'ok':
            raise MoverError('could not start mover %s: %s'%(name, self.config['status']))

        logname = self.config.get('logname', name)
        Trace.init(logname)
        Trace.log(e_errors.INFO, "mover %s started" % (self.name,))
        
        self.address = (self.config['hostip'], self.config['port'])

        self.do_eject = 1
        if self.config.has_key('do_eject'):
            if self.config['do_eject'][0] in ('n','N'):
                self.do_eject = 0

        self.do_cleaning = 1
        if self.config.has_key('do_cleaning'):
            if self.config['do_cleaning'][0] in ('n','N'):
                self.do_cleaning = 0
        
        self.mc_device = self.config.get('mc_device', 'UNDEFINED')
        self.media_type = self.config.get('media_type', '8MM') #XXX
        self.min_buffer = self.config.get('min_buffer', 8*MB)
        self.max_buffer = self.config.get('max_buffer', 64*MB)
        self.buffer = Buffer(0, self.min_buffer, self.max_buffer)
        self.udpc =  udp_client.UDPClient()
        self.state = IDLE
        self.last_error = (e_errors.OK, None)
        if self.check_lockfile():
            self.state = OFFLINE
        self.current_location = 0L
        self.current_volume = None #external label of current mounted volume
        self.last_location = 0L
        self.last_volume = None
        self.mode = None # READ or WRITE
        self.bytes_to_transfer = 0L
        self.bytes_to_read = 0L
        self.bytes_to_write = 0L
        self.bytes_read = 0L
        self.bytes_written = 0L
        self.volume_family = None 
        self.volume_status = (['none', 'none'], ['none', 'none'])
        self.files = ('','')
        self.transfers_completed = 0
        self.transfers_failed = 0
        self.current_work_ticket = {}
        self.vol_info = {}
        self.dismount_time = None
        self.delay = 0
        self.fcc = None
        self.vcc = None
        self.mcc = media_changer_client.MediaChangerClient(self.csc,
                                                           self.config['media_changer'])
        self.config['device'] = os.path.expandvars(self.config['device'])

        import net_driver
        self.net_driver = net_driver.NetDriver()
        self.client_socket = None

        self.config['name']=self.name 
        self.config['product_id']='Unknown'
        self.config['serial_num']=0
        self.config['vendor_id']='Unknown'
        self.config['local_mover'] = 0 #XXX who still looks at this?
        self.driver_type = self.config['driver']

        self.default_dismount_delay = self.config.get('dismount_delay', 60)
        if self.default_dismount_delay < 0:
            self.default_dismount_delay = 31536000 #1 year
        self.max_dismount_delay = self.config.get('max_dismount_delay', 600)
        
        self.libraries = []
        lib_list = self.config['library']
        if type(lib_list) != type([]):
            lib_list = [lib_list]
        for lib in lib_list:
            lib_config = self.csc.get(lib)
            self.libraries.append((lib, (lib_config['hostip'], lib_config['port'])))

        #how often to send a message to the library manager
        self.update_interval = self.config.get('update_interval', 15)

        self.single_filemark=self.config.get('single_filemark', 0)
        ##Setting this attempts to optimize filemark writing by writing only
        ## a single filemark after each file, instead of using ftt's policy of always
        ## writing two and backspacing over one.  However this results in only
        ## a single filemark at the end of the volume;  causing some drives
        ## (e.g. Mammoth-1) to have trouble spacing to end-of-media.
            
        if self.driver_type == 'NullDriver':
            self.device = None
            self.single_filemark = 1 #need this to cause EOD cookies to update.
            ##XXX should this be more encapsulated in the driver class?
            import null_driver
            self.tape_driver = null_driver.NullDriver()
        elif self.driver_type == 'FTTDriver':
            self.device = self.config['device']
            import ftt_driver
            import ftt
            self.tape_driver = ftt_driver.FTTDriver()
            self.maybe_clean()
            have_tape = self.tape_driver.open(self.device, mode=0, retry_count=3)
            stats = self.tape_driver.ftt.get_stats()
            self.config['product_id'] = stats[ftt.PRODUCT_ID]
            self.config['serial_num'] = stats[ftt.SERIAL_NUM]
            self.config['vendor_id'] = stats[ftt.VENDOR_ID]
            if have_tape == 1:
                status = self.tape_driver.verify_label(None)
                if status[0]==e_errors.OK:
                    self.current_volume = status[1]
                    self.state = HAVE_BOUND
                    Trace.log(e_errors.INFO, "have vol %s at startup" % (self.current_volume,))
                    self.dismount_time = time.time() + self.default_dismount_delay
                else:
                    have_tape=0
            self.tape_driver.close()
            if not have_tape:
                Trace.log(e_errors.INFO, "performing precautionary dismount at startup")
                self.dismount_volume(after_function=self.idle)

        else:
            print "Sorry, only Null and FTT driver allowed at this time"
            sys.exit(-1)

        self.mount_delay = self.config.get('mount_delay',
                                           self.tape_driver.mount_delay)
        
        if type(self.mount_delay) != type(0):
            self.mount_delay = int(self.mount_delay)
        if self.mount_delay < 0:
            self.mount_delay = 0

        dispatching_worker.DispatchingWorker.__init__(self, self.address)
        self.set_interval_func(self.update, self.update_interval) #this sets the period for messages to LM.
        self.set_error_handler(self.handle_mover_error)
        ##end of __init__

    def nowork(self, ticket):
        return {}

    def handle_mover_error(self, exc, msg, tb):
        Trace.log(e_errors.ERROR, "handle mover error %s %s"%(exc, msg))
        Trace.trace(10, "%s %s" %(self.current_work_ticket, state_name(self.state)))
        if self.current_work_ticket:
            try:
                Trace.trace(10, "handle error: calling transfer failed, str(msg)=%s"%(str(msg),))
                self.transfer_failed(exc, msg)
            except:
                pass
    
    def update(self, state=None, reset_timer=None):
        if state is None:
            state = self.state
        Trace.trace(20,"update: %s" % (state_name(state)))
        if not hasattr(self,'_last_state'):
            self._last_state = None
        if state in (CLEANING, DRAINING, OFFLINE, ERROR, SEEK, MOUNT_WAIT, DISMOUNT_WAIT):
            if state == self._last_state:
                return
        if reset_timer:
            self.reset_interval_timer()
        ticket = self.format_lm_ticket(state=state)
        for lib, addr in self.libraries:
            if state is OFFLINE and self._last_state is OFFLINE:
                continue
            if state != self._last_state:
                Trace.trace(10, "Send %s to %s" % (ticket, addr))
            self.udpc.send_no_wait(ticket, addr)

        self._last_state = self.state
        self.check_dismount_timer()

    def check_dismount_timer(self):
        ## See if the delayed dismount timer has expired
        now = time.time()
        if self.state is HAVE_BOUND and self.dismount_time and now>self.dismount_time:
            Trace.trace(10,"Dismount time expired %s"% (self.current_volume,))
            self.run_in_thread('media_thread', self.dismount_volume, after_function=self.idle)
            
    def idle(self):
        self.state = IDLE
        self.mode = None
        self.volume_status = (['none', 'none'], ['none','none'])
        self.last_error = (e_errors.OK, None)
        self.vol_info = {}
        self.update() 

    def offline(self):
        self.state = OFFLINE
        self.update()

    def reset(self):
        self.current_work_ticket = None
        self.buffer.reset()
        self.bytes_read = 0L
        self.bytes_written = 0L
        
    def return_work_to_lm(self,ticket):
        try:
            lm_address = ticket['lm']['address']
        except KeyError, msg:
            self.malformed_ticket(ticket, "[lm][address]")
            return
        ticket = self.format_lm_ticket(state=ERROR,
                                       error_info=(e_errors.MOVER_BUSY, state_name(self.state)),
                                       returned_work=ticket)
        self.udpc.send_no_wait(ticket, lm_address)

        
    def read_client(self):
        Trace.trace(8, "read_client starting,  bytes_to_read=%s" % (self.bytes_to_read,))
        driver = self.net_driver
        if self.bytes_read == 0 and self.header: #splice in cpio headers, as if they came from client
            nbytes = self.buffer.header_size
            ##XXX this will fail if nbytes>block_size.
            bytes_read = self.buffer.stream_read(nbytes,self.header)

        while self.state in (ACTIVE, DRAINING) and self.bytes_read < self.bytes_to_read:

            if self.buffer.full():
                Trace.trace(9, "read_client: buffer full %s/%s, read %s/%s" %
                            (self.buffer.nbytes(), self.buffer.max_bytes,
                             self.bytes_read, self.bytes_to_read))
                self.buffer.read_ok.clear()
                self.buffer.read_ok.wait(1)
                continue

            nbytes = min(self.bytes_to_read - self.bytes_read, self.buffer.blocksize)
            bytes_read = 0
            try:
                bytes_read = self.buffer.stream_read(nbytes, driver)
            except:
                exc, detail, tb = sys.exc_info()
                self.transfer_failed(e_errors.ENCP_GONE, detail)
                return
            if bytes_read <= 0:  #  The client went away!
                Trace.log(e_errors.ERROR, "read_client: dropped connection")
                self.transfer_failed(e_errors.ENCP_GONE, None)
                return
            self.bytes_read = self.bytes_read + bytes_read

            if not self.buffer.low():
                self.buffer.write_ok.set()
                
        if self.bytes_read == self.bytes_to_read:
            if self.trailer:
                trailer_driver = string_driver.StringDriver(self.trailer)
                trailer_bytes_read = 0
                while trailer_bytes_read < self.buffer.trailer_size:
                    bytes_to_read = self.buffer.trailer_size - trailer_bytes_read
                    bytes_read = self.buffer.stream_read(bytes_to_read, trailer_driver)
                    trailer_bytes_read = trailer_bytes_read + bytes_read
                    Trace.trace(8, "read %s bytes of trailer" % (trailer_bytes_read,))
            self.buffer.eof_read() #pushes last partial block onto the fifo
            self.buffer.write_ok.set()

        Trace.trace(8, "read_client exiting, read %s/%s bytes" %(self.bytes_read, self.bytes_to_read))
                        
    def write_tape(self):
        Trace.trace(8, "write_tape starting, bytes_to_write=%s" % (self.bytes_to_write,))
        driver = self.tape_driver
        count = 0
        while self.state in (ACTIVE, DRAINING) and self.bytes_written<self.bytes_to_write:
            if (self.bytes_read == self.bytes_to_read and self.buffer.empty()
                or self.bytes_read < self.bytes_to_read and self.buffer.low()):
                Trace.trace(9,"write_tape: buffer low %s/%s, wrote %s/%s"%
                            (self.buffer.nbytes(), self.buffer.min_bytes,
                             self.bytes_read, self.bytes_to_read))
                self.buffer.write_ok.clear()
                self.buffer.write_ok.wait(1)
                continue

            count = (count + 1) % 20
            if count == 0:
                ##Dynamic setting of low-water mark
                if self.bytes_read >= self.buffer.min_bytes:
                    netrate, junk = self.net_driver.rates()
                    taperate, junk = self.tape_driver.rates()
                    if taperate > 0:
                        ratio = netrate/(taperate*1.0)
                        optimal_buf = self.bytes_to_transfer * (1-ratio)
                        optimal_buf = min(optimal_buf, self.max_buffer)
                        optimal_buf = max(optimal_buf, self.min_buffer)
                        Trace.trace(12,"netrate = %.3g, taperate=%.3g" % (netrate, taperate))
                        if self.buffer.min_bytes != optimal_buf:
                            Trace.trace(12,"Changing buffer size from %s to %s"%
                                        (self.buffer.min_bytes, optimal_buf))
                            self.buffer.set_min_bytes(optimal_buf)

            nbytes = min(self.bytes_to_write - self.bytes_written, self.buffer.blocksize)

            bytes_written = 0
            try:
                bytes_written = self.buffer.block_write(nbytes, driver)
            except:
                exc, detail, tb = sys.exc_info()
                self.transfer_failed(e_errors.WRITE_ERROR, detail)
                break
            if bytes_written != nbytes:
                self.transfer_failed(e_errors.WRITE_ERROR, None) #XXX detail?
                break
            self.bytes_written = self.bytes_written + bytes_written

            if not self.buffer.full():
                self.buffer.read_ok.set()
        
            
        Trace.trace(8, "write_tape exiting, wrote %s/%s bytes" %( self.bytes_written, self.bytes_to_write))

        if self.bytes_written == self.bytes_to_write:
            if self.single_filemark:
                self.tape_driver.writefm()
            else:
                self.tape_driver.writefm()
                self.tape_driver.writefm()
                self.tape_driver.skipfm(-1)
            ##We don't ever want to let ftt handle the filemarks for us, because its
            ##default behavior is to write 2 filemarks and backspace over both
            ##of them.
            self.tape_driver.flush()
            if self.update_after_writing():
                self.transfer_completed()
            else:
                self.transfer_failed()


    def read_tape(self):
        Trace.trace(8, "read_tape starting, bytes_to_read=%s" % (self.bytes_to_read,))
        driver = self.tape_driver
        while self.state in (ACTIVE, DRAINING) and self.bytes_read < self.bytes_to_read:
            
            if self.buffer.full():
                Trace.trace(9, "read_tape: buffer full %s/%s, read %s/%s" %
                            (self.buffer.nbytes(), self.buffer.max_bytes,
                             self.bytes_read, self.bytes_to_read))
                self.buffer.read_ok.clear()
                self.buffer.read_ok.wait(1)
                continue
            
            nbytes = min(self.bytes_to_read - self.bytes_read, self.buffer.blocksize)
            if self.bytes_read == 0 and nbytes<self.buffer.blocksize: #first read, try to read a whole block
                nbytes = self.buffer.blocksize

            bytes_read = 0
            try:
                bytes_read = self.buffer.block_read(nbytes, driver)
            except:
                exc, detail, tb = sys.exc_info()
                self.transfer_failed(e_errors.READ_ERROR, detail)
                break
            if bytes_read <= 0:
                self.transfer_failed(e_errors.READ_ERROR, None) ##XXX detail?
                break
            if self.bytes_read==0: #Handle variable-sized cpio header
                if len(self.buffer._buf) != 1:
                    Trace.log(e_errors.ERROR,
                              "read_tape: error skipping over cpio header, len(buf)=%s"%(len(self.buffer._buf)))
                b0 = self.buffer._buf[0]
                if len(b0) >= self.wrapper.min_header_size:
                    header_size = self.wrapper.header_size(b0)
                    self.buffer.header_size = header_size
                    self.bytes_to_read = self.bytes_to_read + header_size
            self.bytes_read = self.bytes_read + bytes_read
            if self.bytes_read > self.bytes_to_read: #this is OK, we read a cpio trailer or something
                self.bytes_read = self.bytes_to_read

            if not self.buffer.empty():
                self.buffer.write_ok.set()
            
        Trace.trace(8, "read_tape exiting, read %s/%s bytes" % (self.bytes_read, self.bytes_to_read))
                
    def write_client(self):
        Trace.trace(8, "write_client starting, bytes_to_write=%s" % (self.bytes_to_write,))
        driver = self.net_driver
        #be careful about 0-length files
        if self.bytes_to_write > 0 and self.bytes_written == 0 and self.wrapper: #Skip over cpio or other headers
            while self.buffer.header_size is None and self.state in (ACTIVE, DRAINING):
                Trace.trace(8, "write_client: waiting for read_tape to set header info")
                self.buffer.write_ok.clear()
                self.buffer.write_ok.wait(1)
            # writing to "None" will discard headers, leaving stream positioned at
            # start of data
            self.buffer.stream_write(self.buffer.header_size, None)

        while self.state in (ACTIVE, DRAINING) and self.bytes_written < self.bytes_to_write:
            if self.buffer.empty():
                Trace.trace(9, "write_client: buffer empty, wrote %s/%s" %
                            (self.bytes_written, self.bytes_to_write))
                self.buffer.write_ok.clear()
                self.buffer.write_ok.wait(1)
                continue
                
            nbytes = min(self.bytes_to_write - self.bytes_written, self.buffer.blocksize)
            bytes_written = 0
            try:
                bytes_written = self.buffer.stream_write(nbytes, driver)
            except:
                exc, detail, tb = sys.exc_info()
                self.transfer_failed(e_errors.ENCP_GONE, detail)
                break
            if bytes_written < 0:
                self.transfer_failed(e_errors.ENCP_GONE, None) #XXX detail?
                break
            if bytes_written != nbytes:
                pass #this is not unexpected, since we send with MSG_DONTWAIT
            self.bytes_written = self.bytes_written + bytes_written

            if not self.buffer.full():
                self.buffer.read_ok.set()
            
        Trace.trace(8, "write_client exiting: wrote %s/%s bytes" % (self.bytes_written, self.bytes_to_write))
  
        if self.bytes_written == self.bytes_to_write:
            self.transfer_completed()

        
    # the library manager has asked us to write a file to the hsm
    def write_to_hsm(self, ticket):
        Trace.log(e_errors.INFO, "WRITE_TO_HSM")
        self.setup_transfer(ticket, mode=WRITE)
        
    # the library manager has asked us to read a file from the hsm
    def read_from_hsm(self, ticket):
        Trace.log(e_errors.INFO,"READ FROM HSM")
        self.setup_transfer(ticket, mode=READ)

    def setup_transfer(self, ticket, mode):
        Trace.trace(10, "setup transfer")
        ##        pprint.pprint(ticket)
        if self.state not in (IDLE, HAVE_BOUND):
            Trace.log(e_errors.ERROR, "Not idle %s" %(state_name(self.state),))
            self.return_work_to_lm(ticket)
            return 0
        ### cgw - abstract this to a check_valid_filename method of the driver ?
        if self.config['driver'] == "NullDriver": 
            filename = ticket['wrapper'].get("pnfsFilename",'')
            if "NULL" not in string.split(filename,'/'):
                ticket['status']=(e_errors.USERERROR, "NULL not in PNFS path")
                self.send_client_done(ticket, e_errors.USERERROR, "NULL not in PNFS path")
                return 0
        self.reset()

        ticket['mover']={}
        ticket['mover'].update(self.config)
        ticket['mover']['device'] = "%s:%s" % (self.config['host'], self.config['device'])

        self.current_work_ticket = ticket
        self.control_socket, self.client_socket = self.connect_client()
        Trace.trace(10, "client connect %s %s" % (self.control_socket, self.client_socket))
        if not self.client_socket:
            ##XXX ENCP GONE
            return 0

        self.t0 = time.time()

        ##all groveling around in the ticket should be done here
        fc = ticket['fc']
        vc = ticket['vc']
        self.vol_info.update(vc)
        self.volume_family=vc['volume_family']
        delay = 0
        if ticket['encp'].has_key('delayed_dismount'):
            delay = 60 * int(ticket['encp']['delayed_dismount']) #XXX is this right? minutes?
                                                                  ##what does the flag really mean?
        self.delay = max(delay, self.default_dismount_delay)
        self.delay = min(self.delay, self.max_dismount_delay)
        self.fcc = file_clerk_client.FileClient(self.csc, bfid=0,
                                                server_address=fc['address'])
        self.vcc = volume_clerk_client.VolumeClerkClient(self.csc,
                                                         server_address=vc['address'])
        volume_label = fc['external_label']
        self.current_work_ticket = ticket
        self.vol_info.update(self.vcc.inquire_vol(volume_label))
        if self.vol_info['status'][0] != 'ok':
            return 0 #XXX NOTAPE
        
        self.buffer.set_blocksize(self.vol_info['blocksize'])
        
        self.wrapper_type = self.vol_info.get('wrapper')
        if self.wrapper_type is None:
            ##XXX hack - why is wrapper not coming in on the vc ticket?
            fam = (self.vol_info.get("volume_family") or
                   self.vol_info.get("file_family"))
            self.wrapper_type = string.split(fam,'.')[-1]
        try:
            self.wrapper = __import__(self.wrapper_type + '_wrapper')
        except ImportError, detail:
            Trace.log(e_errors.ERROR, "%s"%(detail,))
            self.wrapper = None
            
        client_filename = ticket['wrapper'].get('fullname','?')
        pnfs_filename = ticket['wrapper'].get('pnfsFilename', '?')

        self.mode = mode
        self.bytes_to_transfer = long(fc['size'])
        self.bytes_to_write = self.bytes_to_transfer
        self.bytes_to_read = self.bytes_to_transfer

        try:
            client_hostname = ticket['wrapper']['machine'][1]
        except KeyError:
            client_hostname = ''

        if client_hostname:
            client_filename = client_hostname + ":" + client_filename
            
        if self.mode == READ:
            self.files = (pnfs_filename, client_filename)
            self.target_location = cookie_to_long(fc['location_cookie'])
            self.buffer.header_size = None
        elif self.mode == WRITE:
            self.files = (client_filename, pnfs_filename)
            if self.wrapper:
                self.header, self.trailer = self.wrapper.headers(ticket['wrapper'])
            else:
                self.header = ''
                self.trailer = ''
            self.buffer.header_size = len(self.header)
            self.buffer.trailer_size = len(self.trailer)
            self.bytes_to_write = self.bytes_to_write + len(self.header) + len(self.trailer)
            self.target_location = None        

        if volume_label == self.current_volume: #no mount needed
            self.timer('mount_time')
            self.position_media(verify_label=0)
        else:
            self.run_in_thread('media_thread', self.mount_volume, args=(volume_label,),
                               after_function=self.position_media)

    def error(self, msg, err=e_errors.ERROR):
        self.last_error = (str(err), str(msg))
        Trace.log(e_errors.ERROR, str(msg)+ " state=ERROR")
        self.state = ERROR
        
    def position_media(self, verify_label=1):
        #At this point the media changer claims the correct volume is loaded; now position it
        label_tape = 0
        have_tape = 0
        for retry_open in range(3):
            Trace.trace(10, "position media")
            have_tape = self.tape_driver.open(self.device, self.mode, retry_count=10)
            self.tape_driver.set_mode(blocksize = 0)
            if have_tape == 1:
                break
            else:
                Trace.log(e_errors.INFO, "position media: rewind and retry")
                self.tape_driver.rewind()
        else:
            self.error("cannot open tape device for positioning")
            return
        self.state = SEEK  ##XXX start a timer here

        eod = self.vol_info['eod_cookie']
        if eod=='none':
            eod = None
        volume_label = self.current_volume

        if self.mode is WRITE and eod is None:
            verify_label = 0
            label_tape = 1
        
        if self.mode is WRITE:
            if self.target_location is None:
                self.target_location = eod
            if self.target_location != eod:
                Trace.log(e_errors.ERROR, "requested write at location %s, eod=%s" %
                          (self.target_location, eod))
                return 0 # Can only write at end of tape

            if label_tape:
                ## new tape, label it
                ##  need to safeguard against relabeling here
                status = self.tape_driver.verify_label(None)
                Trace.trace(10, "verify label returns %s" % (status,))
                if status[0] == e_errors.OK:
                    if status[1] == volume_label:
                        label_tape = 0
                    else:
                        Trace.log(e_errors.ERROR, "volume %s already labeled as %s" %
                                  (volume_label, status[1]))
                        self.transfer_failed(e_errors.WRITE_VOL1_WRONG, "%s should be %s"%
                                             (status[1], volume_label))
                        self.error(status[1], status[0])
                        ##XXX set volume noaccess? Eject it?
                        return 0
            if label_tape:
                self.tape_driver.rewind()
                vol1_label = 'VOL1'+ volume_label
                vol1_label = vol1_label+ (79-len(vol1_label))*' ' + '0'
                Trace.log(e_errors.INFO, "labeling new tape %s" % (volume_label,))
                self.tape_driver.write(vol1_label, 0, 80)
                self.tape_driver.writefm()
                eod = 1
                self.target_location = eod
                self.vol_info['eod_cookie'] = eod
                if self.driver_type == 'FTTDriver':
                    import ftt
                    stats = self.tape_driver.ftt.get_stats()
                    remaining = stats[ftt.REMAIN_TAPE]
                    if remaining is not None:
                        remaining = long(remaining)
                        self.vol_info['remaining_bytes'] = remaining * 1024L
                        ##XXX keep everything in KB?
                self.vcc.set_remaining_bytes(volume_label,
                                              self.vol_info['remaining_bytes'],
                                              self.vol_info['eod_cookie'])

        if verify_label:
            status = self.tape_driver.verify_label(volume_label, self.mode)
            if status[0] != e_errors.OK:
                self.transfer_failed(status[0], status[1])
                self.error(status[1], status[0])
                return 0
        location = cookie_to_long(self.target_location)
        self.run_in_thread('seek_thread', self.seek_to_location,
                           args = (location, self.mode==WRITE),
                           after_function=self.start_transfer)
        
        return 1
            
    def transfer_failed(self, exc=None, msg=None):
        Trace.log(e_errors.ERROR, "transfer failed %s %s" % (str(exc), str(msg)))

        ### XXX translate this to an e_errors code?
        self.last_error = str(exc), str(msg)

        if self.state == ERROR:
            Trace.log(e_errors.ERROR, "Mover already in ERROR state %s, state=ERROR" % (msg,))
            return

        ###XXX network errors should not count toward rd_err, wr_err
        if self.mode == WRITE:
            self.vcc.update_counts(self.current_volume, wr_err=1, wr_access=1)
        else:
            self.vcc.update_counts(self.current_volume, rd_err=1, rd_access=1)       

        self.transfers_failed = self.transfers_failed + 1
        self.timer('transfer_time')

        self.send_client_done(self.current_work_ticket, str(exc), str(msg))
        self.net_driver.close()

        if self.state == DRAINING:
            self.dismount_volume()
            self.state = OFFLINE
        else:
            self.state = HAVE_BOUND
            self.maybe_clean()
        now = time.time()
        self.dismount_time = now + self.delay
        self.update(state=ERROR, reset_timer=1)
        
        
    def transfer_completed(self):
        Trace.log(e_errors.INFO, "transfer complete, current_volume = %s, current_location = %s"%(
            self.current_volume, self.current_location))
        
        if self.mode == WRITE:
            self.vcc.update_counts(self.current_volume, wr_access=1)
        else:
            self.vcc.update_counts(self.current_volume, rd_access=1)
        self.transfers_completed = self.transfers_completed + 1
        self.timer('transfer_time')
        self.net_driver.close()
        self.current_location = self.tape_driver.tell()
        now = time.time()
        self.dismount_time = now + self.delay
        self.send_client_done(self.current_work_ticket, e_errors.OK)
        self.update(reset_timer=1)
        
        if self.state == DRAINING:
            self.dismount_volume()
            self.state = OFFLINE
        else:
            self.state = HAVE_BOUND
            self.maybe_clean()
        
    def maybe_clean(self):
        needs_cleaning = 0
        if self.driver_type == 'FTTDriver':
            ##XXX
            import ftt
            Trace.trace(25, "maybe_clean: open device to get tape statistics")
            have_tape = self.tape_driver.open(self.device, mode=0, retry_count=1)
            stats = self.tape_driver.ftt.get_stats()
            try:
                self.tape_driver.close()
            except:
                pass #XXX
            cleaning_bit = stats and stats[ftt.CLEANING_BIT]
            Trace.trace(25, "maybe_clean: got tape statistics, stats=%s, stats[CLEANING_BIT]=%s (%s)" % (
                stats, cleaning_bit, type(cleaning_bit)))

            if cleaning_bit and cleaning_bit != '0':
                needs_cleaning = 1

        if needs_cleaning:
            if not self.do_cleaning:
                Trace.log(e_errors.INFO, "cleaning bit set but automatic cleaning disabled")
                return
            Trace.log(e_errors.INFO, "initiating automatic cleaning")
            save_state = self.state
            if save_state == HAVE_BOUND:
                self.dismount_volume()
                save_state = IDLE
            self.state = CLEANING
            self.mcc.doCleaningCycle(self.config)
            self.state = save_state
            Trace.log(e_errors.INFO, "cleaning complete")
        needs_cleaning = 0
        
        
    def update_after_writing(self):
        previous_eod = cookie_to_long(self.vol_info['eod_cookie'])
        self.current_location = self.tape_driver.tell()
        if self.current_location <= previous_eod:
            Trace.log(e_errors.ERROR, " current location %s <= eod %s" %
                      (self.current_location, previous_eod))
            return 0
        
        remaining = self.vol_info['remaining_bytes']-self.bytes_written
        ## XXX make this a driver method
        if self.driver_type == 'FTTDriver':
            import ftt
            stats = self.tape_driver.ftt.get_stats()
            if stats[ftt.REMAIN_TAPE]:
                rt = stats[ftt.REMAIN_TAPE]
                if rt is not None:
                    rt = long(rt)
                    remaining = rt  * 1024L
        eod = loc_to_cookie(self.current_location)
        self.vol_info['eod_cookie'] = eod
        self.vol_info['remaining_bytes']=remaining
        sanity_cookie = (self.buffer.sanity_bytes,self.buffer.sanity_crc)
        complete_crc = self.buffer.complete_crc
        fc_ticket = {  'location_cookie': loc_to_cookie(self.last_seek),
                       'size': self.bytes_to_transfer,
                       'sanity_cookie': sanity_cookie,
                       'external_label': self.current_volume,
                       'complete_crc': complete_crc}
        ##  HACK:  store 0 to database if mover is NULL
        if self.config['driver']=='NullDriver':
            fc_ticket['complete_crc']=0L
            fc_ticket['sanity_cookie']=(self.buffer.sanity_bytes,0L)
        fcc_reply = self.fcc.new_bit_file({'work':"new_bit_file",
                                            'fc'  : fc_ticket
                                            })
        if fcc_reply['status'][0] != e_errors.OK:
            Trace.log(e_errors.ERROR,
                       "cannot assign new bfid")
            self.transfer_failed(e_errors.ERROR,"Cannot assign new bit file ID")
            #XXX exception?
            return 0
        ## HACK: restore crc's before replying to caller
        fc_ticket = fcc_reply['fc']
        fc_ticket['sanity_cookie'] = sanity_cookie
        fc_ticket['complete_crc'] = complete_crc 
        bfid = fc_ticket['bfid']
        self.current_work_ticket['fc'] = fc_ticket
        Trace.log(e_errors.INFO,"set remaining: %s %s %s" %(self.current_volume, remaining, eod))
        reply = self.vcc.set_remaining_bytes(self.current_volume, remaining, eod, bfid)
        self.vol_info.update(reply)
        self.vol_info.update(self.vcc.inquire_vol(self.current_volume))
        self.volume_status = (self.vol_info.get('system_inhibit',['Unknown', 'Unknown']),
                              self.vol_info.get('user_inhibit',['Unknown', 'Unknown']))
        return 1

    
    def malformed_ticket(self, ticket, expected_keys=None):
        msg = "Missing keys "
        if expected_keys is not None:
            msg = "%s %s"(msg, expected_keys)
        msg = "%s %s"%(msg, ticket)
        Trace.log(e_errors.ERROR, msg)

    def send_client_done(self, ticket, status, error_info=None):
        ticket['status'] = (status, error_info)
        try:
            callback.write_tcp_obj(self.control_socket, ticket)
        except:
            exc, detail, tb = sys.exc_info()
            Trace.log(e_errors.ERROR, "error in send_client_done: %s" % (detail,))
        self.control_socket.close()
        self.control_socket = None
        return
            
    def connect_client(self):
        Trace.trace(10, "connecting to client")
        # cgw - Should this thread out?
        try:
            ticket = self.current_work_ticket
            data_ip=self.config.get("data_ip",None)
            host, port, listen_socket = callback.get_callback(fixed_ip=data_ip)
            listen_socket.listen(4)
            ticket['mover']['callback_addr'] = (host,port) #client expects this

            control_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            Trace.trace(10, "connecting to %s" % (ticket['callback_addr'],))
            control_socket.connect(ticket['callback_addr'])
            Trace.trace(10, "connected")
            try:
                callback.write_tcp_obj(control_socket, ticket)
            except:
                exc, detail, tb = sys.exc_info()
                Trace.log(e_errors.ERROR,"error in connect_client_done: %s" % (detail,))
            # we expect a prompt call-back here
            Trace.trace(10, "select: listening for client callback")
            read_fds,write_fds,exc_fds=select.select([listen_socket],[],[],60) # one minute timeout
            Trace.trace(10, "select returned %s" % ((listen_socket in read_fds),))
            if listen_socket in read_fds:
                Trace.trace(10, "accepting client connection")
                client_socket, address = listen_socket.accept()
                listen_socket.close()
                self.net_driver.fdopen(client_socket)
                return control_socket, client_socket
            else:
                Trace.log(e_errors.INFO, "timeout on waiting for client connect")
                return None, None
        except:
            exc, msg, tb = sys.exc_info()
            Trace.log(e_errors.ERROR, "connect_client:  %s %s %s"%
                      (exc, msg, traceback.format_tb(tb)))
            return None, None 
    
    def format_lm_ticket(self, state=None, error_info=None, returned_work=None, error_source=None):
        status = e_errors.OK, None
        work = None
        if state is None:
            state = self.state
        if state is IDLE:
            work = "mover_idle"
        elif state in (HAVE_BOUND,):
            work = "mover_bound_volume"
        elif state in (ACTIVE, SEEK, DRAINING, CLEANING, MOUNT_WAIT, DISMOUNT_WAIT):
            work = "mover_busy"
            if error_info:
                status = error_info
        elif state in (ERROR, OFFLINE):
            work = "mover_error"  ## XXX If I'm offline should I send mover_error? I don't think so....
            if error_info is None:
                status = self.last_error
            else:
                status = error_info
        if work is None:
            Trace.log(e_errors.ERROR, "state: %s work: %s" % (state_name(state),work))

        if not status:
            status = e_errors.OK, None
            
        if type(status) != type(()) or len(status)!=2:
            Trace.log(e_errors.ERROR, "status should be 2-tuple, is %s" % (status,))
            status = (status, None)
            
        ticket =  {
            "mover":  self.name,
            "address": self.address,
            "external_label":  self.current_volume,
            "current_location": loc_to_cookie(self.current_location),
            "read_only" : 0, ###XXX todo: multiple drives on one scsi bus, write locking
            "returned_work": returned_work,
            "state": state_name(self.state),
            "status": status,
            "volume_family": self.volume_family,
            "volume_status": self.volume_status,
            "operation": mode_name(self.mode),
            "error_source": error_source,
            "work": work,
            }
        return ticket

    def run_in_thread(self, thread_name, function, args=(), after_function=None):
        thread = getattr(self, thread_name, None)
        for wait in range(5):
            if thread and thread.isAlive():
                Trace.trace(20, "thread %s is already running, waiting %s" % (thread_name, wait))
                time.sleep(1)
        if thread and thread.isAlive():
                Trace.log(e_errors.ERROR, "thread %s is already running" % (thread_name))
                return -1
        if after_function:
            args = args + (after_function,)
        thread = threading.Thread(group=None, target=function,
                                  name=thread_name, args=args, kwargs={})
        setattr(self, thread_name, thread)
        try:
            thread.start()
        except:
            exc, detail, tb = sys.exc_info()
            Trace.log(e_errors.ERROR, "starting thread %s: %s" % (thread_name, detail))
        return 0
    
    def dismount_volume(self, after_function=None):
        self.dismount_time = None
        prev_state = self.state
        self.state = DISMOUNT_WAIT
        if self.do_eject:
            have_tape = self.tape_driver.open(self.device, mode=0, retry_count=2)
            if have_tape == 1:
                ejected = self.tape_driver.eject()
                if ejected == -1:
                    self.error("Cannot eject tape")
            self.tape_driver.close()
        Trace.log(e_errors.INFO, "dismounting %s" %(self.current_volume,))
        self.last_volume = self.current_volume
        self.last_location = self.current_location

        if not self.vol_info.get('external_label'):
            if self.vcc:
                try:
                    v = self.vcc.inquire_vol(self.current_volume)
                    if type(v) is type({}):
                        self.vol_info.update(v)
                except:
                    exc, detail, tb = sys.exc_info()
                    Trace.log(e_errors.ERROR, "inquire volume for dismount: %s" % (detail,))
        if not self.vol_info.get('external_label'):
            if self.current_volume:
                self.vol_info['external_label'] = self.current_volume
            else:
                self.vol_info['external_label'] = "Unknown"

        if not self.vol_info.get('media_type'):
            self.vol_info['media_type'] = self.media_type #kludge

        mcc_reply = self.mcc.unloadvol(self.vol_info, self.name, self.mc_device)

        status = mcc_reply.get('status')
        if status and status[0]==e_errors.OK:
            self.current_volume = None
            if after_function:
                after_function()
            else:
                self.idle()
        ###XXX aml-specific hack! Media changer should provide a layer of abstraction
        ### on top of media changer error returns, but it doesn't  :-(
        elif status[-1] == "the drive did not contain an unloaded volume":
            self.idle()
        else:
            self.error(status[-1], status[0])
            

    def mount_volume(self, volume_label, after_function=None):
        self.dismount_time = None
        self.state = MOUNT_WAIT
        self.current_volume = volume_label
        
        Trace.log(e_errors.INFO, "mounting %s, after_function=%s" % (volume_label,after_function))
        self.timer('mount_time')
        
        mcc_reply = self.mcc.loadvol(self.vol_info, self.name, self.mc_device)
        status = mcc_reply.get('status')
        Trace.trace(10, 'mc replies %s' % (status,))

        if status and status[0] == e_errors.OK:
            if self.mount_delay:
                Trace.trace(25, "waiting %s seconds after mount"%(self.mount_delay,))
                time.sleep(self.mount_delay)
            if after_function:
                Trace.trace(10, "mount: calling after function")
                after_function()
        else: #Mount failure, attempt to recover
            self.last_error = status
            Trace.log(e_errors.ERROR, "mount %s: %s, dismounting" % (volume_label, status))
            self.state = DISMOUNT_WAIT
            self.transfer_failed(e_errors.MOUNTFAILED, 'mount failure %s' % (status,))
            self.dismount_volume(after_function=self.idle)
            
    def seek_to_location(self, location, eot_ok=0, after_function=None): #XXX is eot_ok needed?
        Trace.trace(10, "seeking to %s, after_function=%s"%(location,after_function))
        failed=0
        try:
            self.tape_driver.seek(location, eot_ok) #XXX is eot_ok needed?
        except:
            exc, detail, tb = sys.exc_info()
            self.transfer_failed(e_errors.ERROR, 'positioning error %s' % (detail,))
            failed=1
        self.timer('seek_time')
        self.current_location = self.tape_driver.tell()
        self.last_seek = self.current_location
        if after_function and not failed:
            Trace.trace(10, "seek calling after function %s" % (after_function,))
            after_function()

    def start_transfer(self):
        Trace.trace(10, "start transfer")
        #If we've gotten this far, we've mounted, positioned, and connected to the client.
        #Just start up the work threads and watch the show...
        self.state = ACTIVE
        if self.mode is WRITE:
            self.run_in_thread('net_thread', self.read_client)
            self.run_in_thread('tape_thread', self.write_tape)
        elif self.mode is READ:
            self.run_in_thread('tape_thread', self.read_tape)
            self.run_in_thread('net_thread', self.write_client)
        else:
            self.transfer_failed(e_errors.ERROR, "invalid mode %s" % (self.mode,))
                
    def status(self, ticket):
        now = time.time()
        status_info = (e_errors.OK, None)
        if self.state == ERROR:
            status_info = self.last_error
        tick = { 'status'       : status_info,
                 'drive_sn'     : self.config['serial_num'],
                 'drive_vendor' : self.config['vendor_id'],
                 'drive_id'     : self.config['product_id'],
                 #
                 'state'        : state_name(self.state),
                 'transfers_completed'     : self.transfers_completed,
                 'transfers_failed': self.transfers_failed,
                 'bytes_read'     : self.bytes_read,
                 'bytes_written'     : self.bytes_written,
                 'bytes_buffered' : self.buffer.nbytes(),
                 # from "work ticket"
                 'bytes_to_transfer': self.bytes_to_transfer,
                 'files'        : self.files,
                 'last_error': self.last_error,
                 'mode'         : mode_name(self.mode),
                 'current_volume': self.current_volume,
                 'current_location': self.current_location,
                 'last_volume' : self.last_volume,
                 'last_location': self.last_location,
                 'time_stamp'   : now,
                 'buffer_min': self.buffer.min_bytes,
                 'buffer_max': self.buffer.max_bytes,
                 'rate of network': self.net_driver.rates()[0],
                 'rate of tape': self.tape_driver.rates()[0],
                 }
        if self.state is HAVE_BOUND and self.dismount_time and self.dismount_time>now:
            tick['will dismount'] = 'in %.1f seconds' % (self.dismount_time - now)
            
        self.reply_to_caller(tick)
        return

    def timer(self, key):
        if not self.current_work_ticket:
            return
        ticket = self.current_work_ticket
        if not ticket.has_key('times'):
            ticket['times']={}
        now = time.time()
        ticket['times'][key] = now - self.t0
        self.t0 = now
    
    def lockfile_name(self):
        d=os.environ.get("ENSTORE_TMP","/tmp")
        return os.path.join(d, "mover_lock")
        
    def create_lockfile(self):
        filename=self.lockfile_name()
        try:
            f=open(filename,'w')
            f.write('locked\n')
            f.close()
        except (OSError, IOError):
            Trace.log(e_errors.ERROR, "Cannot write %s"%(filename,))
            
    def remove_lockfile(self):
        filename=self.lockfile_name()
        try:
            os.unlink(filename)
        except (OSError, IOError):
            Trace.log(e_errors.ERROR, "Cannot unlink %s"%(filename,))

    def check_lockfile(self):
        return os.path.exists(self.lockfile_name())
        
    def start_draining(self, ticket):       # put itself into draining state
        if self.state is ACTIVE:
            self.state = DRAINING
        elif self.state is IDLE:
            self.state = OFFLINE
        elif self.state is HAVE_BOUND:
            self.state = DRAINING # XXX CGW should dismount here. fix this
        self.create_lockfile()
        out_ticket = {'status':(e_errors.OK,None)}
        self.reply_to_caller(out_ticket)
        return

    def stop_draining(self, ticket):        # put itself into draining state
        if self.state != OFFLINE:
            out_ticket = {'status':("EPROTO","Not in draining state")}
            self.reply_to_caller(out_ticket)
            return
        out_ticket = {'status':(e_errors.OK,None)}
        self.reply_to_caller(out_ticket)
        self.remove_lockfile()
        self.idle()
        
    def clean_drive(self, ticket):
        save_state = self.state
        if self.state not in (IDLE, OFFLINE):
            ret = {'status':("EPROTO", "Cleaning not allowed in %s state" % (state_name(self.state)))}
        else:
            self.state = CLEANING
            ret = self.mcc.doCleaningCycle(self.config)
            self.state = save_state
        self.reply_to_caller(ret)
        

class MoverInterface(generic_server.GenericServerInterface):

    def __init__(self):
        # fill in the defaults for possible options
        generic_server.GenericServerInterface.__init__(self)

    #  define our specific help
    def parameters(self):
        return 'mover_name'

    # parse the options like normal but make sure we have a mover
    def parse_options(self):
        interface.Interface.parse_options(self)
        # bomb out if we don't have a mover
        if len(self.args) < 1 :
            self.missing_parameter(self.parameters())
            self.print_help(),
            os._exit(1)
        else:
            self.name = self.args[0]


if __name__ == '__main__':            

    if len(sys.argv)<2:
        sys.argv=["python", "null.mover"] #REMOVE cgw
    # get an interface, and parse the user input

    intf = MoverInterface()
    mover =  Mover((intf.config_host, intf.config_port), intf.name)
    mover.handle_generic_commands(intf)
    mover.start()
    
    while 1:
        try:
            mover.serve_forever()
        except SystemExit:
            Trace.log(e_errors.INFO, "mover %s exiting." % (mover.name,))
            os._exit(0)
            break
        except:
            try:
                exc, msg, tb = sys.exc_info()
                full_tb = traceback.format_exception(exc,msg,tb)
                for l in full_tb:
                    Trace.log(e_errors.ERROR, l[:-1], {}, "TRACEBACK")
                Trace.log(e_errors.INFO, "restarting after exception")
            except:
                pass

    Trace.log(e_errors.INFO, 'ERROR returned from serve_forever')
