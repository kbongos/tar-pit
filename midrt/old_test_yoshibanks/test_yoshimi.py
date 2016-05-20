#!/usr/bin/env python
# test code for PyPortMidi('pypm'), AlsaSeq('alsaseq'),
#    'rtmidi', targeted at Yoshimi synth to issue midi control.
#  This is aimed at building midi routers for music control purposes.
# kbongosmusic at gmail_com, kbongos.com/midi/test_yoshimi.py
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

import os,sys
import gzip
#import array
import time

# bankends -
#   pypm(libportmidi) - no virtual port, have to connect in,out to existing ports.
#   alsaseq - virtual port named client(aconnect routes)
#   rtmidi - virtual port named client(aconnect routes), or no virtual port.
#   mididings - virtual port named client(aconnect routes)
back_end = 'pypm' # default
if len(sys.argv) > 1:
    arg = sys.argv[1]
    back_end = arg
    supported_backends = ['pypm', 'alsaseq', 'rtmidi', 'mididings']
    if arg not in supported_backends:
        print('backend:%s not recognized' % (arg))
        print('supported backends:' + str(supported_backends))
        print('''
Usage> test_yoshimi.py {pypm(default) | rtmidi | alsaseq | mididings}
  pypg - is pyPortMidi lib backend.  Need to connect in/out, no virtual port
     supported.
  rtmidi - rtmidi library interface backend.  This does virtual port
     (makes client to map external). It also does regular port(where we
      need to map it), but we don't support that now).
  alsaseq - AlsaSeq lib backend.  This does virtual port, but we have limited
     support for this now because it required ALSA Event to MIDI mapping,
     some done, some not so much..
  mididings - This implements the 'l' listen, and 'm' midi yoshi router,
     no output

  Menu selections allow you to connect or make the virtual client, listen
  and dump midi messages, send a variety of midi messages as test vehicle,
  and some Yoshimi specific functions - browse and set BANK and Program
  selection via midi, and a M-Audio Oxygen 8 keyboard router that routes
  CC-1 to CC-8 to various Yoshimi controls -
  system effects 1-4 volume control on knobs 1-4(CC-1 to CC-4),
  system pan control on CC-5(knob 5),
  system effect(1-4) PAN via knob-6(CC-6) routed to last one changed
    on knob1-4.
  portamento ctrl(on/off) on CC-7(On >=64, else Off)
  sustain ctrl(on/off) on CC-8(On >=64, else Off)
''')

        sys.exit(1)
else:
    print('using default backend - pypg.  First parameter can specify different backend.')

if back_end == 'pypm':
    import pypm
elif back_end == 'alsaseq':
    import alsaseq #, alsamidi
elif back_end == 'rtmidi':
    import rtmidi
elif back_end == 'mididings':
    import mididings
    import mididings as mid
    import mididings.engine as midr
    import mididings.event as mide
    #from mididings.engine import *
    #from mididings.engine import *
    #from mididings.event import *

INPUT=0
OUTPUT=1

#-------------------------------------------
# setup mididings connections.  If we don't do this we get a simple virtual ALSA
#  client by default.  This can help us make connections, give it a custom name, etc.
def setup_mid_conn():
    route_alsa = 1
    if route_alsa:
        # in_ports=['mididing1', '140:0',
        #_out_ports=[('mdo1', 'FLUID Synth \(.*\):.*', 'MIDI monitor:.*')]
        #_in_ports=[('mdi1', 'Virtual Keyboard:.*')]
        _out_ports=[('mido1', 'MIDI monitor:.*', 'yoshimi:.*')]
        _in_ports=[('midi1', 'Keystation:.*')]
        # data_offset is default to 1, but we go with 0 to match virtual keyboard prog
        #mid.config(data_offset=0, out_ports=_out_ports, in_ports=_in_ports)
        #mid.config(data_offset=0, backend='alsa', in_ports=_in_ports)
        mid.config(data_offset=0, backend='alsa', in_ports=_in_ports, out_ports=_out_ports)
    else:
        # must be jack
        #_out_ports=[]
        #_in_ports=[]
        ##config(
        #  backend='jack-rt',
        #  client_name='example',
        #  )
        #config(data_offset=0, backend='jack-rt', client_name='midj')
        mid.config(data_offset=0, backend='jack', client_name='midj')

    print('done with config settings')


#-------------------------------------------
# custom dump that adds introspective dump of mididings event info.
class MidHookedDump:
    def __init__(self):
        pass
    def __call__(self, ev):
        #if ev.type_ == CTRL and ev.param == 4:
        #if isinstance(ev, mide.CtrlEvent):
        #   print('CtrlEvent found!')
        if isinstance(ev, mide.MidiEvent):
            print('MidiEvent found!')
        if ev.type_ == mid.CTRL:
            print('CTRL Event found!')
        if ev.type_ == mid.ANY:
            print('ANY Event found!')
        if ev.type_ == mid.NOTEON:
            print('NOTEON Event found!')
        if ev.type_ == mid.NOTEOFF:
            print('NOTEOFF Event found!')
        if ev.type_ == mid.PROGRAM:
            print('PROGRAM Event found!')
        if ev.type_ == mid.PITCHBEND:
            print('PITCHBEND Event found!')
        if ev.type_ == mid.AFTERTOUCH:
            print('AFTERTOUCH Event found!')
        print('ev.type_ = %s' % (str(ev.type_)) )
        print('ev = %s' % (str(ev)) )
        return []

#-------------------------------------------
class MidHookedLayer:
    def __init__(self):
        pass
    def __call__(self, ev):
        #if ev.type_ == CTRL and ev.param == 4:
        result = []
        result.append(NoteOnEvent(ev.port, ev.channel, ev.note, ev.velocity))
        if ev.velocity > 32:
            result.append(NoteOnEvent(ev.port, 9, 34 + ev.note-32, ev.velocity))
        return result



