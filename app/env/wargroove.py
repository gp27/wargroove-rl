
import gym
import numpy as np

from .game.wargroove_game import *
from .observation import Observation, list_to_codes
from .actions import Actions
from tabulate import tabulate

from stable_baselines3.common import logger

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
        self.game.reset(random_commanders=False, map_name="playground_1.json")
        #self.game.start()

        self.current_player_num = self.game.player_id
        self.n_players = self.game.n_players

        print(f'\n\n---- NEW GAME ----')
        return self.observation

    @property
    def observation(self):
        return self.wg_obs.get_observation()

    @property
    def legal_actions(self):
        return self.wg_acts.get_legal_actions()

    @property
    def current_player(self):
        return self.game.players[self.current_player_num]

    def convert_action(self, action_index):
        action = self.wg_acts.convert_action_index(action_index)
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
            self.game.continue_game(selection)

            self.current_player_num = self.game.player_id

            p = self.current_player

            done = p.is_victorious or p.has_losed
            reward[self.current_player_num] = 1 if p.is_victorious else -1 if p.has_losed else 0
        self.done = done

        return self.observation, reward, done, {}

    def render(self, mode='human', close=False):
        if close:
            return
        
        if mode == 'human':
            if self.game.phase == Phase.action_selection:
                print(tabulate(self.game.get_board_table(), tablefmt="fancy_grid"))

                for t in self.game.get_unit_tables():
                    print(tabulate(t, headers="keys", tablefmt="fancy_grid"))
            
                print(f'Turn {self.game.turn_number} Player {self.game.player_id + 1}')

        if self.verbose:
            print(
                f'\nObservation: \n{[i if o == 1 else (i,o) for i,o in enumerate(self.observation) if o != 0]}')

        if not self.done:
            print(
                f'\nLegal actions: {[(i, self.wg_acts.convert_action_index(i)) for i,o in enumerate(self.legal_actions) if o != 0]}')

        if self.done:
            print(f'\n\nGAME OVER')

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
