#!/usr/bin/env python
# -*- coding: utf-8 -*- 
# vim: noai:ts=4:sw=4 
import ephem
import os
import time
import sys
import socket
import urllib
import math
import json
import traceback
import fileinput
import curses
import threading
import smtplib
from optparse import OptionParser
from email import encoders
from email.mime.base import MIMEBase
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
import logging
import logging.config
import logging.handlers
from threading import Event, Thread
from espeak import espeak
from datetime import datetime

__version__ = '0.0.3'

_SOL = 299792458.  # speed of light in meters/second
_printLine = ''
_notify = 30 
_useVoice = False
_statusSleep = 1
_curses = True
_lat = 43.1475
_long = -77.5610
_workDir = os.getcwd() + '/'
_tleFile = _workDir + "sat.txt"

os.environ['TERM'] = 'xterm'
os.environ['TERMINFO'] = '/usr/share/terminfo'

_MAJOR_VERSION = "0."
_MINOR_VERSION = "2."
_SUB_VERSION = "0"

__author__ = "Edward Brown"
__copyright__ = "Copyright 2013, jetcom.org"
__credits__ = ["Edward Brown"]
__license__ = "GPL V3"
__version__ = "$Revision: 10 $"
__maintainer__ = "Edward Brown"
__email__ = "edwardb@gmail.com"
__status__ = "alpha"
__revdate__ = "$Date: 2011-10-16 20:24:02 -0400 (Sun, 16 October 2011) $"
__commitby__ = "$Author: emb $"
__revdate__ = '$Date: 2012-11-02 15:19:00 -0400 (Fri, 02 Nov 2012) $'
__revision__ = '$Revision: 27565 $'


#43.1475
#-77.5610
#178 m


# Load tle file
def loadTLE():
    # download weather and amateur tle files from celestrak. For know it gets new
    # files every time it runs. then it copies both files to "sat.txt"
    touch(_workDir + 'special.tle')
    urllib.urlretrieve('http://www.celestrak.com/NORAD/elements/amateur.txt', _workDir + 'amateur.txt')
    urllib.urlretrieve('http://www.celestrak.com/NORAD/elements/weather.txt', _workDir + 'weather.txt')
    filenames = [_workDir + 'amateur.txt'] + [_workDir + 'weather.txt'] + [_workDir + 'special.tle']
    with open('sat.txt', 'w') as fout:
        for line in fileinput.input(filenames):
            fout.write(line)

    f = open(_tleFile)
    z = []
    line1 = f.readline()
    while line1:     # read tle and create an object for each satellite
        line2 = f.readline()
        line3 = f.readline()
        # We are only interested in LEO (Low Earth Orbit) satellites so check the mean motion
        # of the satellite. If it is below 2.0 skip over that satellite. 
        # See http://en.wikipedia.org/wiki/Two-line_element_set for an explanation of the
        # TKE file layout.
        if float(line3[52:62]) > 2.0:
            y = ephem.readtle(line1,line2,line3)
            z.append(y)
            print y.name
        line1 = f.readline()
    f.close()
    print "%i satellites loaded into list"%len(z)
    return z 

class RepeatTimer(Thread):
    def __init__(self, interval, function, iterations=0, args=[], kwargs={}):
        Thread.__init__(self)
        self.interval = interval
        self.function = function
        self.iterations = iterations
        self.args = args
        self.kwargs = kwargs
        self.finished = Event()
 
    def run(self):
        count = 0
        while not self.finished.is_set() and (self.iterations <= 0 or count < self.iterations):
            self.finished.wait(self.interval)
            if not self.finished.is_set():
                self.function(*self.args, **self.kwargs)
                count += 1
 
    def cancel(self):
        self.finished.set()

# Set location info
def loadHome():
    z  = ephem.Observer()
    z.lon = math.radians(-77.5610)
    z.lat = math.radians(43.1475)
    z.elevation = 178
    # Set pressure to zero to turn off adjustments for atmospheric refraction
    z.pressure = 0
    return z

def touch(fname):
    try:
        os.utime(fname, None)
    except:
        open(fname, 'a').close()

def say(x):
    # Say info
    espeak.Parameter.Rate = 120
    espeak.Parameter.Wordgap = 10
    espeak.synth(x)
    return (0)
    
def pathLoss(range):
    # Calculating this just because I can.
    # PATH LOSS(dB) = 32.44 + 20*log(F(MHz)) + 20*log(D(km))
    # range = distance in kilometers
    PL = 32.45 + (20 * math.log10(100)) + (20 * math.log10(range))
    return PL
    
def dop_shift(crv):
    # crv = current range velocity in meters/second
    # ds = doppler shift in Hz at a frequency of 100 MHz.
    # since the shift is linear based on frequency divide the
    # actual frequency by 100 and and multipy the doppler shift be the 
    # result
    ds = (-crv / _SOL) * 100e6
    return ds
        