#global mid_last_sys_effect = 1 # remember last changed system effect(first 4 knob)
#---------------------------------------------------
# Router - Map incoming MidiMan knobs to Yoshi controls
class MidHookedRouter:
    def __init__(self, chan):
        print('start MidiMan to Yoshi Router(change pitchwheel high to exit)')
        print('  This maps CC 0-7 - MidiMan knobs, to System and Insert Effect Levels')
        self.last_sys_effect = 1 # remember last changed system effect(first 4 knob)
        self.mChannel = chan
        pass
    def __call__(self, ev):
        #global mid_last_sys_effect
        #last_sys_effect = 1 # remember last changed system effect(first 4 knob)
        #                    # and route knob 5(pan) to this effect
        ch = self.mChannel # send channel
        if ev.type_ == mid.CTRL:
            result = []
            if ev.ctrl >= 1 and ev.ctrl <= 4: # first 4 knobs CC-1 to CC-4
                print('CTRL Event %d found!' % (ev.ctrl))
                effect_num  = 4 # system effect(4=system, 8=insert)
                effect_index = ev.ctrl-1 # effect index
                self.last_sys_effect = effect_index
                map_desc = 'system effect level(%d)= %d' % (effect_index+1, ev.value)
                msb_effect_ctrl = 0 # level(volume, dry/wet)
                cc_data = ev.value  # route CC data value to new use
                result.append(mide.CtrlEvent(ev.port, ch, 99, effect_num)) # MSB NRPN
                result.append(mide.CtrlEvent(ev.port, ch, 98, effect_index)) # LSB NRPN
                result.append(mide.CtrlEvent(ev.port, ch, 6, msb_effect_ctrl))
                result.append(mide.CtrlEvent(ev.port, ch, 38, cc_data))
                print('map CC %d %d to: ' % (ev.ctrl+1, ev.value) + map_desc)
                return result
            elif ev.ctrl == 5:
                map_desc = ' master PAN CC-10= %d' % (ev.value)
                result.append(mide.CtrlEvent(ev.port, ch, 10, ev.value)) # route to CC-10 PAN(master)
                print('map CC-%d %d to PAN CC-10:' % (ev.ctrl, ev.value) + map_desc)
                return result
            elif ev.ctrl == 6:
                effect_num  = 4 # system effect(4=system, 8=insert)
                effect_index = self.last_sys_effect # effect index, last vol chged above
                self.last_sys_effect = effect_index
                map_desc = ' Effect Pan, System(%d)= %d' % (effect_index+1, ev.value)
                msb_effect_ctrl = 1 # Pan
                cc_data = ev.value  # route CC data value to new use
                result.append(mide.CtrlEvent(ev.port, ch, 99, effect_num)) # MSB NRPN
                result.append(mide.CtrlEvent(ev.port, ch, 98, effect_index)) # LSB NRPN
                result.append(mide.CtrlEvent(ev.port, ch, 6, msb_effect_ctrl))
                result.append(mide.CtrlEvent(ev.port, ch, 38, cc_data))
                print('map CC %d %d to: ' % (ev.ctrl+1, ev.value) + map_desc)
                return result
            elif ev.ctrl == 7:
                map_desc = 'master Yoshi-Portamento CC-65= %d' % (ev.value)
                # This seems digital, > 64 is on, less off
                result.append(mide.CtrlEvent(ev.port, ch, 65, ev.value)) # route to CC-65 Yoshi portamento
                print('map CC %d %d to: ' % (ev.ctrl+1, ev.value) + map_desc)
                return result
            elif ev.ctrl == 8:
                # yoshi expression cc-11, seems like same as master volume?
                map_desc = 'master Yoshi-Sustain CC-64= %d' % (ev.value)
                result.append(mide.CtrlEvent(ev.port, ch, 64, ev.value)) # route to CC-11 Yoshi portamento
                print('map CC %d %d to: ' % (ev.ctrl+1, ev.value) + map_desc)
                return result
        elif ev.type_ == mid.NOTEON:
            print('ch:%d NoteOn:%d Vel:%d' % (ev.channel, ev.note, ev.velocity))
        else:
            print('Unhandled event, type:%d' % (ev.type))


#-------------------------------------------
# parse a num, or return @defnum if invalid
def GetNum(str, defnum=-1):
    try:
        num = int(str)
    except:
        num = defnum
    return num

#-------------------------------------------
# read from console a simple decimal number with prompt
def GetNumPrompt(prompt='Num:', defnum=-1):
    while 1:
        s = raw_input(prompt)
        if s == '':
            return defnum
        n = GetNum(s, -99999)
        if n == -99999:
            print('Invalid number, try again, or blank for default(%d)' % defnum)
        else:
            return n

#-------------------------------------------
# return a list selection, allow p(plus), m(minus) q(quit), or num entry.
# scan list for next/prev one.
def GetNextInput(str, num_list, cur_num):
    if str == 'p': # plus 1
        cur_num += 1
        cur_num = FindKey(cur_num, num_list, 1) # find next going up
    elif str == 'l': # less 1
        cur_num -= 1
        cur_num = FindKey(cur_num, num_list, -1) # find next going down
    elif str == 'q': # quit
        cur_num = -1
    else:
        cur_num = GetNum(str,-1)
        if cur_num != -1:
            cur_num = FindKey(cur_num, num_list, 1)
    return cur_num

#-------------------------------------------
# find next num(prog_num) in list(keys), kludgy..but..
def FindKey(prog_num, keys, incr):
    while prog_num not in keys:
        prog_num += incr
        if (prog_num < 0 or prog_num > 150):
            return 1 # punt
    return prog_num

