
import numpy as np
from .game.wargroove_game import WargrooveGame

MAX_SCORE = 1e5

def get_interpolated_health(health):
    h = health / 100
    return (h + 1 - pow(1 - h, 4)) * 50

class WargrooveReward():
    def __init__(self, game: WargrooveGame, gamma = 0.99):
        self.game = game
        self.gamma = gamma

    def reset(self):
        self.n = self.game.n_players
        self.potentials = self.get_potentials()
    
    def get_rewards(self):
        scores = self.get_scores()
        scores = self.make_zero_sum(scores)
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

            diff =  self.gamma * new_potentials[p.id] - self.potentials[p.id]
            scores[p.id] += diff

        self.potentials = new_potentials
        
        return scores
    
    def get_potentials(self):
        p = [0] * self.n
        
        for u in self.game.units.values():
            pid = u['playerId']
            if pid < 0: continue
            uc = self.game.defs['unitClasses'][u['unitClassId']]
            val = uc.get('income', 0)
            if not val:
                health_val = get_interpolated_health(uc.get('health', 0))
                val = uc.get('cost', 0) * health_val
            
            p[pid] += val

        return p


