
from .wargroove import WargrooveEnv

from gym.envs.registration import register
register(
    id='wargroove-v0',
    entry_point='env:WargrooveEnv'
)