#!/usr/bin/env python

from Tkinter import *
from tkFont import Font

import cmath
import exceptions
import math
import os
import select
import socket
import string
import sys
import time


debug = 1 

###

DEFAULTPORT = 60126

def scale_to_display(x, y, w, h):
    """Convert coordinates on unit circle to Tk display coordinates for
    a window of size w, h"""
    return (x+1)*(w/2), (1-y)*(h/2)

def HMS(s):
    h = s / 3600
    s = s - (h*3600)
    m = s / 60
    s = s - (m*60)
    return "%02d:%02d:%02d" % (h, m, s)

def my_atof(s):
    if s[-1] == 'L':
        s = s[:-1] #chop off any trailing "L"
    return string.atof(s)

def rgbtohex(r,g,b):
    r=hex(r)[2:]
    g=hex(g)[2:]
    b=hex(b)[2:]
    if len(r)==1:
        r='0'+r
    if len(g)==1:
        g='0'+g
    if len(b)==1:
        b='0'+b
    return "#"+r+g+b

def strip_domain(hostname):
    parts = string.split(hostname, '.')
    if parts[-1]=='gov' and parts[-2]=='fnal':
        parts = parts[:-2]
    return string.join(parts,'.')

#######################################################################################
#MOST OF THE FUNCTIONS WILL BE HANDLED BY THE MOVER.
#IT'S FUNCTIONS INCLUDES:
#     DRAW() - DRAWS MOST FEATURES ON THE MOVERS
#     UPDATE_STATE() - AS THE STATE OF THE MOVERS CHANGE, DISPLAY FOR STATE WILL BE UPDATED
#     UPDATE_TIMER() - TIMER ASSOCIATED W/STATE, WILL UPDATE FOR EACH STATE
#     LOAD_TAPE() - TAPE GETS LOADED ONTO MOVER:
#                                  GRAY INDICATES ROBOT RECOGNIZES TAPE AND LOADED IT
#                                  ORANGE INDICATES WHEN CLIENT ACTUALLY RECOGNIZES TAPE     
#     UNLOAD_TAPE() - WILL UNLOAD TAPE TO SIDE OF EACH MOVER, READY FOR ROBOT TO REMOVE F/SCREEN
#     SHOW_PROGRESS() - INDICATES PROGRESS OF EACH DATA TRANSFER; IS IT ALMOST COMPLETE?
#     TRANSFER_RATE() - RATE AT WHICH TRANSFER BEING SENT; CALCULATES A RATE
#     UNDRAW() - UNDRAWS THE FEATURES FROMTHE MOVERS
#     POSITION() - CALCULATES THE POSITION FOR EACH MOVER
#     REPOSITION() - REPOSITION EACH FEATURE AFTER SCREEN HAS BEEN MOVED
#     __DEL__() - CALLS UNDRAW() MODULE AND DELETES FEATURES
#
######################################################################################

