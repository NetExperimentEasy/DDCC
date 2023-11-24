from gym.envs.registration import register

# TCP netlink based
register(
    id="gym_rlcc/rlcc-v1-q",
    entry_point="gym_rlcc.envs:RlccEnvQT",
)

