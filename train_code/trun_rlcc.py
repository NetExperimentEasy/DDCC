import gymnasium as gym
import gym_rlcc
from gym_rlcc.envs import RlccEnvQT
from qlearning import Qlearning
from tile import TileCoder
import numpy as np

# number of tile spanning each dimension
tiles_per_dim = [16, 16]
# value limits of each dimension
# state1 state2 action
th_max = 1024*1000 # 1G
delay_max = 1024*500 # 500ms
lims = [(0, th_max), (0, delay_max)]   # 104857600
# number of tilings
tilings = 32

action_num = 3  # 比例动作

tile = TileCoder(tiles_per_dim, lims, tilings)
w = []
for i in range(action_num):
    w.append(np.zeros(tile.n_tiles))


wfile='./result/rate-acts/180.npy' # 指定加载模型
agent = Qlearning(tile=tile, w=w, action_num=action_num, alpha=0.05, beta=0.9, epsilon=0.8, tilings=tilings, wfile=wfile)

# owl

# 反比例
config = {
    "plan" :3,
    "maxsteps" : 900,
}

env = RlccEnvQT(config=config)

big_th = 0
big_delay = 0

reward_ave = []

try:
    for i in range(1):
        print("train: episode:", i)
        obs, info = env.reset()
        done = False
        record_reward = []
        # env.render()
        delay = (obs[3]-obs[2])
        th = obs[0]
        if delay > delay_max:
            delay = delay_max
        if delay < 0:
            delay = 0
        if th > th_max:
            th = th_max
        states = np.array([th, delay])
        while not done:
            # print(states)
            _, action_index = agent.getMaxPredQ(states=states)

            if delay>big_delay:
                big_delay = delay
                print("---big---", big_th, big_delay)
            if th>big_th:
                big_th = th
                print("---big---", big_th, big_delay)
            print("now :", th, delay, end='\r')

            newobs, reward, terminated, truncated, info = env.step(action_index)
            delay = (newobs[3]-newobs[2])
            th = newobs[0]
            if delay > delay_max:
                delay = delay_max
            if delay < 0:
                delay = 0
            if th > th_max:
                th = th_max
            next_states = np.array([th, delay])

            record_reward.append(reward)
            states = next_states
            if terminated or truncated:
                print("avg reward:", np.mean(record_reward))
                done = True
        reward_ave.append(np.mean(record_reward))

except KeyboardInterrupt:
    print("---big---", big_th, big_delay)
    print(reward_ave)

print("---big---", big_th, big_delay)
print(reward_ave)
env.close()