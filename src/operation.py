#!/usr/bin/env python
"""
Schema

 Schema |       Name        |   Type   |  Owner  
--------+-------------------+----------+---------
 public | job               | table    | huangch
 public | job_definition    | table    | huangch
 public | job_definition_id | sequence | huangch
 public | job_id            | sequence | huangch
 public | object            | table    | huangch
 public | progress          | table    | huangch
 public | task              | table    | huangch
 public | task_id           | sequence | huangch

                                Table "public.job"
 Column  |            Type             |                Modifiers                                                                                 
---------+-----------------------------+------------------------------------------
 id      | integer                     | not null default nextval('job_id'::text)
 name    | character varying           | not null
 type    | integer                     | not null
 start   | timestamp without time zone | default now()
 finish  | timestamp without time zone |
 comment | character varying           |
 id2     | bigint                      | not null
Indexes:
    "job_pkey" PRIMARY KEY, btree (id)
    "job_id2_key" UNIQUE, btree (id2)
    "job_finish_idx" btree (finish)
    "job_name_idx" btree (name)
    "job_start_idx" btree ("start")
    "job_type_idx" btree ("type")
Foreign-key constraints:
    "job_type_fkey" FOREIGN KEY ("type") REFERENCES job_definition(id) ON UPDATE CASCADE ON DELETE CASCADE
 
                           Table "public.job_definition"
 Column  |       Type        |                      Modifiers                                                                                 
---------+-------------------+-----------------------------------------------------
 id      | integer           | not null default nextval('job_definition_id'::text)
 name    | character varying | not null
 tasks   | integer           |
 remarks | character varying |
Indexes:
    "job_definition_pkey" PRIMARY KEY, btree (id)
    "job_definition_name_idx" btree (name)
 
                            Table "public.task"
   Column   |       Type        |                 Modifiers
------------+-------------------+-------------------------------------------
 id         | integer           | not null default nextval('task_id'::text)
 seq        | integer           | not null
 job_type   | integer           | not null
 dsc        | character varying |
 action     | character varying |
 comment    | character varying |
 auto_start | character(1)      | default 'm'::bpchar
Indexes:
    "task_pkey" PRIMARY KEY, btree (seq, job_type)
Foreign-key constraints:
    "task_job_type_fkey" FOREIGN KEY (job_type) REFERENCES job_definition(id) ON UPDATE CASCADE ON DELETE CASCADE
 
                Table "public.progress"
 Column  |            Type             |   Modifiers
---------+-----------------------------+---------------
 job     | integer                     | not null
 task    | integer                     | not null
 start   | timestamp without time zone | default now()
 finish  | timestamp without time zone |
 comment | character varying           |
 args    | character varying           |
 result  | character varying           |
Indexes:
    "progress_job_idx" btree (job)
    "progress_start_idx" btree ("start")
Foreign-key constraints:
    "progress_job_fkey" FOREIGN KEY (job) REFERENCES job(id) ON UPDATE CASCADE ON DELETE CASCADE
 
         Table "public.object"
 Column |       Type        | Modifiers
--------+-------------------+-----------
 job    | integer           | not null
 object | character varying |
Indexes:
    "object_job_idx" btree (job)
    "object_object_idx" btree ("object")
Foreign-key constraints:
    "object_job_fkey" FOREIGN KEY (job) REFERENCES job(id) ON UPDATE CASCADE ON DELETE CASCADE
 

"""

import pg
import time
import pprint
import types
import sys

# timestamp2time(ts) -- convert "YYYY-MM-DD HH:MM:SS" to time 
def timestamp2time(s):
	if s == '1969-12-31 17:59:59':
		return -1
	else:
		# take care of daylight saving time
		tt = list(time.strptime(s, "%Y-%m-%d %H:%M:%S"))
		tt[-1] = -1
		return time.mktime(tuple(tt))

# time2timestamp(t) -- convert time to "YYYY-MM-DD HH:MM:SS"
def time2timestamp(t):
	return time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(t))

# DATABASEHOST = 'stkensrv6.fnal.gov'
DATABASEHOST = 'localhost'
DATABASEPORT = 5432;
DATABASENAME = 'operation'

# get_db() -- initialize a database connection
def get_db():
	return pg.DB(dbname = DATABASENAME, port = DATABASEPORT, host = DATABASEHOST)

# global db connection
db = get_db()