#-------------------------------------------
# save a Note(as in comment) on some bank/instrument(@desc)
def SaveNoteComment(desc):
    s = raw_input('Note for[%s]:' % desc)
    f = open('yoshi_notes.txt', 'a')
    f.write('Note for %s:\n' % desc)
    f.write(s + '\n')
    f.close()
    print('added to yoshi_notes.txt')

#-------------------------------------------
# Return a summary description short string of CC control bytes
def SummaryCC_Desc(m_b1, m_b2):
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
# This class hides backend driver details.
class MidiDevice:
    def __init__(self):
        self.mDevOut = None
        self.mDevIn = None
        self.rtmidi_pkt = None
        self.rtmidi_pkt_read_flag = False
        self.last_alsaseq_pkt = None

    #---------------------------------------------------
    def PrintDevices(self, InOrOut):
        if back_end == 'pypm':
            for loop in range(pypm.CountDevices()):
                interf,name,inp,outp,opened = pypm.GetDeviceInfo(loop)
                if ((InOrOut == INPUT) & (inp == 1) |
                    (InOrOut == OUTPUT) & (outp ==1)):
                    print loop, name," ",
                    if (inp == 1): print "(input) ",
                    else: print "(output) ",
                    if (opened == 1): print "(opened)"
                    else: print "(unopened)"
            print
        elif back_end == 'alsaseq':
            self.mDevIn = alsaseq.client('rtmid_alsaseq', 1, 1, False)
            self.mDevOut = self.mDevIn
        elif back_end == 'rtmidi':
            if InOrOut == INPUT:
                mt = rtmidi.MidiIn()
            else:
                mt = rtmidi.MidiOut()
                print('according to get_ports():')
                pn = mt.get_ports()
                for p in pn:
                    print('name:' + p)

                print('according to get_port_name():')
                n = mt.get_port_count()
                for i in range(n):
                    print('%d) %s' % (i, mt.get_port_name(i)))
            del mt
        elif back_end == 'mididings':
            print('mididings not implemented')

    #---------------------------------------------------
    def pickInput(self):
        if self.mDevIn:
            print('closing existing input')
            del self.mDevIn
            self.mDevIn = None

        dev = -1
        if back_end == 'pypm':
                # list in devices according to alsa:
            os.system('aconnect -i')
            self.PrintDevices(INPUT)
            dev = GetNumPrompt('Input input device number:', -1)
            if dev == -1:
                print('no input picked')
                return False

        if back_end == 'pypm':
            self.mDevIn = pypm.Input(dev)
        elif back_end == 'alsaseq':
            print('alsaseq opening input/output virtual client')
            if not self.mDevIn:
                junk = alsaseq.client('py_alsaseq', 1, 1, False) # returning None
                self.mDevIn = 1
                self.mDevOut = self.mDevIn
        elif back_end == 'rtmidi':
            print('rtmidi opening input/output virtual client')
            self.mDevIn = rtmidi.MidiIn()
            self.mDevOut = rtmidi.MidiOut()
            self.mDevIn.open_virtual_port("py_rtmidi")
            self.mDevOut.open_virtual_port("py_rtmidi")
            print('open input rtmidi')
        elif back_end == 'mididings':
            print('mididings not implemented')
            return False

        print('Midi input opened.')
        return True

    #---------------------------------------------------
    def pickOutput(self):
        if self.mDevOut:
            print('closing existing output')
            del self.mDevOut
            self.mDevOut = None

        dev = -1
        if back_end == 'pypm':
            os.system('aconnect -o')  # list out devices according to alsa:
            self.PrintDevices(OUTPUT) # print selection list according to pyportmidi
            dev = GetNumPrompt('Enter output device number:', -1)
            if dev == -1:
                print('no output picked')
                return False

        if back_end == 'pypm':
            latency = 20 # msec latency.
            self.mDevOut = pypm.Output(dev, latency)
        elif back_end == 'alsaseq':
            print('alsaseq opening input/output virtual client')
            if not self.mDevIn:
                junk = alsaseq.client('py_alsaseq', 1, 1, False) # returning None
                self.mDevIn = 1
                self.mDevOut = self.mDevIn
        elif back_end == 'rtmidi':
            print('rtmidi opening input/output virtual client')
            self.mDevIn = rtmidi.MidiIn()
            self.mDevOut = rtmidi.MidiOut()
            self.mDevIn.open_virtual_port("py_rtmidi")
            self.mDevOut.open_virtual_port("py_rtmidi")
            print('output open, rtmidi')
        elif back_end == 'mididings':
            print('mididings not implemented')
            return False

        print ('Midi output opened')
        return True

    #---------------------------------------------------
    # Open input device if needed
    def CheckDevInOpen(self):
        # this is a messy work in progress
        single_client = False
        virtual_client = False
        if back_end == 'pypm':
            pass
        elif back_end == 'alsaseq':
            single_client = True
            virtual_client = True
        elif back_end == 'rtmidi':
            single_client = True
            virtual_client = True
        elif back_end == 'mididings':
            single_client = True
            virtual_client = True

        if single_client and virtual_client:
            if not self.mDevIn:
                print('CheckDevInOpen - opening')
                ok =  self.pickInput()
                if not self.mDevIn:
                    print('CheckDevInOpen - Input did not open!')
                if not self.mDevOut:
                    print('CheckDevInOpen - Output did not open!')
                return ok
            return True
        else:
            if not self.mDevIn:
                return self.pickInput()
            return True
        return False

    #---------------------------------------------------
    # Open output device if needed
    def CheckDevOutOpen(self):
        # this is a messy work in progress
        single_client = False
        virtual_client = False
        if back_end == 'pypm':
            pass
        elif back_end == 'alsaseq':
            single_client = True
            virtual_client = True
        elif back_end == 'rtmidi':
            single_client = True
            virtual_client = True
        elif back_end == 'mididings':
            single_client = True
            virtual_client = True

        if single_client and virtual_client:
            if not self.mDevOut:
                print('CheckDevOutOpen - opening')
                return self.pickOutput()
            return True
        else:
            if not self.mDevOut:
                return self.pickOutput()
            return True
        return False

    #---------------------------------------------------
    def Poll(self):
        if back_end == 'pypm':
            return self.mDevIn.Poll()
        elif back_end == 'alsaseq':
            return alsaseq.inputpending()
        elif back_end == 'rtmidi':
            if self.rtmidi_pkt_read_flag:
                self.rtmidi_pkt = None
            if not self.rtmidi_pkt:
                self.rtmidi_pkt = self.mDevIn.get_message()
                self.rtmidi_pkt_read_flag = False
            if self.rtmidi_pkt != None:
                return True
        elif back_end == 'mididings':
            print('mididings not implemented')
            return False
        return False

    #---------------------------------------------------
    def Read(self, num_events):
        if back_end == 'pypm':
            pkt = self.mDevIn.Read(num_events)
            m_time = pkt[0][1]
            b0 = pkt[0][0][0]
            b1 = pkt[0][0][1]
            b2 = pkt[0][0][2]
            b3 = pkt[0][0][3]
            return (m_time, b0, b1, b2, b3)
        elif back_end == 'alsaseq':
            pkt = alsaseq.input()
            mtype = pkt[0]
            flags = pkt[1]
            tag = pkt[2]
            queue = pkt[3]
            #m_time = pkt[4] todo...
            m_time = 0
            src = pkt[5]
            dest = pkt[6]
            mdata = pkt[7]
            if mtype == alsaseq.SND_SEQ_EVENT_SENSING: #42: # tick?  get about 3 per second
                return None

            b0 = mdata[0] # 0, ch? mtype=6
            b1 = mdata[1] # note
            b2 = mdata[2] # velocity
            b3 = mdata[3] # 0

            print(pkt) # need to debug,understand, print it.
            if mtype == alsaseq.SND_SEQ_EVENT_NOTEON: #6:
                if len(mdata) != 5:
                    print('noteon unexpected len:%d' % (len(mdata)))
                print('ch:%d noteon:%d vel:%d' % (b0, b1, b2))
                return (m_time, b0 | 0x80, b1, b2, b3)
            if mtype == alsaseq.SND_SEQ_EVENT_NOTEOFF: #7:
                if len(mdata) != 5:
                    print('noteoff unexpected len:%d' % (len(mdata)))
                print('ch:%d noteoff:%d vel:%d' % (b0, b1, b2))
                return (m_time, b0 | 0x90, b1, b2, b3)
            elif mtype == alsaseq.SND_SEQ_EVENT_CONTROLLER: #10:
                if len(mdata) != 6:
                    print('cc unexpected len:%d' % (len(mdata)))
                b4 = mdata[4] # cc number
                b5 = mdata[5] # value
                print('ch:%d cc:%d val:%d' % (b0, b4, b5))
                return (m_time, b0 | 0xb0, b4, b5, b3)
            elif mtype == alsaseq.SND_SEQ_EVENT_PITCHBEND: # 13:
                if len(mdata) != 6:
                    print('cc unexpected len:%d' % (len(mdata)))
                b4 = mdata[4] # cc number
                b5 = mdata[5] # value here, see on pitch wheel -8192 to 8192
                print('ch:%d cc-ext?pitch? cc:%d val:%d' % (b0, b4, b5))
                return (m_time, b0 | 0xe0, b4, b5, b3)
            else:
                print('unhandled alsaseq pkt type:%d' % (mtype))
                print(pkt)
            return None
        elif back_end == 'rtmidi':
            if not self.rtmidi_pkt:
                return None

            self.rtmidi_pkt_read_flag = True
            print('rtmidi pkt:')
            print(self.rtmidi_pkt)
            buf = self.rtmidi_pkt[0]
            mtime = self.rtmidi_pkt[1]
            ret_pkt = [mtime,]
            for b in buf:
                ret_pkt.append(b)
            ret_pkt.append(0)
            return ret_pkt
        elif back_end == 'mididings':
            print('mididings Read not implemented')
            return None

    #---------------------------------------------------
    def Write(self, pkt, mtime=None):
        if back_end == 'pypm':
            if mtime == None:
                mtime = pypm.Time()
            self.mDevOut.Write([[pkt,mtime]])
        elif back_end == 'alsaseq':
            # work in progress, alsa event handling is very complex...
            if self.last_alsaseq_pkt:
                    # just copy from last in pkt, reverse src,dest
                    # this is just a quick hack workaround.
                dest = self.last_alsaseq_pkt[5] # src
                src = self.last_alsaseq_pkt[6] # dest
            else:
                # otherwise punt, try setting them to (0,0).
                dest = (0,0)
                src = (0,0)

            if (pkt[0] & 0xf0) == 0x80: # NoteOn
                alsa_pkt = (alsaseq.SND_SEQ_EVENT_CONTROLLER, # mtype
                  0, 0, 253, # flags, tag, queue
                  (0,0), # m_time
                  src, # src
                  dest, # dest
                  (0, pkt[1], pkt[2], 0, 100)) # mdata
                alsaseq.output(alsa_pkt)
                print('tried sending alsa note on')
            elif (pkt[0] & 0xf0) == 0xb0: # CC
                alsa_pkt = (alsaseq.SND_SEQ_EVENT_CONTROLLER, # mtype
                  0, 0, 253, # flags, tag, queue
                  (0,0), # m_time
                  src, # src
                  dest, # dest
                  (1, 0, 0, 0, pkt[1], pkt[2])) # mdata: ? ? ? ctrl-num, value
                alsaseq.output(alsa_pkt)
                print('tried sendin alsa cc %02x %02x' % (pkt[1], pkt[2]))
            else:
                print('todo: send alsaseq')
                return False
        elif back_end == 'rtmidi':
            self.rtmidi_pkt = self.mDevOut.send_message(pkt)
            #note_on = [0x90, 60, 112] # channel 1, middle C, velocity 112
            #note_off = [0x80, 60, 0]
            #mDevOut.send_message(note_on)
            #time.sleep(0.5)
            #mDevOut.send_message(note_off)
        elif back_end == 'mididings':
            print('mididings Write not implemented')
            return False
        return True

    #---------------------------------------------------
    def Close(self):
        if back_end == 'pypm':
            if self.mDevOut:
                del self.mDevOut
            if self.mDevIn:
                del self.mDevIn
        elif back_end == 'alsaseq':
            print('todo: close alsaseq')
        elif back_end == 'rtmidi':
            if self.mDevOut:
                del self.mDevOut
            elif self.mDevIn:
                del self.mDevIn
            print('closed rtmidi')
        elif back_end == 'mididings':
            print('todo: close mididings')
        return True

        pypm.Terminate()

    #---------------------------------------------------
    def Init(self):
        if back_end == 'pypm':
            pypm.Initialize()
        elif back_end == 'alsaseq':
            #print('todo: init alsaseq')
            pass
        elif back_end == 'rtmidi':
            #print('todo: init rtmidi')
            pass
        elif back_end == 'mididings':
            #print('todo: init mididings')
            pass

