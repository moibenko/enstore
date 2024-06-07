#!/usr/bin/env python
"""
migration_scope.py

A tool to watch migration and/or to analyze its log files

This is designed to read from a file, if specified, or stdin.
Since migrate.py spits everything out through stdout, in addition to
writing log files, it is good to pipe migrate.py to this.

migrate.py <command> .... | migration_scope.py

In migrate.py's log file, each line has a keyword.
Based on the keyword, migration_scope.py displays the messages in
appropriate windows. Special attention is paid to ERROR message.

"""
from future import standard_library
standard_library.install_aliases()
import tkinter
import tkinter.messagebox
import tkinter.scrolledtext
import time
import os
import sys
import queue
import _thread

input_queue = queue.Queue(1024)

# read_input


def read_input(f):
    l = f.readline()
    while l:
        ll = l.strip()
        input_queue.put(ll, True)
        l = f.readline()
    return

# InfoBox is a ScrooledText with a label as heading


class InfoBox(tkinter.Frame):

    def __init__(self, master, w=200, h=20, heading="InfoBox"):
        tkinter.Frame.__init__(self, master)
        self.label = tkinter.Label(
            self,
            text=heading,
            bd=1,
            relief=tkinter.SUNKEN,
            anchor=tkinter.W)
        self.label.configure(
            foreground="#FFFFFF",
            background="#0000FF",
            font=(
                "Times",
                12,
                "bold"))
        self.label.pack(fill=tkinter.X)
        self.s = tkinter.scrolledtext.ScrolledText(self, height=h, width=w)
        # self.s = ScrolledText.ScrolledText(self)
        self.s.pack()
        self.s.config(state=tkinter.DISABLED)

    def printline(self, s):
        self.s.config(state=tkinter.NORMAL)
        self.s.insert(tkinter.END, s)
        self.s.see(tkinter.END)
        self.s.config(state=tkinter.DISABLED)


class StatusBar(tkinter.Frame):
    def __init__(self, master):
        tkinter.Frame.__init__(self, master)
        self.label = tkinter.Label(
            self,
            text="",
            bd=1,
            relief=tkinter.SUNKEN,
            anchor=tkinter.W)
        self.label.pack(fill=tkinter.X)

    def set(self, format, *args):
        self.label.config(text=format % args)
        self.label.update_idletasks()

    ##def set(self, s):
    ##    self.label.config(text=s)
    ##    self.label.update_idletasks()

    def clear(self):
        self.label.config(text="")
        self.label.update_idletasks()


# for event loop
quit_now = 0
single_step = 0
piped = 0

# set_quit() -- callback for Exit


def set_quit():
    global quit_now, piped
    if piped:
        if not tkinter.messagebox.askokcancel("Quit at your risk",
                                        "The input is piped.\nQuiting now will kill the process in the upstream.\nDo you still want to quit?"):
            return
    quit_now = 1
    sys.exit(0)

# show_help() -- callback for Help


def show_help():
    # God helps those who help themselves
    tkinter.messagebox.showinfo(
        "God helps those who help themselves",
        "Call Chih-Hao at x8076")

# set_single_step() -- active single step


def set_single_step():
    global single_step
    single_step = 1

# StateButton


class StatusButton(tkinter.Button):
    def __init__(self, root, states, **arg):
        self.state = states
        self.state_id = 0
        next_state = (self.state_id + 1) % len(self.state)
        tkinter.Button.__init__(
            self,
            root,
            text=states[next_state],
            command=self.change_state,
            **arg)

    def get_state(self):
        return self.state[self.state_id]

    def change_state(self):
        self.state_id = (self.state_id + 1) % len(self.state)
        next_state = (self.state_id + 1) % len(self.state)
        self.config(text=self.state[next_state])

# migration_watch() -- for "migrate.py --vol ..."


