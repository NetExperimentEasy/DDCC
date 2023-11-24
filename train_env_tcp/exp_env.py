from core.expenv import QcongMininet
from mininet.log import setLogLevel
from core.reward_monitor import monitor_reward
from core.utils import save_model, set_cc
import multiprocessing
setLogLevel('info')

expname = "test-xquic_satcc_1"

num_links=1 # 并发训练的流数 64
exp_round=1 # 试验轮次 120
round_time=180 # 条流的长度
monitor_time = 182 # kmsg reward监控时间长度
monitor_round = exp_round*round_time/monitor_time # 监控轮次
ifloss = False # 训练环境是否开启丢包场景
tcpdump_ips = {"c1":["10.0.0.3"]}
# tcpdump_ips = {}
tcpdump_ports = [8443, 5001]

# 该机器tcpdump出问题了
set_cc("satcc") # 必须在启动mininet前设置好cc

Exp = QcongMininet(num_links) # 并行数量

# set_cc("satcc") # 必须在启动mininet前设置好cc

# Exp.run_train("fix", exp_round, ifloss, expname, False, tcpdump_ips, tcpdump_ports)

# set_cc("bbr")

try:
    # p1 = multiprocessing.Process(target=monitor_reward, args=(monitor_round, monitor_time, expname))
    # p2 = multiprocessing.Process(target=Exp.run_train, args=("fix", exp_round, ifloss, round_time, expname, False, tcpdump_ips, tcpdump_ports))
    p2 = multiprocessing.Process(target=Exp.run_train, args=("fix", exp_round, ifloss, round_time, expname, False))
    # p1.start() 
    p2.start()
    # p1.join()
    p2.join()
except KeyboardInterrupt as e:
    set_cc("bbr")
    print("waiting: close others link and mininet env")

set_cc("bbr")
Exp.stop()

# Exp.cli()
