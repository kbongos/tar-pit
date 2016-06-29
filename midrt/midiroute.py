#!/usr/bin/python
# !/usr/bin/env python
# midiroute - midi router
#  This is aimed at building midi routers for music control purposes.
# My initial devices to use with include Yosihimi synth, m-audio keyboard
#  controls.
# kbongosmusic at gmail_com - licensed as GPLv2.
#
# reference- mididings has good web link to midi spec online.
#   http://www.somascape.org/midi/tech/spec.html
# yoshimi/doc/Yoshi_Zyn_NRPNs.txt - for effect MIDI NRPN doc.
# yoshimi/doc/Banks.txt
# Can turn CC dumps on under Settings, MIDI tab, dumps to stdout.
#  My bank changes were not working because I checked Settings->MIDI->
#    'Enable Bank Root Change', with Bank Root Change:0(default).  This maybe conflicts
#    with Bank Change:MSB below(that I believe is CC 0(msb)).  I would get this dump msg:
#       'Set root 15 /usr/share/yoshimi/banks' and then it always switched to first bank.
#    Once I unchecked that it worked.  Not sure what this 'bank root change' is yet,
#    must be a way to change to a different set of banks maybe?
#  FIXED: my mistake, leave MSB 0, set using LSB seems the standard method.
from __future__ import print_function
import os,sys
import gzip
#import re
#import array
import time
import copy
import atexit
import termios
import select
import subprocess

import alsaseq, alsamidi

import yoshibanks

# some global vars:
verbose = 0
globs = None # ref to Globals object


# following watches modwheel, when > 100 it allows selecting favorite bank
# prog based on midi-key hit(based on octave, 12 picks).  I don't really
# like this so far.
MODWHEEL_BANKPROG_KEY_FEATURE = True

# Following will turn modwheel into differential pitch adjustment.
# So do same as pitch wheel but without the dead-spot, and then auto
# reset pitch back to zero on next key event.
MODWHEEL_TO_PITCH_FEATURE = True

#------------------------
def runproc(exe_str):
    # run an external program,collect output string
    ret_str = ''
    if (1):
        f = os.popen(exe_str)
        s = f.readline()
        while s:
            ret_str += s
            s = f.readline()

#----------------------------
def run(cmd):
    sp = subprocess.Popen(cmd, shell=True, stderr=subprocess.STDOUT, stdout=subprocess.PIPE)
    wait_on = 0
    if wait_on:
        f = sp.stdout
        s = f.readline()
        ret_s = s
        while s:
        #print s.strip()
            s = f.readline()
            if s:
                ret_s + s

        rc = sp.wait()
        #print "Run Result:", rc
        return (rc,ret_s)
    return 0
    # another possible way...
    #try:
    #  pid = os.fork()
    #except OSError, e:
    #  sys.exit(1)
    #if pid == 0:
    #  os.execv(argv[0], args)

#-------------------------------------------
def gl():
    ' return the global object'
    global globs
    return globs

#-------------------------------------------
class Globals:
    def __init__(self):
        self.mKeys = None # ref to KeyInput object
        self.verbose = 0
        self.mMain = None # ref to Main object

    #---------------------------------------
    # this is rigged up to allow routing in our_input() to work with out
    # using threads.
    def PollWork(self):
        g = gl()
        while (self.mMain.MidimanToYoshiRouter_Poll()):
            pass
        time.sleep(0.001) # sleep 1ms, play nice

#---------------------------------------
def KeyExit():
    g = gl()
    k = g.mKeys
    if k != None:
        #print('putting keys back to cooked mode')
        k.kb_cooked()
        k = None
    #print('exiting')

#-------------------------------------------
def pr(str):
    ' abreviated print() '
    print(str)

#-------------------------------------------
def ourAlsaIn(alsa_midi_io):
    ''' Is this a Alsa Midi Input we wish to connect to? Keyboard? '''
    a = alsa_midi_io
    if verbose & 2:
        print('in search:' + a.port_name)
    if a.client_name.find('midiroute') >=0: # it's us!
        return 0 # no

    if a.client_name.find('Keystation') >=0:
        if verbose & 4:
            print('Found Keystation Midi to connect as input')
        return 1 # yes
    if a.client_name.find('Axiom') >=0:
        if verbose & 4:
            print('Found Axiom Midi to connect as input')
        return 1 # yes

    return 0 # no

#-------------------------------------------
def ourAlsaOut(alsa_midi_io):
    ''' Is this a Alsa Midi Output we wish to connect to? Synth? '''
    a = alsa_midi_io
    if verbose & 2:
        print('out search:' + a.port_name)
    if a.client_name.find('midiroute') >=0: # it's us!
        return 0 # no

    if a.client_name.find('yoshimi') >=0:
        if verbose & 4:
            print('Found Yoshimi to connect as output')
        return 1 # yes
    if a.client_name.find('FLUID') >=0:
        if verbose & 4:
            print('Found Fluid synth to connect as output')
        return 1 # yes
    if (a.client_name.find('idimon') >=0 or
        a.client_name.find('onitor') >=0 or
        a.client_name.find('midisnoop') >=0):
        if verbose & 4:
            print('Found a Midi Monitor to connect as output')
        return 1 # yes
    #if a.client_name.find('Through Port-0') >=0:
    #    if verbose & 4:
    #        print('Found a Midi Through to connect as output')
    #    return 1 # yes
    if a.client_name.find('fluidSynth') >=0: # guess
        if verbose & 4:
            print('Found FluidSynth to connect as output')
        return 1 # yes

    return 0 # no

#-------------------------------------------
# quick empty container
class Empty:
    def __init__(self):
        pass