if __name__ == "__main__":
    satList = loadTLE()
    home = loadHome()
    
    if _curses:
        stdscr = curses.initscr()
        curses.noecho()
        curses.cbreak()
        curses.start_color()
        curses.init_pair(1, curses.COLOR_BLACK, curses.COLOR_YELLOW)
        curses.init_pair(2, curses.COLOR_WHITE, curses.COLOR_RED)
        curses.curs_set(0)
        stdscr.clear()
        stdscr.refresh()
    else:
        os.system('clear')
        
    with open('sat_info.json') as infile:
        nameDict = json.load(infile)
    
    while 1:
        info = []    # Results of calculations
        visible = [] # Hold info about visible satellites
        soon = []     # Holds info for satellites which will be visible within the next 30 minutes
        now = ephem.now() # Sets the time to be used in all the calculations
        home.date = now
                    
        for i in range(len(satList)):
            # azimuth, elevation, range, and range rate), and right ascension and declination
            try:
                # this computes the data for the satellite as seen form the home location
                satList[i].compute(home)
                # Here is where the problem initially starts.
                # The next_pass returns 6 elements with a value of none.
                # Sometimes it will work for several minutes other time quite quickly
                # I also tried computing the next_pass info using the the compute(home)
                # The Docs suggest that you use the next_pass method for LEO's because 
                # that is more accurate.
                next_pass = home.next_pass(satList[i])
                c_az = math.degrees(satList[i].az)
                c_el = math.degrees(satList[i].alt)
                c_altitude = satList[i].elevation
                c_range = (satList[i].range / 1000)
                crv = satList[i].range_velocity
                doppler = dop_shift(crv)
                path_loss = pathLoss(c_range)
                aos = next_pass[0]
                los = next_pass[4]
                inital_az = math.degrees(next_pass[1])
                final_az = math.degrees(next_pass[5])
                cat_num = satList[i].catalog_number
                # spk_name supplies a simplified name foe espeak to use
                spk_name = nameDict[str(cat_num)]['speak']
                disp_name = nameDict[str(cat_num)]['short']
                # create a list[] of the info  
                new = (satList[i].name, cat_num, c_az, c_el, aos, inital_az, los, final_az, str(spk_name), str(disp_name))
                info.append(new)
                # Calc the number of minutes until visible (AOS)
                timeToRise = (aos - now) * 1440
                # Calc the number of minutes the object sets (LOS)
                timeLeft = (los - now) * 1440
            except:
                # A generally unproductive attempt to track down the problem, skip it and restart.
                e = sys.exc_info()[0]
                print( "<p>Error: %s</p>" % e )
                continue
            if _useVoice:
                # Talk to me
                if current_el > 0:
                    say("%s,,, is visible.. Current elevation is,,, %d,,, degrees, at an azmuth of,,, %d,,, degrees a generally unproductivend a doppler shift of %d Hertz." % (info[i][9], c_el, c_az, doppler))
                if timeToRise < 30 and timeToRise > 29:
                    say("%s,,, WILL BE MAKING A PASS IN, 30 MINUTES." % (info[i][8]))            
                if  timeToRise < 10 and timeToRise > 9:
                    say("%s,,, WILL BE MAKING A PASS IN, 10 MINUTES." % (info[i][8]))
                if timeToRise < 5 and timeToRise > 4:
                    say("%s,,, WILL BE MAKING A PASS IN 5, MINUTES." % (info[i][8]))
            
            if c_el > 0:
                # If it's visible display info in red/white
                visible.append('{:<20} {:2.0f}    {:3.0f}     {:-5.0f}Hz       {:5.1f} {:>24}\n'
                      .format(info[i][9], c_el, c_az, doppler, timeLeft, ""))                  
            elif timeToRise < 30:
                # if it less than 30 minutes until visible show on screen in yellow/black
                soon.append('{:<20} will be visible in {:2.0f} minutes at an azimuth of {:3.0f} {:>7}\n'
                    .format(info[i][9], timeToRise, inital_az, ""))

        if len(visible) > 0:
            # Create top of screen. The screen is buffered so it will not change until the refresh
            c = curses.color_pair(2) | curses.A_BOLD | curses.A_UNDERLINE
            stdscr.addstr('Satellite Name       El     Az     Doppler    TimeLeft  {:>23}\n' .format(time.strftime("%H:%M:%S Z", time.gmtime())),c)
                
            for p in range(len(visible)):                
                stdscr.addstr(str(visible[p]), curses.color_pair(2))
        else:
            c = curses.color_pair(2) | curses.A_BOLD | curses.A_BLINK
            stdscr.addstr('No visible satellites found\n', c )

        if len(soon) > 0:
            # Create bottom of screen
            for p in range(len(soon)):
                stdscr.addstr(str(soon[p]), curses.color_pair(1))
        else:
            stdscr.addstr('No satellites scheduled in the next 30 minutes\n', curses.color_pair(1))            

        stdscr.refresh()  # and voila we see the screen (I have an LCD3 screen to go on the beagle bone black)
        stdscr.clear() #Clear screen for next display round. This doesnt happen until it gets back to the refresh
    time.sleep(10*_statusSleep) # sleep 10 seconds and start again
    if _curses:
        curses.nocbreak(); stdscr.keypad(0); curses.echo()
        curses.endwin()