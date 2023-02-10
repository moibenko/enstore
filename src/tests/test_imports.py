# empty test that just does imports to improve coverage report
import sys
import mock
sys.modules['pg'] = mock.MagicMock()
sys.modules['psycopg2'] = mock.MagicMock()
sys.modules['psycopg2.extras'] = mock.MagicMock()
sys.modules['aci_shadow'] = mock.MagicMock()
sys.modules['libtpshelve'] = mock.MagicMock()
sys.modules['ExtendedAttributes'] = mock.MagicMock()
import enroute
import Cache
import Trace
#commented imports trigger non-zero exit so dont 
#import acc_daily_summary
import accounting
import accounting_client
import accounting_query
import accounting_server
import aci
import alarm
import alarm_client
import alarm_server
#import aml2
#import aml2_dummy
#import aml2_log
import atomic
import backup
import backup_backup
import backup_client
import bfid_db
import bfid_util
import bytes_per_day_plotter_module
import callback
import cern_wrapper
#import change_loc_cookie
#import change_s_i
import charset
import check_pnfs_db
import checkdb
import checkdb_PITR
import checkdbs
import chimera
import cleanUDP
import configuration_client
import configuration_server
import cpio_odc_wrapper
import db
#import db_compare
#import db_dump
#import db_retrieve_backup
import dbaccess
import dbs
import dcache_make_queue_plot_page
import dcache_monitor
import delete_at_exit
import delfile_chimera
import dict_u2a
#import discard_copy
import discipline
import disk_driver
import dispatcher_client
import dispatching_worker
import drive_hours_plotter_module
import drive_hours_sep_plotter_module
import drive_utilization_plotter_module
import drivestat2
import drivestat_client
import drivestat_server
import duplicate
import duplicate_chimera
#import duplication_util
import duplication_util_chimera
import e_errors
import ecron_util
import edb
import ejournal
import en_eval
import encp
import encp_admin
import encp_rate_multi_plotter_module
import encp_ticket
import encp_user
import encp_user2
import encp_wrapper
import enmail
import enmv
import enmv_admin
import enmv_user
import enstore
import enstore_admin
import enstore_alarm_cgi
import enstore_alarm_search_cgi
import enstore_constants
import enstore_display
import enstore_erc_functions
#import enstore_file_listing_cgi
import enstore_files
import enstore_functions
import enstore_functions2
import enstore_functions3
import enstore_html
import enstore_log_file_search_cgi
import enstore_mail
import enstore_make_generated_page
import enstore_make_log_calendar
import enstore_make_plot_page
import enstore_overall_status
import enstore_pg
import enstore_plots
import enstore_plotter_framework
import enstore_plotter_module
#import enstore_recent_files_on_tape_cgi
import enstore_restart
import enstore_saag
import enstore_saag_network
import enstore_sfa_files_in_transition_cgi
import enstore_sfa_hud_cgi
import enstore_sfa_show_cached_files_cgi
import enstore_show_inv_summary_cgi
import enstore_show_inventory_cgi
import enstore_start
import enstore_status
import enstore_stop
import enstore_system_html
import enstore_up_down
import enstore_user
import enstore_user2
import enstore_user_cgi
import enstore_utils_cgi
import ensync
import ensync_admin
import ensync_user
import entv
import espion
import estart
import estop
import event_relay
import event_relay_client
import event_relay_messages
import fake_quota
import fdbdump
import file_cache_status
import file_clerk
import file_clerk_client
import file_family_analysis_plotter_module
import file_utils
import fileinfo
import files_rw_plotter_module
import files_rw_sep_plotter_module
import fill_slot_usage
import find_pnfs_file
import fs
import ftt
import ftt_driver
import generic_alarm
import generic_client
import generic_driver
import generic_server
import get
import get_all_bytes_counter
import get_cron_title
import get_total_bytes_counter
import histogram
import host_config
import hostaddr
import html_main
import idlemovers
import info_client
import info_server
import inquisitor
import inquisitor_client
import inquisitor_plots
import interface
import inventory
import journal
#import label_tape
import library_manager
import library_manager_client
import library_manager_director_client
#import library_manager_nanny
import lm_director
import lm_director_client
import lm_list
#import lm_que_length
import lmd_policy_selector
import log_client
import log_finish_event
import log_server
#import log_server_proc_tcp
#import log_server_stress_test
#import log_server_stress_test_tcp
import log_start_event
import log_trans_fail
import m2
import make_ingest_rates_html_page
import make_migrated_as_duplicate
import make_original_as_duplicate
#import makec_files
import makeplot
import manage_queue
#import match_syslog
#import media_changer
import media_changer_client
import media_changer_test
import migrate
import migrate_chimera
import migration_scope
import migration_summary_plotter_module
import migrator_client
import module_trace
import monitor_client
import monitor_server
import monitored_server
import mount_latency_plotter_module
import mounts_per_robot_plotter_module
import mounts_plot
import mounts_plotter_module
import movcmd_mc
#import mover-nanny
import mover
import mover_client
import mover_constants
import mover_summary_plotter_module
import mpq
import multiple_interface
import namespace
import net_directory
import net_driver
import null_driver
import null_wrapper
#import on-call
#import operation
import option
import plotter
import plotter_main
import pnfs
import pnfs_agent
import pnfs_agent_client
import pnfs_backup_plot
import pnfs_backup_plotter_module
import pnfsidparser
import priority_selector
import purge_files
import put
#import quickquota
import quota
import quotas_plotter_module
#import rate_test
import ratekeeper
import ratekeeper_client
import ratekeeper_plotter_module
import ratemeter
import rawUDP
import rawUDP_p
import read_write_condition_variable
import readonly_volumes
import recent_file_listing
import recent_files_on_tape
import requests_snapshot
import restoredb
import rm_volmap
import run1
import safe_dict
import scan
import scanfiles
import scsi_mode_select
import send_alive
import set_cache_status
#import set_lm_noread
import setpath
import sfa_plotter_module
import show_file_cgi
import show_volume_cgi
import slots_usage_plotter_module
import snow_fliptab
import snow_interface
import stethoscope
import string_driver
import summary_bpd_plotter_module
import summary_burn_rate_plotter_module
import summary_plots
#import swap_original_and_copy
import tab_flipping_exemption
#import tab_flipping_nanny
import tapes_burn_rate_plotter_module
import time_fifo
import timeofday
import udp_cl
import udp_client
import udp_common
import udp_load_test
import udp_proxy_client
import udp_server
import udp_srvr
#import vdbdump
import volume_assert
import volume_assert_wrapper
import volume_clerk
import volume_clerk_client
import volume_family
import web_server
#import weekly_summary_report
#import wr_errors_logger
import write_protection_alert
import www_server
#import yank
import unittest

if __name__ == "__main__":   # pragma: no cover
    unittest.main()