class Mover:
    def __init__(self, name, display, index=0,N=0):
        self.name = name
        self.display = display
        self.index = index
        self.N=N
        self.width = 125
        self.height = 30
        self.state = "Unknown"
        now = time.time()
        self.timer_started = now
        self.timer_seconds = 0
        self.timer_string = '00:00:00'
        self.last_activity_time = now
        self.connection = None
        self.rate = 0.0
        self.x, self.y = 0, 0 # Not placed yet
        self.volume = None
        #These 3 pieces make up the progress gauge display
        self.progress_bar = None
        self.progress_bar_bg = None
        self.progress_percent_display = None
        # This is the numeric value.  "None" means don't show the progress bar.
        self.percent_done = None
        self.removed = 0

    def draw(self):
        x, y = self.x, self.y
        self.outline =  self.display.create_rectangle(x, y, x+self.width, y+self.height, fill='black')
        self.label = self.display.create_text(x+60, y+40, text=self.name)
        self.state_display = self.display.create_text(x+90, y+8, text=self.state, fill='light blue')
        self.timer_display = self.display.create_text(x+100, y+22, text='00:00:00',fill='white')
        if self.percent_done != None:
            bar_width = 38
            self.progress_bar_bg = self.display.create_rectangle(x+5,y+17,x+6+bar_width,y+26,fill='magenta')
            self.progress_bar = self.display.create_line(x+5,y+17,
                                                         x+6+(bar_width*self.percent_done/100.0), y+22,
                                                         fill='yellow', width=8)
            
            self.progress_percent_display =  self.display.create_text(x+60, y+22,
                                                              text = str(self.percent_done)+"%",
                                                              fill = 'green') #,font=8)

    def update_state(self, state):
        if state == self.state:
            return
        self.state = state
        x, y = self.x, self.y
        self.display.delete(self.state_display) # "undraw" the prev. state message
        self.state_display = self.display.create_text(x+90, y+8, text=self.state, fill='light blue')
        now = time.time()
        self.timer_started = now
        if state != 'ACTIVE':
            self.show_progress(None)
        self.update_timer(0)
        
    def update_timer(self, seconds):
        x, y = self.x, self.y
        self.timer_seconds = seconds
        self.timer_string = HMS(seconds)
        self.display.delete(self.timer_display)
        self.timer_display = self.display.create_text(x+100, y+22, text=self.timer_string,fill='white')

    def load_tape(self, volume_name,load_state):
        self.volume = Volume(volume_name, self.display)
        self.volume.x, self.volume.y = self.x + 5, self.y + 2
        self.volume.draw(load_state)

    def unload_tape(self, volume):
        
        if volume != self.volume.name: 
            print "Mover does not have this tape : ", volume
        else:
           k=self.index
           N=self.N
           angle=math.pi/(N-1)
           i=(0+1J)
           coord=.75+.5*cmath.exp(i*(math.pi/2 + angle*k))
           x,y=coord.real,coord.imag
           self.volume.x, self.volume.y = scale_to_display(x, y, self.display.width, self.display.height)
           self.volume.moveto(self.volume.x, self.volume.y)
           self.volume.draw(load_state='loaded')

    def robot_move(self, volume_name, robot_command):
        robot=self.display.robot
        k=self.index
        N=self.N
        angle=math.pi/(N-1)
        i=(0+1J)
        if robot_command == 'moveto':
            coord =.99+.5*cmath.exp(i*(math.pi/2 + angle*k))
            x,y=coord.real,coord.imag
        else: #remove the volume from the screen
            coord =1.65+.5*cmath.exp(i*(math.pi/2 + angle*k))
            x,y=coord.real, coord.imag
            self.volume.x, self.volume.y = scale_to_display(x, y, self.display.width, self.display.height)
            self.volume.moveto(self.volume.x-100, self.volume.y)
            self.volume.draw(load_state='loaded')
        robot.x, robot.y = scale_to_display(x, y, self.display.width, self.display.height)
        robot.moveto(robot.x, robot.y)
        robot.draw()

    def show_progress(self, percent_done):
        x,y=self.x,self.y
        bar_width = 38
        if percent_done == self.percent_done:
            #don't need to redraw
            return
        
        self.percent_done = percent_done

        # Undraw the old progress gauge
        if self.progress_bar:
            self.display.delete(self.progress_bar)
            self.progress_bar = None
        if self.progress_bar_bg:
            self.display.delete(self.progress_bar_bg)
            self.progress_bar_bg = None
        if self.progress_percent_display:
            self.display.delete(self.progress_percent_display)
            self.progress_percent_display = None
            
        if self.percent_done is None:
            #Don't display the progress gauge
            return

        # Draw the new progress gauge
        self.progress_bar_bg = self.display.create_rectangle(x+5,y+17,x+6+bar_width,y+26,fill='magenta')
        self.progress_bar = self.display.create_line(x+6,y+22,
                                                     x+6+bar_width*(self.percent_done/100.0),y+22,
                                                     fill='yellow', width=8)
        self.progress_percent_display =  self.display.create_text(x+60, y+22,
                                                                  text = str(self.percent_done)+"%",
                                                                  fill = 'green') #,font=8)

    def transfer_rate(self, num_bytes, total_bytes):
        #keeps track of last number of bytes and time; calculates rate in bytes/second
        self.b1=num_bytes
        self.t1=time.time()
        rate=(self.b1-self.b0)/(self.t1-self.t0)
        self.b0=self.b1
        self.t0=self.t1
        return rate

    def undraw(self):
        self.display.delete(self.timer_display)
        self.display.delete(self.outline)
        self.display.delete(self.label)
        self.display.delete(self.state_display)
        self.display.delete(self.tape_slot)
        self.display.delete(self.progress_bar_bg)
        self.display.delete(self.progress_bar)
        self.display.delete(self.progress_percent_display)
    
    def position(self, N):
        k = self.index
        if N == 1: ## special positioning for a single mover.
            k = 1
            angle = math.pi / 2
        else:
            angle = math.pi / (N-1)
        i=(0+1J)
        coord=.75+.8*cmath.exp(i*(math.pi/2 + angle*k))
        x, y=coord.real, coord.imag
        self.x, self.y = scale_to_display(x, y, self.display.width, self.display.height)

    def reposition(self, N):
        if self.volume:
            volume_offset = self.volume.x-self.x, self.volume.y - self.y
        self.undraw()
        self.position(N)
        self.draw()
        if self.volume:
            self.volume.undraw()
            self.volume.x, self.volume.y = self.x+volume_offset[0], self.y + volume_offset[1]
            self.volume.draw()
        if self.connection:
            self.connection.undraw()
            self.connection.draw()
        
    def __del__(self):
        self.undraw()