# create_job() -- generic job creation
def create_job(name, type, args, comment = ''):
	# check if any of the args are in open job
	problem_args = {}
	for i in args:
		q = "select job.id, job.name, job_definition.name as job_def, \
			job.start from job, job_definition, object \
			where \
				object.object = '%s' and \
				job.id = object.job and \
				job.finish is null and \
				job.type = job_definition.id;"%(i)
		res = db.query(q).dictresult()
		if res:
			problem_args[i] = res[0]

	if problem_args:
		for i in problem_args.keys():
			print "%s is already in unfinished job %d %s %s %s"%(
				i,
				problem_args[i]['id'],
				problem_args[i]['name'],
				problem_args[i]['job_def'],
				problem_args[i]['start'])
		return -1

	q = "insert into job (name, type, comment) \
		values ('%s', (select id from job_definition where \
				name = '%s'), '%s');"%(
		name, type, comment)
	db.query(q)
	# get job id
	q = "select id from job where name = '%s';"%(
		name)
	id = db.query(q).getresult()[0][0]
	for i in args:
		q = "insert into object values (%d, '%s');"%(id, i)
		db.query(q)
	return id

# get_job_by_name() -- from a name to find the job; name is unique
def get_job_by_name(name):
	q = "select * from job where name = '%s';"%(name)
	res = db.query(q).dictresult()
	if res:
		return retrieve_job(res[0])
	else:
		return None

# get+job_by_id() -- get_job_using internal id
def get_job_by_id(id):
	q = "select * from job where id = %d;"%(id)
	res = db.query(q).dictresult()
	if res:
		return retrieve_job(res[0])
	else:
		return None

# get_job_by_time() --get job using time frame
def get_job_by_time(after, before = None):
	if not before:	# default now()
		before = time2timestamp(time.time())
	if type(after) != types.StringType:
		after = time2timestamp(after)
	if type(before) != types.StringType:
		before = time2timestamp(before)
	q = "select * from job where start >= '%s' and start <= '%s' \
		order by start;"%(after, before)
	res = db.query(q).dictresult()
	if res:
		return retrieve_job(res[0])
	else:
		return None

# retrieve_job() -- get all related information of this job
def retrieve_job(job):
	# assemble its related objects
	q = "select * from object where job = %d order by object;"%(job['id'])
	object = []
	res = db.query(q).getresult()
	for j in res:
		object.append(j[1])
	job['object'] = object
	# list its related tasks
	q = "select * from job_definition where id = %d;"%(job['type'])
	job_definition = db.query(q).dictresult()[0]
	job['job_definition'] = job_definition
	q = "select * from task left outer join progress \
		on (progress.job = %d and task.id = progress.task) \
		where task.job_type = %d \
			order by seq;"%(job['id'], job['type'])
	job['task'] = db.query(q).dictresult()
	job['current'] = get_current_task(job['name'])
	job['next'] = get_next_task(job['name'])
	if job['finish']:
		job['status'] = 'finished'
	else:
		if job['current'] == 0:
			job['status'] = 'not_started'
		else:
			job['status'] = 'in_progress'
	return job

# get_job_tasks(name) -- show the tasks related to this job
def get_job_tasks(name):
	q = "select seq, dsc, action from task, job \
		where job.name = '%s' and job.type = task.job_type \
		order by seq;"%(id)
	return db.query(q).dictresult()

# start_job_task(job_name, task_id) -- start a task
def start_job_task(job_name, task_id, args=None, comment=None):
	if has_started(job_name, task_id):
		return "job %s task %d has already started"%(job_name, task_id)

	if args:
		args = "'%s'"%(args)
	else:
		args = "null"
	if comment:
		comment = "'%s'"%(comment)
	else:
		comment = "null"
	q = "insert into progress (job, task, comment, args) \
		values ((select id from job where name = '%s'), %d, %s, %s);"%(
			job_name, task_id, comment, args)
	res = db.query(q)

# finish_job_task(job_name, task_id) -- finish/close a task
def finish_job_task(job_name, task_id, comment=None, result=None):
	if not has_started(job_name, task_id):
		return "job %s task %d has not started"%(job_name, task_id)
	if has_finished(job_name, task_id):
		return "job %s task %d has lready finished"%(job_name, task_id)
	if result:
		result = "'%s'"%(string(result))
	else:
		result = "null"
	if comment:
		q = "update progress \
			set finish = now(), comment = '%s', \
				result = %s \
			where job = (select id from job where name = '%s') \
			and task = %d;"%(
			comment, result, job_name, task_id)
	else:
		q = "update progress \
			set finish = now(), result = %s \
			where job = (select id from job where name = '%s') \
			and task = %d"%(
				result, job_name, task_id)
	res = db.query(q)

# get_current_task(name) -- get current task
def get_current_task(name):
	q = "select case \
		when max(task) is null then 0 \
		else max(task) \
		end \
		from progress, job \
		where \
			job.name = '%s' and \
			progress.job = job.id and \
			progress.start is not null;"%(name)
	res = db.query(q).getresult()
	return res[0][0]

