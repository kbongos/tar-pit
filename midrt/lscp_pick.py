#!/usr/bin/python
# App to help quickly load SFZ files from a list.

# kbongosmusic at gmail_com - licensed as GPLv2.

from __future__ import print_function
#from __future__ import unicode_literals
import lscp
import os,sys
import socket

APPNAME = 'lscp_pick'
APPVER  = '0.1'

#=============================
class Empty():
    pass

#=============================
class Global():
    pass

#-------------------------
def gl():
    global _gl
    if not _gl:
        _gl = Global()
        _gl.log = 0
        _gl.lscp_handle = None
        _gl.sfz_list = [] # from scan, list of sfz files found
        _gl.sfz_idx = 0 # last sfz pick
    return _gl

#-------------------------------------
def logit(str, no_cr):
    if gl().log:
        f = open(APPNAME + '.log', 'a')
        if no_cr:
            f.write(str)
        else:
            f.write(str + '\n')
        f.close()

#-------------------------------------
def logprn(str, no_cr):
    if gl().log:
        logit(str, no_cr)
    if no_cr:
        print(str, end='')
    else:
        print(str)

#-------------------------------------
def loge(str):
    logprn('ERROR:' + str,0)

#-------------------------------------
def logi(str):
    logprn(str,0)

#-------------------------------------
def logd(str):
    logprn(str,0)

#-------------------------------------
def pr(str):
    logprn(str,0)

#-------------------------------------
def prn(str):
    logprn(str,1)

#-------------------------------------
def con_input(prompt=None):
    if prompt:
        prn(prompt)
    #if sys.version_info.major >= 3:
    if sys.version_info[0] >= 3:
        s = input() # v3 code, what 2to3 recommends
    else:
        s = raw_input()
    if not s:
        s = ''
    logit(s, 0)
    return s

_gl = None

#-------------------------------------
def addSFZ(filename):
    ' load a sfz file to channel 0 '
    l = gl().lscp_handle
    channel = l.add_channel()
    l.load_engine('sfz',channel)
    l.query('SET CHANNEL AUDIO_OUTPUT_DEVICE %d 0'%channel)
    l.query('SET CHANNEL MIDI_INPUT_DEVICE %d 0' % (channel))
    l.load_instrument(filename, 0, channel)
    gl().lscp_handle = l

#-------------------------------------
def init_lscp():
    ' open a tcp connection to the linuxsampler app '
    try:
        l = lscp.LSCPClient()
        gl().lscp_handle = l
    except socket.error:
        print('Could not connect, linuxsampler not running?')
        sys.exit(1)

#------------------------
def st_fmode(st):
    ' return string indicating file or dir, or other(raw mode hex str). '
    if st.st_mode & 0x4000:
        fmode = 'D'
    elif st.st_mode & 0x8000:
        fmode = 'F'
    else:
        fmode = '%x' % st.st_mode
    return fmode

#-------------------------------------
def search_sfz(dir):
    ' scan dir for sfz files, create a list '
    list = os.listdir(dir)
    fnd_list = []
    for file in list:
        if file in ['.', '..']:
            continue
        dirfile = os.path.join(dir, file)
        st = os.stat(dirfile)
        fmode = st_fmode(st)
        if fmode == 'D':
            search_sfz(dirfile)
        elif fmode == 'F':
            if file.lower().endswith('.sfz'):
                #print('fnd:' + file)
                print(dirfile)
                fnd_list.append(dirfile)
        else:
            print('odd dir entry:' + dirfile + ' mode:' + fmode)

    print('final list:')
    idx = 0
    sfzidx = len(gl().sfz_list)
    for file in fnd_list:
        #line_entry = '%d %s' % (sfzidx, file)
        #print(line_entry)
        gl().sfz_list.append(file)


#-------------------------------------
def au_cmd():
    ' audio info, ask to add if none '
    l = gl().lscp_handle
    lst = l.list_audio_output_devices()
    print('audio output devices:' + str(lst))  # 0,1,2,3
    if len(lst) <= 0:
        c = con_input('create an JACK audio output device?(y/n):')
        if c == 'y':
            l.create_audio_output_device('JACK')
    else:
        print('A JACK audio output device exists')

#-------------------------------------
def ch_cmd():
    ' channel info '
    l = gl().lscp_handle

    ch_lst = l.list_channels()
    print('channels:' + str(ch_lst)) #

    for i in ch_lst:
        info = l.query('GET CHANNEL INFO %d' % (i))
        print('ch:%d => %s' % (i, info))

    lst = l.list_available_engines()
    print('engines:' + str(lst)) #

#-------------------------------------
def info_cmd():
    ' show general info '
    l = gl().lscp_handle
    info = l.get_server_info()
    print('linuxsampler server info:')
    for i in info:
        print('   %s:\t%s'%(i,info[i]))

#-------------------------------------
def md_cmd():
    ' midi info show, inputs, ask to add if none '
    l = gl().lscp_handle
    lst = l.list_available_midi_input_drivers()
    print('available midi input drivers:' + str(lst)) # 'JACK', 'ALSA'

    lst = l.list_midi_input_devices()
    print('midi input devices:' + str(lst))  # 0,1,2,3
    if len(lst) <= 0:
        c = con_input('create an ALSA midi input device?(y/n):')
        if c == 'y':
            l.create_midi_input_device('ALSA')
    else:
        print('A midi input device exists')