######################################
#
#                           CLASS: VOLUME
#
######################################

class Volume:
    def __init__(self, name, display):
        self.name = name
        self.display = display
        self.loaded = 0
    
    def draw(self,load_state):
        self.loaded=load_state
        x, y = self.x, self.y
        if self.loaded:
            tape_color = 'orange'
            label_color= 'white'
        else:
            tape_color = 'grey'
            label_color='black'
        self.outline = self.display.create_rectangle(x, y, x+50, y+11, fill = tape_color)
        self.label = self.display.create_text(x+25, y+6, text=self.name, fill = label_color)

    def moveto(self, x, y):
        self.display.move(self.outline, x, y)
        self.display.move(self.label, x, y)
        self.x, self.y = x, y

    def undraw(self):
        self.display.delete(self.outline)
        self.display.delete(self.label)

    def __del__(self):
        self.undraw()


######################################
#
#                           CLASS: CLIENT
#
######################################
    
class Client:

    def __init__(self, name, display):
        self.name = name
        self.width = 100
        self.height = 26
        self.display = display
        self.last_activity_time = 0.0 
        self.n_connections = 0
        self.waiting = 0
        i = 0
        ## Step through possible positions in order 0, 1, -1, 2, -2, 3, -3, ...
        while display.client_positions.has_key(i):
            if i == 0:
                i =1
            elif i>0:
                i = -i
            else:
                i = 1 - i
        self.index = i
        display.client_positions[i] = self
        self.x, self.y = scale_to_display(-0.9, i/10., display.width, display.height)

    def draw(self):
        x, y = self.x, self.y
        if self.waiting:
            color = rgbtohex(100,100,100)
        else:
            color = 'green'
        self.outline =  self.display.create_oval(x, y, x+self.width, y+self.height, fill=color)
        self.label = self.display.create_text(x+self.width/2, y+self.height/2, text=self.name)
        
    def undraw(self):
        self.display.delete(self.outline)
        self.display.delete(self.label)

    def update_state(self):
        if self.waiting:
            color = rgbtohex(100,100,100)
        else:
            color = 'green'
        self.display.itemconfigure(self.outline, fill = color) 
        
    def reposition(self):
        self.undraw()
        self.x, self.y = scale_to_display(-0.9, self.index/10.,
                                          self.display.width, self.display.height)
        self.draw()
        
    def __del__(self):
        self.undraw()