#-------------------------------------------
#-------------------------------------------
class YoshiBankProg:
    def __init__(self, mDev):
        self.mDev = mDev
        self.mChannel = 0
        self.mBank = 5
        self.mProg = 1

    #---------------------------------------------------
    def readYoshiBankConfig(self):
        print('scanning config')
        cfg_file = os.path.expandvars('$HOME/.config/yoshimi/yoshimi.banks')
        fp = gzip.open(cfg_file, 'r') # the .bank file is gzipped
        l = fp.readline()
        #print('line:' + l)
        ls = fp.readlines()
        #print('[%s]num lines:%d' % (cfg_file, len(ls)))
        fp.close()
        # this parsing is quick and dirty, should switch to xml lib, or better parsing..
        bank_root = ''
        bank_num_name = [] # make a list of lists to return of [bank_num, bank_name, Key_ProgInfo]
        bank_name = ''
        bank_num = -1
        #for l in fp:
        for l in ls:
            l = l.strip()
            #print('grepping:' + l)
            if bank_root == '':
                if l.find('name="bank_root"') >= 0:
                    i1 = l.find('">') + 2
                    i2 = l.find('</')
                    bank_root = l[i1:i2]
                    #print('bank_root:' + bank_root)
                continue
            i0 = l.find('<bank_id id=')
            if i0 >= 0:
                i1 = l.find('"') + 1
                i2 = l.find('">')
                bank_num = int(l[i1:i2])
                #print('bank_num:%d' %(bank_num))
            i0 = l.find('dirname">')
            if i0 >= 0:
                i1 = i0 + 9
                i2 = l.find('</')
                bank_name = l[i1:i2]
                #print('bank_name:' + bank_name)
                bank_num_name.append([bank_num, bank_name, None]) # reserve [2] for attaching prog info
                bank_num = -1
                bank_name = ''

        #print('bank_root:' + bank_root)
        for e in bank_num_name:
            #print('%d) %s' % (e[0], e[1]))
            dir = bank_root + '/' + e[1]
            list = os.listdir(dir)
            bank_dict = {}
            for l in list:
                #print(l)
                if l.startswith('0'):
                    num = int(l[0:4])
                    i2 = l.find('.xiz')
                    name = l[5:i2]
                    #print(' %d>%s' % (num, name))
                    bank_dict[num] = name
            e[2] = bank_dict
        return bank_num_name # return our list of Yoshi Bank information

    #---------------------------------------------------
    # Allow to pick bank and instrument choices, Yoshimi
    def bankBrowser(self):
        print('reading yoshi config info...')
        cfg = self.readYoshiBankConfig() # returns list [[bank_num, bank_name, spare],..]
        ch = self.mChannel

        print('For selections num=number, p=plus(next), l=less(previous),')
        print(' n=save note comment, q=quit')

        while 1:
            i = 0
            line = ''
            bank_nums = []
            for e in cfg:
                bank_nums.append(e[0])

            bank_desc = ''
            # print the list of bank choices
            for e in cfg:
                bank_num = e[0]
                bank_name = e[1]
                if len(bank_name) > 20: bank_name = bank_name[0:20] # limit name size
                entry = '%3d) %-20s ' % (bank_num, bank_name)
                if bank_num == self.mBank:
                    entry = entry.replace(' ', '_') # highlight current selection with '_'
                    entry = entry.replace(')', ']') # highlight current selection ')' -> ']'
                    bank_desc = bank_name # cache current selection name
                line += entry
                i += 1
                if (i % 3) == 0:
                    print(line)
                    line = ''
            if len(line) > 0: print(line)

            bank_info = None
            prompt = '(%d)Enter bank(num,p,l,n,q):' % (self.mBank)
            str = raw_input(prompt)
            if str == 'n':
                SaveNoteComment('Bank %d[%s]' % (self.mBank, bank_desc))
                continue
            bank_num = GetNextInput(str, bank_nums, self.mBank)
            if bank_num == -1:
                break # quit
            if self.mBank != bank_num:
                self.mBank = bank_num
                self.mProg = 1

            for e in cfg:
                if e[0] == self.mBank:
                    bank_info = e
                    break

            if not self.mDev.CheckDevOutOpen():
                print('No Output open')
                return

            prog_num = self.mProg
            #self.mDev.Write([0xb0 | ch,0,bank_num])
            self.mDev.Write([0xb0 | ch,0,bank_num])
            self.mDev.Write([0xb0 | ch,0x20,0]) # lsb not used in yoshi(do not need?)
            # need to send prog change to activate ?  I think so..
            self.mDev.Write([0xc0 | ch, self.mProg-1])

            prog_desc = '?'
            while 1:
                keys = sorted(bank_info[2].keys()) # sort Prog key numbers
                # Print out menu of Prog choices.  3 columns.  Highlight current selection.
                print('------ Bank %3d) %-20s Program Selection --------' % (self.mBank, bank_desc))
                num = len(keys)
                ki = 0
                line = '' # TODO: match layout(32 lines per col) as gui would be nice.
                prog_desc = ''
                for k in keys:
                    name = bank_info[2][k]
                    if len(name) > 20:
                        name = name[0:19] + ':'
                    entry = '%3d. %-20s ' % (k, name)
                    if self.mProg == k:
                        entry = entry.replace(' ', '_') # highlight cur prog selection
                        entry = entry.replace('.', ':')
                        prog_desc = name # cache
                    line += entry
                    ki += 1
                    if (ki % 3) == 0:
                        print(line)
                        line = ''
                if len(line) > 0: print(line)

                # Prompt for entry of program choice
                prompt = '(%d-%d) Choice(num,p,l,n,q):' % (self.mBank, self.mProg)
                str = raw_input(prompt)
                if str == 'n':
                    SaveNoteComment('Bank %d[%s] Prog %d[%s]' % \
                      (self.mBank, bank_desc, self.mProg, prog_desc))
                    continue
                prog_num = GetNextInput(str, keys, self.mProg)
                if prog_num == -1:
                    break # quit
                self.mProg = prog_num
                # prog_num is zero indexed going out midi(1-indexed in yoshi list)
                self.mDev.Write([0xc0 | ch, self.mProg-1])

