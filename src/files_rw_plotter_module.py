#!/usr/bin/env python

"""
Plot number of files read and written per mount versus date, stacked by
storage group, individually for each unique drive type.

.. note::

   - This module is referenced by the :mod:`plotter_main` module.
   - This module has code in common with the
     :mod:`files_rw_sep_plotter_module` module.
"""

# Python imports
from __future__ import division, print_function
import collections
import os
import time

# Enstore imports
import dbaccess
import enstore_constants
import enstore_plotter_module
import histogram

WEB_SUB_DIRECTORY = enstore_constants.FILES_RW_PLOTS_SUBDIR
"""Subdirectory in which to write plots. This constant is also referenced by
the :mod:`enstore_make_plot_page` module."""


class FilesRWPlotterModule(enstore_plotter_module.EnstorePlotterModule):
    """Plot number of files read and written per mount versus date, stacked
       by storage group, individually for each unique drive type."""

    num_bins = 32

    def book(self, frame):
        """
        Create destination directory for plots as needed.

        :type frame: :class:`enstore_plotter_framework.EnstorePlotterFramework`
        :arg frame: provides configuration client.
        """

        cron_dict = frame.get_configuration_client().get('crons', {})
        self.html_dir = cron_dict.get('html_dir', '')
        self.plot_dir = os.path.join(self.html_dir,
                                     enstore_constants.PLOTS_SUBDIR)
        if not os.path.exists(self.plot_dir):
            os.makedirs(self.plot_dir)
        self.web_dir = os.path.join(self.html_dir, WEB_SUB_DIRECTORY)
        if not os.path.exists(self.web_dir):
            os.makedirs(self.web_dir)
        print('Plots sub-directory: {}'.format(self.web_dir))

    def fill(self, frame):
        """
        Read and store values for plots from the database into memory.

        :type frame: :class:`enstore_plotter_framework.EnstorePlotterFramework`
        :arg frame: provides configuration client.
        """

        # Get database
        csc = frame.get_configuration_client()
        db_info = csc.get(enstore_constants.ACCOUNTING_SERVER)
        db_get = db_info.get
        db = dbaccess.DatabaseAccess(maxconnections=1,
                                     host=db_get('dbhost', 'localhost'),
                                     database=db_get('dbname', 'accounting'),
                                     port=db_get('dbport', 8800),
                                     user=db_get('dbuser', 'enstore'),
                                     )

        # Read from database
        db_query = ("select type as drive, storage_group, "
                    "date_trunc('day', finish) as date, "
                    "sum(reads)::float/count(state) as reads_per_dismount, "
                    "sum(writes)::float/count(state) as writes_per_dismount, "
                    "(sum(reads)+sum(writes))::float/count(state) "
                    " as reads_and_writes_per_dismount "
                    "from tape_mounts where "
                    "storage_group notnull and finish notnull "
                    "and finish > CURRENT_TIMESTAMP - interval '{} days' "
                    "and state='D' "
                    "group by drive, storage_group, date "
                    "order by drive, storage_group, date"
                    ).format(self.num_bins)
        res = db.query_dictresult(db_query)

        # Restructure data into nested dict
        counts = collections.OrderedDict()  # Preserves preexisting sort order.
        for row in res:
            row = row.get
            counts.setdefault(row('drive'), collections.OrderedDict()) \
                  .setdefault(row('storage_group'), {})[row('date')] = {'reads': row('reads_per_dismount'),
                                                                        'writes': row('writes_per_dismount'),
                                                                        'reads+writes':
                                                                        row('reads_and_writes_per_dismount')
                                                                        }

        db.close()
        self.counts = counts

    def plot(self):
        """Write plot files."""

        str_time_format = "%Y-%m-%d %H:%M:%S"

        now_time = time.time()
        now_time = enstore_plotter_module.roundtime(now_time, 'ceil')
        now_time -= enstore_constants.SECS_PER_HALF_DAY  # For bin placement.
        now_time_str = time.strftime(str_time_format,
                                     time.localtime(now_time))

        start_time = now_time - self.num_bins * enstore_constants.SECS_PER_DAY
        # Note: "start_time = enstore_plotter_module.roundtime(start_time,
        #                     'ceil')" has no effect.
        start_time_str = time.strftime(str_time_format,
                                       time.localtime(start_time))

        plot_key_setting = 'set key outside width 2'
        # Note: "width 2" is used above to prevent a residual overlap of the
        # legend's labels and the histogram.

        set_xrange_cmds = ('set xdata time',
                           'set timefmt "{}"'.format(str_time_format),
                           'set xrange ["{}":"{}"]'.format(start_time_str,
                                                           now_time_str))

        # Make plots
        for action in ('reads', 'writes'):  # , 'reads+writes'):

            ylabel = 'Average file {} per mount'.format(action)

            for drive, drive_dict in list(self.counts.items()):

                plot_name = '{}_{}'.format(drive, action)
                plot_title = ('Average file {} per mount by storage group '
                              'for {} drives.').format(action, drive)
                plotter = histogram.Plotter(plot_name, plot_title)
                plotter.add_command(plot_key_setting)
                for cmd in set_xrange_cmds:
                    plotter.add_command(cmd)

                hist_sum_name = 'h_' + plot_name
                hist_sum = histogram.Histogram1D(hist_sum_name,
                                                 hist_sum_name, self.num_bins,
                                                 float(start_time),
                                                 float(now_time))
                hist_sum.set_time_axis(True)
                hists = []

                plot_enabled = False
                for sg, sg_dict in drive_dict.items():

                    hist_name = plot_name + '_' + sg
                    hist = histogram.Histogram1D(hist_name, hist_name,
                                                 self.num_bins,
                                                 float(start_time),
                                                 float(now_time))

                    for datetime_str, datetime_dict in sg_dict.items():
                        secs = time.mktime(time.strptime(datetime_str,
                                                         '%Y-%m-%d %H:%M:%S'))
                        secs -= enstore_constants.SECS_PER_HALF_DAY
                        # Note: The shift above is to match the previously
                        # applied shift of now_time and start_time by half day.
                        value = datetime_dict[action]
                        if value > 0:
                            # Note: This check ensures that the number of
                            # entries in the histogram can if needed later be
                            # used as an indicator of whether the histogram
                            # contains nonzero data.
                            hist.fill(secs, value)

                    status = ('Plotting' if (hist.n_entries() > 0) else
                              'Skipping')
                    print('{}: action={}; drive={}; storage_group={}'
                          .format(status, action, drive, sg))

                    if hist.n_entries() > 0:
                        plot_enabled = True
                    else:
                        continue

                    hist.set_time_axis(True)
                    hist.set_ylabel(ylabel)
                    hist.set_xlabel('Date (year-month-day)')
                    hist.set_line_width(20)
                    hist.set_marker_text(sg)
                    hist.set_marker_type('impulses')
                    hists.append(hist)

                hists.sort()
                color = 0
                for hist in hists:
                    hist_sum += hist
                    hist_sum_name = 'drive_{}'.format(hist.get_name())
                    hist_sum.set_name(hist_sum_name)
                    hist_sum.set_data_file_name(hist_sum_name)
                    hist_sum.set_marker_text(hist.get_marker_text())
                    hist_sum.set_time_axis(True)
                    hist_sum.set_ylabel(ylabel)
                    hist_sum.set_marker_type('impulses')
                    hist_sum.set_line_color(color)
                    hist_sum.set_line_width(20)
                    plotter.add(hist_sum)
                    color += 1

                if plot_enabled:  # Check prevents error if no hist was added.
                    plotter.reshuffle()
                    plotter.plot(directory=self.web_dir)
