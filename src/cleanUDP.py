#!/usr/bin/env python
###############################################################################
# src/$RCSfile$   $Revision$
#

"""
	The purpose of this module is to provide a clean datagram
	interface for Enstore. By "clean" we mean that we try to
        provide a uniform interface on all platforms by masking specific
	errors.

	Specific errors that are masked:

	1) Linux ipv4 -- returning an error on the next UDP send or recieve
	when an ICMP port unreachable measage is recieved. The socket 
	implementation will return, then automaticallay clear ECONNREFUSED.
	To handle this, we transpearently retry self.retry_max times 


	Notice that the python socket is a primitive type in the 
	language, like file descriptors, and so is not available for 
	inheritance. therefore we have to pedantically code all the "methods".
	This implementaion does nto handle all patterns of optional 
	arguments.

	cleanUDP.select() must be used instead of select.select()

"""
import socket
import Trace
import errno
import time
import select

def Select (R, W, X, timeout) :

# we have an error under linux where we get an error, and
# r and x are set, but there is no data. If the erro ris a spurrious erro, 
# we must delete the object from all lists.
#

	Trace.trace (0, "{cleanUDP.Select")

	cleaned_r = []
	while 1 :
		t0 = time.time()
		r, w, x = select.select(R, W, X, timeout)
		timeout = timeout - (time.time() - t0)
		timeout = max (0, timeout)
		Trace.trace (1, "cleanUDP.Select: %s %s" % (r, cleaned_r))

		if r == cleaned_r :
			# all except FD's as the saem as not scrubbed
			# previously.
			Trace.trace (0, "}cleanUDP.Select")
			return r, w, x
		cleaned_r = []
		for obj in r :
			try :
				if obj.scrub() :
				        Trace.trace (0, "cleaned_r cleanUDP object")
					cleaned_r.append(obj)		
			except : 
				Trace.trace (0, "non clean UDP object")
				cleaned_r.append(obj)


class cleanUDP :

	retry_max = 10
	previous_sendto_address="N/A"
	this_sendto_address="N/A"

	def __init__(self, protocol, kind) :
		if kind != socket.SOCK_DGRAM :
			raise "mis-use of class cleanUDP"
		self.socket = socket.socket(protocol, kind)
		return
	
	def scrub(self) :
		self.socket.getsockopt(socket.SOL_SOCKET, socket.SO_ERROR)
		r, w, x = select.select([self], [], [self], 0)
		Trace.trace (20, "cleanUDP.scrub : %s %s %s" % (r, w, x))
		if r :
			return 1 # it's clean - there really is a read to do
		return 0 # it went away - just the icmp message under A. Cox's linux implementation

	def accept(self) : 
		return self.socket.accept()
	def bind(self, address) : 
		return self.socket.bind(address)
	def close(self) : 
		retval =  self.socket.close()
		self.socket = None
		return retval
	def connect(self, address) : 
		return self.socket.bind(address)
	def fileno(self) : 
		return self.socket.fileno()
	def getpeername(self) : 
		return self.socket.getpeername()
	def getsockname(self) : 
		return self.socket.getscokname()
	def getsockopt(self, level, optname) :
		return self.socket.getsockopt(level, optname)
	def listen(self, backlog) : 
		return self.socket.listen(backlog)
	def makefile(self) : 
		return self.socket.makefile()
	def recv(self, bufsize) : 
		return self.socket.recv(bufsize)

	# Mitigate case 1 -- ECONNREFUSED from previous sendto
	def recvfrom(self, bufsize) :
		for n in range(0, self.retry_max - 1) :
			try:
				return self.socket.recvfrom(bufsize)
			except socket.error:
				self.logerror("recvfrom", n)
		return self.socket.recvfrom(bufsize)


	def send(self, string) : 
		return self.socket.send(string)

	# Mitigate case 1 -- ECONNREFUSED from previous sendto
	def sendto(self, string, address) : 
		self.previous_sendto_address = self.this_sendto_address
		self.this_sendto_address = address

		for n in range(0, self.retry_max - 1) :
			try:
				Trace.trace (0, "about to sendto")
				return self.socket.sendto(string, address)
			except socket.error:
				self.logerror("sendto", n)
		return self.socket.sendto(string, address)
		
	def setblocking(self, flag) :
		return self.socket.setblocking(flag)
	def setsockopt(self, level, optname, value) : 
		return self.socket.setsockopt(level, optname, value)
	def shutdown(self, how) :
		return self.socket.shutdown(how)


	def logerror(self, sendto_or_recvfrom, try_number) :
		badsockerrno = self.socket.getsockopt(
				socket.SOL_SOCKET,socket.SO_ERROR)
		try :
			badsocktext = repr(errno.errorcode[badsockerrno])
		except:
			badsocktext = repr(badsockerrno)
		etext = "cleanUDP %s try %d %s failed on %s last %s" % (
			  sendto_or_recvfrom, try_number,
			  badsocktext, self.this_sendto_address,
			  self.previous_sendto_address)

		Trace.trace(0, etext)
		# self.enprint(etext)

if __name__ == "__main__" :
	sout = cleanUDP(socket.AF_INET, socket.SOCK_DGRAM)
	sout.bind(('localhost',303030))
	# on linux, should see one retry from the following.

	sout.sendto("all dogs have fleas", ('localhost', 303031))	
	r, w, x = select.select([sout],[sout],[sout], 1.0)
	if not x and not r and w:
		print "expected select.select behavoir on non-linux" 
	elif x and r and w:
		print "expected select.select behavior on linux, pre 2.2 kernel"
	elif not x and r and w:
		print "expected select.select behavior on linux, post 2.2 kernel"
	else:
		print "***unexpected  behavior on _any_ platform"
	r, w, x = Select([sout],[sout],[sout],1.0)

	if not r and not x :
		print "expected behavior"
	else :
		print "***unexpected behavior"

	sout.sendto("all dogs have fleas", ('localhost', 303031))
	sin = cleanUDP(socket.AF_INET, socket.SOCK_DGRAM)
	sin.bind(('localhost',303031))
	sout.sendto("Expected behavior", ('localhost', 303031))
	print sin.recvfrom(1000)