#-------------------------------------------
#-------------------------------------------
class MidiTester:
    def __init__(self):
        #self.mDevOut = None
        #self.mDevIn = None
        self.mDev = MidiDevice()
        self.mChannel = 0
        self.mBank = 5
        self.mProg = 1
        self.yoshiBankProg = None

    #---------------------------------------------------
    # Router - Map incoming MidiMan knobs to Yoshi controls
    # For starters, let's assume the keys are connected to Yoshi in parallel to us.
    #  so we do not have to pass thru events.  We just capture them and send Yoshi
    #  some altered events to control the things we want.  This may conflict with
    #  any existing CC mappings done by Yoshimi, but we don't care now, this is just
    #  the simplest thing to do.  You could filter out with mididings if you wanted.
    # Currently I have system effects setup as: reverb, alienwah, phaser, echo.
    def MidimanToYoshiRouter(self):
        print('start MidiMan to Yoshi Router(change pitchwheel high to exit)')
        print('  This maps CC 0-7 - MidiMan knobs, to System and Insert Effect Levels')

        if back_end == 'mididings':
            print('press ctrl-c to break out of mididings processing loop')
            self.MidDoHookedRouter()
            return

        if not self.mDev.CheckDevInOpen():
            print('No Input open')
            return
        if not self.mDev.CheckDevOutOpen():
            print('No Output open')
            return
        mIn  = self.mDev
        mOut = self.mDev
        last_sys_effect = 1 # remember last changed system effect(first 4 knob)
                            # and route knob 5(pan) to this effect
        ch = self.mChannel # send channel
        while 1:
            while not mIn.Poll():
                time.sleep(0.0100)
            pkt = mIn.Read(1) # read only 1 message at a time
            if pkt == None:
                continue # ignore bogus(alsaseq giving 3 odd pkts per sec)
            m_time = pkt[0]
            m_b0 = pkt[1]
            m_b1 = pkt[2]
            m_b2 = pkt[3]
            m_b3 = pkt[4]
            if (m_b0 & 0xf0) == 0xe0: # pitch wheel change
                if m_b1 > 120:
                    print('exiting on pitchwheel change')
                    break
            rx_ch = m_b0 & 0xf
            if (m_b0 & 0xf0) == 0xb0:
                desc = 'ch:%d CC %d Val:%d' % (rx_ch, m_b1, m_b2)
                desc +=  SummaryCC_Desc(m_b1, m_b2)
                print(desc)
                # we have 8 knobs.  On my Oxygen 8, these come as ch2(for some reason)
                # and appear as CC #
                if m_b1 >= 1 and m_b1 < 5: # first 4 knobs CC-1 to CC-4
                    effect_num  = 4 # system effect(4=system, 8=insert)
                    effect_index = m_b1-1 # effect index
                    last_sys_effect = effect_index
                    map_desc = 'system effect level(%d)= %d' % (effect_index+1, m_b2)
                    msb_effect_ctrl = 0 # level(volume, dry/wet)
                    cc_data = m_b2 # route CC data value to new use
                    mOut.Write([0xb0 | ch, 99,effect_num]) # MSB NRPN
                    mOut.Write([0xb0 | ch, 98, effect_index]) # LSB NRPN
                    mOut.Write([0xb0 | ch, 6,  msb_effect_ctrl])
                    mOut.Write([0xb0 | ch, 38, cc_data])
                    print('map CC %d %d to: ' % (m_b1, m_b2) + map_desc)
                elif m_b1 == 5:
                    map_desc = ' master PAN CC-10= %d' % (m_b2)
                    mOut.Write([0xb0 | ch, 10, m_b2]) # route to CC-10 PAN(master)
                    print('map CC-%d %d to PAN CC-10:' % (m_b1, m_b2) + map_desc)
                elif m_b1 == 6:
                    effect_num  = 4 # system effect(4=system, 8=insert)
                    effect_index = last_sys_effect # effect index, last vol chged above
                    map_desc = ' Effect Pan, System(%d)= %d' % (effect_index+1, m_b2)
                    msb_effect_ctrl = 1 # Pan
                    cc_data = m_b2 # route CC data value to new use
                    mOut.Write([0xb0 | ch, 99,effect_num]) # MSB NRPN
                    mOut.Write([0xb0 | ch, 98, effect_index]) # LSB NRPN
                    mOut.Write([0xb0 | ch, 6,  msb_effect_ctrl])
                    mOut.Write([0xb0 | ch, 38, cc_data])
                    print('map CC %d %d to: ' % (m_b1, m_b2) + map_desc)
                elif m_b1 == 7:
                    map_desc = 'master Yoshi-Portamento CC-65= %d' % (m_b2)
                    # This seems digital, > 64 is on, less off
                    mOut.Write([0xb0 | ch, 65, m_b2]) # route to CC-65 Yoshi portamento
                    print('map CC-%d %d to: ' % (m_b1, m_b2) + map_desc)
                elif m_b1 == 8:
                    # yoshi expression cc-11, seems like same as master volume?
                    #map_desc = 'master Yoshi-Expression CC-11= %d' % (m_b2)
                    #mOut.Write([0xb0 | ch, 11, m_b2]) # route to CC-11 Yoshi portamento
                    map_desc = 'master Yoshi-Sustain CC-64= %d' % (m_b2)
                    mOut.Write([0xb0 | ch, 64, m_b2]) # route to CC-11 Yoshi portamento
                    print('map CC-%d %d to: ' % (m_b1, m_b2) + map_desc)

            elif (m_b0 & 0xf0) == 0x90:
                print('ch:%d NoteOn:%d Vel:%d' % (rx_ch, m_b1, m_b2))
            else:
                print('Unhandled event ch:%d Cmd:%d Vel:%d' % (rx_ch, m_b1, m_b2))

    #---------------------------------------------------
    # Mididings dump simple
    def MidDumpSimple(self):
        print('mididings: run simple dump Print()')
        patch = (
         # filter out SysEx Sensing(ongoing noise for me)
         ~mid.Filter(mid.SYSRT_SENSING) >> # ~ is invert filter
         # route it to just print out the event info.
         mid.Print()
        )
        mid.run(patch)

    #---------------------------------------------------
    # Mididings hooked custom dump
    def MidDumpHookCustom(self):
        print('mididings: run hooked custom dump')
        patch = (
         # filter out SysEx Sensing(ongoing noise for me)
         ~mid.Filter(mid.SYSRT_SENSING) >> # ~ is invert filter
         # route it to just print out the event info.
         mid.Print() >>
         # now route it to our custom MidHookedDump
         mid.Process(MidHookedDump())
        )
        mid.run(patch)

    #---------------------------------------------------
    # Mididings dump simple
    def MidDoHookedRouter(self):
        print('mididings: run hooked router')
        patch = (
         # filter out SysEx Sensing(ongoing noise for me)
         ~mid.Filter(mid.SYSRT_SENSING) >> # ~ is invert filter
         # route it to just print out the event info.
         mid.Print() >>
         # now route it to our custom MidHookedDump
         mid.Process(MidHookedRouter(self.mChannel))
        )
        mid.run(patch)

    #---------------------------------------------------
    # Test Input, pick an input to hook to, show/dump midi X number of events:
    def testInput(self):
        if back_end == 'mididings':
            print('''
  press ctrl-c to break out of mididings processing listen
  1 - Basic Print() of input events.
  2 - Hooked custom print of input events.
''')
            k = raw_input('Enter choice(q,1..2):')
            if k == '1':
                self.MidDumpSimple()
            elif k == '2':
                self.MidDumpHookCustom()
            return

        if not self.mDev.CheckDevInOpen():
            print('No Input open')
            return
        mIn = self.mDev
        NUM_MSGS = 100
        print('Showing %d midi events...' % (NUM_MSGS))

        # MidiIn.SetFilter(pypm.FILT_ACTIVE | pypm.FILT_CLOCK)
        c_i = 0
        while 1:
            while not mIn.Poll():
                time.sleep(0.0100)
            pkt = mIn.Read(1) # read only 1 message at a time
            if pkt == None:
                continue # ignore bogus(alsaseq giving 3 odd pkts per sec)
            m_time = pkt[0]
            m_b0 = pkt[1]
            m_b1 = pkt[2]
            m_b2 = pkt[3]
            m_b3 = pkt[4]
            s =   '%d) time:%d %02x %02x %02x %02x ' % (c_i, m_time, m_b0, m_b1, m_b2, m_b3)
            desc = ''
            ch = m_b0 & 0xf
            if (m_b0 & 0xf0) == 0x80:
                desc += 'ch:%d NoteOff:%d' % (ch, m_b1)
            elif (m_b0 & 0xf0) == 0x90:
                desc += 'ch:%d NoteOn:%d Vel:%d' % (ch, m_b1, m_b2)
            elif (m_b0 & 0xf0) == 0xa0:
                desc += 'ch:%d Note:%d PolyPress:%d' % (ch, m_b1, m_b2)
            elif (m_b0 & 0xf0) == 0xb0:
                desc += 'ch:%d CC %d Val:%d ' % (ch, m_b1, m_b2)
                desc += SummaryCC_Desc(m_b1, m_b2)
            elif (m_b0 & 0xf0) == 0xc0:
                desc += 'ch:%d PROG %d' % (ch, m_b1)
            elif (m_b0 & 0xf0) == 0xd0:
                desc += 'ch:%d ChPress %d' % (ch, m_b1)
            elif (m_b0 & 0xf0) == 0xe0:
                desc += 'ch:%d Pitch LSB:%d MSB:%d' % (ch, m_b1, m_b2)
            print (s + desc)
            # NOTE: most Midi messages are 1-3 bytes,
            # but the 4 byte is returned for use with SysEx messages.

            c_i += 1
            if c_i >= NUM_MSGS:
                break;



    #---------------------------------------------------
    def pickChannel(self):
        ch = GetNumPrompt('Enter channel number(0-15):', 0)
        self.mChannel = ch

    #---------------------------------------------------
    def sendMidiTest(self):
        if not self.mDev.CheckDevOutOpen():
            print('No Output open')
            return
        mOut = self.mDev
        while 1:
            print('''
Test Output Menu:
  b - send bank change
  c - send control change
  e - first sys effect send wet/dry(yoshi)
  n - send note on, note off
  p - send program change
  x - send an NRPN
  q - quit
''')
            k  = raw_input('Enter choice and enter:')
            ch = self.mChannel # just assume channel 0 for now

            #if k == 'bank':
            #    self.bankBrowser()
            if k.startswith('b'):
                bank_num = int(raw_input('Enter bank to change to(0-127):'))
                mOut.Write([0xb0 | ch,0,bank_num])
                mOut.Write([0xb0 | ch,0x20,0]) # lsb not used in yoshi
                prog_num = 0 # need to send prog change to activate
                mOut.Write([0xc0 | ch, prog_num])
                print('done')
            elif k.startswith('c'):
                print('''
   controller change notes:
   1-modwheel 2-breath 4-foot 5-portamento 6-data(rpn/nrpn) 7-volume
   8-balance 10-pan 11-expression 12-effect ctrl 1, 13-effect ctrl 2
''')
                cc_num = GetNumPrompt('Enter control to change(0-127):')
                cc_data = GetNumPrompt('Enter data to send(0-127):')
                mOut.Write([0xb0 | ch, cc_num,cc_data])
                print('done')
            elif k.startswith('e'):
                effect_num  = 4 # insert effect(4=sys, 8=insert)
                effect_index = 0 # first effect index
                msb_effect_ctrl = 0 # level
                cc_data = GetNumPrompt('Enter wet/dry for sys.effect0(0-127):')
                mOut.Write([0xb0 | ch, 99,effect_num])
                mOut.Write([0xb0 | ch, 98, effect_index])
                mOut.Write([0xb0 | ch, 6,  msb_effect_ctrl])
                mOut.Write([0xb0 | ch, 38, cc_data])
                print('done')
            elif k.startswith('l'):
                self.testInput()
            elif k == 'n':
                note_num = GetNumPrompt('Enter note to toggle on off(0-127):')
                mOut.Write([0x90 | ch,note_num,100])
                time.sleep(1.0)
                mOut.Write([0x80 | ch,note_num,0])
                print('done')
            elif k.startswith('p'):
                prog_num = GetNumPrompt('Enter program to change to(0-127):')
                mOut.Write([0xc0 | ch, prog_num])
                print('done')
            elif k == 'x':
                msb = GetNumPrompt('Enter CC-99 MSB(0-127):')
                lsb = GetNumPrompt('Enter CC-98 LSB(0-127):')
                d_lsb = GetNumPrompt('Enter Data-Entry CC-6 MSB(0-127):')
                d_lsb = GetNumPrompt('Enter Data-Entry CC-38 LSB(0-127):')
                mOut.Write([0xb0 | ch, 99, msb])
                mOut.Write([0xb0 | ch, 98, lsb])
                mOut.Write([0xb0 | ch, 6,  d_msb])
                mOut.Write([0xb0 | ch, 38, d_lsb])
            elif k.startswith('q'):
                print('quiting')
                break
            else: print('Unknown cmd:' + k)


    #---------------------------------------------------
    def testMidi(self):
        if back_end == 'mididings':
            print('setting up mididings virtualclient')
            # no, just use default, creates ALSA virtual client 'mididings'
            setup_mid_conn()

        while 1:
            ch = 0 # just assume channel 0 for now
            print('''
 Main Menu:
  bank - Yoshimi bank browser, picker and comment maker.
  channel - Pick a channel to send on.
  input - pick input device(keys,ctrl)
  listen - listen and report 100 midi input events.
  midiyoshi - Route midiman knobs to yoshi effects
  output - pick output device(synth)
  sendmidi - Send various midi messages to a Synth, for simple testing.
   (follow with Enter, only first character above will work too)
  q - quit
''')
            k  = raw_input('Enter choice and enter:')
            if k.startswith('b'):
                if not self.yoshiBankProg:
                    self.yoshiBankProg = YoshiBankProg(self.mDev)
                #self.bankBrowser()
                self.yoshiBankProg.bankBrowser()
            if k.startswith('c'):
                self.pickChannel()
            elif k.startswith('i'):
                if not self.mDev.CheckDevInOpen():
                    print('No Input open')
                #self.mDev.pickInput()
            elif k.startswith('l'):
                self.testInput()
            elif k.startswith('m'):
                self.MidimanToYoshiRouter()
            elif k.startswith('o'):
                if not self.mDev.CheckDevInOpen():
                    print('No Output open')
                #self.mDev.pickOutput()
            elif k.startswith('s'):
                self.sendMidiTest()
            elif k.startswith('q'):
                return
            else: print('Unknown cmd:' + k)

    #---------------------------------------------------
    def mainTest(self):
        self.mDev.Init()

        self.testMidi()

        self.mDev.Close()

mo = MidiTester()
mo.mainTest()
