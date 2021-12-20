
import numpy as np
from .game.wargroove_game import WargrooveGame, Phase

MAX_SCORE = 1e5

def get_interpolated_health(health):
    h = health / 100
    return (h + 1 - pow(1 - h, 4)) / 2


class Potential():
    def __init__(self, monotonic=0, val = 0):
        self.val = val
        self._cursor = val
        self._monotonic = 1 if monotonic > 0 else -1 if monotonic < 0 else 0
    
    def set_val(self, val):
        c = self._cursor
        self._cursor = val

        if self._monotonic * (val - c) >= 0:
            self.val = val
    
    def set_delta(self, delta):
        self.set_val(self._cursor + delta)
    
    


class WargrooveReward():
    def __init__(self, game: WargrooveGame, gamma = 0.99):
        self.game = game
        self.gamma = gamma

    def reset(self):
        self.n = self.game.n_players
        self.pp = [ {
            'actions': Potential(monotonic=1),
            'cancel': Potential(monotonic=-1)
        } for pid in range(self.n) ]
        
        self.potentials = self.get_potentials()
    
    def get_rewards(self):
        scores = self.get_scores()

        #print('scores', scores)

        scores = self.make_zero_sum(scores)
        #print('zero_sum_scores', scores)
        return np.interp(scores, [-MAX_SCORE*2,MAX_SCORE*2], [-1, 1]).tolist()
    
    def make_zero_sum(self, scores):
        team_scores = {}
        team_n = {}
        tot = 0

        players = self.game.players

        for p in players.values():
            team = p.team
            score = scores[p.id]
            if not team in team_scores:
                team_scores[team] = 0.0
                team_n[team] = 0
            team_scores[team] += score
            team_n[team] += 1
            tot += score
        
        m = len(team_scores) - 1

        enemy_team_score_avg = { team: (tot - team_scores[team]) / m for team in team_scores.keys() }


        return [
            scores[p.id] - enemy_team_score_avg[p.team] / team_n[p.team]
            for p in players.values()
        ]
    

    def get_scores(self):
        scores = [0] * self.n

        new_potentials = self.get_potentials()

        for p in self.game.players.values():
            scores[p.id] = MAX_SCORE if p.is_victorious else -MAX_SCORE if p.has_losed else 0

            diff =  -self.potentials[p.id] + new_potentials[p.id] #* self.gamma 
            scores[p.id] += diff

        self.potentials = new_potentials
        
        return scores
    
    def get_potentials(self):
        p = [0] * self.n
        acts = [0] * self.n

        is_action_phase = self.game.phase == Phase.action_selection
        
        for u in self.game.units.values():
            pid = u['playerId']
            if pid < 0: continue
            uc = self.game.defs['unitClasses'][u['unitClassId']]
            #isStructure = uc.get('isStructure', False)
            isCommander = uc.get('isCommander', False)
            isHQ = uc.get('isHQ', False)

            val = uc.get('income', 0)

            if not val or isHQ:
                health_val = get_interpolated_health(u.get('health', 0))
                val = (uc.get('cost', 0) + 100) * health_val * (1.5 if isCommander else 1)
            
            if u.get('hadTurn', False):
                acts[pid] += 20
            
            p[pid] += val
        
        for pid in self.game.players.keys():
            pp = self.pp[pid]
            pp['actions'].set_val(acts[pid])

            if pid == self.game.player_id:
                if is_action_phase:
                   pp['cancel'].set_delta(self.game.canceled_actions_count * -20)
            
            p[pid] += pp['cancel'].val + pp['actions'].val
                    

        return p


