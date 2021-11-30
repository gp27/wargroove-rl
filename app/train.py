# docker-compose exec app python3 train.py -r -e butterfly

import os

import argparse
import time
from shutil import copyfile

from sb3_contrib.ppo_mask import MaskablePPO as PPO, MlpPolicy
from stable_baselines3.common.callbacks import EvalCallback

from stable_baselines3.common.vec_env import DummyVecEnv
from stable_baselines3.common.utils import set_random_seed
from stable_baselines3.common import logger

#from utils.callbacks import SelfPlayCallback
from utils.files import reset_logs, reset_models
from utils.selfplay import selfplay_wrapper

from env import WargrooveEnv
#from models import CustomPolicy

import config

def main(args):

  model_dir = os.path.join(config.MODELDIR, 'wargroove')

  try:
    os.makedirs(model_dir)
  except:
    pass
  reset_logs(model_dir)
  if args.reset:
    reset_models(model_dir)
  logger.configure(config.LOGDIR)

  #if args.debug:
  #  logger.set_level(config.DEBUG)
  #else:
  #  time.sleep(5)
  #  logger.set_level(config.INFO)

  seed = args.seed
  set_random_seed(seed)

  print('\nSetting up the selfplay training environment opponents...')
  env = selfplay_wrapper(WargrooveEnv)(opponent_type = args.opponent_type, verbose = args.verbose)
  env.seed(seed)


  params = {'gamma':args.gamma
    , 'timesteps_per_actorbatch':args.timesteps_per_actorbatch
    , 'clip_param':args.clip_param
      , 'entcoeff':args.entcoeff
      , 'optim_epochs':args.optim_epochs
      , 'optim_stepsize':args.optim_stepsize
      , 'optim_batchsize':args.optim_batchsize
      , 'lam':args.lam
      , 'adam_epsilon':args.adam_epsilon
      , 'schedule':'linear'
      , 'verbose':1
      , 'tensorboard_log':config.LOGDIR
  }

  time.sleep(5) # allow time for the base model to be saved out when the environment is created

  if args.reset or not os.path.exists(os.path.join(model_dir, 'best_model.zip')):
    print('\nLoading the base PPO agent to train...')
    model = PPO.load(os.path.join(model_dir, 'base.zip'), env, **params)
  else:
    print('\nLoading the best_model.zip PPO agent to continue training...')
    model = PPO.load(os.path.join(model_dir, 'best_model.zip'), env, **params)

  #Callbacks
  print('\nSetting up the selfplay evaluation environment opponents...')
  callback_args = {
    'eval_env': selfplay_wrapper(WargrooveEnv)(opponent_type = args.opponent_type, verbose = args.verbose),
    'best_model_save_path' : config.TMPMODELDIR,
    'log_path' : config.LOGDIR,
    'eval_freq' : args.eval_freq,
    'n_eval_episodes' : args.n_eval_episodes,
    'deterministic' : False,
    'render' : True,
    'verbose' : 0
  }

  if args.rules:  
    print('\nSetting up the evaluation environment against the rules-based agent...')
    # Evaluate against a 'rules' agent as well
    eval_actual_callback = EvalCallback(
      eval_env = selfplay_wrapper(WargrooveEnv)(opponent_type = 'rules', verbose = args.verbose),
      eval_freq=1,
      n_eval_episodes=args.n_eval_episodes,
      deterministic = args.best,
      render = True,
      verbose = 0
    )
    callback_args['callback_on_new_best'] = eval_actual_callback
    
  # Evaluate the agent against previous versions
  #eval_callback = SelfPlayCallback(args.opponent_type, args.threshold, args.env_name, **callback_args)

  print('\nSetup complete - commencing learning...\n')

  #model.learn(total_timesteps=int(1e9), callback=[eval_callback], reset_num_timesteps = False, tb_log_name="tb")
  model.learn(total_timesteps=int(1e9), reset_num_timesteps = False, tb_log_name="tb")

  env.close()
  del env


def cli() -> None:
  """Handles argument extraction from CLI and passing to main().
  Note that a separate function is used rather than in __name__ == '__main__'
  to allow unit testing of cli().
  """
  # Setup argparse to show defaults on help
  formatter_class = argparse.ArgumentDefaultsHelpFormatter
  parser = argparse.ArgumentParser(formatter_class=formatter_class)


  parser.add_argument("--reset", "-r", action = 'store_true', default = False
                , help="Start retraining the model from scratch")
  parser.add_argument("--opponent_type", "-o", type = str, default = 'mostly_best'
              , help="best / mostly_best / random / base / rules - the type of opponent to train against")
  parser.add_argument("--debug", "-d", action = 'store_true', default = False
              , help="Debug logging")
  parser.add_argument("--verbose", "-v", action = 'store_true', default = False
              , help="Show observation in debug output")
  parser.add_argument("--rules", "-ru", action = 'store_true', default = False
              , help="Evaluate on a ruled-based agent")
  parser.add_argument("--best", "-b", action = 'store_true', default = False
              , help="Uses best moves when evaluating agent against rules-based agent")
  parser.add_argument("--seed", "-s",  type = int, default = 17
            , help="Random seed")

  parser.add_argument("--eval_freq", "-ef",  type = int, default = 10240
            , help="How many timesteps should each actor contribute before the agent is evaluated?")
  parser.add_argument("--n_eval_episodes", "-ne",  type = int, default = 100
            , help="How many episodes should each actor contirbute to the evaluation of the agent")
  parser.add_argument("--threshold", "-t",  type = float, default = 0.2
            , help="What score must the agent achieve during evaluation to 'beat' the previous version?")
  parser.add_argument("--gamma", "-g",  type = float, default = 0.99
            , help="The value of gamma in PPO")
  parser.add_argument("--timesteps_per_actorbatch", "-tpa",  type = int, default = 1024
            , help="How many timesteps should each actor contribute to the batch?")
  parser.add_argument("--clip_param", "-c",  type = float, default = 0.2
            , help="The clip paramater in PPO")
  parser.add_argument("--entcoeff", "-ent",  type = float, default = 0.1
            , help="The entropy coefficient in PPO")

  parser.add_argument("--optim_epochs", "-oe",  type = int, default = 4
            , help="The number of epoch to train the PPO agent per batch")
  parser.add_argument("--optim_stepsize", "-os",  type = float, default = 0.0003
            , help="The step size for the PPO optimiser")
  parser.add_argument("--optim_batchsize", "-ob",  type = int, default = 1024
            , help="The minibatch size in the PPO optimiser")
            
  parser.add_argument("--lam", "-l",  type = float, default = 0.95
            , help="The value of lambda in PPO")
  parser.add_argument("--adam_epsilon", "-a",  type = float, default = 1e-05
            , help="The value of epsilon in the Adam optimiser")

  # Extract args
  args = parser.parse_args()

  # Enter main
  main(args)
  return


if __name__ == '__main__':
  cli()