def migration_watch(l1):
    global single_step, quit_now, piped
    # root window
    root = tkinter.Tk()
    root.title("Migration Watch")
    root.protocol("WM_DELETE_WINDOW", set_quit)

    # create menu bar
    menu = tkinter.Menu(root)
    root.config(menu=menu)
    filemenu = tkinter.Menu(menu)
    menu.add_cascade(label="File", menu=filemenu)
    filemenu.add_command(label="Exit", command=set_quit)
    helpmenu = tkinter.Menu(menu)
    menu.add_cascade(label="Help", menu=helpmenu)
    helpmenu.add_command(label="Help me!", command=show_help)

    # create tool bar
    tool_frame = tkinter.Frame(root)
    quick_button = tkinter.Button(
        tool_frame,
        width=10,
        text='Exit',
        command=set_quit)
    quick_button.pack(side=tkinter.LEFT)
    action_button = StatusButton(tool_frame, ["Resume", "Pause"], width=10)
    action_button.pack(side=tkinter.LEFT)
    single_step_button = tkinter.Button(
        tool_frame,
        width=10,
        text='Step',
        command=set_single_step,
        state=tkinter.DISABLED)
    single_step_button.pack(side=tkinter.LEFT)
    help_button = tkinter.Button(
        tool_frame,
        width=10,
        text='Help',
        command=show_help)
    help_button.pack(side=tkinter.RIGHT)
    tool_frame.pack(fill=tkinter.X)

    # pack command_line and volume_status in the same frame
    frame1 = tkinter.Frame(root)
    # command_line to show the migrate.py command and its arguments
    command_line = InfoBox(frame1, h=5, w=133, heading="Command Line")
    command_line.pack(side=tkinter.LEFT)
    # volume_status to show everything about the volume
    volume_status = InfoBox(frame1, h=5, w=63, heading="Volume Status")
    volume_status.pack(side=tkinter.LEFT)
    frame1.pack()
    # error_info to show ERROR messages
    error_info = InfoBox(root, h=10, heading="Errors")
    error_info.s.config(foreground="#FF0000")
    error_info.pack()
    # progress shows EVERYTHING
    progress = InfoBox(root, h=20, heading="Progress")
    progress.pack()
    # copy_to_disk shows COPYING_TO_DISK messages
    copy_to_disk = InfoBox(root, h=10, heading="Copying to Disk")
    copy_to_disk.pack()
    # copy_to_tape shows COPYING_TO_TAPE messages
    copy_to_tape = InfoBox(root, h=10, heading="Copying to Tape")
    copy_to_tape.pack()
    # swap_metadata shows SWAPPING_METADATA messages
    swap_metadata = InfoBox(root, h=10, heading="Swapping Meta Data")
    swap_metadata.pack()

    command_line.printline(l1 + '\n')
    cnl = 1
    while True:
        if quit_now:
            sys.exit(0)
        # if paused:
        if action_button.get_state() == "Pause":
            single_step_button.config(state=tkinter.NORMAL)
            if single_step:
                single_step = 0
            else:
                # sleep so that it won't consume too
                # much CPU cycle while being paused
                time.sleep(0.1)
                # still needs to process the events
                root.update()
                continue
        else:
            single_step_button.config(state=tkinter.DISABLED)
        if input_queue.empty():
            time.sleep(0.1)
            root.update()
            continue
        l = input_queue.get(True)
        progress.printline(l + '\n')
        # processing line
        part = l.split()
        key = part[5]
        if key == "COMMAND":
            # some padding to make it prettier
            part[8] = part[8] + '    '
            ll = ' '.join(part[7:])
            command_line.printline(ll + '\n')
        elif key == "COPYING_TO_DISK":
            if part[6] != "processing" and part[6] != "no":
                if part[6] == "tmp":
                    ll = ' '.join(part[9:])
                elif part[6] == "failed":
                    ll = ' '.join(part[6:])
                else:
                    ll = ' '.join(part[7:])
                if part[-1] != 'OK' and part[-1] != 'ERROR':
                    copy_to_disk.printline(ll + ' ... ')
                else:
                    copy_to_disk.printline(ll + '\n')
        elif key == "COPYING_TO_TAPE":
            if part[6] != "removing":
                if part[6] == "copying":
                    tf = os.path.basename(part[-1]).split(":")
                    ll = part[7] + ' ' + tf[0] + ' ' + tf[1] + ' ... '

                elif part[9] == 'is':
                    ll = ' '.join(part[12:])
                else:
                    ll = ' '.join(part[7:])
                if part[-1] != 'OK' and part[-1] != 'ERROR':
                    if part[6] == "copying" and not cnl:
                        copy_to_tape.printline('\n')
                    copy_to_tape.printline(ll)
                    cnl = 0
                else:
                    copy_to_tape.printline(ll + '\n')
                    cnl = 1
        elif key == "SWAPPING_METADATA":
            if part[6] != "swapping":
                if part[11] == "been":
                    ll = part[6] + ' <--> ' + part[8] + \
                        ' ' + part[-2] + ' ' + part[-1]
                elif part[11] == "already":
                    ll = part[6] + ' <--> ' + part[8] + \
                        ' have already been swapped ... OK'
                else:
                    ll = ' '.join(part[6:])
                swap_metadata.printline(ll + '\n')
        elif key == "MIGRATING_VOLUME":
            ll = ' '.join(part[6:])
            volume_status.printline(ll + '\n')

        if part[-1] == "ERROR":
            error_info.printline(l + '\n')
        root.update()
        # time.sleep(1)
    root.mainloop()

