
import time
from datetime import datetime
from .topo import multiTopo
from mininet.net import Mininet
from mininet.node import Node
from mininet.cli import CLI
import random
from .utils import cmd_at, traffic_shaping, iperf_command,\
    tcpdump_command, kill_pid_by_name, create_dir_not_exist, kill_all_pid_by_name
from mininet.util import info
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from queue import Queue
import os


@dataclass
class PcapAt:
    host: str
    aim_hosts: list
    aim_ports: list


class QcongMininet:
    def __init__(self,
                 host_num,
                 Topo=multiTopo,
                 ) -> None:
        """
        host_num : num of host
        Topo : Train Topo
        """
        
        # init Topo
        info("\n*** Init Mininet Topo \n")
        topo = Topo(host_num)
        self.network = Mininet(topo, waitConnected=True)
        self.network.start()

        info("\n*** Hosts addresses:\n")
        for host in self.network.hosts[1:]:
            info(host.name, host.IP(), '\n')

        for item in self.network.switches:
            info(f"*** Init bottleneck property: {item.name}\n")
            self.set_fix_env(item, ifpublish=False)

        self.pool = ThreadPoolExecutor(max_workers=len(self.network.hosts))
        
        self.missions_que = Queue() # 任务队列 存储host，意味要在那个host上开始任务
        self.missions_count = {}
        for host in self.network.hosts[1:]:
            self.missions_count[host.name] = 0  # 记录该host执行任务的次数

    def set_random_env(self, switch, ifloss=True, ifpublish=True):
        """
        set random env to link
        """
        e = random.randrange(0, 10)
        # rate = f'{random.randrange(5,60)}Mbit'
        rate = f'{random.randrange(25,35)}Mbit'
        buffer = f'{random.randrange(1400,2000)}b'
        # delay = f'{random.randrange(5,200)}ms' if e > 7 else \
        #     f'{random.randrange(5,70)}ms'
        delay = f'{random.randrange(5,200)}ms' if e > 8 else \
            f'{random.randrange(5,70)}ms'
        if ifloss:
            loss = f'{random.randrange(0,100)/10}%' if e > 7 else '0%'
        else:
            loss = '0%'
        
        cmd_at(switch, traffic_shaping, ifbackend=False,
               mode='both',
               interface=switch.intfs[2].name,
               add=False,
               rate=rate,
               buffer=buffer,
               delay=delay,
               loss=loss)
        if ifpublish:
            print(
                'mininet reset path ', f"bandwidth:{rate};"
                + f"rtt:{delay};loss:{loss}")
        return f"{rate}{delay}{loss}"

    def set_fix_env(self, switch, ifpublish=True,
                    rate='100Mbit',
                    buffer='1600b',
                    delay='30ms',
                    loss='0%'
                    ):
        cmd_at(switch, traffic_shaping, ifbackend=False,
               mode='both',
               interface=switch.intfs[2].name,
               add=False,
               rate=rate,
               buffer=buffer,
               delay=delay,
               loss=loss)
        if ifpublish:
            print(
                'mininet set path ', f"bandwidth:{rate};"
                + f"rtt:{delay};loss:{loss}")
        return f"{rate}{delay}{loss}"
        
    def cli(self):
        try:
            CLI(self.network)
        except:
            self.stop()

    def stop(self):
        try:
            self.network.stop()
        except AttributeError as e:
            print(e)
            pass

    def run_client(self, host, queue, stream_time, train_info=None, exp=False, logdir_name="default"):
        create_dir_not_exist(f"./iperflog/{logdir_name}/")
        start = time.time()
        id = int(host.name[1:])
        aim_server = self.network.get(f'ser{id}')
        now = datetime.now()
        name = str(now.day)+str(now.hour)+str(now.minute)+str(now.second)
        if train_info != None:
            name+=f".{train_info}"
        # print(f"{host} ----> ")
        if exp == True: # fix env exp
            cmd_at(host, iperf_command, ifprint=True,
               type="client",
               logname=f"./iperflog/{logdir_name}/iperf.log{name}.exp",
               aimip=aim_server.IP(),
               time=stream_time, # 流长度
               interval=1)
        else:
            cmd_at(host, iperf_command, ifprint=True,
                type="client",
                logname=f"./iperflog/{logdir_name}/iperf.log{name}",
                aimip=aim_server.IP(),
                time=stream_time, # 流长度
                interval=1)
        queue.put(host)
        self.missions_count[host.name] += 1
        end = time.time()
        running_time = end-start
        print(f"::{host.name} {self.missions_count[host.name]} done;time:{running_time:.2f} sec; end at {time.ctime()}")

    def run_train(self, mode, eposide=1, ifloss=True, stream_time=60, logdir_name="default", ifexp=False, tcpdump_ips=None, tcpdump_ports=None):
        """
        mode : random : random env ,
                fix   :    fix env
        eposide : max num of eposides on each host
        """
        info("\n ---Qcong experiment start---\n")

        info("Start iperf server\n")
        for item in [s for s in self.network.hosts if
                     s.name.startswith('ser')]:
            cmd_at(item, iperf_command, ifbackend=True,
                   type='server')
        info("Start ok\n")
        
        for host in [s for s in self.network.hosts[1:] if
                     s.name.startswith('c')]:
            self.missions_que.put(host)
        
        if tcpdump_ips != None:
            for hostname in tcpdump_ips:
                cmd_at(self.network.get(hostname), tcpdump_command, ifbackend=True, ifprint=True, aim_ips=tcpdump_ips[hostname], ports=tcpdump_ports)
        
        exp = 0
        try:
            while True:
                time.sleep(0.01) # 一轮的时间内开的条数>100条会不正常
                host = self.missions_que.get(True)
                
                if ifexp and self.missions_count[host.name] == exp:
                    switch = self.network.get(f"sw{host.name[1:]}")
                    tinfo = self.set_fix_env(switch)         # 固定环境测试
                    self.pool.submit(self.run_client, host, self.missions_que, stream_time=stream_time, train_info=tinfo, exp=ifexp, logdir_name=logdir_name)   # 开始流
                    exp+=10 # exp every 10 round
                    continue

                if self.missions_count[host.name] < eposide:
                    switch = self.network.get(f"sw{host.name[1:]}")
                    tinfo = ""
                    if mode == "random":
                        tinfo = self.set_random_env(switch, ifloss=ifloss)      # 随机重置环境
                    if mode == "fix":
                        tinfo = self.set_fix_env(switch)         # 固定环境测试
                    
                    result = self.pool.submit(self.run_client, host,  self.missions_que, stream_time=stream_time, train_info=tinfo, exp=ifexp, logdir_name=logdir_name)   # 开始流
                    # print(result.exception())
                    print(f"::start flow at : host {host.name}, eposide {self.missions_count[host.name]}")
                else:
                    self.missions_count.pop(host.name)
                
                if len(self.missions_count) == 0: # 代表任务全部结束
                    break
        except KeyboardInterrupt:
            if tcpdump_ips != None:
                kill_all_pid_by_name("tcpdump")
            self.pool.shutdown()
            self.stop()
            
        if tcpdump_ips != None:
            kill_all_pid_by_name("tcpdump")   
        self.pool.shutdown()
        self.stop()    
