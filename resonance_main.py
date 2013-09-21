################################################################################
# The Pyretic Project                                                          #
# frenetic-lang.org/pyretic                                                    #
# author: Joshua Reich (jreich@cs.princeton.edu)                               #
################################################################################
# Licensed to the Pyretic Project by one or more contributors. See the         #
# NOTICES file distributed with this work for additional information           #
# regarding copyright and ownership. The Pyretic Project licenses this         #
# file to you under the following license.                                     #
#                                                                              #
# Redistribution and use in source and binary forms, with or without           #
# modification, are permitted provided the following conditions are met:       #
# - Redistributions of source code must retain the above copyright             #
#   notice, this list of conditions and the following disclaimer.              #
# - Redistributions in binary form must reproduce the above copyright          #
#   notice, this list of conditions and the following disclaimer in            #
#   the documentation or other materials provided with the distribution.       #
# - The names of the copyright holds and contributors may not be used to       #
#   endorse or promote products derived from this work without specific        #
#   prior written permission.                                                  #
#                                                                              #
# Unless required by applicable law or agreed to in writing, software          #
# distributed under the License is distributed on an "AS IS" BASIS, WITHOUT    #
# WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied. See the     #
# LICENSE file distributed with this work for specific language governing      #
# permissions and limitations under the License.                               #
################################################################################


################################################################################
# Resonance Project                                                            #
# Resonance implemented with Pyretic platform                                  #
# author: Hyojoon Kim (joonk@gatech.edu)                                       #
# author: Nick Feamster (feamster@cc.gatech.edu)                               #
# author: Arpit Gupta (glex.qsd@gmail.com)                                     #
################################################################################

from pyretic.lib.corelib import *
from pyretic.lib.std import *
from pyretic.modules.mac_learner import learn

from resonance_policy import *
from resonance_states import *
from resonance_handlers import EventListener
from resonance_globals import *

from multiprocessing import Process, Queue
from importlib import import_module
import time
import subprocess
import threading
import os
import sys
import re

from resonance_globals import *

DEBUG = True

""" Dynamic resonance policy """
def resonance(self, name_mod_map, composition_str, ip_to_modulename_map):

  # Make policy_map
  def make_policy_map():
    self.policy_map = {}

    if DEBUG is True:
      print "\n*** Policy composition for each src-dst pair: ***"

    for src in self.ip_to_modulename_map:
      for dst in self.ip_to_modulename_map:
        if src!='core' and dst!='core':
          src_dst_tuple = (src,dst)
          # If traffic is within one departement:
          if self.ip_to_modulename_map[src]==self.ip_to_modulename_map[dst]:
            self.policy_map[src_dst_tuple] = [self.name_po_map.get(self.ip_to_modulename_map[src])]
            if DEBUG is True:
              print str(src_dst_tuple) + ":\t" + str(self.ip_to_modulename_map[src])

          # Else,
          else:
            self.policy_map[src_dst_tuple] = [self.name_po_map.get(self.ip_to_modulename_map[src]), \
                                              self.name_po_map.get(self.ip_to_modulename_map['core']),\
                                              self.name_po_map.get(self.ip_to_modulename_map[dst])]

            if DEBUG is True:
              print str(src_dst_tuple) + ":\t" +  str(self.ip_to_modulename_map[src]) + " >> " + str(self.ip_to_modulename_map['core']) + " >> " + str(self.ip_to_modulename_map[dst])

  # Composing policy
  def compose_policy_departments_switchbased():
    final_policy = parallel([(fsm.get_match_switch() >> self.fsm_to_policyobject_map[fsm].policy()) \
                              for fsm in self.fsm_to_policyobject_map])

    return final_policy

  # Composing policy
  def compose_policy_departments():
    final_policy = drop
    for m in self.policy_map:
      if str(m[0])!='core' and str(m[1])!='core':
        p = if_(match(srcip=str(m[0]), dstip=str(m[1])), \
                sequential([i.policy() for i in self.policy_map[m]]), drop)
        final_policy = final_policy + p

    return final_policy

  # Composing policy
  def compose_policy():
    policy_str = self.composition_str
    print policy_str
    # Get composition string, replace with relevant ones.
    for name in self.name_po_map:
      idx = policy_str.find(name)
      if idx != -1:
        if self.name_po_map[name] in self.user_policy_object_list:
          p_index = self.user_policy_object_list.index(self.name_po_map[name])
          replace_str = 'self.user_policy_object_list[' + str(p_index) + '].policy()'
          policy_str = policy_str.replace(name, replace_str)
          #if name=='auth':
          #  print "trigger value from main: "+str(self.user_policy_object_list[p_index].fsm.trigger)
    return eval(policy_str)

  # Updating policy
  def update_policy(pkt=None):
    #print "comp str: "+self.composition_str

    if self.composition_str == '':
