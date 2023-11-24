import os, sys
from .utils import create_dir_not_exist
from .utils import kill_all_pid_by_name
import time
import re
from subprocess import check_output


def save_kmsg_to(filepath, monitor_time=60):
    start = time.time()
    # p = subprocess.Popen(["sudo", "cat", "/proc/kmsg",">",f"{filepath}"], stdin = subprocess.PIPE, stdout = subprocess.PIPE, stderr = subprocess.PIPE, shell = False, preexec_fn = os.setpgrp )
    os.system("sudo dmesg -c &")
    kill_all_pid_by_name("dmesg")
    print("clear old log, start record new log")
    os.system(f"sudo dmesg -w | grep -i -e reward -e action > {filepath} &")
    time.sleep(monitor_time)
    print(f"record {monitor_time} finished")
    pid = int(check_output(["pidof","-s", 'dmesg']))
    os.system("kill %d"%pid)

def del_file(filepath):
    os.system(f"sudo rm {filepath}")
    
    
def find_reward(msg):
    findstr = re.search(r'reward:(.*?);', msg)
    if findstr != None:
        return float(findstr.group()[7:-1])
    return None    

def find_action(msg):
    findstr = re.search(r'action:(.*?);', msg)
    if findstr != None:
        return float(findstr.group()[7:-1])
    return None    

def read_kmsg_to_data(filepath):
    reward_list = []
    action_list = []
    with open(filepath, "r") as f:
        while True:
            line = f.readline()
            # print(line)
            if not line:
                break
            reward = find_reward(line)
            action = find_action(line)
            if reward != None:
                reward_list.append(reward)
            if action != None:
                action_list.append(action)
    return reward_list, action_list

def monitor_reward(rounds, monitor_time, kmsgdir_name="default"):
    try:
        create_dir_not_exist(f"./kmsgs/{kmsgdir_name}/")
        count = 0
        while True:
            if count>rounds:
                sys.exit(1)
            now = time.time()
            save_kmsg_to(f"./kmsgs/{kmsgdir_name}/kmsg_{now}", monitor_time=monitor_time)
            count+=1
    except KeyboardInterrupt as e:
        sys.exit(1)

if __name__ == "__main__":
    monitor_time = 60
    round = 10*60/monitor_time
    monitor_reward(round, monitor_time)
    
