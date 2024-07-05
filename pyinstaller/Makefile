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
ENSTORE_SBIN_DIR=$(ENSTORE_TARGET_DIR)/sbin
ENSTORE_TARGET_DCACHE=$(ENSTORE_TOP_DIR)/dcache
ENSTORE_BIN_DCACHE=$(ENSTORE_TARGET_DCACHE)/bin
PYINSTALLER_DIR=$(ENSTORE_HOME)/pyinstaller
PYINSTALLER_SPEC_DIR=$(PYINSTALLER_DIR)/specs

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
	- $(RM) specs
	- $(RM) $(ENSTORE_TARGET_DIR)

### The following groupings for for building the client side programs
### intended for release to the general public.
###
### The two commands of interest are "make encp" and "make encp_for_dcache".

entv_sa:
	(cd $(ENSTORE_DIR)/modules; make all mouse_move autologinenstore)
	pyinstaller pyinstaller/entv.spec
	cp dist/entv $(ENSTORE_BIN_DIR)/
	$(RM) dist/entv


### intended for use by the Enstore administrators.
###
### The command of interest is "make enstore".
### All python code is built in sbin and then moved to proper places

pre_enstore:
	(cd $(ENSTORE_DIR)/modules; make all mouse_move autologinenstore ddencp)
	mkdir -p $(ENSTORE_BIN_DIR)
	mkdir -p $(ENSTORE_TARGET_DIR)/etc
	mkdir -p $(ENSTORE_TARGET_DIR)/www/cgi-bin
	mkdir -p $(ENSTORE_TARGET_DIR)/crontabs
	mkdir -p $(ENSTORE_TARGET_DIR)/external_distr
	mkdir -p $(ENSTORE_TARGET_DIR)/tools

post_enstore: install_enstore
	$(MV) $(ENSTORE_SBIN_DIR)/encp_admin   $(ENSTORE_BIN_DIR)/encp
	$(MV) $(ENSTORE_SBIN_DIR)/enstore_admin $(ENSTORE_BIN_DIR)/enstore
	$(MV) $(ENSTORE_SBIN_DIR)/ensync_admin $(ENSTORE_BIN_DIR)/ensync
	$(MV) $(ENSTORE_SBIN_DIR)/enmv_admin   $(ENSTORE_BIN_DIR)/enmv
	$(MV) $(ENSTORE_SBIN_DIR)/migrate_chimera   $(ENSTORE_BIN_DIR)/migrate
	$(MV) $(ENSTORE_SBIN_DIR)/duplicate_chimera   $(ENSTORE_BIN_DIR)/duplicate
	$(MV) $(ENSTORE_SBIN_DIR)/volume_assert   $(ENSTORE_BIN_DIR)/

	$(CP) $(ENSTORE_DIR)/modules/ddencp             $(ENSTORE_BIN_DIR)
	$(CP) $(ENSTORE_DIR)/modules/enroute2		$(ENSTORE_BIN_DIR)
	$(CP) $(ENSTORE_DIR)/modules/ecrc		$(ENSTORE_BIN_DIR)

