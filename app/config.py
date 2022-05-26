import os
import wandb

DEBUG = 10
INFO = 20
WARN = 30
ERROR = 40
DISABLED = 50

_dir_path = os.path.dirname(os.path.realpath(__file__))


LOGDIR = _dir_path + "/logs"
RESULTSPATH = _dir_path + "/results.csv"
TMPMODELDIR = _dir_path + "/tmp"
MODELDIR = _dir_path + '/models'

MODEL_NAME = "wg_8x8_alpha"

# Wargroove configurations
MAX_PLAYERS = 2
MAX_UNITS = 100
MAX_GOLD = int(1e8) # used for normalization
MAX_MAP_SIZE = 8 # real max size: 96, average competitive size: 20
MAP_POOL=['playground_2.json']

default_config = {
  "wg_obs_max_players": MAX_PLAYERS,
  "wg_obs_max_units": MAX_UNITS,
  "wg_obs_max_gold": MAX_GOLD,
  "wg_obs_max_map_size": f'{MAX_MAP_SIZE}x{MAX_MAP_SIZE}',
  "wg_map_pool": ','.join(MAP_POOL)
}

model_artifact = wandb.Artifact(MODEL_NAME, type="model")
model_artifact.add_dir(MODELDIR)

def init_wandb():
  run =  wandb.init(
    project="wargroove-rl",
    config=default_config,
    sync_tensorboard=True,
    #monitor_gym=True
  )

  run.use_artifact(model_artifact)

  #artifact = run.use_artifact(MODEL_NAME + ':latest')
  #artifact_dir = artifact.download()

  return run