######################################
#
#                           CLASS: CONNECTION
#
######################################
        
class Connection:
    """ a line connecting a mover and a client"""
    def __init__(self, mover, client, display):
        self.mover = mover
        self.client = client
        self.display = display
        self.dashoffset = 0 #current offset
        self.start_offset = 0 #offset when we got most recent rate info
        self.rate = 0 #pixels/second, not MB
        self.segment_start_time = 0
        self.segment_stop_time = 0

    def draw(self):
        mover_end = (self.mover.x,
                     self.mover.y + self.mover.height/2.0) # middle of left side
        client_end = (self.client.x + self.client.width,
                      self.client.y + self.client.height/2.0) #middle of right side
        x_distance = mover_end[0] - client_end[0]
        self.line = self.display.create_line(mover_end[0], mover_end[1],
                                             mover_end[0]-x_distance/3, mover_end[1],
                                             client_end[0]+x_distance/3,client_end[1],
                                             client_end[0],client_end[1],
                                             dash='...-',width=2,
                                             dashoffset = self.dashoffset,
                                             smooth=1)
    def undraw(self):
        self.display.delete(self.line)

    def __del__(self):
        self.undraw()
        
    def update_rate(self, rate):
        now = time.time()
        self.segment_start_time = now #starting time at this rate
        self.segment_stop_time = now + 5 #let the animation run 5 seconds
        self.segment_start_offset = self.dashoffset
        self.rate = rate
        
    def animate(self, now=None):
        if now is None:
            now=time.time()
        if now >= self.segment_stop_time:
            return

        new_offset = self.segment_start_offset + self.rate * (now-self.segment_start_time) 
    
        if new_offset != self.dashoffset:  #we need to redraw the line
            self.dashoffset = new_offset
            self.display.itemconfigure(self.line,dashoffset=new_offset)



######################################
#
#                           CLASS: ROBOT
#
######################################
class Robot:
    def __init__(self,display):
        self.display = display
        self.x, self.y = display.width, display.height/2
        

    def draw(self):
       
        self.robot_hand = self.display.create_line(self.x-125,self.y-60, self.x-65,self.y-60, fill='black', width = 15)
        self.robot_arm = self.display.create_line(self.x-80,self.y, self.x-100,self.y-60, fill='black', width = 15)
        self.robot_shoulder = self.display.create_line(self.x-80,self.y, self.x,self.y, fill='black', width = 15)
        self.bolt = self.display.create_oval(self.x-68,self.y-8, self.x-88,self.y+8, fill='grey')

    def moveto(self, x, y):
        self.display.move(self.robot_hand, x,y)
        self.display.move(self.robot_arm, x, y)
        self.display.move(self.robot_shoulder, x, y)
        self.display.move(self.bolt,x,y)
        self.x, self.y=x,y
    
    def undraw(self):
        self.display.delete(self.robot_shoulder)
        self.display.delete(self.robot_arm)
        self.display.delete(self.robot_hand)
        self.display.delete(self.bolt)
  
    def __del__(self):
        self.undraw()


    


######################################
#
#                           CLASS: TITLE
#
######################################
        
class Title:
    def __init__(self, text, display):
        self.text = text #this is just a string
        self.display = display
        self.tk_text = None #this is a tk Text object
        self.fill = None #color to draw with
        self.font = Font(size=36, family="Helvetica")
        self.length = 2.5  #animation runs 2.5 seconds
        now = time.time()
        self.start_time = now
        self.stop_time = now + self.length

    def draw(self):
        #center this in the entire canvas
        self.tk_text = self.display.create_text(self.display.width/2, self.display.height/2,
                                                text=self.text,
                                                font=self.font, justify=CENTER)
    def animate(self, now=None):
        if now==None:
            now = time.time()
        if not self.tk_text:
            self.draw()
        elapsed = now - self.start_time
        startrgb = 0,0,0
        endrgb = 173, 216, 230
        currentrgb = [0,0,0]
        for i in range(3):
            currentrgb[i] = int(startrgb[i] + (endrgb[i]-startrgb[i])*(elapsed/self.length))
        fill=rgbtohex(currentrgb[0], currentrgb[1], currentrgb[2])
        self.display.itemconfigure(self.tk_text, fill=fill)
    def __del__(self):
        self.display.delete(self.tk_text)
        

