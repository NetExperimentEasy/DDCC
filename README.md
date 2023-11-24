# 环境配置

均使用 python3

deploy:

```
apt install redis-server
pip3 install numpy, redis
```

gym_rlcc:

```
cd gym_rlcc
pip3 install -e .
```

satcc_framework:

```
apt install redis-server
# install hiredis
wget https://github.com/redis/hiredis/archive/refs/tags/v1.0.2.tar.gz
tar -xf v1.0.2.tar.gz
cd hiredis-1.0.2/
make
make install
```

train_code:

```
pip3 install numpy, redis
# 安装好gym_rlcc
```

train_env_tcp

```
apt install redis-server
# 安装mininet
https://zhuanlan.zhihu.com/p/576832894

pip3 install streamlit, redis
```

# 如何训练 satcc

1. 挂载 satcc_framework
   cd satcc_framework
   sudo bash load.sh

2. 启动训练环境
   cd train_env_tcp
   sudo python3 train_env_tcpnl.py

3. 训练
   cd train_code
   python3 train_rlcc.py

# 如何部署 satcc

1. 挂载 satcc_framework
   cd satcc_framework
   sudo bash load.sh

2. 部署
   cd deploy
   python3 deploy.py

# 如何实时可视化

cd train_env_tcp/webui
streamlit run app.py