# scan_watch() -- for "migrate.py --scan-vol ..."


def scan_watch(l1):
    global single_step, quit_now, piped

    # root window
    root = tkinter.Tk()
    root.title("Final Scan Watch")
    root.protocol("WM_DELETE_WINDOW", set_quit)

    # create menu bar
    menu = tkinter.Menu(root)
    root.config(menu=menu)
    filemenu = tkinter.Menu(menu)
    menu.add_cascade(label="File", menu=filemenu)
    filemenu.add_command(label="Exit", command=set_quit)
    helpmenu = tkinter.Menu(menu)
    menu.add_cascade(label="Help", menu=helpmenu)
    helpmenu.add_command(label="Help me!", command=show_help)

    # create tool bar
    tool_frame = tkinter.Frame(root)
    quick_button = tkinter.Button(
        tool_frame,
        width=10,
        text='Exit',
        command=set_quit)
    quick_button.pack(side=tkinter.LEFT)
    action_button = StatusButton(tool_frame, ["Resume", "Pause"], width=10)
    action_button.pack(side=tkinter.LEFT)
    single_step_button = tkinter.Button(
        tool_frame,
        width=10,
        text='Step',
        command=set_single_step,
        state=tkinter.DISABLED)
    single_step_button.pack(side=tkinter.LEFT)
    help_button = tkinter.Button(
        tool_frame,
        width=10,
        text='Help',
        command=show_help)
    help_button.pack(side=tkinter.RIGHT)
    tool_frame.pack(fill=tkinter.X)

    # pack command_line and volume_status in the same frame
    frame1 = tkinter.Frame(root)
    command_line = InfoBox(frame1, h=5, w=133, heading="Command Line")
    command_line.pack(side=tkinter.LEFT)
    volume_status = InfoBox(frame1, h=5, w=63, heading="Volume Status")
    volume_status.pack(side=tkinter.LEFT)
    frame1.pack()
    error_info = InfoBox(root, h=10, heading="Errors")
    error_info.s.config(foreground="#FF0000")
    error_info.pack()
    progress = InfoBox(root, h=20, heading="Progress")
    progress.pack()
    final_scan = InfoBox(root, h=20, heading="Final Scan")
    final_scan.pack()

    command_line.printline(l1 + '\n')
    while True:
        if quit_now:
            sys.exit(0)
        if action_button.get_state() == "Pause":
            single_step_button.config(state=tkinter.NORMAL)
            if single_step:
                single_step = 0
            else:
                # sleep so that it won't consume too
                # much CPU cycle while being paused
                time.sleep(0.1)
                # still needs to process the events
                root.update()
                continue
        else:
            single_step_button.config(state=tkinter.DISABLED)
        if input_queue.empty():
            time.sleep(0.1)
            root.update()
            continue
        l = input_queue.get(True)

        # processing line
        part = l.split()
        key = part[5]
        if key == "COMMAND":
            ll = ' '.join(part[7:])
            command_line.printline(ll + '\n')
        elif key == "FINAL_SCAN_VOLUME":
            if part[6] != "set":
                ll = ' '.join(part[6:])
                if part[7] == "volume" or part[6] == "restore":
                    volume_status.printline(ll + '\n')
                else:
                    final_scan.printline(ll + '\n')
            elif part[7] == "comment":
                ll = ' '.join(part[6:])
                volume_status.printline(ll + '\n')
        if part[-1] == "ERROR":
            error_info.printline(l + '\n')
        root.update()
    root.mainloop()


if __name__ == "__main__":   # pragma: no cover
    if len(sys.argv) > 1:
        f = open(sys.argv[1])
        piped = 0
    else:
        f = sys.stdin
        piped = 1

    l = f.readline()
    part = l.split()

    pid = _thread.start_new_thread(read_input, (f,))

    # determine which one to call based on the command line switch

    # some padding to make it prettier
    if part[8] == "--vol":
        part[8] = part[8] + '    '
        migration_watch(' '.join(part[7:]))
    elif part[8] == "--scan-vol":
        scan_watch(' '.join(part[7:]))