#-------------------------------------------
def AlsaSeq_List(inout):
    ''' return a list of Alsa IO, either input(0) or output(1) '''
    ret_list = []
    # this gets a list of (client_id, port_id, client_name, port_name)
    lst = alsaseq.list(inout) # 0=inputs, 1=outputs
    for io_list_entry in lst: # 0=inputs, 1=outputs
        l = Empty()
        l.client_id, l.port_id, l.client_name, l.port_name = io_list_entry
        ret_list.append(l)
    return ret_list

#-------------------------------------------
def usage():
    print('''
    midiroute - yosh midi synth controller.
       Parameters:
          -i#,#  input connects to make
          -o#,#  output connections to make
          -p0    turn off pass thru(series) device(notes, some CC's)
          -v#    verbose level flags, 0=off, 1=min, 3=more, 7=lots
          -a0    turn off auto connect base on string matches

  ''')
    sys.exit(1)

#-------------------------------------------
#-------------------------------------------
class KeyInput:
    def __init__(self):
        self.fd = None
        self.org = None
        #self.wait_func = None # call back, avoid threads
        self.last_key = None # last key pressed, string
        self.last_last_key = None # last key pressed, string

    def kb_cooked(self):
        if self.fd != None:
            termios.tcsetattr(self.fd, termios.TCSANOW, self.org)
            #print('back to cooked:', self.org)
            self.fd = None
        else:
            print('not cooked!')

    def kb_raw(self):
        ' put the tty in raw mode if not already done '
        if self.fd == None:
            self.fd = sys.stdin.fileno()
            #self.fd = open('/dev/tty').filehandle()
            self.org = termios.tcgetattr(self.fd)
            #print('putting keybd in raw mode! attr was:', self.org)
            #print('putting keybd in raw mode!')
            newx = copy.copy(self.org)
            # attr=[iflag,oflag, cflag, lflag, ispeed, ospeed, [cc-spec-chars]]
            #newx[0] = 0 # iflags
            # lflags:
            newx[3] = newx[3] & ~termios.ICANON & ~termios.ECHO & ~termios.ISIG
            # cc
            newx[6][termios.VMIN] = 1
            newx[6][termios.VTIME] = 0
            termios.tcsetattr(self.fd, termios.TCSANOW, newx)

    def getkey(self):
        ' get keyboard input(string).  Return empty string or None if empty.'
        if self.fd == None:
            self.kb_raw()
        if not select.select([sys.stdin], [], [], 0) == ([sys.stdin], [], []):
            return None
        kstr = os.read(self.fd, 1)
        self.last_key = self.last_last_key
        self.last_last_key = kstr[0:1]
        return self.last_last_key

    def getlastkey(self):
        return self.last_key # last key pressed, string

    #-------------------------------------------
    # take the place of raw_input() when in non-cooked poll mode
    def our_input(self, prompt):
        g = gl()
        print(prompt, end='') # no line-end
        # flush stdout?
        sys.stdout.flush()
        instr = ''
        cn = None
        while (cn != 0xd) and (cn != 0xa) and (cn != 0x1b): # cr/lf or esc
            c = self.getkey()
            if c != None:
                cs = c[0:1]
                cn = ord(cs)
                if cn > 0x20 and cn <= 0x80:
                    #print('got k')
                    if cn == 0x80:
                        instr = instr[:-1] # strip last char
                    else: instr += cs # add char to string input
                    print(cs, end='')
                    sys.stdout.flush()
                elif cn == 0x1b:
                    instr = ''
                elif cn == 0xd or cn == 0xa:
                    pass
                else:
                    print('got ctrl k %x' % (cn))
            else:
                g.PollWork()

        print() # cr
        return instr

