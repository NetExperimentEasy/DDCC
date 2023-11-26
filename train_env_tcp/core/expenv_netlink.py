
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
from redis.client import Redis


@dataclass
class PcapAt:
    host: str
    aim_hosts: list
    aim_ports: list


class TCPNLMininet:
    def __init__(self,
                 host_num,
                 Topo=multiTopo,
                 redis_ip = "127.0.0.1",
                 redis_port = 6379,
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
        
        # init Redis
        info("\n*** Init Redis \n")
        self.r = Redis(host=redis_ip, port=redis_port)
        self.rp = Redis(host=redis_ip, port=redis_port)
        self.pub = self.r.pubsub()
        self.pub.subscribe('tcpnl_control')

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
        rate = f'{random.randrange(5,200)}Mbit'
        buffer = f'{random.randrange(1400,2000)}b'
        delay = f'{random.randrange(5,300)}ms' if e > 8 else \
            f'{random.randrange(5,100)}ms'
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
                    rate='20Mbit',
                    buffer='1600b',
                    delay='40ms',
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

    def run_client(self, host, queue, stream_time, train_info=None, exp=False, logdir_name="default", cc=None):
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
               interval=1,
               cc=cc)
        else:
            cmd_at(host, iperf_command, ifprint=True,
                type="client",
                logname=f"./iperflog/{logdir_name}/iperf.log{name}",
                aimip=aim_server.IP(),
                time=stream_time, # 流长度
                interval=1,
                cc=cc)
        queue.put(host)
        self.missions_count[host.name] += 1
        end = time.time()
        running_time = end-start
        print(f"::{host.name} {self.missions_count[host.name]} done;time:{running_time:.2f} sec; end at {time.ctime()}")
        self.rp.publish("mininet", f"flow_id;state:done;time:"
            + f"{running_time:.2f} sec")

    def run_train(self, mode, ifloss=True, stream_time=60, logdir_name="default", ifexp=False, tcpdump_ips=None, tcpdump_ports=None, cc="satcc"):
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
        
        if tcpdump_ips != None:
            for hostname in tcpdump_ips:
                cmd_at(self.network.get(hostname), tcpdump_command, ifbackend=True, ifprint=True, aim_ips=tcpdump_ips[hostname], ports=tcpdump_ports)

        msg_stream = self.pub.listen()

        host_list = [s for s in self.network.hosts[1:] if s.name.startswith('c')]
        host1 =  host_list[0]
        sw1 = self.network.get("sw1")

        exp_count = 0
        exp = False

        try:
            for msg in msg_stream:
                if msg["type"] == "message":
                    command = str(msg["data"], encoding="utf-8")
                    if command == "tcpnl_control":
                        # 订阅消息 跳过
                        continue
                    if command.endswith("reset"): # 收到重启命令，重启流
                        if ifexp:
                            if exp_count%5 == 0: # 每5次 测试一次
                                exp = True
                            else:
                                exp = False
                            exp_count += 1
                        kill_all_pid_by_name("iperf")
                        tinfo = ""
                        if mode == "random" and not exp:
                            tinfo = self.set_random_env(sw1, ifloss=ifloss)      # 随机重置环境
                        if mode == "fix" or exp:
                            tinfo = self.set_fix_env(sw1)         # 固定环境测试
                        cmd_at(item, iperf_command, ifbackend=True, type='server')
                        result = self.pool.submit(self.run_client, host1,  self.missions_que, stream_time=stream_time, train_info=tinfo, exp=exp, logdir_name=logdir_name, cc=cc)   # 开始流
                        # print(result.exception())
                        print(f"::start flow at : host {host1.name}, eposide {self.missions_count[host1.name]}")

        except KeyboardInterrupt:
            kill_all_pid_by_name("iperf")
            if tcpdump_ips != None:
                kill_all_pid_by_name("tcpdump")
            self.pool.shutdown()
            self.stop()
            

        if tcpdump_ips != None:
            kill_all_pid_by_name("tcpdump")   
        self.pool.shutdown()
        self.stop()    
