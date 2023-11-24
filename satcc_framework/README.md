# satcc_framework

satcc_framework 是一个在用户态进行 TCP 拥塞控制算法开发的接口实现，基于 netlink 技术。

satcc_framework 实现了将内核统计的状态采样（如发送速率，时延）发送到 redis 通道（rlccstate\*{flag}:flag 为模块自动分配的流 id），通过 redis 通道(rlccaction\_{flag})将想要设置的拥塞参数:cwnd，pacing_rate 传送给内核模块，内核模块进行自动配置的功能。

## 项目构成：

- tcp_satcc.c : 内核模块
- tcp_satcc_user.c : 用户态转发程序，内核与 redis 通信中转
- load.sh : 启动脚本
- rmmod.sh : 卸载模块脚本

## 使用方法：

'''
make all : 编译所有
make module : 编译内核模块
make user : 编译转发程序
make clean : 清理编译结果
'''

## 编译依赖：

- libhiredis ： redis c 语言客户端
- pthread ： 多线程库

## 运行依赖：

- redis ： apt install redis-server
