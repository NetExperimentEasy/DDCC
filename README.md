# DDCC——A General Data-Driven Congestion Control Framework
---

## Introduction
  DDCC framework provides interfaces for reinforcement learning algorithms and a corresponding OpenAI Gym standard reinforcement learning environment, allowing integration of mainstream reinforcement learning models with high flexibility. The framework decouples the learning model from congestion control, enabling lightweight deployment on end devices. This decoupled design lays the foundation for end-network collaborative congestion control and supports various network protocols. The framework is highly modular, equipped with out-of-the-box network simulation training environments and visualization components. 
![1](https://github.com/NetExperimentEasy/DDCC/assets/48404708/8be6cbdd-7f59-47db-8ae5-0c1f450dfc46)

## Directory Introduction

- The deploy directory is the deploy module
- The gym_rlcc directory is the standard gym environment implemented
- The train_code directory is the training module
- The train_env_tcp directory is Network Simulation Component
- The satcc_framework directory contains the executor and forwarder.
---

## Environment Configuration

All use python3

### deploy:

```bash
apt install redis-server
pip3 install numpy redis
```

### gym_rlcc:

```bash
cd gym_rlcc
pip3 install -e .
```

### executor and forwarder:

```bash
apt install redis-server
# install hiredis
wget https://github.com/redis/hiredis/archive/refs/tags/v1.0.2.tar.gz
tar -xf v1.0.2.tar.gz
cd hiredis-1.0.2/
make
make install

cd satcc_framework
make all
```

### train_code:

```bash
pip3 install numpy redis
# Install gym_rlcc
```

### train_env_tcp

```bash
apt install redis-server
# Install mininet
https://zhuanlan.zhihu.com/p/576832894

pip3 install streamlit redis
```

# QuickStart Guide
---
## How to train DDCCQ

1. Mounting kernel modules
```bash
cd satcc_framework
sudo bash load.sh
```

1. Start training environment

```bash
cd train_env_tcp
sudo python3 train_env.py
```

3. Train

```bash
cd train_code
python3 train_rlcc.py
```

## How to deploy DDCC

1. Mounting kernel modules

```bash
cd satcc_framework
sudo bash load.sh
```

2. Deploy

```bash
cd deploy
python3 deploy.py
```

## How to visualize in real-time

```bash
cd train_env_tcp/webui
streamlit run app.py
```

---
