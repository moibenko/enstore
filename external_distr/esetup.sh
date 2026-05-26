#!/usr/bin/sh
# this is to run to setup enstore environment

setup() {
    return 0 # do noting
}

# fakes ups function for products enstore, python and ftt for anything else uses ups
ups() {
    return # do noting
}
if [ "${ENSTORE_DIR:-x}" = "x" ];
then
	# this is a very trivial way to check if enstore is set
	# the usual location of enstore is /home/enstore
	e_home=`grep enstore /etc/passwd | cut -f6 -d\:`
	#e_dir=`rpm -ql enstore_sa | head -1`
	# if ENSTORE_HOME is defined execute setup-enstore in the user area
	user_home="${ENSTORE_HOME:-x}"
	if [ $user_home != "x" -a -f "${user_home}/site_specific/config/setup-enstore" ]; then
	#if [ "${ENSTORE_HOME:-x}" != "x" -a -f "${ENSTORE_HOME}/site_specific/config/setup-enstore" ]; then
	    source ${ENSTORE_HOME}/site_specific/config/setup-enstore
	    return 0
	fi
	# otherwise execute a common setup-enstore from enstore area
	if [ -f ${e_home}/site_specific/config/setup-enstore ]; then
	    source ${e_home}/site_specific/config/setup-enstore
	    return 0
	else
	    echo '****'
	    echo '**** Unable to initialize the Enstore environment'
	    echo '****'
	    return 1
	fi
fi

