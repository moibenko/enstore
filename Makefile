SHELL=/bin/sh

CP=cp -rp
MV=mv
RM=rm -rf

# need a robust way of finding freeze, especially for non-kits version of python

ENCP_TOP_DIR=$(ENSTORE_INSTALL_DIR)
ENCP_BIN_DIR=$(ENCP_TOP_DIR)/bin

ENSTORE_TOP_DIR=$(ENSTORE_INSTALL_DIR)
#ENSTORE_TARGET_DIR=$(ENSTORE_TOP_DIR)/enstore
ENSTORE_TARGET_DIR=$(ENSTORE_TOP_DIR)
ENSTORE_BIN_DIR=$(ENSTORE_TARGET_DIR)/bin
ENSTORE_TARGET_DCACHE=$(ENSTORE_TOP_DIR)/dcache
ENSTORE_BIN_DCACHE=$(ENSTORE_TARGET_DCACHE)/bin

OSV=`uname -s r`

# just for testing
setenvs:
	echo "uname =" `uname`
	echo "LDFLAGS2 =" $(LDFLAGS2)

all:
	@echo nothing to build

clean:
	@ $(ENSTORE_DIR)/bin/enstoreClean
	rm -f *.pyc encp
	- rm -rf build
	- rm -rf dist
	- rm -f *.spec spec_list
	-rm -rf specs
	- $(RM) $(ENSTORE_TARGET_DIR)

### The following groupings for for building the client side programs
### intended for release to the general public.
###
### The two commands of interest are "make encp" and "make encp_for_dcache".

pre_encp_cmd:
	(cd $(ENSTORE_DIR)/modules; make all)

encp_cmd:
	pyinstaller pyinstaller/encp_user.spec
	$(CP) dist/encp_user	$(ENCP_BIN_DIR)/encp
	$(RM) dist/encp_user
	pyinstaller pyinstaller/monitor_client.spec
	$(CP) dist/monitor_client    $(ENCP_BIN_DIR)
	$(RM) dist/monitor_client

post_encp_cmd:
	$(CP) $(ENSTORE_DIR)/modules/ddencp		$(ENCP_BIN_DIR)/
	$(CP) $(ENSTORE_DIR)/modules/ecrc		$(ENCP_BIN_DIR)/
	$(CP) $(ENSTORE_DIR)/modules/enroute2		$(ENCP_BIN_DIR)/
	$(CP) $(ENSTORE_DIR)/sbin/EPS                   $(ENCP_BIN_DIR)/
	chmod -R ug+rw $(ENCP_BIN_DIR)/

post_encp_cmd_for_dcache:
	$(CP) $(ENSTORE_DIR)/modules/ddencp             $(ENSTORE_BIN_DCACHE)/
	$(CP) $(ENSTORE_DIR)/modules/ecrc               $(ENSTORE_BIN_DCACHE)/
	$(CP) $(ENSTORE_DIR)/modules/enroute2           $(ENSTORE_BIN_DCACHE)/
	$(CP) $(ENSTORE_DIR)/sbin/EPS                   $(ENSTORE_BIN_DCACHE)/
	$(CP) $(ENSTORE_DIR)/dcache-deploy		$(ENSTORE_TARGET_DCACHE)
	chmod -R ug+rw $(ENSTORE_BIN_DCACHE)/

enstore_cmd:
	pyinstaller pyinstaller/enstore_user.spec
	$(CP) dist/enstore_user      $(ENCP_BIN_DIR)/enstore
	$(RM) dist/enstore_user

enstore_cmd_for_dcache:
	pyinstaller pyinstaller/enstore_user2.spec
	if [ ! -d $(ENSTORE_BIN_DCACHE) ]; then \
                mkdir -p $(ENSTORE_BIN_DCACHE); \
        fi

	$(CP) dist/enstore_user2      $(ENSTORE_BIN_DCACHE)/enstore
	$(RM) dist/enstore_user2

ensync_cmd_for_dcache:
	pyinstaller pyinstaller/ensync_user.spec
	$(CP) dist/ensync_user      $(ENSTORE_BIN_DCACHE)/ensync
	$(RM) dist/ensync_user


enmv_cmd_for_dcache:
	pyinstaller pyinstaller/enmv_user.spec
	$(CP) dist/enmv_user      $(ENSTORE_BIN_DCACHE)/enmv
	$(RM) dist/enmv_user

entv:
	(cd $(ENSTORE_DIR)/modules; make all mouse_move autologinenstore)
	pyinstaller pyinstaller/entv.spec
	cp dist/entv $(ENSTORE_BIN_DIR)/
	$(RM) dist/entv

encp: pre_encp_cmd encp_cmd enstore_cmd ensync_cmd enmv_cmd post_encp_cmd

encp_for_dcache: pre_encp_cmd encp_cmd_for_dcache enstore_cmd_for_dcache ensync_cmd_for_dcache enmv_cmd_for_dcache post_encp_cmd_for_dcache