#-------------------------------------------
#-------------------------------------------
class MidiDevice:
    def __init__(self):
        self.mChannel = 0 # raw channel, displayed is +1
        self.mBank = 5
        self.mProg = 1
        self.last_alsaseq_pkt = None # hack, for output event making
        self.verbose = 0   # -v1 basic, -v3 loud, -v7 louder
        self.pass_thru = 1 # true to act as a router of everything else
                           # like notes, and CC's we don't act on
        self.auto_midi_conn = 1 # true to connect based on string match
                                # via ourMidiIn() ourMidiOut()

    #-------------------------------------------
    def Open(self, src_list=[], dest_list=[]):
        ''' src_list is a list of src ports to connect to. From -i#,#
        dest_list is a list of dest ports to connect to.  From -o#,#,
        '''
        print('opening alsaseq client')
        junk_None = alsaseq.client(
           'midiroute', # name of virtual client
           1, #num in ports
           1, #num out ports
           False) # create_queue Y/N - rx buf?

        # there is also connectto(), connectfrom() funcs...
        # these appear to be for connecting client() to other ports

        # following input port, output port appear to be 0 for input,
        # 1 for output.
        for src_i in src_list:
            print('in:%d' % (src_i))
            alsaseq.connectfrom(0, # input port
                                src_i, # src client
                                0) # src port

        for dest_i in dest_list:
            print('out:%d' % (dest_i))
            alsaseq.connectto(1, # output port(first one of ours?)
                              dest_i, # dest client
                              0) # dest port

        # connect ins and outs based on string comparisons:
        # see ourAlsaIn()/Out() above for setting your string connect matches
        #if len(src_list) == 0 and len(dest_list) == 0:
        if self.auto_midi_conn: # -a[0|1] option, default 1 on
            print('scanning Alsa Midi Inputs')
            lst = AlsaSeq_List(0) # list inputs(Midi Keys for ex)
            for m in lst:
                if ourAlsaIn(m):
                    print('connect input client %3d %-26s port %d %s' % (m.client_id,m.client_name, m.port_id,m.port_name))
                    alsaseq.connectfrom(m.port_id, # our port, first input is 0
                                        m.client_id, # 28 for example
                                        m.port_id) # 0 for example
            print('scanning Alsa Midi Outputs')
            lst = AlsaSeq_List(1) # list outputs(synth ex)
            for m in lst:
                if ourAlsaOut(m):
                    print('connect output client %3d %-26s port %d %s' % (m.client_id,m.client_name, m.port_id,m.port_name))
                    alsaseq.connectto(1, # our first output port is 1 now
                                        m.client_id, # 28 for example
                                        m.port_id)   # 0 for example

        # how do we tell if successful?  This is returning None?
        #   it calls exit(1) if fails, I guess client is not expected
        #   to fail...
        self.mDevIn = True
        if self.mDevIn != None:
            return True # ok
        print('fail!')
        return False # no open

    #-------------------------------------------
    # Read a single alsa event, reconstruct to MIDI where approriate
    def Read(self):

        # read the alsa event
        ev = alsaseq.input()
        (mtype, flags, tag, queue, m_time, src, dest, mdata) = ev

        if mtype == alsaseq.SND_SEQ_EVENT_SENSING: #42: # tick?  get about 3 per second
            return None # ignore for now, filter these out quitely.

        b0 = mdata[0] # 0, ch? mtype=6
        b1 = mdata[1] # note
        b2 = mdata[2] # velocity
        b3 = mdata[3] # 0
        if self.verbose & 4:
            print(mtype, flags, tag, queue, m_time, src, dest, mdata)
            # need to debug,understand, print it.
        # there is just a NOTE ev, why?  would I see this ever?
        if mtype == alsaseq.SND_SEQ_EVENT_NOTEON: #6:
            if len(mdata) != 5:
                print('noteon unexpected len:%d' % (len(mdata)))
            if self.verbose & 2:
                print('ch:%d noteon:%d vel:%d' % (b0, b1, b2))
            return (ev, b0 | 0x80, b1, b2, b3)
        elif mtype == alsaseq.SND_SEQ_EVENT_NOTEOFF: #7:
            if len(mdata) != 5:
                print('noteoff unexpected len:%d' % (len(mdata)))
            if self.verbose & 2:
                print('ch:%d noteoff:%d vel:%d' % (b0, b1, b2))
            return (ev, b0 | 0x90, b1, b2, b3)
        elif mtype == alsaseq.SND_SEQ_EVENT_CONTROLLER: #10:
            if len(mdata) != 6:
                print('cc unexpected len:%d' % (len(mdata)))
            b4 = mdata[4] # cc number
            b5 = mdata[5] # value
            if self.verbose & 2:
                print('ch:%d cc:%d val:%d' % (b0, b4, b5))
            return (ev, b0 | 0xb0, b4, b5, b3)
        elif mtype == alsaseq.SND_SEQ_EVENT_PGMCHANGE: #?:
            if len(mdata) != 4:
                print('cc unexpected len:%d' % (len(mdata)))
            b4 = mdata[4] # prog number
            if self.verbose & 2:
                print('ch:%d prog:%d' % (b0, b4))
            return (ev, b0 | 0xc0, b4, 0, 0)
        elif mtype == alsaseq.SND_SEQ_EVENT_PITCHBEND: # 13:
            if len(mdata) != 6:
                print('cc unexpected len:%d' % (len(mdata)))
            b4 = mdata[4] # cc number
            b5 = mdata[5] # value here, see on pitch wheel -8192 to 8192
            if self.verbose & 2:
                print('ch:%d cc-ext?pitch? cc:%d val:%d' % (b0, b4, b5))
            return (ev, b0 | 0xe0, b4, b5, b3)
        else:
            if self.verbose & 2:
                print('Unhandled alsaseq pkt type:%d' % (mtype))
            if self.verbose & 4:
                print(mtype, flags, tag, queue, m_time, src, dest, mdata)

            if self.verbose & 2:
                print('  mtype:%x flags:%x tag:%x queue:%x m_time:%s src:%s dest:%s mdata:%s' % \
                  (mtype, flags, tag, queue, str(m_time), str(src), str(dest), str(mdata)))
        return None

    #-------------------------------------------
    # Read a single alsa event, reconstruct to MIDI where approriate
    def ReadMidi(self):

        # read the alsa event
        ev = alsaseq.inmidi()
        (mtype, rx_ch, note_param, vel_ctrl) = ev

        if mtype == alsaseq.SND_SEQ_EVENT_SENSING: #42: # tick?  get about 3 per second
            return None # ignore for now, filter these out quitely.

        #b0 = mdata[0] # 0, ch? mtype=6
        #b1 = mdata[1] # note
        #b2 = mdata[2] # velocity
        #b3 = mdata[3] # 0
        if self.verbose & 4:
            print(mtype, rx_ch, note_param, vel_ctrl)
            # need to debug,understand, print it.
        # there is just a NOTE ev, why?  would I see this ever?
        if mtype == alsaseq.SND_SEQ_EVENT_NOTEON: #6:
            if self.verbose & 2:
                print('ch:%d noteon:%d vel:%d' % (rx_ch, note_param, vel_ctrl))
            return (rx_ch | 0x80, note_param, vel_ctrl)
        elif mtype == alsaseq.SND_SEQ_EVENT_NOTEOFF: #7:
            if self.verbose & 2:
                print('UNEXPECTED: ch:%d noteoff:%d vel:%d' % (rx_ch, note_param, vel_ctrl))
            return (rx_ch | 0x90, note_param, vel_ctrl)
        elif mtype == alsaseq.SND_SEQ_EVENT_CONTROLLER: #10:
            if self.verbose & 2:
                print('ch:%d cc:%d val:%d' % (rx_ch, note_param, vel_ctrl))
            return (rx_ch | 0xb0, note_param, vel_ctrl)
        elif mtype == alsaseq.SND_SEQ_EVENT_PGMCHANGE: #?:
            if self.verbose & 2:
                print('ch:%d progchg:%d val:%d' % (rx_ch, note_param, vel_ctrl))
            return (rx_ch | 0xc0, note_param, vel_ctrl)

        elif mtype == alsaseq.SND_SEQ_EVENT_PITCHBEND: # 13:
            if self.verbose & 2:
                print('ch:%d pitch_chg:%d val:%d' % (rx_ch, note_param, vel_ctrl))
            return (rx_ch | 0xe0, note_param, vel_ctrl)
        else:
            if self.verbose & 2:
                print('Unhandled alsaseq pkt type:%d' % (mtype))
            if self.verbose & 2:
                print('ch:%d note_param:%d val:%d' % (rx_ch, note_param, vel_ctrl))
            return (rx_ch | 0xf0, note_param, vel_ctrl)
        return None

    #-------------------------------------------
    def WriteAlsaEvent(self, event):
        ''' write raw alsa event '''
        # swap out and send on our selected channel
        #event[7][0] = (event[7][0] & 0xf0) | self.mChannel
        #nope, it's a tuple... can't modify
        alsaseq.output(event)

    #-------------------------------------------
    def Write(self, pkt):
        # work in progress, alsa event handling is very complex...
        # there are helper functions in alsaseq - alsamidi module.
        if self.last_alsaseq_pkt:
            # just copy from last in pkt, reverse src,dest
            # this is just a quick hack workaround.
            dest = self.last_alsaseq_pkt[5] # src
            src = self.last_alsaseq_pkt[6] # dest
        else:
            # otherwise punt, try setting them to (0,0).
            src = (0,0)
            dest = (0,0)

        if (pkt[0] & 0xf0) == 0x80: # NoteOn
            alsa_pkt = (alsaseq.SND_SEQ_EVENT_NOTEON, # mtype
              0, 0, 253, # flags, tag, queue
              (0,0), # m_time
              src, # src
              dest, # dest
              (pkt[0] & 0xf, pkt[1], pkt[2], 0, 100)) # mdata
            alsaseq.output(alsa_pkt)
            if self.verbose & 4:
                print('tried sending alsa note on')
        elif (pkt[0] & 0xf0) == 0xb0: # CC
            alsa_pkt = (alsaseq.SND_SEQ_EVENT_CONTROLLER, # mtype
              0, 0, 253, # flags, tag, queue
              (0,0), # m_time
              src, # src
              dest, # dest
              (pkt[0] & 0xf, 0, 0, 0, pkt[1], pkt[2])) # mdata: ? ? ? ctrl-num, value
                #(1, 0, 0, 0, pkt[1], pkt[2])) # mdata: ? ? ? ctrl-num, value
            alsaseq.output(alsa_pkt)
            if self.verbose & 4:
                print('tried sendin alsa cc %02x %02x' % (pkt[1], pkt[2]))
        elif (pkt[0] & 0xf0) == 0xc0: # program change
            alsa_pkt = (alsaseq.SND_SEQ_EVENT_PGMCHANGE, # mtype
              0, 0, 253, # flags, tag, queue
              (0,0), # m_time
              src, # src
              dest, # dest
              (pkt[0] & 0xf, 0, 0, 0, 0, pkt[1])) # mdata: ? ? ? ctrl-num, value
                #(1, 0, 0, 0, 0, pkt[1])) # mdata: ? ? ? ctrl-num, value
            alsaseq.output(alsa_pkt)
            if self.verbose & 4:
                print('tried sendin alsa prog %02x' % (pkt[1]))
        else:
            print('todo: send alsaseq')
            print(pkt)
            return False

    #-------------------------------------------
    # Return a summary description short string of CC control bytes
    def SummaryCC_Desc(self, m_b1, m_b2):
        desc = ''
        if m_b1 < 64:
            desc += ' HiRes Cont Ctrl'
            m_b1c = m_b1
            if m_b1 >= 32:
                desc += ' HiRes'
                m_b1c &= 0x1f
            if   m_b1c == 0: desc += ' BankSel'
            elif m_b1c == 1: desc += ' ModWheel'
            elif m_b1c == 2: desc += ' Breath'
            elif m_b1c == 3: desc += ' ?'
            elif m_b1c == 4: desc += ' Foot'
            elif m_b1c == 5: desc += ' PortaTime'
            elif m_b1c == 6: desc += ' Data(RPN)'
            elif m_b1c == 7: desc += ' ChVolume'
            elif m_b1c == 8: desc += ' Balance'
            elif m_b1c == 9: desc += ' ?'
            elif m_b1c == 10: desc += 'Pan'
            elif m_b1c == 11: desc += ' Express'
            elif m_b1c == 12: desc += ' Effect1'
            elif m_b1c == 13: desc += ' Effect2'
            elif m_b1c == 16: desc += ' Gen1'
            elif m_b1c == 17: desc += ' Gen2'
            elif m_b1c == 18: desc += ' Gen3'
            elif m_b1c == 19: desc += ' Gen4'
            else: desc += ' ?(%d)' % (m_b1)
        elif m_b1 < 70:
            desc += ' Switch'
            if   m_b1 == 64: desc += ' Sustain'
            elif m_b1 == 65: desc += ' Porta'
            elif m_b1 == 66: desc += ' Sosten'
            elif m_b1 == 67: desc += ' Soft'
            elif m_b1 == 68: desc += ' Legato'
            elif m_b1 == 69: desc += ' Hold'
        elif m_b1 < 120:
            desc += ' LoRes Cont Ctrl'
            if   m_b1 == 96: desc += ' DataInc'
            elif m_b1 == 97: desc += ' DataDesc'
            elif m_b1 == 98: desc += ' NRPN LSB'
            elif m_b1 == 99: desc += ' NRPN MSB'
            elif m_b1 == 100: desc += ' RPN LSB'
            elif m_b1 == 101: desc += ' RPN MSB'
        elif m_b1 < 128:
            desc += ' Ch Mode Msg'
            if   m_b1 == 120: desc += ' SndOff'
            elif m_b1 == 121: desc += ' ResetAll'
            elif m_b1 == 122: desc += ' Local'
            elif m_b1 == 123: desc += ' AllNotes'
            elif m_b1 == 124: desc += ' OmniOff'
            elif m_b1 == 125: desc += ' OmniOn'
            elif m_b1 == 126: desc += ' MonoOn'
            elif m_b1 == 127: desc += ' PolyOn'
        return desc

    #-------------------------------------------
    def Poll(self):
        ' returns True if input event pending, otherwise False if nothing '
        return alsaseq.inputpending()
        # future: returns true on note on's or ctrl msgs we care about
        #return alsaseq.in_note_ctrl()

