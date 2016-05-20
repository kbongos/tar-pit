#!/usr/bin/env python
# yoshibank.py - yoshi bank browsing tools
#  reads yoshi config, allows browsing and activating yoshi bank/prog.
# kbongosmusic at gmail_com - GPLv2

import os,sys
import gzip
#import array
import time

#-------------------------------------------
# save a Note(as in comment) on some bank/instrument(@desc) to a log file
#  eventually want to produce favorites to rifle thru with router magic.
#  for now we just humbly save to file.
def SaveNoteComment(desc):
    s = raw_input('Note for[%s]:' % desc)
    f = open('yoshi_notes.txt', 'a')
    f.write('Note for %s:\n' % desc)
    f.write(s + '\n')
    f.close()
    print('added to yoshi_notes.txt')

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
#-------------------------------------------
class YoshiBankProg:
    def __init__(self, mDev=None):
        self.mDev = mDev
        self.mChannel = 0
        self.mBank = 5 # current bank
        self.mProg = 1 # current program
        self.yoshiBankProgs = None # for read yoshi bank info, ver2

        #self.ChanSelection = [[5,1]]*16 # for per channel bank,prog settings
        # above doesn't work for me.
        self.ChanSelection = [] # for per channel bank,prog settings
        for i in range(16):
            self.ChanSelection.append([5,1])
        self.ChanSelection[1][0] = 10

    #-------------------------------------------
    # find prog number based on name of program, search thru all banks, programs
    def FindProg(self, prog_name):
        ret_val = None
        for bk,bv in self.yoshiBankProgs.items():
            for pk,pv in bv[1].items():
                if pv.find(prog_name) >= 0:
                    #print('found %d)%s - %d]%s' % (bk, bv[0], pk, pv))
                    ret_val = (bk,bv[0], pk,pv)
        return ret_val

    #---------------------------------------------------
    def readYoshiBankConfig(self):
        ''' this reads yoshi config file and reads in Bank and Prog
        information into a structure that looks like:
            [[bank_num, bank_name, bank_dict], []]
            Where bank_dict is a dict {prog_name : prog_num}
        '''
        print('scanning config')
        cfg_file = os.path.expandvars('$HOME/.config/yoshimi/yoshimi.banks')
        fp = open(cfg_file, 'r') # the .bank file is gzipped.
        hdr = fp.read(6)
        fp.close()
        if hdr.find('\x1f\x8b')>=0:
            fp = gzip.open(cfg_file, 'r') # the .bank file is gzipped.
                                          # that's an option in Yoshi.
        else:
            fp = open(cfg_file, 'r') # the .bank file not gzipped

        # TODO: will above crash if it's not gzipped?  find out!

        l = fp.readline()
        #print('line:' + l)
        ls = fp.readlines()
        #print('[%s]num lines:%d' % (cfg_file, len(ls)))
        fp.close()
        # this parsing is quick and dirty, should switch to xml lib, or better parsing..
        bank_root = ''
        bank_num_name = [] # make a list of lists to return of [bank_num, bank_name, Key_ProgInfo]
        bank_num_dict = {} # make a dict of bank info
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
                bank_num_dict[bank_num] = [bank_name, None] # reserve [1] for attaching prog info
                bank_num_name.append([bank_num, bank_name, None]) # reserve [2] for attaching prog info
                bank_num = -1
                bank_name = ''

        #print('bank_root:' + bank_root)
        for e in bank_num_name:
            #print('%d) %s' % (e[0], e[1]))
            bank_num = e[0]
            bank_name = e[1]
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
            bank_num_dict[bank_num][1] = bank_dict
        self.yoshiBankProgs = bank_num_dict
        print('yoshi bank info read')
        return self.yoshiBankProgs # return our list of Yoshi Bank information

    #---------------------------------------------------
    def sendBankProgSelect(self, ch, bank_num, prog_num):
        ' Send bank and prog_num, or just prog_num '
        if bank_num >= 0:
            if self.mDev != None:
                self.mDev.Write([0xb0 | ch,0,0]) # msb, leave 0 like yamaha output
                self.mDev.Write([0xb0 | ch,0x20,bank_num]) # lsb, for primary bank selection
            self.ChanSelection[self.mChannel][0] = bank_num
        # need to send prog change to activate ?  I think so..
        if self.mDev != None:
            self.mDev.Write([0xc0 | ch, prog_num-1])
        self.ChanSelection[self.mChannel][1] = prog_num

    #---------------------------------------------------
    def PrintChanSettings(self):
        ' print current channel prog, bank selection '
        chinfo = self.ChanSelection[self.mChannel]
        bank,prog = chinfo
        bank_name = ''
        prog_name = ''
        cfg = self.checkBanksRead()
        if len(cfg) == 0:
            print('Error, banks not read')
            return
        if not cfg.has_key(bank):
            print('bank key not found:%d'% (bank))
            return
        bank_name, _bank_dict = cfg[bank]
        prog_name = _bank_dict[prog]
        print('ch:%d %d.)%s - %d.)%s' % (self.mChannel+1, bank,bank_name, prog,prog_name))

    #---------------------------------------------------
    def GetBankProgNames(self):
        chinfo = self.ChanSelection[self.mChannel]
        bank_num,prog_num = chinfo
        cfg = self.checkBanksRead()
        bank_name = '?'
        prog_name = '?'
        if cfg.has_key(bank_num):
            bank_name, bank_dict = cfg[bank_num]
            if prog_num in bank_dict:
                prog_name = bank_dict[prog_num]
        return (bank_num, bank_name, prog_num, prog_name)

    #---------------------------------------------------
    def PrintBankSelection(self):
        ' print current bank, then complete selection menu '
        bn,bs,pn,ps = self.GetBankProgNames()
        print('ch:%d Current Bank: %d.)%s' % (self.mChannel+1, bn,bs))

        cfg = self.checkBanksRead()
        line = ''
        i = 0
        for k,v in cfg.items():
            bank_num = k
            bank_name,prog_dict = v
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

    #---------------------------------------------------
    def PrintProgSelection(self):
        ' print current bank prog, then complete selection menu '
        bn,bs,pn,ps = self.GetBankProgNames()
        print('ch:%d Current Bank: %d.)%s Program:%d) %s' % (
                self.mChannel+1, bn,bs, pn,ps))

        cfg = self.checkBanksRead()
        if cfg.has_key(self.mBank):
            bv = cfg[self.mBank]
            bank_name = bv[0]
            bank_dict = bv[1]
            prog_nums = sorted(bank_dict.keys()) # sorted Prog key numbers
            # Print out menu of Prog choices.  3 columns.  Highlight current selection.
            print('------ Bank %3d) %-20s Program Selection --------' % (self.mBank, bank_name))
            #num = len(prog_nums)
            ki = 0
            line = '' # TODO: match layout(32 lines per col) as gui would be nice.
            prog_desc = ''
            for prog_num in prog_nums:
                name = bank_dict[prog_num]
                if len(name) > 20:
                    name = name[0:19] + ':'
                entry = '%3d. %-20s ' % (prog_num, name)
                if self.mProg == prog_num:
                    entry = entry.replace(' ', '_') # highlight cur prog selection
                    entry = entry.replace('.', ':')
                    prog_desc = name # cache
                line += entry
                ki += 1
                if (ki % 3) == 0:
                    print(line)
                    line = ''
            if len(line) > 0: print(line)

    #---------------------------------------------------
    def PrintAllBankProgs(self):
        ' this is for generating a master listing, python src compatible '
        cfg = self.checkBanksRead()
        bank_nums = sorted(cfg.keys()) # sorted Bank key numbers
        for bank_num in bank_nums:
            bank_name, bank_dict = cfg[bank_num]
            prog_nums = sorted(bank_dict.keys()) # sorted Prog key numbers
            for prog_num in prog_nums:
                prog_name = bank_dict[prog_num]
                print('        (%d, "%s", %d, "%s"),' % (bank_num,bank_name, prog_num,prog_name))


    #---------------------------------------------------
    def checkBanksRead(self):
        if len(self.yoshiBankProgs) == 0:
            print('reading yoshi config info...')
            cfg = self.readYoshiBankConfig() # returns list [[bank_num, bank_name, spare],..]
        else:
            cfg = self.yoshiBankProgs
        return cfg

    #---------------------------------------------------
    def setBank(self, bank_num):
        self.mBank = bank_num
        self.mProg = 1 # todo: remember, scan for first or next..
        self.sendBankProgSelect(self.mChannel, self.mBank, self.mProg)

    #---------------------------------------------------
    def setProg(self, prog_num):
        self.mProg = prog_num # todo: remember, scan for first or next..
        self.sendBankProgSelect(self.mChannel, self.mBank, self.mProg)

    #---------------------------------------------------
    # Allow to pick bank and instrument choices, Yoshimi
    def bankBrowser(self):
        cfg = self.checkBanksRead()

        ch = self.mChannel
        print('Channel:%d' % (ch))
        print('For selections num=number, p=plus(next), l=less(previous),')
        print(' n=save note comment, q=quit')

        self.mBank = self.ChanSelection[ch][0]
        self.mProg = self.ChanSelection[ch][1]

        while 1:
            i = 0
            line = ''
            bank_nums = []
            #for e in cfg:
            for k,v in cfg.items():
                #bank_nums.append(e[0])
                bank_nums.append(k)

            bank_desc = ''
            # print the list of bank choices
            #for e in cfg:
            for k,v in cfg.items():
                bank_num = k
                bank_name,prog_dict = v
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

            #for e in cfg:
            #    if e[0] == self.mBank:
            #        bank_info = e
            #        break
            bank_info = cfg[bank_num][1]

            prog_num = self.mProg
            self.sendBankProgSelect(ch, bank_num, self.mProg)

            prog_desc = '?'
            while 1:
                keys = sorted(bank_info.keys()) # sort Prog key numbers
                # Print out menu of Prog choices.  3 columns.  Highlight current selection.
                print('------ Bank %3d) %-20s Program Selection --------' % (self.mBank, bank_desc))
                num = len(keys)
                ki = 0
                line = '' # TODO: match layout(32 lines per col) as gui would be nice.
                prog_desc = ''
                for k in keys:
                    name = bank_info[k]
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
                self.sendBankProgSelect(ch, -1, self.mProg)

#---------------------------------------
def main():
    y = YoshiBankProg()
    y.readYoshiBankConfig()
    #y.printChanSettings()
    y.bankBrowser()

if __name__ == '__main__':
    main()
