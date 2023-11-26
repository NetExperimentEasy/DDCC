import gym
import numpy as np
from redis.client import Redis
from gym import spaces
from typing import Optional, Union
# from gym.utils import seeding

class RlccEnvQT(gym.Env):
    """
    ### Description

    This environment is for reinforcement learning based congestion control algorithm research based TCP netlink
    This environment relays on mininet and redis, you need install them first.
    For installing mininet, if you are in china, i recommand you use this repo : https://gitee.com/derekwin/mininet.git

    ### Action Space
    
    # plan 1 : *rate mode
    The action is a `ndarray` with shape `(1,)` representing the pacing rate changing .

    | Num |      Action     | Min  | Max |
    |-----|-----------------|------|-----|
    | 0   |    cwnd_rate    | 0.5  | 3.0 |

    # plan 2 : owl mode
    The action is a `ndarray` with shape `(1,)` representing the cwnd changing .
    
    spaces.Discrete(7)
    | Num |      Action     |            value           |
    |-----|-----------------|--------------|-------------|
    | 0   |    cwnd_value   | [-10, -3, -1, 0, 1, 3, 10] |

    # plan 3 : satcc mode
    The action is a `ndarray` with shape `(1,)` representing the choosen action .
    
    spaces.Discrete(3)
    | Num |      Action     |    value   |
    |-----|-----------------|------|-----|
    | 0   |    cwnd_value   | [-1, 0, 1] |
    -1 : down action
    0  : stay action
    1  : up action


    ### Observation Space

    The observation is a `ndarray` with shape `(7,)` representing the x-y coordinates of the pendulum's free
    end and its angular velocity.

    | Num | Observation      | Min  |           Max            |
    |-----|------------------|------|--------------------------|
    | 0   | delivered_rate   | 0.0  | np.finfo(np.float64).max | need /1460
    | 1   |sending_throughput| 0.0  | np.finfo(np.float32).max |  /1460
    | 2   | min_rtt_us       | 0.0  | np.finfo(np.float32).max |  /512
    | 3   | rtt_us           | 0.0  | np.finfo(np.float32).max |  /512
    | 4   | losses           | 0.0  | np.finfo(np.float32).max |  /512
    | 5   | prior_in_flight  | 0.0  | np.finfo(np.float32).max |  /512
    | 6   | cwnd             | 0.0  | np.finfo(np.float32).max |  /512

    ### Rewards

    The default reward function is throughput - (rtt - min_rtt)
    You can define your reward_function and set it by config['reward_function']  

    ### Arguments
    config : dict
        config["reward_function"] : selfdefined reward function : 
            input : state : obs
            return : reward value

    """
    # metadata = {"render_modes": ["human", "rgb_array"], "render_fps": 4}

    def __init__(self, config: dict, render_mode: Optional[str] = None):

        self.flow_id = None
        self.last_state = None      # fill state while flow is over
        self.state = None
        self.cwnd = None
        self.minrtt = None
        self.up_change_EMA = 5 # 0.1
        self.up_stay_EMA = 5
        self.down_change_EMA = 5
        self.down_stay_EMA = 5
        self.aveV = 0
        if config.__contains__("reward_function"):
            self.reward_function = config["reward_function"]
        else:
            self.reward_function = self._reward

        r = Redis(host='0.0.0.0', port=6379)
        self.rp = Redis(host='0.0.0.0', port=6379)
        pub = r.pubsub()
        pub.psubscribe("rlccstate_*", "mininet")
        self.msg_stream = pub.listen()

        high = np.array(
            [
                np.finfo(np.float64).max,  # delivered_rate
                np.finfo(np.float32).max,  # sending_throughput
                np.finfo(np.float32).max,  # min rtt
                np.finfo(np.float32).max,  # rtt
                np.finfo(np.float32).max,  # losses
                np.finfo(np.float32).max,  # prior_in_flight
                np.finfo(np.float32).max,  # cwnd
            ],
            dtype=np.float32,
        )

        self.scale = np.array([1, 1, 1, 1, 1, 1, 1], dtype=np.float32)
        
        if "plan" in config.keys():
            self.plan = config["plan"]
        else:
            self.plan = 2

        if "maxsteps" in config.keys():
            self.maxsteps = config["maxsteps"]
        else:
            # 300Mb / (10Mb/s) * 33 [1000ms/(15ms*2)] = 990 
            self.maxsteps = 1800
        self.step_count = 0

        # 对应rlcc.c中 pacing rate，用倍率调整
        if self.plan == 1:
            self.action_max = 3.0
            self.action_min = 0.5
            self.action_space = spaces.Box(
                low=self.action_min, high=self.action_max, shape=(1,), dtype=np.float32
            )
        
        # owl方案，agent从给定的多个动作中选择一个
        if self.plan == 2:
            self.action_max = 10
            self.action_min = -10
            self.action_space = spaces.Discrete(7)
            self._action_to_direction = {
                0: -10,
                1: -3,
                2: -1,
                3: 0,
                4: 1,
                5: 3,
                6: 10,
            }
        # satcc方案，agent仅选择是否增加还是减少还是不动，尺度交给 自动变速器
        if self.plan == 3:
            self.cwnd_init = None
            self.cwnd_alpha = None # 反比例动作分子
            self.action_max = 1
            self.action_min = -1
            self.action_space = spaces.Discrete(3)
            self._action_to_direction = {
                0: 1,
                1: 0,
                2: -1,
            }

        self.observation_space = spaces.Box(0, high, dtype=np.float32)

        for msg in self.msg_stream:
            print(str(msg["channel"], encoding="utf-8"), '订阅成功')
            break

    def _reward(self, state):  
        
        throughput = state[1]
        delivered_rate = state[0]
        delivered_rate_scale = state[0]/256 if state[0]/256 > 1 else 1
        delay = state[3] - state[2]
        delay_scale = delay/1024

        # # log line reward
        # if delay_scale < 1: # log不能对0计算, 防止过量惩罚
        #     reward = np.log(delivered_rate_scale) + delivered_rate*10/(100*1024)
        # else:
        #     reward = np.log(delivered_rate_scale) + delivered_rate*10/(100*1024) - 2*np.log(delay_scale)
        
        # log reward
        if delay_scale < 1: # log不能对0计算, 防止过量惩罚
            reward = np.log(delivered_rate_scale)
        else:
            reward = np.log(delivered_rate_scale) - 2*np.log(delay_scale)
        
        return reward

    def _get_obs(self):
        # also can : pub.get_message()
        for msg in self.msg_stream:
            if msg["type"] == "pmessage":
                """
                mininet 
                len(data_list) 为0 出错
                len(data_list) 为1 channel初始化消息
                len(data_list) 为3 流结束通知
                len(data_list) 为4 启动时的流初始状态信息
                """
                channel = str(msg["channel"], encoding="utf-8")
                if channel.startswith("mininet"):
                    data_list = msg["data"].decode("utf-8").split(';')
                    if len(data_list) == 3:      # done
                        return np.array([0], dtype=np.float32)

                if channel.startswith("rlccstate_"):
                    cid = channel.replace("rlccstate_", "", 1) # 删除前缀，获取cid
                    if self.cid == None:
                        self.cid = cid
                    elif cid != self.cid:
                        continue
                    else:                    
                        data_list = msg["data"].decode("utf-8").split(';')
                        len_of_list = len(data_list)

                        if len_of_list > 6:
                            data = np.array(data_list, dtype=np.float64)    # receive with np.int64
                            self.cwnd = data[-1]
                            self.minrtt = data[2]
                            return np.divide(data, self.scale, dtype=np.float32)
                        else:
                            continue
            
    def reset(self, seed: Optional[int] = None, options: Optional[dict] = None):
        self.cid = None # get new cid
        
        self.rp.publish('tcpnl_control', "reset") # mininet重启iperf

        self.state = self._get_obs()
        if len(self.state) == 1: 
            self.reset()
        print(f"reset : {self.cid} : {self.state}")

        # # rllib 
        return self.state, {}

    def EMA(self, new, old, rate): # rate 4, 8
        return (1/rate)*new + ((rate-1)/rate)*old

    def step(self, action_index):

        cwnd_change = 0
        if self.plan == 1:
            # cwnd = self.cwnd * action_index * 2  # acition value is rate, cwnd_gain = 2
            pass

        if self.plan == 2:
            # action is the index of action
            cwnd_change = self._action_to_direction[action_index]
            cwnd_change = np.clip(cwnd_change, self.action_min-1, self.action_max+1)

        if self.plan == 3:
            # add satcc action here
            
            action_choosed = self._action_to_direction[action_index]
            action_choosed = np.clip(action_choosed, self.action_min-1, self.action_max+1)

            if action_choosed == 0:
                self.up_stay_EMA = self.EMA(5, self.up_stay_EMA, 4)
                self.up_change_EMA = self.EMA(5, self.up_change_EMA, 4)
                self.down_stay_EMA = self.EMA(5, self.down_stay_EMA, 4)
                self.down_change_EMA = self.EMA(5, self.down_change_EMA, 4)
                cwnd_change = 0
            elif action_choosed == 1:
                self.up_change_EMA = self.EMA(10, self.up_change_EMA, 16)
                self.up_stay_EMA = self.EMA(0.2, self.up_stay_EMA, 16)
                self.down_change_EMA = self.EMA(5, self.down_change_EMA, 4)
                cwnd_change = (int)(self.up_change_EMA/self.up_stay_EMA)+1
            elif action_choosed == -1:
                self.down_stay_EMA = self.EMA(0.2, self.down_stay_EMA, 16)
                self.down_change_EMA = self.EMA(10, self.down_change_EMA, 16)
                self.up_change_EMA = self.EMA(5, self.up_change_EMA, 4)
                cwnd_change = -(int)(self.down_change_EMA/self.down_stay_EMA)-1

        # 执行动作
        self.rp.publish(f'rlccaction_{self.cid}', f"{cwnd_change}")  # 适配rllib和tianshou

        # 获取下一步状态
        self.state = self._get_obs()
        
        if len(self.state) == 1:
            # # return
            return self.last_state, self.reward_function(self.last_state), True, False, {}
        # state, reward, done, info
        self.last_state = self.state
        # # return
        reward  = self.reward_function(self.state)
        # print(f"cwnd {'increased' if cwnd_change>0 else 'decrease'}:{self.cwnd}; action:{self._action_to_direction[action[0]]}; reward:{reward}")
        return self.state, reward, False, False, {}

    def render(self):
        return

    def close(self):
        # close
        return

    def seed(self, seed):
        np.random.seed(seed)
