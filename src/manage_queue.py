# manage the pending Library Managerwork queue
import time
import db
import Trace
import e_errors

class LM_Queue:

    def __init__(self, db_dir):
	self.dict = db.DbTable("pending_queue", db_dir, None, None, 0)
	self.queue=[]
	self.queue_ptr=0

    # resotre queue from DB
    def restore_queue(self):
	self.dict.cursor("open")
	key,value=self.dict.cursor("first")
	while key:
	    self.queue.append(value)
            Trace.log(e_errors.INFO, "restoring LM pending work %s "%(value,))
	    key,value=self.dict.cursor("next")
	self.dict.cursor("close")

    # return the priority of a ticket
    def priority(self,ticket):
	if ticket["encp"]["adminpri"] >= 0:
	    return ticket["encp"]["adminpri"]
	p = ticket["encp"]["basepri"]
	deltas=0
	if ticket["encp"]["agetime"] > 0:
	    # deltas is the number of delta time periods 
	    deltas=int(time.time()-ticket["times"]["job_queued"])/60/ticket["encp"]["agetime"]
	    p=p + ticket["encp"]["delpri"]*deltas
	ticket["encp"]["curpri"]=p
	return p
   
    # A call back for sort, highest priority should be first.
    def compare_priority(self,t1,t2):
	if t1["encp"]["curpri"] < t2["encp"]["curpri"]:
	    return 1
	if t1["encp"]["curpri"] > t2["encp"]["curpri"]:
	    return -1
	# if priority is equal, then time in rules
	if t1["times"]["t0"] > t2["times"]["t0"]:
	    return 1
	elif t1["times"]["t0"] == t2["times"]["t0"]:
	    return 0
	return -1
   
    # A call back for sort, highest file location should be first.
    def compare_location(self,t1,t2):
	# compare location is not appliable for write requests
	if t1["work"] == "write_to_hsm" or t2["work"] == "write_to_hsm":
	    return 0
	if not (t1["fc"].has_key("external_label") and
		t2["fc"].has_key("external_label")):
	    return 0
	if t1["fc"]["external_label"] == t2["fc"]["external_label"]:
	    if t1["fc"]["location_cookie"] > t2["fc"]["location_cookie"]:
		return 1
	    if t1["fc"]["location_cookie"] < t2["fc"]["location_cookie"]:
		return -1
	return -1
   
    # Add work to the end of the set of jobs
    def insert_job(self,ticket):
        if ticket['work'] == 'write_to_hsm':
            output_file_name = ticket["wrapper"]["pnfsFilename"]
        else: output_file_name = None
	# see if there is a job with this id in the queueu
	w,status = self.find_job(ticket["unique_id"], output_file_name)
	if not w:
	    ticket['times']['job_queued'] = time.time()
	    ticket['at_the_top'] = 0
	    self.queue.append(ticket)
	    self.dict[ticket["unique_id"]] = ticket
            ret = None
        else: ret = status
        return ret
    
    # Remove a ticket 
    def delete_job(self,ticket):
	for w in self.queue:
	    if w.has_key("unique_id") and ticket.has_key("unique_id"):
		if w["unique_id"] == ticket["unique_id"]:
		    if ticket['times'].has_key('job_queued'):
			ticket['times']['in_queue'] = time.time() - \
						      ticket['times']['job_queued']
			del(ticket['times']['job_queued'])
		    else:
			ticket['times']['in_queue'] = 0
		    self.queue.remove(w)
		    #print "deleted",w["fc"]["location_cookie"]
		    del self.dict[w["unique_id"]]
		    return

    # Find a job 
    def find_job(self,id,output_file_name=None):
	for w in self.queue:
	    if w["unique_id"] == id:
		return w,e_errors.OK
            if (output_file_name and
                output_file_name == w["wrapper"]['pnfsFilename']):
                return w,e_errors.INPROGRESS
	return None, None

    # change a job priority
    def change_pri(self,id, pri):
	# priority cannot be less than 0
	if pri < 0:
	    return None
	for w in self.queue:
	    if w["unique_id"] == id:
		w["encp"]["curpri"] = pri
		w["encp"]["basepri"] = pri
		return w
	return None

    # Make a prioritized list of the jobs, and return the top one
    # This is done by calculating current priority of each job and sorting
    def get_init(self):
	self.queue_ptr=0
	if len(self.queue) == 0:				# There are no jobs
	    return
	for w in self.queue:
	    w["encp"]["curpri"] = self.priority(w)
	self.queue.sort(self.compare_priority)		# Sort the jobs by priority
	# this is for test
	#if self.queue[0]["fc"].has_key("location_cookie"):
	#    print "LC0", self.queue[0]["fc"]["location_cookie"]
        self.queue[0]['at_the_top'] = self.queue[0]['at_the_top'] + 1
	return self.queue[0]				# Return the top one

    # Sort jobs by location for the given volume and return the top one
    def get_init_by_location(self):
	self.queue_ptr=0
	if len(self.queue) == 0:			    # There are no jobs
	    return
	self.queue.sort(self.compare_location)	    # Sort the jobs by location
	# this is for test
	#if self.queue[0]["fc"].has_key("location_cookie"):
	#    print "LC0", self.queue[0]["fc"]["location_cookie"]
        self.queue[0]['at_the_top'] = self.queue[0]['at_the_top'] + 1
	return self.queue[0]			    # Return the top one

    # Return the next highest priority job.  get_init must be called first
    def get_next(self):
	self.queue_ptr=self.queue_ptr+1
        Trace.trace(12,"get_next: len %s ptr %s"%(repr(len(self.queue)),repr(self.queue_ptr)))
	if len(self.queue) > self.queue_ptr:
	    self.queue[self.queue_ptr]['at_the_top'] = \
	      self.queue[self.queue_ptr]['at_the_top'] + 1
	    # this is for test
	    #if self.queue[self.queue_ptr]["fc"].has_key("location_cookie"):
	    #  print "LC", self.queue[self.queue_ptr]["fc"]["location_cookie"]
	    return self.queue[self.queue_ptr]
	return

    # Get next job for the given volume, note that get_init_by_location must be
    # before calling this function
    def get_next_for_this_volume(self, v):
	for w in self.queue:
	    if w["work"] == "read_from_hsm":
		if w['vc']['external_label'] == v["external_label"]:
		    if w['fc']['location_cookie'] >= v["current_location"]:
			w['at_the_top'] = w['at_the_top']+1
			break
	else:
	    # no match has been found, return first for this volume
	    for w in self.queue:
                if (w['vc'].has_key('external_label') and
                    w['vc']['external_label'] == v["external_label"]):
                        w['at_the_top'] = w['at_the_top']+1
                        w['status'] = v['status']
                        break
	    else: return None 
	# this is for test
	#if w["fc"].has_key("location_cookie"):
	#    print "LC1", w["fc"]["location_cookie"]
	return w

      

    # return the entire sorted queue with current priorities for reporting
    def get_queue(self):
	for w in self.queue:
	    w["encp"]["curpri"] = self.priority(w)
	self.queue.sort(self.compare_priority)
	return self.queue

