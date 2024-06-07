#!/usr/bin/env python
###############################################################################
#
# $Id$
#
###############################################################################

# system imports
from __future__ import print_function
from builtins import str
import sys
import os
import stat

# enstore modules
import enstore_functions2
import configuration_client
import e_errors


def copy_it(src, dst):
    crontab = os.path.basename(src)

    # Verify the source file exists.
    if not os.path.exists(src):
        sys.stderr.write("%s does not exist.\n" % (src,))
        return 1

    # Don't clobber a good file.  Make sure that the src is newer
    # before overwriting.
    if os.path.exists(dst) and os.path.getmtime(src) <= os.path.getmtime(dst):
        sys.stderr.write("%s already exists.\n" % (crontab,))
        return 0

    print("Installing crontab:", crontab)

    try:
        # it is very important that we copy with the mtime of the source
        sf = open(src, "r")
        df = open(dst, "w")

        data = sf.readlines()
        df.writelines(data)
        print("Copied %s to %s." % (src, dst))

    except (OSError, IOError) as msg:
        sys.stderr.write("%s\n" % (str(msg),))
        return 1

    try:
        src_stat = os.stat(src)
    except (OSError, IOError) as msg:
        sys.stderr.write("stat:  %s\n" % (str(msg),))
        return 1

    try:
        os.utime(dst, (src_stat[stat.ST_ATIME], src_stat[stat.ST_MTIME]))
    except (OSError, IOError) as msg:
        sys.stderr.write("utime:  %s\n" % (str(msg),))
        return 1

    try:
        os.chmod(dst, stat.S_IRUSR | stat.S_IWUSR |
                 stat.S_IRGRP | stat.S_IROTH)
    except (OSError, IOError) as msg:
        sys.stderr.write("chmod: %s\n" % (str(msg),))
        return 1

    try:
        os.chown(dst, 0, 0)
    except (OSError, IOError) as msg:
        sys.stderr.write("chown: %s\n" % (str(msg),))
        return 1

    return 0


def delete_it(target):
    crontab = os.path.basename(target)

    if os.path.exists(target):
        print("Uninstalling crontab:", crontab)
        try:
            os.remove(target)
        except (OSError, IOError) as msg:
            sys.stderr.write("%s\n" % (str(msg),))
            return 1

    return 0


if __name__ == '__main__':

    # Verify we are on Linux.
    if os.uname()[0] != "Linux":
        sys.stderr.write("Only supported on Linux.\n")
        sys.exit(1)

    # Verify we are user root.
    if os.geteuid() != 0:
        sys.stderr.write("Must be user root.\n")
        sys.exit(1)

    # Verify we have a source directory.
    try:
        CRONJOB_SRC_DIR = os.path.join(os.environ['ENSTORE_DIR'], "crontabs")
        if not os.path.isdir(CRONJOB_SRC_DIR):
            sys.stderr.write("%s does not exist.\n" % (CRONJOB_SRC_DIR,))
            sys.exit(1)
    except KeyError:
        sys.stderr.write("$ENSTORE_DIR not defined.\n")
        sys.exit(1)

    # Verify we have a destination directory.
    CRONJOB_DST_DIR = "/etc/cron.d"
    if not os.path.isdir(CRONJOB_DST_DIR):
        # /etc/cron.d is a Linux specific directory.
        sys.stderr.write("/etc/cron.d does not exist.\n")
        sys.exit(1)

    # Get the cronjob mapping from the configuration server.
    config_host = enstore_functions2.default_host()
    config_port = enstore_functions2.default_port()
    csc = configuration_client.ConfigurationClient((config_host, config_port))
    config_dict = csc.dump_and_save(timeout=5, retry=2)
    if not e_errors.is_ok(config_dict):
        print("configuration_server is not responding ... ")
        print("Get configuration from local file: %s" %
              (os.environ['ENSTORE_CONFIG_FILE'],))
        config_dict = configuration_client.configdict_from_file()

    cronjobs_dict = config_dict.get("crontabs", None)
    if cronjobs_dict is None:
        sys.stderr.write("No crontabs section defined in configuration.\n")
        sys.exit(1)

    # Reomve the status from the ticket.
    if 'status' in cronjobs_dict:
        del cronjobs_dict['status']

    installed_crons = []
    rtn = 0  # exit status return value
    for (configuration_key, cron_info) in list(cronjobs_dict.items()):
        # Determine the host the cronjob should run on.
        use_host = None
        config_info = config_dict.get(configuration_key, {})
        if config_info:
            if 'host' in config_info:
                use_host = config_info['host']
            elif 'hostip' in config_info:
                use_host = config_info['hostip']
        # The first two if/elifs look at the just obtained confg information.
        #  The following elif looks at the host entry in the crontab section
        #  obtained earlier.
        if use_host is None and 'host' in cron_info:
            use_host = cron_info['host']

        if enstore_functions2.is_on_host(use_host):
            for cron in cron_info['cronfiles']:
                src = os.path.join(CRONJOB_SRC_DIR, cron)
                dst = os.path.join(CRONJOB_DST_DIR, cron)
                rtn = rtn + copy_it(src, dst)

                # Rememember the crons that should be installed on this
                # node.  We will use this list to prevent them from being
                # deleted when we look for crontab files that have totally
                # been removed from the Enstore configuration.
                installed_crons.append(cron)
        else:
            for cron in cron_info['cronfiles']:
                dst = os.path.join(CRONJOB_DST_DIR, cron)
                rtn = rtn + delete_it(dst)

    # There is one more situation to consider.  If a cronjob is totally
    # removed from the configuration, we need a way to distinguish these
    # crons from other system installed crons.  The goal is to only remove
    # the obsolete enstore crons while leaving the system installed crons
    # in place.
    #
    # Now loop through the crons and remove any that are not configured
    # for this Enstore system and exist in the crontab source directory.
    for cron in os.listdir(CRONJOB_DST_DIR):
        if cron in os.listdir(CRONJOB_SRC_DIR) and cron not in installed_crons:
            dst = os.path.join(CRONJOB_DST_DIR, cron)
            rtn = delete_it(dst)

    sys.exit(rtn)