#-------------------------------------------
#-------------------------------------------
class Main:
    def __init__(self):
        self.mDev = None #reference tomidi handler class
        self.mChannel = 0
        self.verbose = 0
        self.pass_thru = 1
        self.yoshiBank = None
        self.auto_midi_conn = 1
        self.last_sys_effect = 1 # remember last changed system effect(first 4 knob)
                                 # and route knob 5(pan) to this effect
        self.last_modwheel = 0 # used to escape the keyboard, use keys
                                 # for controls under certain conditions

        self.virtual_pitchval = 0 # +- our virtual pitchwheel value
        self.key_select = -1 # last bank/prog select from list

        self.cmdargs = ''
        self.options = '' # -oSTRING
        global globs
        globs = Globals() # make a Globals container
        gl = globs
        gl.mKeys = KeyInput() # make a raw key input object, chg to non-cooked
        k = gl.mKeys
        gl.mMain = self

        atexit.register(KeyExit)
        # need to make sure we put keyboard back to cooked mode
        # otherwise it doesn't echo, need 'reset' command.

        # used in router as program list
        # this plucked from list run with -l option
        self.prog_table = (
          (65, "Plucked", 3, "Plucked 3"),
          (5, "Arpeggios", 34, "Sequence2"),
          (10, "Bass", 33, "Wah Bass"),
          (20, "Choir_and_Voice", 4, "Voice OOH"),
          (20, "Choir_and_Voice", 36, "Eooooo"),
          (30, "Dual", 2, "Layered2"),

          (40, "Guitar", 4, "Dist Guitar 4"),
          (55, "Organ", 33, "Cathedral Organ1"),
          (70, "Reed_and_Wind", 66, "Fat Reed2"),
          (105, "Will_Godfrey_Collection", 101, "Bottle"),
          (115, "chip", 39, "iBrazz_2"),
          (115, "chip", 44, "ChipBass"),
          )

    #---------------------------------------------------
    def readYoshiBankInfo(self):
        if self.yoshiBank == None:
            y = yoshibanks.YoshiBankProg(self.mDev)
            self.yoshiBank = y
            y.readYoshiBankConfig()
            print('setting yosh ctrl channel to:%d' % (self.mChannel))
            y.mChannel = self.mChannel # set, this is set to last event channel seen

    #---------------------------------------------------
    def keymenu(self, c):
        g = gl()
        k = g.mKeys
        if self.verbose & 2:
            print('pressed:%s' % (c))
        if self.yoshiBank == None:
            self.readYoshiBankInfo()
        if c == '?':
            self.MidimanToYoshiRouter_ShowMenuHelp()
        elif c == 'a':
            # show bank/prog selection
            self.yoshiBank.PrintChanSettings()
        elif c == 'b':
            self.yoshiBank.PrintBankSelection()
            s = k.our_input('Select a bank:')
            if s:
                num = yoshibanks.GetNum(s)
                if num >= 0:
                    num = int(s)
                    self.yoshiBank.setBank(num)
        elif c == 'c':
            s = k.our_input('Select a channel(1-16):')
            if s:
                num = yoshibanks.GetNum(s)
                self.mChannel = num-1 # use zero indexing for channel
                self.yoshiBank.mChannel = self.mChannel
                pr('change to channel:%d' % (self.mChannel+1))
        elif c >= 'd' and c <= 'e':
            # select next/prev bank/prog from list
            if c == 'd':
               self.key_select -= 1
               if self.key_select < 0:
                 self.key_select = 11
            else:
               self.key_select += 1
               if self.key_select > 11:
                 self.key_select = 0
            self.ProgBankListSelect(self.key_select)
            self.yoshiBank.PrintChanSettings() # show bank/prog selection
        elif c == 'l':
            # list alsa midi ins/outs
            if self.verbose & 2:
                print('******* aconnect -i INPUTS:')
                os.system('aconnect -i')
                print('******* aconnect -o OUTPUTS:')
                os.system('aconnect -o')
            print('** alsaseq INPUTS:')
            lst = alsaseq.list(0)
            for (client_id, port_id, client_name, port_name) in lst:
                print('client %3d %-26s port %d %s' % (client_id,client_name, port_id,port_name))
            print('** alsaseq OUTPUTS:')
            lst = alsaseq.list(1)
            #print(lst)
            for (client_id, port_id, client_name, port_name) in lst:
                print('client %3d %-26s port %d %s' % (client_id,client_name, port_id,port_name))
        elif c == 'p':
            self.readYoshiBankInfo()
            self.yoshiBank.PrintProgSelection()
            s = k.our_input('Select a program:')
            if s:
                num = yoshibanks.GetNum(s)
                if num >= 0:
                    num = int(s)
                    self.yoshiBank.setProg(num)

        elif c >= '0' and c <= '9':
            num = ord(c) - ord('0')
            if num == 0:
                num = 10 # typically drums are channel 10
            self.mChannel = num-1 # use zero indexing for channel
            self.yoshiBank.mChannel = self.mChannel
            pr('change to channel:%d' % (self.mChannel+1))
        elif c == 'd':
            s = k.our_input('Enter a num:')
            if s:
                num = int(s)
                print('entered:%d' % (num))
        elif c >= 'A' and c <= 'Z':
            # do a cheap keyboard with these capital chars
            note_num = 45 + ord(c) - ord('A') # 45 is A(3?)
            velocity = 100
            duration = 0.01
            if verbose & 1:
                pr('playing ch:%d note:%d vel:%d %0.1f sec' % (self.mChannel+1, note_num, velocity, duration))
            pkt = [0x80 | self.mChannel, # NoteOn Midi(0x80)
                   note_num,
                   velocity # velocity(0-127)
                  ]
            self.mDev.Write(pkt)
            time.sleep(duration) # quick and simple, play note for 1 second
            pkt[2] = 0 # velocity, note-off when 0
            self.mDev.Write(pkt)
        elif c == 'z':
            # this is going away, for newer state-machine method(b,p)
            self.readYoshiBankInfo()
            self.yoshiBank.mChannel = self.mChannel # set, this is set to last event channel seen
            k.kb_cooked()
            self.yoshiBank.bankBrowser()
            k.kb_raw()


    #---------------------------------------------------
    def MidimanToYoshiRouter_ShowMenuHelp(self):
        print('''ESC to exit.
a - print current channel bank/prog selection
b - see/set yoshi bank
c - see/set channel
l - list midi ins/outs
p - see/set yoshi program
0 to 9 - set channel(where 0 is 10)
A to Z - caps, use as cheap virtual keyboard(play a note)
l - list midi devices
''')

    #---------------------------------------------------
    # Router - Map incoming MidiMan knobs to Yoshi controls
    # For starters, let's assume the keys are connected to Yoshi in parallel to us.
    #  so we do not have to pass thru events.  We just capture them and send Yoshi
    #  some altered events to control the things we want.  This may conflict with
    #  any existing CC mappings done by Yoshimi, but we don't care now, this is just
    #  the simplest thing to do.  You could filter out with mididings if you wanted.
    # Currently I have system effects setup as: reverb, alienwah, phaser, echo.
    #---------------------------------------------------
    def MidimanToYoshiRouter_Start(self):
        print('start MidiMan to Yoshi Router(change pitchwheel high to exit)')
        print('  This maps CC 0-7 - MidiMan knobs, to System and Insert Effect Levels')
        if self.pass_thru:
            print('  Acting as Pass Thru router, passing thru notes, etc')
        else:
            print('  Acting as Non-Pass thru device, no pass thru of notes, etc')
        self.MidimanToYoshiRouter_ShowMenuHelp()

    #---------------------------------------------------
    def MidimanToYoshiRouter_Loop(self):
        g = gl()
        k = g.mKeys
        while 1:
            c = k.getkey()
            if c != None:
                cn = ord(c[0:1])
                if cn == 0xa or cn == 0xd: # we see 0xa(lf)
                    #pr('cn %x' % (cn))
                    #pr('last key:' + k.getlastkey())
                    if k.getlastkey() == 'q':
                        pr('bye, hope you had fun!')
                        return
                if cn == 0x1b:
                        # make sure it's not esc sequence, like Fx keys, etc.
                    c = k.getkey()
                    if c == None:
                        print('exiting ESC')
                        s = k.our_input('quit?(y/n):')
                        if s == 'y':
                            return
                    else:
                        # print the funny esc sequence
                        keystr = '1b '
                        while c != None:
                            keystr += '%x ' % (ord(c))
                            c = k.getkey()
                        print('unhandled keycode sequence:%s' % (keystr))
                else:
                    self.keymenu(c)
            while (self.MidimanToYoshiRouter_Poll()):
                pass
            time.sleep(0.0010) # sleep 1ms, play nice

    #---------------------------------------------------
    def Send_NRPN(self, tx_ch, effect_num, effect_index,
                                   msb_effect_ctrl, cc_data):
        ' Send a NRPN midi message '
        self.mDev.Write([0xb0 | tx_ch, 99,effect_num]) # MSB NRPN
        self.mDev.Write([0xb0 | tx_ch, 98, effect_index]) # LSB NRPN
        self.mDev.Write([0xb0 | tx_ch, 6,  msb_effect_ctrl])
        self.mDev.Write([0xb0 | tx_ch, 38, cc_data])

    #---------------------------------------------------
    def ProgBankListSelect(self, key_select):
        ' set bank,program based on synth keybd key press when pitch > 120 '
        bn,bs,pn,ps = self.prog_table[key_select]
        self.readYoshiBankInfo()
        self.yoshiBank.mChannel = self.mChannel
        pr('switch to %d %d.%s %d.%s' % (key_select, bn,bs, pn,ps))
        self.yoshiBank.sendBankProgSelect(self.mChannel, bn, pn)

    #---------------------------------------------------
    def MidimanToYoshiRouter_Poll(self):
        ' Router, worker, poll often, so we do not have to use threads ;)'

        if not self.mDev.Poll():
            return False # no midi events, nothing processed

        #print('got a midi event!')
        if 1:
          pkt = self.mDev.ReadMidi() # read only 1 message at a time
          if pkt == None:
            # ignore bogus(alsaseq giving 3 odd pkts per sec)
            return True # processed something
          m_b0 = pkt[0] # rx_ch | midi_ctrl
          m_b1 = pkt[1] # note or param
          m_b2 = pkt[2] # velocity or value
          #m_b3 = pkt[3]
        else:
          pkt = self.mDev.Read() # read only 1 message at a time
          if pkt == None:
            # ignore bogus(alsaseq giving 3 odd pkts per sec)
            return True # processed something

          #print('got a midi event!')
          alsa_event = pkt[0]
          #m_time = alsa_event[4]
          m_b0 = pkt[1]
          m_b1 = pkt[2]
          m_b2 = pkt[3]
          m_b3 = pkt[4]

        rx_ch = m_b0 & 0xf        # The channel in lower first nibble
        tx_ch = self.mChannel # send channel, send on channel we select

        if (m_b0 & 0xf0) == 0xb0: # CC control message upper nibble
            # we have 8 knobs.  On my Oxygen or Radium.
            # I have them mapped to CC-70,71,..,77
            #  On Radium, have 8 extra sliders mapped to CC-80,81..
            #   third one does not work ;(
            if m_b1 >= 70 and m_b1 < 74: # first 4 knobs CC-70 to CC-73
                # map them to the 4 yoshi system effects 0 level control
                effect_num  = 4 # system effect(4=system, 8=insert)
                effect_index = m_b1-70 # effect index
                self.last_sys_effect = effect_index
                if self.verbose & 1:
                    map_desc = 'system effect level(%d)= %d' % (effect_index+1, m_b2)
                msb_effect_ctrl = 0 # level(volume, dry/wet)
                cc_data = m_b2 # route CC data value to new use
                self.Send_NRPN(tx_ch, effect_num, effect_index,
                               msb_effect_ctrl, cc_data)
                if self.verbose & 1:
                    print('map CC %d %d to: ' % (m_b1, m_b2) + map_desc)
            elif m_b1 == 74:
                if self.verbose & 1:
                    map_desc = ' master PAN CC-10= %d' % (m_b2)
                self.mDev.Write([0xb0 | tx_ch, 10, m_b2]) # route to CC-10 PAN(master)
                if self.verbose & 1:
                    print('map CC-%d %d to PAN CC-10:' % (m_b1, m_b2) + map_desc)
            elif m_b1 == 75:
                # this one routes pan based on last first 4 knobs used.
                # routes pan to that system effect.
                effect_num  = 4 # system effect(4=system, 8=insert)
                effect_index = self.last_sys_effect # effect index, last vol chged above
                if self.verbose & 1:
                    map_desc = ' Effect Pan, System(%d)= %d' % (effect_index+1, m_b2)
                msb_effect_ctrl = 1 # Pan
                cc_data = m_b2 # route CC data value to new use
                self.Send_NRPN(tx_ch, effect_num, effect_index,
                               msb_effect_ctrl, cc_data)
                if self.verbose & 1:
                    print('map CC %d %d to: ' % (m_b1, m_b2) + map_desc)
            elif m_b1 == 76:
                if self.verbose & 1:
                    map_desc = 'master Yoshi-Portamento CC-65= %d' % (m_b2)
                # This is digital on/off, > 64 is on, less off
                self.mDev.Write([0xb0 | tx_ch, 65, m_b2]) # route to CC-65 Yoshi portamento
                if self.verbose & 1:
                    print('map CC-%d %d to: ' % (m_b1, m_b2) + map_desc)
            elif m_b1 == 77:
                # yoshi expression cc-11, seems like same as master volume?
                #map_desc = 'master Yoshi-Expression CC-11= %d' % (m_b2)
                #mOut.Write([0xb0 | tx_ch, 11, m_b2]) # route to CC-11 Yoshi portamento
                if self.verbose & 1:
                    map_desc = 'master Yoshi-Sustain CC-64= %d' % (m_b2)
                self.mDev.Write([0xb0 | tx_ch, 64, m_b2]) # route to CC-11 Yoshi sustain?
                if self.verbose & 1:
                    print('map CC-%d %d to: ' % (m_b1, m_b2) + map_desc)
            else:
                if m_b1 == 1: # mod wheel
                    if MODWHEEL_BANKPROG_KEY_FEATURE:
                    # mod wheel escape for setting bank/prog selection.
                    # we save last mod value to try out using to set
                    # bank/prog as escape sequence - push mod up > 100
                    # then press a key, then pull mod down < 100
                    # kludgy, don't think I like it very much, but..
                        self.last_modwheel = m_b2
                        if self.last_modwheel > 100:
                            if self.verbose & 2:
                                pr('Filter Mod-Wheel %d' % (self.last_modwheel))
                            return True # processed, filter out
                    if MODWHEEL_TO_PITCH_FEATURE:
                        # mod wheel convert to differential pitch modulation
                        # make it do what pitch wheel does, but without dead middle spot
                        diff_mod = m_b2 - self.last_modwheel
                        self.last_modwheel = m_b2
                        # pitch value see from -8192 to 8191
                        self.virtual_pitchval += (diff_mod * 64)
                        if self.virtual_pitchval > 8191: self.virtual_pitchval = 8191
                        if self.virtual_pitchval < -8192: self.virtual_pitchval = -8192
                        ev = alsamidi.pitchbendevent(tx_ch, self.virtual_pitchval)
                        if self.verbose & 4:
                            print('made:')
                            print(ev)
                        fixed_ev = (13,0,0,253, (0,0), (0,0), (0,0), (0,0,0, 0,0, self.virtual_pitchval))
                        ev = fixed_ev
                        if self.verbose & 4:
                            print('fixed:')
                            print(ev)
                        #self.mDev.Write(ev) # send out as pitch wheel control
                        alsaseq.output(ev)
                        # put out a pitch wheel change based on mod wheel change
                        if self.verbose & 2:
                            pr('Filter Mod-Wheel %d, to pitch %d bend' % (self.last_modwheel, self.virtual_pitchval))
                        return True # processed, filter out

                if self.pass_thru:
                    if self.verbose & 2:
                        desc = self.mDev.SummaryCC_Desc(m_b1, m_b2)
                        print('pass thru CC event:' + desc)
                    #self.mDev.WriteAlsaEvent(alsa_event)
                    alsaseq.outlast((tx_ch | 0x10, 0,0,0)) # modify first(channel)

        elif (m_b0 & 0xf0) == 0x90:
            if self.verbose & 2:
                print('ch:%d NoteOff:%d Vel:%d' % (rx_ch, m_b1, m_b2))
            self.mDev.Write([0x90 | tx_ch, m_b1, m_b2])
        elif (m_b0 & 0xf0) == 0x80:
            if self.verbose & 2:
                print('ch:%d NoteOn:%d Vel:%d' % (rx_ch, m_b1, m_b2))

            if MODWHEEL_BANKPROG_KEY_FEATURE:
                if self.last_modwheel > 100:
                # using top of modwheel to set program(12 choices)
                    if m_b2 != 0: # velocity: off (only do when key on)
                        self.key_select = m_b1 % 12 # C-B, 12 choices, any octave
                        self.ProgBankListSelect(self.key_select)
                    if self.verbose & 2:
                        pr('Filter Prog Key')
                    return True # processed, don't pass thru, filter

            if MODWHEEL_TO_PITCH_FEATURE:
                if self.virtual_pitchval != 0:
                    self.virtual_pitchval = 0 # reset it and send out
                    ev = alsamidi.pitchbendevent(tx_ch, self.virtual_pitchval)
                    #fixed_ev = (13,0,0,253, (0,0), (28,0), (130,0), (0,0,0, 0,0,0))
                    ev = fixed_ev
                    #self.mDev.Write(ev) # send out as pitch wheel control
                    self.mDev.WriteAlsaEvent(ev)
                    #alsaseq.output(ev)
                    # put out a pitch wheel change based on mod wheel change
                    if self.verbose & 2:
                        pr('RESET Filter Mod-Wheel %d, to pitch %d bend' % (self.last_modwheel, self.virtual_pitchval))

            if self.pass_thru:
                if self.verbose & 2:
                    print('pass thru noteon')
                alsaseq.outlast((tx_ch | 0x10, 0,0,0)) # modify first(channel)
        else:
            if self.verbose & 1:
                print('Unhandled event ch:%d Cmd:%d Vel:%d' % (rx_ch, m_b1, m_b2))
            if self.pass_thru:
                if self.verbose & 2:
                    print('pass thru event')
                #self.mDev.WriteAlsaEvent(alsa_event)
                #self.mDev.Write([0x80 | tx_ch, m_b1, m_b2])
                alsaseq.outlast((tx_ch | 0x10, 0,0,0)) # modify first(channel)
        return True # processed something

    #---------------------------------------------------
    def ProcessArgs(self):
        src_list = []
        dest_list = []
        self.cmdargs = '' # collect the whole cmd line
        for a in sys.argv[1:]:
            self.cmdargs += a + ' '

            if a.startswith('-i'):
                for nstr in a[2:].split(','):
                    src_list.append(int(nstr))
            elif a.startswith('-o'):
                for nstr in a[2:].split(','):
                    dest_list.append(int(nstr))
            elif a.startswith('-v'):
                self.verbose = int(a[2:])
                if self.verbose:
                    global verbose
                    verbose = self.verbose
            elif a.startswith('-l'):
                self.readYoshiBankInfo()
                self.yoshiBank.PrintAllBankProgs()
                return
            elif a.startswith('-p0'):
                self.pass_thru = 0
            elif a.startswith('-a0'):
                self.auto_midi_conn = 0 # turn off string match connect
            elif a.startswith('-o'):
                self.options = a[1:] # cheesy hack for misc options string
            else:
                usage()
        self.src_list = src_list
        self.dest_list = dest_list

    #---------------------------------------------------
    def Run(self):
        self.mDev = MidiDevice()
        self.mDev.verbose = self.verbose
        self.mDev.pass_thru = self.pass_thru
        self.mDev.auto_midi_conn = self.auto_midi_conn # set string match connect option

        if not self.mDev.Open(self.src_list, self.dest_list):
            print('failed to open midi device')
            return False

        self.MidimanToYoshiRouter_Start()
        self.MidimanToYoshiRouter_Loop()


#---------------------------------------
def main():
    mo = Main()
    mo.ProcessArgs()

    # an attempt at auto-starting Yoshimi, not a very good attempt..
    if mo.options.find('runyosh') >= 0:
        # yosh -c no cmdline, -C cmdline, -i no gui, -I gui.
        #   -S load state, -K auto connect to jack
        # This is not working, must be a simple way to daemonize it..
        # should see if it is already running..
        subprocess.Popen(["yoshimi", "-K", "-S", "-I", "-c"])
        #run('yoshimi -K -S -I -c &')
        #os.system('yoshimi -K -S')

    mo.Run()

if __name__ == '__main__':
    main()
