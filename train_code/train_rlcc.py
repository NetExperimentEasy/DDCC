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
lims = [(0, 104857600), (0, 2048000)]   # 104857600
# number of tilings
tilings = 32

# satcc
# action_num = 9  # 3x3动作 action 0,1,2表示 step为0； aciton 345表示 step为1； action 678表示 step为2；动作总共为9个
action_num = 3  # 比例动作

tile = TileCoder(tiles_per_dim, lims, tilings)
w = []
for i in range(action_num):
    w.append(np.zeros(tile.n_tiles))

wfile = "rlcc.npy"
# , wfile=wfile
# , wfile='./result/0929/90.npy'
agent = Qlearning(tile=tile, w=w, action_num=action_num, alpha=0.05, beta=0.9, epsilon=0.8, tilings=tilings, wfile='./result/0929/980.npy')

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

count_eposide = 980

try:
    for i in range(690): #90 3小时 360 12h  690  23h
        print("train: episode:", i+count_eposide)
        
        if(i%30 == 0):
            agent.save_w(f"./result/0929/{i+count_eposide}.npy")
        
        obs, info = env.reset()
        done = False
        record_reward = []
        # env.render()
        delay = (obs[3]-obs[2])
        th = obs[0]
        if delay > 2048000:
            delay = 2048000
        if delay < 0:
            delay = 0
        if th > 104857600:
            th = 104857600
        states = np.array([th, delay])
        while not done:
            # print(states)
            if i%10 != 0: # exp 不进行训练
                action_index = agent.explore_action(states=states)
            else:
                _, action_index = agent.getMaxPredQ(states=states)
            action = action_index
            # print(action)
            if delay>big_delay:
                big_delay = delay
                print("---big---", big_th, big_delay)
            if th>big_th:
                big_th = th
                print("---big---", big_th, big_delay)
            print("now :", th, delay, end='\r')

            newobs, reward, terminated, truncated, info = env.step(np.array(action))
            delay = (newobs[3]-newobs[2])
            th = newobs[0]
            if delay > 2048000:
                delay = 2048000
            if delay < 0:
                delay = 0
            if th > 104857600:
                th = 104857600
            next_states = np.array([th, delay])
            if(i%10 == 0): # exp 不进行训练
                agent.updateQ(reward=reward, prev_states=states, action_index=action_index, next_states=next_states)
            record_reward.append(reward)
            states = next_states
            if terminated or truncated:
                print("avg reward:", np.mean(record_reward))
                done = True
        reward_ave.append(np.mean(record_reward))

except KeyboardInterrupt:
    print("---big---", big_th, big_delay)
    agent.save_w(wfile)
    print(reward_ave)

print("---big---", big_th, big_delay)
print(reward_ave)
agent.save_w(wfile)
env.close()