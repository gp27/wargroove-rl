
import gym
import numpy as np

from .game.wargroove_game import *
from .observation import Observation, listToCodes
from .actions import Actions
from tabulate import tabulate

from stable_baselines import logger

from .wargroove_spaces import WargrooveObservation, WargrooveActions

class WargrooveEnv(gym.Env):
    metadata = {'render.modes': ['human']}

    def __init__(self, verbose=False, manual = False):
        super(WargrooveEnv, self).__init__()
        self.name = 'wargroove'
        self.manual = manual

        self.n_players = 2
        self.game = WargrooveGame()

        self.wg_obs = WargrooveObservation(self.game)
        self.wg_acts = WargrooveActions(self.game)

        self.observation_space = self.wg_obs.space
        self.action_space = self.wg_acts.space

        self.verbose = verbose

    def reset(self):
        self.done = False
        self.game.reset(random_commanders=False)
        #self.game.start()

        self.current_player_num = self.game.playerId
        self.n_players = self.game.n_players

        logger.debug(f'\n\n---- NEW GAME ----')
        return self.observation

    @property
    def observation(self):
        return self.wg_obs.getObservation()

    @property
    def legal_actions(self):
        return self.wg_acts.getLegalActions()

    @property
    def current_player(self):
        return self.game.players[self.current_player_num]

    def convert_action(self, action_index):
        action = self.wg_acts.convertActionIndex(action_index)
        if action == 'cancel': return action
        return self.game.selectables.index(action)

    def step(self, action):

        reward = [0] * self.n_players
        done = False

        legal_actions = self.legal_actions

        # check move legality
        if legal_actions[action] == 0:
            reward = [1.0/(self.n_players-1)] * self.n_players
            reward[self.current_player_num] = -1
            done = True

        else:
            selection = self.convert_action(action)
            self.game.continueGame(selection)

            self.current_player_num = self.game.playerId

            p = self.current_player

            done = p.isVictorious or p.hasLosed
            reward[self.current_player_num] = 1 if p.isVictorious else -1 if p.hasLosed else 0
        self.done = done

        return self.observation, reward, done, {}

    def render(self, mode='human', close=False):
        if close:
            return
        
        if mode == 'human':
            print(tabulate(self.game.getBoardTable(), tablefmt="fancy_grid"))

            for t in self.game.getUnitTables():
                print(tabulate(t, headers="keys", tablefmt="fancy_grid"))

        if self.verbose:
            logger.debug(
                f'\nObservation: \n{[i if o == 1 else (i,o) for i,o in enumerate(self.observation) if o != 0]}')

        if not self.done:
            logger.debug(
                f'\nLegal actions: {[(i, self.wg_acts.convertActionIndex(i)) for i,o in enumerate(self.legal_actions) if o != 0]}')

        if self.done:
            logger.debug(f'\n\nGAME OVER')

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
            if p.hasLosed:
                losers.append(p.id)
            #else: # subtract time

        for u in self.game.units.values():
            pid = u['playerId']
            if pid < 0 or p in losers: continue

            uc = self.game.dfn['unitClasses'][u['unitClassId']]
            value = u['health'] * uc.get('cost', 0) + uc.get('income', 0)
            scores[playerId] = value
        
        return scores