### The following groupings for for building the server side programs
### intended for use by the Enstore administrators.
###
### The command of interest is "make enstore".

pre_enstore:
	(cd $(ENSTORE_DIR)/modules; make all)
	(cd $(ENSTORE_DIR)/sbin; make clean; make all)
	(cd $(ENSTORE_DIR)/tools; make clean; make all)
	mkdir -p $(ENSTORE_BIN_DIR)
	mkdir -p $(ENSTORE_TARGET_DIR)/sbin
	mkdir -p $(ENSTORE_TARGET_DIR)/etc
	mkdir -p $(ENSTORE_TARGET_DIR)/www/cgi-bin
	mkdir -p $(ENSTORE_TARGET_DIR)/crontabs
	mkdir -p $(ENSTORE_TARGET_DIR)/external_distr
	(cd $(ENSTORE_DIR)/bin; make clean; make all)
	(cd $(ENSTORE_DIR)/external_distr; make clean; make all)

post_enstore: install_enstore
	$(MV) $(ENSTORE_BIN_DIR)/encp_admin   $(ENSTORE_BIN_DIR)/encp
	$(MV) $(ENSTORE_BIN_DIR)/enstore_admin $(ENSTORE_BIN_DIR)/enstore
	$(MV) $(ENSTORE_BIN_DIR)/ensync_admin $(ENSTORE_BIN_DIR)/ensync
	$(MV) $(ENSTORE_BIN_DIR)/enmv_admin   $(ENSTORE_BIN_DIR)/enmv
	$(MV) $(ENSTORE_BIN_DIR)/migrate_chimera   $(ENSTORE_BIN_DIR)/migrate
	$(MV) $(ENSTORE_BIN_DIR)/duplicate_chimera   $(ENSTORE_BIN_DIR)/duplicate

	$(CP) $(ENSTORE_DIR)/modules/enroute2		$(ENSTORE_BIN_DIR)
	$(CP) $(ENSTORE_DIR)/modules/ddencp		$(ENSTORE_BIN_DIR)
	$(CP) $(ENSTORE_DIR)/modules/ecrc		$(ENSTORE_BIN_DIR)