install_enstore:
	$(CP) $(ENSTORE_DIR)/etc/* 		$(ENSTORE_TARGET_DIR)/etc/
	$(CP) $(ENSTORE_DIR)/www/* 			$(ENSTORE_TARGET_DIR)/www/
	$(CP) `ls -1dp $(ENSTORE_DIR)/crontabs/* | egrep -v "CVS" | egrep -v "old"` 	$(ENSTORE_TARGET_DIR)/crontabs/

	rsync -r --exclude 'deprecated' --exclude '*.py' $(ENSTORE_DIR)/external_distr/* $(ENSTORE_TARGET_DIR)/external_distr
	rsync -r --exclude 'deprecated' --exclude '*.py' $(ENSTORE_DIR)/tools/* $(ENSTORE_TARGET_DIR)/tools
	rsync -r --exclude 'deprecated' --exclude '*.py' $(ENSTORE_DIR)/bin/* $(ENSTORE_BIN_DIR)
	$(CP) $(ENSTORE_DIR)/bin/en_check		$(ENSTORE_BIN_DIR)
#Why are these two in $ENSTORE_DIR/bin?
	$(CP) $(ENSTORE_DIR)/bin/enstore-boot		$(ENSTORE_BIN_DIR)
	$(CP) $(ENSTORE_DIR)/bin/monitor_server-boot	$(ENSTORE_BIN_DIR)
	$(CP) $(ENSTORE_DIR)/bin/pidkill*    $(ENSTORE_BIN_DIR)
	./install.py $(ENSTORE_DIR) $(ENSTORE_TARGET_DIR) 'tools'
	./install.py $(ENSTORE_DIR) $(ENSTORE_TARGET_DIR) 'external_distr'
	././install_shell_scripts.py $(ENSTORE_DIR)/sbin $(ENSTORE_SBIN_DIR)

#These are the list breakdowns.
SERVER_LIST=configuration_server log_server event_relay library_manager media_changer udp_server
SERVER_HTMLGEN_LIST=alarm_server inquisitor ratekeeper monitor_server
SERVER_SQL_LIST=file_clerk volume_clerk info_server accounting_server drivestat_server
SERVER_SFA_LIST=dispatcher lm_director
WEB_SERVER = web_server
ENSTORE_SYSTEM = make_enstore_system

# for mover need a special spec file
MOVER=mover
#mover media_changer
MISC_LIST=get_cron_title udp_client log_start_event log_finish_event
CRON_LIST=plotter_main summary_plots log_trans_fail recent_files_on_tape inventory plotter fill_slot_usage \
enstore_system_html make_ingest_rates_html_page get_total_bytes_counter html_main delfile_chimera \
checkdb_PITR enstore_make_plot_page acc_daily_summary

CGI_SCRIPTS=enstore_alarm_cgi enstore_alarm_search_cgi enstore_file_listing_cgi \
enstore_log_file_search_cgi enstore_recent_files_on_tape_cgi \
enstore_sfa_files_in_transition_cgi enstore_sfa_hud_cgi \
enstore_sfa_show_cached_files_cgi enstore_show_inventory_cgi enstore_show_inv_summary_cgi \
enstore_user_cgi enstore_utils_cgi show_file_cgi show_volume_cgi
SBIN:=$(shell ls -1 ../sbin/*.py | grep -v make_enstore_system | sed -e "s^.py^^g" -e "s^../sbin/^^g"| tr '\n' ' ')
BIN:=$(shell ls -1 ../bin/*.py | sed -e "s^.py^^g" -e "s^../sbin/^^g"| tr '\n' ' ')
TOOLS:=$(shell ls -1 ../tools/*.py | sed -e "s^.py^^g" -e "s^../tools/^^g"| tr '\n' ' ')
EXT_DISTR:=$(shell ls -1 ../external_distr/*.py | sed -e "s^.py^^g" -e "s^../external_distr/^^g"| tr '\n' ' ')

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
FULL_CLIENT_LIST=enstore_admin encp_admin ensync_admin enmv_admin volume_assert migrate_chimera duplicate_chimera get entv


$(FULL_SERVER_LIST): $$@
	pyi-makespec --specpath specs --hidden-import enroute ../src/$@.py
	echo $@ >> spec_list
$(FULL_CLIENT_LIST): $$@
	pyi-makespec --specpath specs --hidden-import enroute ../src/$@.py
	echo $@	>> spec_list

$(CRON_LIST): $$@
	pyi-makespec --specpath specs --hidden-import enroute ../src/$@.py
	echo $@	>> spec_list
$(MISC_LIST): $$@
	pyi-makespec --specpath specs --hidden-import enroute ../src/$@.py
	echo $@ >> spec_list

$(CGI_SCRIPTS): $$@
	pyinstaller --onefile --distpath cgi_dist  --workpath cgi_build --hidden-import enroute ../src/$@.py
	$(MV) cgi_dist/$@ $(ENSTORE_TARGET_DIR)/www/cgi-bin
	$(RM) cgi_dist cgi_build

$(WEB_SERVER): $$@
	pyinstaller --onefile --distpath web_dist  --workpath web_build --hidden-import enroute ../src/$@.py
	$(MV) web_dist/$@ $(ENSTORE_TARGET_DIR)/sbin
	$(RM) web_dist web_build

$(ENSTORE_SYSTEM): $$@
	pyinstaller --onefile --distpath web_dist  --workpath web_build --hidden-import enroute ../sbin/$@.py
	$(MV) web_dist/$@ $(ENSTORE_TARGET_DIR)/sbin
	$(RM) web_dist web_build

$(SBIN): $$@
	pyi-makespec --specpath specs --hidden-import enroute ../sbin/$@.py
	echo $@	>> spec_list
$(BIN): $$@
	pyi-makespec --specpath specs --hidden-import enroute ../bin/$@.py
	echo $@ >> spec_list

$(TOOLS): $$@
	pyi-makespec --specpath specs --hidden-import enroute ../tools/$@.py
	echo $@	>> spec_list
$(EXT_DISTR): $$@
	pyi-makespec --specpath specs --hidden-import enroute ../external_distr/$@.py
	echo $@	>> spec_list
$(MOVER):
	pyi-makespec --specpath specs --hidden-import enroute --hidden-import media_changer --hidden-import cpio_odc_wrapper --hidden-import cern_wrapper --hidden-import null_wrapper ../src/mover.py
	echo mover >> spec_list

spec_files: $(FULL_SERVER_LIST) $(MOVER) $(FULL_CLIENT_LIST) $(MISC_LIST) $(CRON_LIST) $(SBIN) $(TOOLS) $(EXT_DISTR)

clear_spec_files:
	$(RM) spec_list
	$(RM) specs
build_spec_file:
	./build_sbin_spec.py
build_spec: clear_spec_files spec_files build_spec_file

build_distr: 
	pyinstaller -y --distpath $(ENSTORE_TARGET_DIR) specs/enstore_sbin.spec

#enstore: pre_enstore $(FULL_CLIENT_LIST) $(FULL_SERVER_LIST) $(CGI_SCRIPTS) $(MISC_LIST) entv post_enstore $(CRON_LIST)
enstore: pre_enstore build_spec build_distr $(CGI_SCRIPTS) $(WEB_SERVER) $(ENSTORE_SYSTEM) post_enstore

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