# get_next_task(name) -- get next task
def get_next_task(name):
	q = "select tasks from job, job_definition where \
		job.name = '%s' and \
		job.type = job_definition.id;"%(name)
	tasks = db.query(q).getresult()[0][0]
	ct = get_current_task(name)
	if ct == tasks:
		return 0
	else:
		return ct + 1

# has_finished(job, task) -- has task (job, task) finished?
def has_finished(job, task):
	q = "select p.finish from progress p, job j where \
		j.name = '%s' and \
		p.job = j.id and p.task = %d and finish is not null;"%(
		job, task)
	res = db.query(q).getresult()
	if not res:
		return False
	else:
		return True

# is_started(job, task) -- has task (job, task) started?
def has_started(job, task):
	q = "select p.start from progress p, job j where \
		j.name = '%s' and \
		p.job = j.id and p.task = %d and start is not null;"%(
		job, task)
	res = db.query(q).getresult()
	if not res:
		return False
	else:
		return True

# start_next_task(job) -- start next task
def start_next_task(job, args=None, comment=None):
	ct = get_current_task(job)
	if has_finished(job, ct):
		nt = get_next_task(job)
		if nt:
			start_job_task(job, nt, args, comment)

# finish_current_task(job) -- finish current task
def finish_current_task(job, comment, result):
	ct = get_current_task(job)
	if ct:
		finish_job_task(job, task, comment, result)

def create_write_protect_on_job(name, args, comment = ''):
	return create_job(name, 'WRITE_PROTECTION_TAB_ON', args, comment)

def create_write_protect_off_job(name, args, comment = ''):
	return create_job(name, 'WRITE_PROTECTION_TAB_OFF', args, comment)

# shell() -- interactive shell
def shell():
	print "interactive shell has not been implemented yet"
	return

# execute(args) -- execute args[0], args[1:]
def execute(args):
	n_args = len(args)
	if n_args < 1:
		return None

	cmd = args[0]

	if cmd == "list": # list all job
		if n_args < 2 or args[1] == 'all':
			q = "select job.id, job.name, \
				job_definition.name as job, start, \
				finish, comment \
				from job, job_definition where \
					job.type = job_definition.id \
				order by job.id;"
			return db.query(q)
		elif args[1] == 'open':
			q = "select job.id, job.name, \
				job_definition.name as job, start, \
				finish, comment \
				from job, job_definition where \
					job.type = job_definition.id and \
					finish is null \
				order by job.id;"
			return db.query(q)
		elif args[1] == 'closed' or args[1] == 'completed':
			q = "select job.id, job.name, \
				job_definition.name as job, start, \
				finish, comment \
				from job, job_definition where \
					job.type = job_definition.id and \
					not finish is null \
				order by job.id;"
			return db.query(q)
		else:
			or_stmt = "job.name = '%s' "%(args[1])
			for i in args[2:]:
				or_stmt = or_stmt + "or job.name = '%s' "%(i)
			q = "select job.id, job.name, \
				job_definition.name as job, start, \
				finish, comment \
				from job, job_definition where \
					job.type = job_definition.id \
					and (%s) \
				order by job.id;"%(or_stmt)
			return db.query(q)
	elif cmd == "show": # show a job
		for i in args[1:]:
			job = get_job_by_name(i)
			pprint.pprint(job)
	elif cmd == "create": # create job
		if args[1] == "write_protect_on":
			return create_write_protect_on_job(args[2], args[3:])
		elif args[1] == "write_protect_off":
			return create_write_protect_off_job(args[2], args[3:])
		else:
			return "don't know what to do"
	elif cmd == "current": # current task
		if len(args) > 1:
			for i in args[1:]:
				job = get_job_by_name(i)
				if not job:
					print "%s does not exist"%(i)
					continue
				if job['status'] == "not_started":
					print "%s has not started"%(i)
					continue
				q = "select d.name as desc, t.seq, \
					p.start, p.finish \
					from job j, job_definition d, \
						task t, progress p \
					where \
						p.job = %d and \
						p.task = %d and \
						j.type = d.id and \
						j.id = p.job;"%(
						job['id'], job['current'])
				ct = db.query(q).dictresult()[0]
				if ct['finish'] == None:
					ct['finish'] = ""
				print "%s %d %s %s - %s"%(
					i, ct['seq'], ct['desc'],
					ct['start'], ct['finish'])
						
	else:
		return "unknown command"


if __name__ == '__main__':

	if len(sys.argv) < 2:
		shell()
	else:
		res = execute(sys.argv[1:])
		if res:
			print res