######################################
#
#                           CLASS: DISPLAY
#
######################################
    
class Display(Canvas):
    """  The main state display """
    def __init__(self, master, **attributes):
        ##** means "variable number of keyword arguments" (passed as a dictionary)
        Canvas.__init__(self, master)
        self.configure(attributes)
        self.pack(expand=1, fill=BOTH)
        self.stopped = 0
        self.width =  int(self['width'])
        self.height = int(self['height'])
        
        self.movers = {} ## This is a dictionary keyed by mover name,
                      ##value is an instance of class Mover
        self.clients = {} ## dictionary, key = client name, value is instance of class Client
        self.client_positions = {} #key is position index (0,1,-1,2,-2) and value is Client
        self.volumes={}
        self.title_animation = None
        
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM) #use IP addressing and UDP protocol
        port = os.environ.get("ENSTORE_WATCH_PORT", DEFAULTPORT)
        myaddr = ("", int(port)) # "" = local host
        s.bind(myaddr)
        self.inputs = [s]
        
    def create_movers(self, mover_names):
        #Create a Mover class instance to represent each mover.
        N = len(mover_names)
        for k in range(N):
            mover_name = mover_names[k]
            ##These are coordinates on the unit circle
            M = Mover(mover_name, self, index=k, N=N)
            self.movers[mover_name] = M
            M.position(N)
            M.draw()

    def reposition_movers(self):
        items = self.clients.items()
        N = len(items) #need this to determine angle
        for mover_name, mover in items:
            mover.reposition(N)            
                
    def reposition_clients(self):
        for client_name, client in self.clients.items():
            client.reposition()
            
    def handle_command(self, command):
        ## Accept commands of the form:
        # 1 word:
        # quit
        # 3 words:
        # state MOVER_NAME STATE_NAME
        # connect MOVER_NAME CLIENT_NAME
        # disconnect MOVER_NAME CLIENT_NAME
        # load MOVER_NAME VOLUME_NAME
        # unload MOVER_NAME VOLUME_NAME
        # 4 words:
        # transfer MOVER_NAME nbytes total_bytes
        # variable number of words
        # movers M1 M2 M3 ...
        # title (?)
        
        now = time.time()
        command = string.strip(command) #get rid of extra blanks and newlines
        words = string.split(command)
        if not words: #input was blank, nothing to do!
            return
        #"quit" is the only 1-word command

        if words[0]=='quit':
            self.stopped = 1
            return

        if words[0]=='movers':
            self.create_movers(words[1:])
            return

        if words[0]=='client':
            client_name = words[1]
            client = self.clients.get(client_name) 
            if client is None: #new client
                client = Client(client_name, self)
                self.clients[client_name] = client
                client.waiting = 1
                client.draw()
            return

        if words[0]=='robot':
            self.robot=Robot(self)
            self.robot.draw()
            return

        if words[0]=='title':
            title = command[6:]
            title=string.replace(title, '\\n', '\n')
            self.title_animation = Title(title, self)
            return
            
        # all following commands have the name of the mover in the 2nd field
        mover_name = words[1]
        mover = self.movers.get(mover_name)
  
        if words[0]=='delete':
            del self.movers[mover_name]
            return

        if len(words) < 3:
            print "Error, bad command", command
            return
        if not mover:#This is an error, a message from a mover we never heard of
            return
        if words[0]=='state':
            what_state = words[2]
            mover.update_state(what_state)
            return
        
        if words[0]== 'connect':
            #print "CONNECT", words
            client_name = strip_domain(words[2])
            client = self.clients.get(client_name)
            if not client: ## New client, we must add it
                client = Client(client_name, self)
                self.clients[client_name] = client
                client.draw()
            client.waiting = 0
            client.update_state() #change fill color if needed
            client.last_activity_time = now
            connection = Connection(mover, client, self)
            mover.t0 = now
            mover.b0 = 0
            connection.update_rate(0)
            connection.draw()
            mover.client = client
            mover.connection = connection
            client.n_connections = client.n_connections + 1
            return
        
        if words[0]=='disconnect':
            client_name = strip_domain(words[2])
            client = self.clients.get(client_name)
            if not client: ## this client is not displayed
                return
            if mover.connection:
                mover.connection = None
            if mover.client:
                mover.client = None
                client.n_connections = client.n_connections - 1
            mover.t0 = time.time()
            mover.b0 = 0
            mover.show_progress(None)
            return

        if words[0]=='loading':
            what_volume = words[2]
            volume=self.volumes.get(what_volume)
            if volume is None:
                volume=Volume(what_volume,self)
                self.volumes[what_volume]=volume
                mover.load_tape(what_volume,0)
            else:
                print "!!! Error !!!  Volume already exists."
            return

        if words[0]=='loaded':
            what_volume = words[2]
            mover.load_tape(what_volume,1)
            return
        
        if words[0]=='unload':
            what_volume = words[2]
            mover.unload_tape(what_volume)
            return

        if words[0] =='moveto':
            what_volume = words[2]
            mover.robot_move(what_volume,words[0])
            return

        if words[0] =='remove':
            what_volume = words[2]
            mover.robot_move(what_volume,words[0])
            return
        
        if len(words)<4: 
            print "Error, bad command", command
            return
        
        if words[0]=='transfer':
            num_bytes = my_atof(words[2])
            total_bytes = my_atof(words[3])
            percent_done = abs(int(100 * num_bytes/total_bytes))
            mover.show_progress(percent_done)
            rate = mover.transfer_rate(num_bytes, total_bytes) / (256*1024)
            mover.connection.update_rate(rate)
            mover.client.last_activity_time = time.time()

            
    def mainloop(self):
        # Our mainloop is different from the normal Tk mainloop in that we have
        # (A) an interval timer to control animations and
        # (B) we check for commands coming from standard input

        while not self.stopped:
            size = self.winfo_width(), self.winfo_height()
            if size != (self.width, self.height):
                # size has changed
                self.width, self.height = size
                if self.clients:
                    self.reposition_clients()
                if self.movers:
                    self.reposition_movers()
                    
            #test whether there is a command ready to read, timeout in 1/30 second.
            readable, junk, junk = select.select(self.inputs, [], [], 1.0/30)

            for r in readable:
                command = r.recv(1024)
                if debug:
                    self.handle_command(command)
                else:
                    try:
                        self.handle_command(command)
                    except: 
                        print "cannot handle", command 
                    
            ## Here is where we handle periodic things
            now = time.time()
            #### Update all mover timers
            for mover in self.movers.values():
                seconds = int(now - mover.timer_started)
                if seconds != mover.timer_seconds:
                    mover.update_timer(seconds)           #We must advance the timer
                if mover.connection:
                    mover.connection.animate(now)

            #### Check for unconnected clients
            for client_name, client in self.clients.items():
                if client.n_connections > 0:
                    continue
                if now - client.last_activity_time >  5: # grace period
                    del client

            #### Handle titling
            if self.title_animation:
                if now > self.title_animation.stop_time:
                    self.title_animation = None
                else:
                    self.title_animation.animate(now)
                
            ####force the display to refresh
            self.update()
        

if __name__ == "__main__":
    display = Display(None, width=1000, height=700,
                      background=rgbtohex(173, 216, 230))
    display.mainloop()