#-------------------------------------
def load_sfz_list_file(fname):
    f = open(fname)
    lns = f.readlines()
    for l in lns:
        i = l.find(' ')
        if i>=0:
            #num = int(l[:i])
            fname = l[i+1:].strip()
            gl().sfz_list.append(fname)
    pr('loaded:%d lines' % (len(gl().sfz_list)))

#-------------------------------------
def sfz_file_cmd():
    gl().sfz_list = []
    if 1:
        c = con_input('sfz file to load:')
        if os.path.isfile(c):
            load_sfz_list_file(c)
        else:
            pr('could not find:' + c)

#-------------------------------------
def get_embedded_list():
    home = os.getenv('HOME')
    my_list = '''
$HOME/1/sfz/PianoCrown_v4/piano_crown.sfz
$HOME/1/sfz/hpiano/piano88.sfz
$HOME/1/sfz/VocLa/vocla_03.sfz
'''
    my_list = my_list.replace('$HOME', home)
    sfz_files = []
    for f in my_list.split():
        if len(f) > 0 and os.path.isfile(f):
            sfz_files.append(f)
        else:
            pr('bad entry:' + f)
    return sfz_files

#-------------------------------------
def sfz_load_cmd():
    ' sfz file, ask to load new selection '
    l = gl().lscp_handle
    ch_lst = l.list_channels()
    if len(gl().sfz_list) > 0:
        sfz_files = gl().sfz_list
    else:
        pr('no scan sfz files, using canned embedded list')
        sfz_files = get_embedded_list()

    if 0:
        # show 10 entries starting with current selection -5
        idx = gl().sfz_idx - 5
        if idx > len(sfz_files) or idx < 0:
            idx = 0
        for i in range(10):
            if idx+i >= len(sfz_files):
                break
            pr('%d %s' % (idx+i, sfz_files[idx+i]))

    #idx = gl().sfz_idx
    while 1:
        pr('current:%d' % (gl().sfz_idx))
        nstr = con_input('pick SFZ to load(q,n,0-%d):' % (len(sfz_files)-1))
        if nstr == 'q':
            break
        elif nstr == 'n': # next
            num = gl().sfz_idx + 1
        else:
            try:
                num = int(nstr)
            except:
                num = -1
                pr('bad num')

        if num >= 0 and num < len(sfz_files):
            if len(ch_lst) > 0:
                if len(ch_lst):
                    channel = ch_lst[0]
                    print('removing channel:%d' % (channel))
                    l.remove_channel(channel)

            sfz_file = sfz_files[num]
            print('adding channel:' + sfz_file)
            addSFZ(sfz_file)
            gl().sfz_idx = num

#-------------------------------------
def sfz_scan_cmd():
    home = os.getenv('HOME')
    dir = con_input('enter dir to scan for sfz files:')
    #dir = home + '/1/sfz'

    gl().sfz_list = []

    search_sfz(dir)

    fh = open('sfz_list.out','w')

    sfzidx = 0
    for file in gl().sfz_list:
        line_entry = '%d %s' % (sfzidx, file)
        sfzidx += 1
        print(line_entry)
        fh.write(line_entry + '\n')
    fh.close()
    print('list(%d sfz entries) written to sfz_list.out' % sfzidx)

#-------------------------------------
def main_menu():
    print('''Menu:
      au - view/add audio device
      ch - view/add lscp channels
      info - read and show info
      md - view/add midi input device
      sfz_file - load a file with sfz selections(like sfz_list.out)
      sfz_scan - search for sfz files, make list
      sfz_load - change SFZ selection
      ? - this help
      q - quit/exit
      ''')

#-------------------------------------
def run():
    init_lscp()
    l = gl().lscp_handle

    # load last sfz_list.out file if exists
    fname = 'sfz_list.out'
    if (os.path.isfile(fname)):
        load_sfz_list_file(fname)
        pr('loaded:' + fname)

    lst = l.list_midi_input_devices()
    if len(lst) <= 0:
        md_cmd() # offer to create a midi input channel
    lst = l.list_audio_output_devices()
    if len(lst) <= 0:
        au_cmd() # offer to create a audio output channel

    main_menu()
    while 1:
        ks = con_input('main>')
        if ks == 'q':
            pr('Bye! Thanks for playing!')
            sys.exit(0)
        elif ks == '?':
            main_menu()
        elif ks == 'au':
            au_cmd()
        elif ks == 'ch':
            ch_cmd()
        elif ks == 'info':
            info_cmd()
        elif ks == 'sfz_file':
            sfz_file_cmd()
        elif ks == 'sfz_load':
            sfz_load_cmd()
        elif ks == 'sfz_scan':
            sfz_scan_cmd()
        elif ks == 'md':
            md_cmd()
        else:
            pr('unknown cmd:' + ks)

    sys.exit(0)

    # following didn't work, said connection was active, but it wasn't..
    # close all existing audio links.
    #for i in l.list_audio_output_devices():
    #  l.destroy_audio_output_device(i)

#----------------------------
def main():
    run()

if __name__ == '__main__':
    main()