#      self.policy = compose_policy_departments()
      self.policy = compose_policy_departments_switchbased()
    else:
      self.policy = compose_policy()
    # Record
    ts = time.time()
    #subprocess.call("echo %.7f >> /home/mininet/hyojoon/benchmark/pyresonance-benchmark/event_test/output/process_time/of.txt"%(ts), shell=True)

#    print self.policy

  self.update_policy = update_policy

  # Listen for state transitions.
  def transition_signal_catcher(queue):
    while 1:
      try:
        line = queue.get(timeout=.1)
#        line = queue.get_nowait() # or q.get(timeout=.1)
      except:
        continue
      else: # Got line.
        #print "AG: calling the update policy"
        self.update_policy()

  def update_d2s():
   #print "updating the 'reso_auto.config' file"
    fi='./pyretic/pyresonance/reso_auto.config'
    fo='./pyretic/pyresonance/reso_auto.config_new'
    fin = open(fi,'r')
    fout = open(fo,'w+')
    flag=0
    for line in fin.readlines():
      if line.startswith('D2S'):
        flag=1
        fout.write(line)
      elif flag==1:
        if line.startswith('}'):
          flag=0
          fout.write(line)
        else:
          if len(line.split(':'))==2:
            dep=line.split(':')[0].strip(' ')
            newline=dep+':'
            for sw in d2S_map[dep]:
              newline+=sw+','
            fout.write(newline+'\n')
      else:
        fout.write(line)
    os.system('mv '+fo+' fi')
    #os.system('rm '+fo)

  def synch_d2s():
    #print 'd2s thread started'
    while True:
      update_d2s()
      time.sleep(60) # synch the config file every 1 minute




  def update_comp(po,pname,strn):
    temp = strn.split(' ')
    #print temp
    ind = temp.index(pname)
    pre=''
    post=''
    if ind-1>0:
      pre=temp[ind-1]

    if ind+1<len(temp):
      post=temp[ind+1]


    if pre =='+' or post=='+':
      #print 'parallel'
      po.fsm.comp.value = 1
    else:
      #print 'sequential'
      po.fsm.comp.value = 0

  def initialize():
    self.composition_str = composition_str
    self.ip_to_modulename_map = ip_to_modulename_map
    self.name_mod_map = name_mod_map
    self.name_po_map = {}
    self.user_fsm_list = []
    self.fsm_to_policyobject_map = {}
    self.user_policy_object_list = []

    # Create queue for receiving state transition notification
    queue = Queue()

    # Get user-defined FSMs, make them, make eventListeners
    for idx,name in enumerate(self.name_mod_map):
      user_fsm, user_policy_object = self.name_mod_map[name].setupStateMachineAndPolicy(name)
      self.user_fsm_list.append(user_fsm)
      self.fsm_to_policyobject_map[user_fsm] = user_policy_object
      self.user_policy_object_list.append(user_policy_object)
      self.name_po_map[name] = user_policy_object

      if idx==0:
        self.eventListener = EventListener(user_fsm)
      else:
        self.eventListener.add_fsm(user_fsm)
    ## Adding the feature to determine the comp variable to determine action for the module while turning it off
    for pname in self.name_po_map.keys():
      po = self.name_po_map[pname]
      #print pname
      #print po.fsm.trigger.value
      #update_comp(po,pname, self.composition_str)

    # Make main event listener. For querying states.
#    main_fsm = ResonanceStateMachine()
#    if self.eventListener:
#      self.eventListener.add_fsm(main_fsm)
#    else:
#      self.eventListener = EventListener(main_fsm)

    # Start eventListener with queue
    self.eventListener.start(queue)

    # Start signal catcher thread
    t = threading.Thread(target=transition_signal_catcher, args=(queue,))
    t.daemon = True
    t.start()

    # Make policy map for 'auto' mode.
    # This method will return immediately if the mode is 'manual'.
