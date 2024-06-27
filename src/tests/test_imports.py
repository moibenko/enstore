# empty test that just does imports to improve coverage report
import unittest
import www_server
import write_protection_alert
import web_server
import volume_family
import volume_clerk_client
import volume_clerk
import volume_assert_wrapper
import volume_assert
import udp_srvr
import udp_server
import udp_proxy_client
import udp_load_test
import udp_common
import udp_client
import udp_cl
import timeofday
import time_fifo
import tapes_burn_rate_plotter_module
import tab_flipping_exemption
import summary_plots
import summary_burn_rate_plotter_module
import summary_bpd_plotter_module
import string_driver
import stethoscope
import snow_interface
import snow_fliptab
import slots_usage_plotter_module
import show_volume_cgi
import show_file_cgi
import sfa_plotter_module
import setpath
import set_cache_status
import send_alive
import scsi_mode_select
import scanfiles
import scan
import safe_dict
import run1
import rm_volmap
import restoredb
import requests_snapshot
import recent_files_on_tape
import recent_file_listing
import readonly_volumes
import read_write_condition_variable
import rawUDP_p
import rawUDP
import ratemeter
import ratekeeper_plotter_module
import ratekeeper_client
import ratekeeper
import quotas_plotter_module
import quota
import put
import purge_files
import priority_selector
import pnfsidparser
import pnfs_backup_plotter_module
import pnfs_backup_plot
import pnfs_agent_client
import pnfs_agent
import pnfs
import plotter_main
import plotter
import option
import null_wrapper
import null_driver
import net_driver
import net_directory
import namespace
import multiple_interface
import mpq
import mover_summary_plotter_module
import mover_constants
import mover_client
import mover
import movcmd_mc
import mounts_plotter_module
import mounts_plot
import mounts_per_robot_plotter_module
import mount_latency_plotter_module
import monitored_server
import monitor_server
import monitor_client
import module_trace
import migrator_client
import migration_summary_plotter_module
import migration_scope
import migrate_chimera
import migrate
import media_changer_test
import media_changer_client
import manage_queue
import makeplot
import make_original_as_duplicate
import make_migrated_as_duplicate
import make_ingest_rates_html_page
import m2
import log_trans_fail
import log_start_event
import log_server
import log_finish_event
import log_client
import lmd_policy_selector
import lm_list
import lm_director_client
import lm_director
import library_manager_director_client
import library_manager_client
import library_manager
import journal
import inventory
import interface
import inquisitor_plots
import inquisitor_client
import inquisitor
import info_server
import info_client
import idlemovers
import html_main
import hostaddr
import host_config
import histogram
import get_total_bytes_counter
import get_cron_title
import get_all_bytes_counter
import get
import generic_server
import generic_driver
import generic_client
import generic_alarm
import ftt_driver
import ftt
import fs
import find_pnfs_file
import fill_slot_usage
import files_rw_sep_plotter_module
import files_rw_plotter_module
import fileinfo
import file_utils
import file_family_analysis_plotter_module
import file_clerk_client
import file_clerk
import file_cache_status
import fdbdump
import fake_quota
import event_relay_messages
import event_relay_client
import event_relay
import estop
import estart
import espion
import entv
import ensync_user
import ensync_admin
import ensync
import enstore_utils_cgi
import enstore_user_cgi
import enstore_user2
import enstore_user
import enstore_up_down
import enstore_system_html
import enstore_stop
import enstore_status
import enstore_start
import enstore_show_inventory_cgi
import enstore_show_inv_summary_cgi
import enstore_sfa_show_cached_files_cgi
import enstore_sfa_hud_cgi
import enstore_sfa_files_in_transition_cgi
import enstore_saag_network
import enstore_saag
import enstore_restart
import enstore_plotter_module
import enstore_plotter_framework
import enstore_plots
import enstore_pg
import enstore_overall_status
import enstore_make_plot_page
import enstore_make_log_calendar
import enstore_make_generated_page
import enstore_mail
import enstore_log_file_search_cgi
import enstore_html
import enstore_functions3
import enstore_functions2
import enstore_functions
import enstore_files
import enstore_erc_functions
import enstore_display
import enstore_constants
import enstore_alarm_search_cgi
import enstore_alarm_cgi
import enstore_admin
import enstore
import enmv_user
import enmv_admin
import enmv
import enmail
import encp_wrapper
import encp_user2
import encp_user
import encp_ticket
import encp_rate_multi_plotter_module
import encp_admin
import encp
import en_eval
import ejournal
import edb
import ecron_util
import e_errors
import duplication_util_chimera
import duplicate_chimera
import duplicate
import drivestat_server
import drivestat_client
import drivestat2
import drive_utilization_plotter_module
import drive_hours_sep_plotter_module
import drive_hours_plotter_module
import dispatching_worker
import dispatcher_client
import disk_driver
import discipline
import dict_u2a
import delfile_chimera
import delete_at_exit
import dcache_monitor
import dcache_make_queue_plot_page
import dbs
import dbaccess
import db
import cpio_odc_wrapper
import configuration_server
import configuration_client
import cleanUDP
import chimera
import checkdbs
import checkdb_PITR
import checkdb
import check_pnfs_db
import charset
import cern_wrapper
import callback
import bytes_per_day_plotter_module
import bfid_util
import bfid_db
import backup_client
import backup_backup
import backup
import atomic
import alarm_server
import alarm_client
import alarm
import aci
import accounting_server
import accounting_query
import accounting_client
import accounting
import Trace
import Cache
import enroute
import sys
import mock
sys.modules['pg'] = mock.MagicMock()
sys.modules['psycopg2'] = mock.MagicMock()
sys.modules['psycopg2.extras'] = mock.MagicMock()
sys.modules['aci_shadow'] = mock.MagicMock()
sys.modules['libtpshelve'] = mock.MagicMock()
sys.modules['ExtendedAttributes'] = mock.MagicMock()
# commented imports trigger non-zero exit so dont
# import acc_daily_summary
# import aml2
# import aml2_dummy
# import aml2_log
# import change_loc_cookie
# import change_s_i
# import db_compare
# import db_dump
# import db_retrieve_backup
# import discard_copy
# import duplication_util
# import enstore_file_listing_cgi
# import enstore_recent_files_on_tape_cgi
# import label_tape
# import library_manager_nanny
# import lm_que_length
# import log_server_proc_tcp
# import log_server_stress_test
# import log_server_stress_test_tcp
# import makec_files
# import match_syslog
# import media_changer
# import mover-nanny
# import on-call
# import operation
# import quickquota
# import rate_test
# import set_lm_noread
# import swap_original_and_copy
# import tab_flipping_nanny
# import vdbdump
# import weekly_summary_report
# import wr_errors_logger
# import yank

if __name__ == "__main__":   # pragma: no cover
    unittest.main()
