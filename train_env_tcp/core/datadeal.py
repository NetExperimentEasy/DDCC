import re
import matplotlib.pyplot as plt
import numpy as np
from pathlib import Path
import statistics

""" 
file api
"""
def get_sort_filelist(filepath:str, startswith=None, endswith=None):
    # logpath='./log'; startswith = "iperf"； endswith = "exp"
    workdir = Path(filepath)
    result_files_list = []
    if startswith:
        if endswith:
            result_files_list = sorted([i for i in workdir.iterdir() if i.name.startswith(startswith) and i.name.endswith(endswith)])
        else:
            result_files_list = sorted([i for i in workdir.iterdir() if i.name.startswith(startswith)])
    else:
        result_files_list = sorted([i for i in workdir.iterdir()])
    return sorted(result_files_list, key=lambda x: x.stat().st_ctime, reverse=False)

""" 
data paser api
"""    
def get_link_info_from_iperflog_filename(filename:str):
    # filename : Path().name : iperf.1231244.22m22rtt0%.exp
    th = re.search(r'\.(\d+?)Mbit', filename).group().strip()[1:-4]
    rtt = re.search(r'Mbit(.*?)ms', filename).group().strip()[4:-2]
    loss = re.search(r'ms(.*?)%', filename).group().strip()[2:-1]
    return {"th":float(th), "rtt":float(rtt), "loss":float(loss)}
    

# paser iperf log file
def get_data_from_iperflog(filepath: Path, link_info=False):
    # filepath : Path()
    # return : result data[] ; info (if link_info is True)
    result = []        
    with open(filepath, "r") as f:
        lines = f.readlines()
        for line in lines:
            if line.startswith("[  3]") and line.endswith("sec\n"):
                type = None
                gettime = re.match(r'\[  3\] (.*?) sec', line).group().split('-')
                start, end = gettime[0][-4:].strip(), gettime[1][:4].strip()
                start, end = float(start), float(end)
                getbandwidth = re.search(r"Bytes  (.*?) Mbits", line)
                type = "M"
                if getbandwidth == None:
                    type = "K"
                    getbandwidth = re.search(r"Bytes  (.*?) Kbits", line)
                    if getbandwidth == None:
                        type = "B"
                        getbandwidth = re.search(r"Bytes  (.*?) bits", line)
                getbandwidth = getbandwidth.group()[7:-5].strip()
                bandwidth = float(getbandwidth)
                if type == "K":
                    bandwidth = bandwidth/1000
                if type == "B":
                    bandwidth = bandwidth/1000000
                result.append([start, end, bandwidth])
    if link_info:
        return result, get_link_info_from_iperflog_filename(filepath.name)
    return result


""" 
statistic api
"""
def avg(iperf_name):
    mptcp_data = get_data_from_iperflog(iperf_name)
    mptcp_bandwith = [i[2] for i in mptcp_data]
    if len(mptcp_bandwith)==0:
        return 0
    return statistics.mean(mptcp_bandwith)

def distance(datalist, aim_data):
    # 计算 距离比例的平方均值
    index_p95 = int(len(datalist)*0.1)
    aimlist = [aim_data] * len(datalist[index_p95:])
    dataarray = np.array(datalist[index_p95:])
    aimarray = np.array(aimlist)
    tmparray = (aimarray-dataarray)/aimarray
    return np.sum(tmparray**2)/(len(datalist[index_p95:]))
    
def percent_larger_than(datalist, value):
    count = 0
    for i in datalist:
        if i >= value:
            count+=1
    return count/len(datalist)

def partition(data_list, size):
    for i in range(0, len(data_list), size):
        yield data_list[i : i+size]

""" 
paint api
"""
def paint(data,filename=None):
    plt.rcParams['figure.figsize'] = (20.0, 6.0)
    fig, ax = plt.subplots()
    # ax.set_ylim(0,35)
    for i in data:
        ax.plot(i)
    if filename:
        plt.savefig(filename+'.png',bbox_inches='tight',dpi=fig.dpi,pad_inches=0.0)
        
def paint_point(data,filename=None):
    plt.rcParams['figure.figsize'] = (20.0, 6.0)
    fig, ax = plt.subplots()
    # ax.set_ylim(0,35)
    index_list = list(range(len(data)))
    ax.plot(index_list, data, 'r*','LineWidth',1)
    if filename:
        plt.savefig(filename+'.png',bbox_inches='tight',dpi=fig.dpi,pad_inches=0.0)