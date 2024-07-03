# DDCC——A General Data-Driven Congestion Control Framework
---

## Introduction
  DDCC framework provides interfaces for reinforcement learning algorithms and a corresponding OpenAI Gym standard reinforcement learning environment, allowing integration of mainstream reinforcement learning models with high flexibility. The framework decouples the learning model from congestion control, enabling lightweight deployment on end devices. This decoupled design lays the foundation for end-network collaborative congestion control and supports various network protocols. The framework is highly modular, equipped with out-of-the-box network simulation training environments and visualization components. 
![1](https://github.com/NetExperimentEasy/DDCC/assets/48404708/8be6cbdd-7f59-47db-8ae5-0c1f450dfc46)

- The executor is responsible for collecting end-to-end transmission state information from the data flow and executing congestion control actions issued by the learning model. 
- The forwarder is a user-space program designed for transport protocols like TCP,   and it is implemented in the kernel. It serves as the bridge between the functional modules and the executor,  handling the transmission of state  and control action messages.
- Visualization module  is a real-time monitoring application implemented using Streamlit，which is a  Python framework that can quickly create interactive data applications. The visualization module subscribes to stream status messages from the message middleware and dynamically presents the curves of throughput, delivery rate, RTT, and packet loss rate in the form of a web application to achieve real-time monitoring of the stream status.
- Training module is implemented based on an open source reinforcement learning framework that conforms to the OpenAI Gym standard interface, so any reinforcement learning framework and model compatible with the OpenAI Gym environment can be used flexibly, such as rllib, tianshou, sample-factory and other frameworks, as well as Q-learning, PPO, and DQN models).
- Deployment module loads the trained model and then synchronously updates the model parameters. The behavior of this component is similar to the Gym instance, except that the Gym instance is used for model training, while the deployment component uses the trained model.
- Network Simulation module implements a dynamic virtual network environment based on Mininet, which can independently control each pair of end-to-end transmission parameters, such as bandwidth, delay, packet loss rate, and queue size.


These functional modules comprise multiple components, including the OpenAI Gym interface, training components, network simulation components, deployment components, and visualization components. These modules receive transmission state messages via message middleware and transmit control action messages to the forwarder or executor. The functional modules  carry the majority of the computational load, can be deployed on network-side hosts with sufficient computing power, and  execute complex reinforcement learning models. They form the foundation for ensuring the performance of congestion control on  terminal devices.

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