#    make_policy_map()

    # Set the policy
    self.update_policy()

    # Start the thread to update the D2S mapping information

    t_d2s = threading.Thread(target=synch_d2s)
    t_d2s.daemon = True
    t_d2s.start()


  initialize()


def parse_config_file(content, mode, repeat):
  name_mod_map = {}           # {shortname : module_object} dictionary
  composition_str = ''        # Policy composition in string format (in manual mode)
  ip_to_modulename_map = {}   # {ip_address : shortname} dictionary

  # Get module list and import.
  match = re.search('MODULES = \{(.*)\}\n+COMPOSITION = \{',content, flags=re.DOTALL)
  if match:
    modules_list = match.group(1).split(',')
    ### TEST
    if repeat != 0:
      modules_list = [modules_list[0]]*int(repeat)
    ### TEST

    print '\n*** Specified Modules are: ***'
    for m in modules_list:
      corrected_m = m.strip('\n').strip()
      if corrected_m != '' and corrected_m.startswith('#') is False:
        try:
          mod = import_module(corrected_m)
        except Exception as ex:
          print 'Import Exception: ', ex
          sys.exit(1)

        split_list = corrected_m.split('.')
        name_mod_map[split_list[-1]] = mod
        print corrected_m + ' (' + split_list[-1] + ')'

  if mode.__eq__('auto'):
    # Get Departments
    print "Auto Mode"
    d2s={}
    match = re.search('D2S = \{(.*)\}\n+DEPARTMENTS = \{', content, flags=re.DOTALL)
    #print match
    if match:
      ilist = match.group(1).split('\n')
      for item in ilist:
        if item!='':
          item = item.strip(' ')
          dep = item.split(':')[0]

          d2S_map[dep]=[]
          switchlist = item.split(':')[1].split(',')
          for sw in switchlist:
            if sw !='':
              d2S_map[dep].append(sw.strip(' '))

          #print dep
      #print d2S_map


    match = re.search('DEPARTMENTS = \{(.*)\}',content, flags=re.DOTALL)
    if match:
      policy_list = match.group(1).split('\n')
      for policy in policy_list:
        policy_str = policy.strip('\n').strip()
        if policy_str !='' and policy_str.startswith('#') is False:
          line = policy_str.split(':')
          ip_to_modulename_map[str(line[0]).strip(' ')] = str(line[1]).strip(' ')

#    return name_mod_map, '', ip_to_modulename_map

  elif mode.__eq__('manual'):
    ### TEST
    if repeat != 0:
      composition_str = 'passthrough >> ' *int(repeat)
      composition_str = composition_str.rstrip(' >> ')
      print '\n\n*** The Policy Composition is: ***\n' + composition_str + '\n'
    ### TEST

    else:
      # Get Composition.
      #match = re.search('D2S = \{.*}\}', content, flags=re.DOTALL)
      #if match:
      #  print match.group(1)

      match = re.search('COMPOSITION = \{(.*)\}',content, flags=re.DOTALL)
      if match:
        compose_list = match.group(1).split('\n')
        for compose in compose_list:
          composition_str = compose.strip('\n').strip()
          if composition_str != '' and composition_str.startswith('#') is False:
            print '\n\n*** The Policy Composition is: ***\n' + composition_str + '\n'
            break


  # Return
  return name_mod_map, composition_str, ip_to_modulename_map


""" Main Method """
def main(config, mode, modrepeat=None):
  # Open configuration file.
  print config
  try:
    fd = open(config, 'r')
  except IOError as ex:
    print 'IO Exception: ', ex
    sys.exit(1)

  # Get mode, check validity.
  if mode!='auto' and mode!='manual':
    print 'Wrong mode value. Exit'
    sys.exit(1)

  # check test mode.
  repeat = 0
  if modrepeat is not None:
    if modrepeat != 0:
      repeat = modrepeat

  # Read config file
  content = fd.read()
  fd.close()

  # Parse configuration file.
  name_mod_map, composition_str, ip_to_modulename_map  = parse_config_file(content, mode, repeat)

  if len(name_mod_map) == 0:
    print 'Config file seems incorrect. Exiting.'
    sys.exit(1)

  # Run Resonance main.
  return dynamic(resonance)(name_mod_map, composition_str, ip_to_modulename_map) >> dynamic(learn)()
#  return dynamic(resonance)(name_mod_map, composition_str)