install_enstore:
	$(CP) $(ENSTORE_DIR)/etc/* 		$(ENSTORE_TARGET_DIR)/etc/
	$(CP) $(ENSTORE_DIR)/www/* 			$(ENSTORE_TARGET_DIR)/www/
	$(CP) `ls -1dp $(ENSTORE_DIR)/crontabs/* | egrep -v "CVS"` 	$(ENSTORE_TARGET_DIR)/crontabs/

	$(CP) $(ENSTORE_DIR)/external_distr		$(ENSTORE_TARGET_DIR)
	$(CP) $(ENSTORE_DIR)/bin/en_check		$(ENSTORE_BIN_DIR)
#Why are these two in $ENSTORE_DIR/bin?
	$(CP) $(ENSTORE_DIR)/bin/enstore-boot		$(ENSTORE_BIN_DIR)
	$(CP) $(ENSTORE_DIR)/bin/monitor_server-boot	$(ENSTORE_BIN_DIR)
	$(CP) $(ENSTORE_DIR)/bin/pidkill*    $(ENSTORE_BIN_DIR)


#These are the list breakdowns.
SERVER_LIST=configuration_server log_server event_relay library_manager media_changer mover udp_server
SERVER_HTMLGEN_LIST=alarm_server inquisitor ratekeeper monitor_server web_server
SERVER_SQL_LIST=file_clerk volume_clerk info_server accounting_server drivestat_server
SERVER_SFA_LIST=dispatcher lm_director
#mover media_changer
MISC_LIST=get_cron_title udp_client
CRON_LIST=plotter_main summary_plots log_trans_fail recent_files_on_tape inventory plotter fill_slot_usage \
enstore_system_html make_ingest_rates_html_page get_total_bytes_counter html_main delfile_chimera \
checkdb_PITR enstore_make_plot_page acc_daily_summary

CGI_SCRIPTS=enstore_alarm_cgi enstore_alarm_search_cgi enstore_file_listing_cgi \
enstore_log_file_search_cgi enstore_recent_files_on_tape_cgi \
enstore_sfa_files_in_transition_cgi enstore_sfa_hud_cgi \
enstore_sfa_show_cached_files_cgi enstore_show_inventory_cgi enstore_show_inv_summary_cgi \
enstore_user_cgi enstore_utils_cgi show_file_cgi show_volume_cgi


#This .SECONDEXPANSION necessary to enable $$@ to work on newer versions of GNU
# Make.  This became necessary with the version of GNU Make that shipped with
# SLF5.  SLF4 and ealier had $$@ enabled by default.
#
# The third edition of "Managing Progjects with GNU Make" does not mention
# $$@ or .SECONDEXPANSION.  The first edition described $$@ as a Sys V
# extension.
.SECONDEXPANSION:

#These are the full lists.
FULL_SERVER_LIST=$(SERVER_LIST) $(SERVER_HTMLGEN_LIST) $(SERVER_SQL_LIST) $(SERVER_LIB_LIST) $(NON_SERVER_LIST)
FULL_CLIENT_LIST=enstore_admin encp_admin ensync_admin enmv_admin volume_assert migrate_chimera duplicate_chimera get

crons: $(CRON_LIST)
$(CRON_LIST): $$@
	pyinstaller pyinstaller/$@.spec
	cp dist/$@ $(ENSTORE_TARGET_DIR)/sbin/$@
	$(RM) dist/$@

$(FULL_SERVER_LIST): $$@
	pyinstaller pyinstaller/$@.spec
	cp dist/$@ $(ENSTORE_TARGET_DIR)/sbin/$@
	$(RM) dist/$@

$(FULL_CLIENT_LIST): $$@
	pyinstaller pyinstaller/$@.spec
	cp dist/$@ $(ENSTORE_BIN_DIR)/$@
	$(RM) dist/$@

$(CGI_SCRIPTS): $$@
	@echo "making CGI scripts"
	pyinstaller pyinstaller/$@.spec
	cp dist/$@ $(ENSTORE_TARGET_DIR)/www/cgi-bin/$@
	$(RM) dist/$@

$(MISC_LIST): $$@
	pyinstaller pyinstaller/$@.spec
	cp dist/$@ $(ENSTORE_TARGET_DIR)/sbin
	$(RM) dist/$@

make_enstore_system: ../sbin/$$@.py
	- rm -rf $(SERVER_BIN_TEMP)
	mkdir $(SERVER_BIN_TEMP)
	python $(FREEZE) $(FREEZE_ENSTORE_OPTIONS) -e $(ENSTORE_DIR)/modules -e $(PYMODULES) -o SERVER_BIN_TEMP ../sbin/$@.py
	(cd SERVER_BIN_TEMP; LDFLAGS=$(LDFLAGS2); export LDFLAGS; make -e;)
	cp SERVER_BIN_TEMP/$@ $(ENSTORE_BIN_DIR)/sbin/$@
	rm -rf $SERVER_BIN_TEMP

enstore: pre_enstore $(FULL_CLIENT_LIST) $(FULL_SERVER_LIST) $(CGI_SCRIPTS) $(MISC_LIST) entv post_enstore $(CRON_LIST)

enstore_servers: $(FULL_SERVER_LIST) 

meadia_changer:
	pre_enstore
	(cd $(ENSTORE_DIR)/modules; make all)
	pyinstaller pyinstaller/media_changer.spec
	cp dist/media_changer $(ENSTORE_BIN_DIR)/sbin
	$(RM) dist/media_changer

#get:
#	(cd $(ENSTORE_DIR)/modules; make all)
#	$(CP) pyinstaller/get.spec .
#	pyinstaller get.spec
#	cp dist/get $(ENSTORE_BIN_DIR)
#	cp ../ups/chooseConfig GET_BIN
#	cp ../modules/enroute2 GET_BIN
#	sed -e 's/encp/get/g' $(ENSTORE_DIR)/ups/encp.table > GET_BIN/get.table
#	- rm -rf GET_TEMP

source: pre_source install_enstore

pre_source:
	(cd $(ENSTORE_DIR)/modules; make clean)
	- $(RM) $(ENSTORE_BIN_DIR)
	mkdir -p $(ENSTORE_BIN_DIR)/bin
	mkdir -p $(ENSTORE_BIN_DIR)/sbin
	mkdir -p $(ENSTORE_BIN_DIR)/etc
	mkdir -p $(ENSTORE_BIN_DIR)/www
	mkdir -p $(ENSTORE_BIN_DIR)/crontabs
	mkdir -p $(ENSTORE_BIN_DIR)/src
	mkdir -p $(ENSTORE_BIN_DIR)/modules

	$(CP) $(ENSTORE_DIR)/src/*.py 		$(ENSTORE_BIN_DIR)/src
	$(CP) $(ENSTORE_DIR)/modules/* 	$(ENSTORE_BIN_DIR)/modules

	ln -s ENSTORE_BIN/opt/enstore/src/mover.py $(ENSTORE_BIN_DIR)/sbin/mover

#	- rm -rf MONITOR_CLIENT_BIN_TEMP
#	mkdir MONITOR_CLIENT_BIN_TEMP
#	python $(FREEZE) -e $(ENSTORE_DIR)/modules -e $(PYMODULES) -o MONITOR_CLIENT_BIN_TEMP monitor_client.py
#	(cd MONITOR_CLIENT_BIN_TEMP; LDFLAGS=$(LDFLAGS2); export LDFLAGS; make -e;)
#	cp MONITOR_CLIENT_BIN_TEMP/monitor_client      ENCPBIN/enmonitor
#	rm -rf MONITOR_CLIENT_BIN_TEMP

# This install never works!
install: encp enstore_user
	cp encp $ENSTORE_DIR/bin
	cp enstore_user $ENSTORE_DIR/bin

