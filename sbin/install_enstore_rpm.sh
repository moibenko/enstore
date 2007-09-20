#!/bin/sh
###############################################################################
#
# $Id$
#
###############################################################################

set -u  # force better programming and ability to use check for not set
if [ "${1:-}" = "-x" ] ; then set -xv; shift; fi
if [ "${1:-}" = "-q" ] ; then export quiet=1; shift; else quiet=0; fi
if [ "${1:-}" = "64" ] ; then export x_64="_x64"; shift; else x_64=""; fi
if [ "${1:-}" = "server" ] ; then export server=1; shift; else server=0; fi
if [ "${1:-}" = "fnal" ]; then export fnal=$1; shift; else fnal="";fi

echo "Installing enstore rpm and required products"
echo "This is a fermilab specific installation"
if [ "`whoami`" != 'root' ]
then
    echo You need to run this script as user "root"
    exit 1
fi

if [ -x /etc/rc.d/init.d/enstore-boot ]
then
    echo "stopping enstore"
    /etc/rc.d/init.d/enstore-boot stop
fi
if [ -x /etc/rc.d/init.d/monitor_server-boot ]
then
    /etc/rc.d/init.d/monitor_server-boot stop
fi


echo "Installing ftt"
rpm -U --force ftp://ssasrv1.fnal.gov/en/enstore_related/ftt-2.26-1.i386.rpm 
echo "Installing tcl"
yum install tcl
echo "Installing tk"
yum install tk
echo "Installing python"
rpm -U --force ftp://ssasrv1.fnal.gov/en/enstore_related/Python-enstore-1.0.0-3.i386.rpm
if [ "${fnal:-x}" = "fnal" ]
then
    echo "installing aci"
    rpm -U --force ftp://ssasrv1.fnal.gov/en/enstore_related/aci-3.1.2-1.i386.rpm
    echo "Installing enstore"
    rpm -Uvh --force ftp://ssasrv1/en/enstore_related/enstore-1.0.1-8.i386.rpm
    ENSTORE_DIR=`rpm -ql enstore | head -1`
else
    echo "Installing enstore"
    rpm -Uvh --force ftp://ssasrv1/en/enstore_related/enstore_sa-1.0.1-8.i386.rpm
    ENSTORE_DIR=`rpm -ql enstore_sa | head -1`
fi


$ENSTORE_DIR/external_distr/create_enstore_environment.sh $fnal
$ENSTORE_DIR/sbin/copy_farmlets.sh
if [ $server -eq 1 ]
then
    $ENSTORE_DIR/sbin/finish_server_install.sh
fi
