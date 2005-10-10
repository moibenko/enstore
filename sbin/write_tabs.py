#!/usr/bin/env python
###############################################################################
# $Author$
# $Date$
# $Id$
#
# This script is originally written by Alexander Moibenko. I just added
# more stuff to it (Dmitry Litvintsev 05/10)
# 
###############################################################################
import sys
import os
import string
import time
import configuration_client
import pg
import enstore_constants
import histogram

SELECT_STMT="select  to_char(date, 'YY-MM-DD HH:MM:SS'), total, should, not_yet, done from write_protect_summary order by date"
SELECT_STMT1="select date,total, should, not_yet, done from write_protect_summary where date(time) between date(%s%s%s) and date(%s%s%s) and mb_user_write != 0 order by date desc"

def showError(msg):
    sys.stderr.write("Error: " + msg)

def usage():
    print "Usage: %s  <file_family> "%(sys.argv[0],)
def main():
    intf  = configuration_client.ConfigurationClientInterface(user_mode=0)
    csc   = configuration_client.ConfigurationClient((intf.config_host, intf.config_port))

    acc = csc.get(enstore_constants.ACCOUNTING_SERVER)
    inq = csc.get('inquisitor')
    inq_host=inq.get('www_host').split('/')[2]

    db_server_name = acc.get('dbhost')
    db_name        = acc.get('dbname')
    db_port        = acc.get('dbport')

    name=db_server_name.split('.')[0]
    now_time    = time.time()
    Y, M, D, h, m, s, wd, jd, dst = time.localtime(now_time)
    now_time = time.mktime((Y, M, D, 0, 0, 0, wd, jd, dst))
    start_time  = now_time-30*3600*24-7*3600*24

    h  = histogram.Histogram1D("write_tabs_%s"%(name,),"Write tab states %s"%(name,),37,float(start_time),float(now_time))
    h1 = histogram.Histogram1D("write_tabs_not_done_%s"%(name,),"Write tab states %s"%(name,),37,float(start_time),float(now_time))
    h2 = histogram.Histogram1D("write_tabs_done_%s"%(name,),"Write tab states %s"%(name,),37,float(start_time),float(now_time))

    h.set_time_axis(True)
    h.set_profile(True)
    h.set_ylabel("# of tapes that should have write tabs ON")
    h.set_xlabel("Date (year-month-day)")

    h1.set_time_axis(True)
    h1.set_profile(True)
    h1.set_ylabel("# of tapes that  have write tabs OFF")
    h1.set_xlabel("Date (year-month-day)")

    h2.set_time_axis(True)
    h2.set_profile(True)
    h2.set_ylabel("# of tapes that should have write tabs ON")
    h2.set_xlabel("Date (year-month-day)")

    if db_port:
        db = pg.DB(host=db_server_name, dbname=db_name, port=db_port);
    else:
        db = pg.DB(host=db_server_name, dbname=db_name);

    res=db.query(SELECT_STMT)
    should = 0
    not_yet   = 0
    done  = 0 
    for row in res.getresult():
        if not row:
            continue
        h.fill(time.mktime(time.strptime(row[0],'%Y-%m-%d %H:%M:%S')),row[2])
        h1.fill(time.mktime(time.strptime(row[0],'%Y-%m-%d %H:%M:%S')),row[3])
        h2.fill(time.mktime(time.strptime(row[0],'%Y-%m-%d %H:%M:%S')),row[4])
        should  = row[2]
        not_yet = row[3]
        done    = row[4]
    db.close()

    h.set_line_color(2)
    h.set_line_width(20)
    h.set_marker_type("impulses")
    h.set_marker_text("ON")

    t = time.ctime(time.time())
    
    h.add_text("set label \"Plotted %s \" at graph .99,0 rotate font \"Helvetica,10\"\n"% (t,))
    h.add_text("set label \"Should %s, Done %s(%3.1f%%), Not Done %s.\" at graph .05,.90\n" % (should,done,100.*done/should,not_yet,))

    h1.set_line_color(1)
    h1.set_line_width(20)
    h1.set_marker_type("impulses")
    h1.set_marker_text("OFF")


    h2.set_line_color(2)
    h2.set_line_width(20)
    h2.set_marker_type("impulses")
    h2.set_marker_text("OFF")
    

    h.plot2(h1)
    
#    os.system("display %s.jpg&"%(h.get_name()))

    h2.set_time_axis(True)
    h2.set_profile(True)
    h2.set_logy(True)
    h2.set_ylabel("# of tapes flipped per day")
    h2.set_xlabel("Date (year-month-day)")
    h2.set_marker_text("")
    h2.add_text("set label \"Plotted %s \" at graph .99,0 rotate font \"Helvetica,10\"\n"% (t,))

    h2.plot_derivative()

#    os.system("display %s.jpg&"%(h2.get_name()))

    cmd = "source /home/enstore/gettkt; $ENSTORE_DIR/sbin/enrcp *.ps *.jpg %s:/fnal/ups/prd/www_pages/enstore/"%(inq_host,)
    os.system(cmd)

    
    sys.exit(0)

    
    
if __name__ == "__main__":
    main()
