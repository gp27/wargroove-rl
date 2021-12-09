
import gym
import numpy as np
from tabulate import tabulate

from stable_baselines3.common import logger

from .game.wargroove_game import *
from .wargroove_spaces import WargrooveObservation, WargrooveActions
from .wargroove_reward import WargrooveReward
from config import LOGDIR, MAP_POOL

class WargrooveEnv(gym.Env):
    metadata = {'render.modes': ['human']}

    def __init__(self, verbose=False, manual = False, gamma=0.99):
        super(WargrooveEnv, self).__init__()
        self.name = 'wargroove'
        self.manual = manual

        self.n_players = 2
        self.game = WargrooveGame()

        self.wg_obs = WargrooveObservation(self.game)
        self.wg_acts = WargrooveActions(self.game)
        self.wg_reward = WargrooveReward(self.game, gamma=gamma)

        self.observation_space = self.wg_obs.space
        self.action_space = self.wg_acts.space

        self.verbose = verbose

    def reset(self):
        self.move_i = 0
        self.done = False
        self.game.reset(random_commanders=False, map_names=MAP_POOL,log=True)
        self.wg_reward.reset()
        #self.game.start()

        self.current_player_num = self.game.player_id
        self.n_players = self.game.n_players

        gym.logger.debug(f'\n\n---- NEW GAME ----')
        return self.observation

    @property
    def observation(self):
        return self.wg_obs.get_observation()

    def action_masks(self):
        return self.wg_acts.get_action_masks()

    @property
    def current_player(self):
        return self.game.players[self.current_player_num]

    def convert_action(self, action_index):
        action = self.wg_acts.convert_action_index(action_index)
        if action == 'cancel': return action
        return self.game.selectables.index(action)

    def step(self, action):

        #reward = [0] * self.n_players
        done = False

        action_masks = self.action_masks()

        # check move legality
        if action_masks[action] == 0:
            reward = [1.0/(self.n_players-1)] * self.n_players
            reward[self.current_player_num] = -1
            done = True

        else:
            selection = self.convert_action(action)
            self.game.continue_game(selection)

            if self.game.phase == Phase.action_selection:
                self.move_i += 1

            self.current_player_num = self.game.player_id

            p = self.current_player

            done = p.is_victorious or p.has_losed
            reward = self.wg_reward.get_rewards()
            #reward[self.current_player_num] = 1 if p.is_victorious else -1 if p.has_losed else 0
        self.done = done

        return self.observation, reward, done, {}

    def render(self, mode='human', close=False):
        if close:
            return
        
        if mode == 'human':
            gym.logger.debug(tabulate(self.game.get_step_table(), headers="keys", tablefmt="fancy_grid"))

            if self.game.phase == Phase.action_selection:
                gym.logger.debug(tabulate(self.game.get_board_table(), tablefmt="fancy_grid"))

                for t in self.game.get_unit_tables():
                    gym.logger.debug(tabulate(t, headers="keys", tablefmt="fancy_grid"))
            
                gym.logger.debug(f'Turn {self.game.turn_number} Player {self.game.player_id + 1}')

                if self.move_i % 100 == 0:
                    self.game.game_logger.save(LOGDIR)
                    

        if self.verbose:
            gym.logger.debug(f'\nObservation: \n{[i if o == 1 else (i,o) for i,o in enumerate(self.observation) if o != 0]}')

        if not self.done:
            gym.logger.debug(f'\nLegal actions: {[(i, self.wg_acts.convert_action_index(i)) for i,o in enumerate(self.action_masks()) if o != 0]}')

        if self.done:
            self.game.game_logger.save(LOGDIR)
            gym.logger.debug(f'\n\nGAME OVER')

    def rules_move(self):
        raise Exception(
            'Rules based agent is not yet implemented for Wargroove!')


    def get_rewards(self):
        n = self.n_players
        m = n - 1
        scores = [0] * n
        
        self.get_scores(scores)
        
        tot = sum(scores)
        m = self.n_players - 1

        # subtracts average of opponents values to make it a zero sum game
        rewards = [(s * n - tot) / m for s in scores]

        return rewards
    
    def get_scores(self, scores):
        if not scores:
            scores = [0] * self.n_players
        
        losers = []
        for p in self.game.players.values():
            if p.has_losed:
                scores[p.id] = -1
                losers.append(p.id)
            #else: # subtract time
            if p.is_victorious:
                scores[p.id] = 1

        #for u in self.game.units.values():
        #    pid = u['playerId']
        #    if pid < 0 or p in losers: continue

        #    uc = self.game.dfn['unitClasses'][u['unitClassId']]
        #    value = u['health'] * uc.get('cost', 0) + uc.get('income', 0)
        #    scores[pid] = value
        
        return scores