if __name__ == "__main__":
  import pprint
  pending_work = LM_Queue()
  t1={}
  t1["encp"]={}
  t1["times"]={}
  t1["unique_id"]=1
  t1["encp"]["basepri"]=100
  t1["encp"]["adminpri"]=-1
  t1["encp"]["delpri"]=100
  t1["encp"]["agetime"]=1
  t1["times"]["t0"]=time.time()
  pending_work.insert_job(t1)

  t2={}
  t2["encp"]={}
  t2["times"]={}
  t2["unique_id"]=2
  t2["encp"]["basepri"]=200
  t2["encp"]["adminpri"]=-1
  t2["encp"]["delpri"]=125
  t2["encp"]["agetime"]=2
  t2["times"]["t0"]=time.time()
  pending_work.insert_job(t2)

  t3={}
  t3["encp"]={}
  t3["times"]={}
  t3["unique_id"]=3
  t3["encp"]["basepri"]=300
  t3["encp"]["adminpri"]=-1
  t3["encp"]["delpri"]=0
  t3["encp"]["agetime"]=0
  t3["times"]["t0"]=time.time()
  pending_work.insert_job(t3)
  while 1:
    print pending_work.get_queue()
    time.sleep(10)
  n=10
  while n:
    w=pending_work.get_init()
    print w["encp"]["pri"]
    while w:
      w=pending_work.get_next()
    time.sleep(30)
    n=n-1
  print "delete t1"
  pending_work.delete_job(t1)
# get the whole list of jobs
  print "get_queue"
  pprint.pprint(pending_work.get_queue())
