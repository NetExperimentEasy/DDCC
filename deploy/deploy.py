
from qlearning import Qlearning
from tile import TileCoder
import numpy as np
from redis.client import Redis
from collections import namedtuple

ACTION_MAP = {} # cid: action_matrix
action_matrix = namedtuple('action_matrix', ['up_stay_EMA', 'up_change_EMA', 'down_stay_EMA', 'down_change_EMA'])

## start redis
r = Redis(host='0.0.0.0', port=6379)
rp = Redis(host='0.0.0.0', port=6379)
pub = r.pubsub()
pub.psubscribe("rlccstate_*")
msg_stream = pub.listen()

for msg in msg_stream:
    print(str(msg["channel"], encoding="utf-8"), 'subscribe success')
    break


def EMA(new, old, rate): # rate 4, 8
    return (1/rate)*new + ((rate-1)/rate)*old

def satcc_action(cid: int, action_index: int):
    """
    Input : action_index  0, 1, 2 
    Output : cwnd_change
    """
    global ACTION_MAP
    action_to_direction = {
            0: 1,
            1: 0,
            2: -1,
        }
    # 比例动作
    action_choosed = action_to_direction[action_index]
    
    if cid not in ACTION_MAP.keys():
        ACTION_MAP[cid] = action_matrix(5,5,5,5)
        # ACTION_MAP[cid] = action_matrix(0.1,0.1,0.1,0.1)

    if action_choosed == 0:
        ACTION_MAP[cid] = ACTION_MAP[cid]._replace(up_stay_EMA=EMA(5, ACTION_MAP[cid].up_stay_EMA, 4), 
                                                   up_change_EMA=EMA(5, ACTION_MAP[cid].up_change_EMA, 4),
                                                   down_stay_EMA=EMA(5, ACTION_MAP[cid].down_stay_EMA, 4),
                                                   down_change_EMA=EMA(5, ACTION_MAP[cid].down_change_EMA, 4))
        cwnd_change = 0
    elif action_choosed == 1:
        ACTION_MAP[cid] = ACTION_MAP[cid]._replace(up_stay_EMA=EMA(0.2, ACTION_MAP[cid].up_stay_EMA, 16), 
                                                   up_change_EMA=EMA(10, ACTION_MAP[cid].up_change_EMA, 16),
                                                   down_change_EMA=EMA(5, ACTION_MAP[cid].down_change_EMA, 4))
        cwnd_change = (int)(ACTION_MAP[cid].up_change_EMA/ACTION_MAP[cid].up_stay_EMA)+1
    elif action_choosed == -1:
        ACTION_MAP[cid] = ACTION_MAP[cid]._replace(up_change_EMA=EMA(5, ACTION_MAP[cid].up_change_EMA, 4),
                                                   down_stay_EMA=EMA(0.2, ACTION_MAP[cid].down_stay_EMA, 16),
                                                   down_change_EMA=EMA(10, ACTION_MAP[cid].down_change_EMA, 16))
        cwnd_change = -(int)(ACTION_MAP[cid].down_change_EMA/ACTION_MAP[cid].down_stay_EMA)-1
    
    return cwnd_change
    
def get_obs():
    """
    Output : 
        cid
        stage np.nparray
    """
    cid = 0
    state = np.array([0], dtype=np.float32)

    for msg in msg_stream:
        if msg["type"] == "pmessage":
            """
            mininet 
            len(data_list) 为0 出错
            len(data_list) 为1 channel初始化消息
            len(data_list) 为3 流结束通知
            len(data_list) 为4 启动时的流初始状态信息
            """
            channel = str(msg["channel"], encoding="utf-8")
            if channel.startswith("rlccstate_"):
                cid = channel.replace("rlccstate_", "", 1) # 删除前缀，获取cid 
                
                data_list = msg["data"].decode("utf-8").split(';')
                len_of_list = len(data_list)

                if len_of_list > 6:
                    state = np.array(data_list, dtype=np.float32)    # receive with np.int64
                    break
                else:
                    continue
                
    return cid, state
    
    
if __name__ == "__main__":
    
    ## start q-learing
    action_num = 3  # 动作数量

    tiles_per_dim = [16, 16]
    max_th = 1000*1024
    max_delay = 1024*500
    lims = [(0, max_th), (0, max_delay)]
    # number of tilings
    tilings = 32

    tile = TileCoder(tiles_per_dim, lims, tilings)
    w = []
    for i in range(action_num):
        w.append(np.zeros(tile.n_tiles))

    agent = Qlearning(tile=tile, w=w, action_num=action_num, alpha=0.05, beta=0.9, epsilon=0.8, tilings=tilings, wfile='./model/385.npy')
    
    try:
        while True:
            cid, state = get_obs()
            
            th = state[0]
            delay = (state[3]-state[2])
            input_state = np.array([th, delay])
            
            if delay > max_delay:
                delay = max_delay
            if delay < 0:
                delay = 0
            if th > max_th:
                th = max_th
            
            _, action_index = agent.getMaxPredQ(states=input_state)
            cwnd_change = satcc_action(cid=cid, action_index=action_index)
            
            # 执行动作
            rp.publish(f'rlccaction_{cid}', f"{cwnd_change}")
            
    except KeyboardInterrupt:
        pass
    
