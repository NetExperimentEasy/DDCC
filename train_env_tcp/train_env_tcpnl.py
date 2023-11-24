from core.expenv_netlink import TCPNLMininet
from mininet.log import setLogLevel
from core.reward_monitor import monitor_reward
from core.utils import save_model, set_cc
import multiprocessing
setLogLevel('info')

expname = "q-tcpnetlink"

num_links = 1
exp_round = 100 # 要记录的次数；
round_time=120 # 每条流的长度 （iperf长度）
monitor_time = 120 # kmsg reward监控时间长度
monitor_round = exp_round*round_time/monitor_time # 监控轮次
ifloss = False # 训练环境是否开启丢包场景
ifexp=True
tcpdump_ips=None
tcpdump_ports=None

Exp = TCPNLMininet(num_links) # 并行数量

try:
    # p1 = multiprocessing.Process(target=monitor_reward, args=(monitor_round, monitor_time, expname))
    p2 = multiprocessing.Process(target=Exp.run_train, args=("random", ifloss, round_time, expname, ifexp, tcpdump_ips, tcpdump_ports, "satcc"))
    # p1.start() 
    p2.start()
    # p1.join()
    p2.join()
except KeyboardInterrupt as e:
    set_cc("bbr")
    print("waiting: close others link and mininet env")