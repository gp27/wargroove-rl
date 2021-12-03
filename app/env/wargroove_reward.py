
import numpy as np
from .game.wargroove_game import WargrooveGame

MAX_SCORE = 1e5

class WargrooveReward():
    def __init__(self, game: WargrooveGame):
        self.game = game
    
    def get_rewards(self):
        scores = self.get_scores()
        scores = self.make_zero_sum(scores)
        return np.interp(scores, [-MAX_SCORE*2,MAX_SCORE*2], [-1, 1]).tolist()
    
    def make_zero_sum(self, scores):
        team_scores = {}
        tot = 0

        players = self.game.players

        for p in players.values():
            team = p.team
            score = scores[p.id]
            if not team in team_scores: team_scores[team] = 0.0
            team_scores[team] += score
            tot += score
        
        n = len(team_scores)
        m = n - 1

        zero_sum_team_scores = { team: (team_scores[team] * n - tot) / m for team in team_scores.keys() }


        return [
            scores[p.id] / team_scores[p.team] * zero_sum_team_scores[p.team]
            for p in players.values()
        ]
    

    def get_scores(self):
        n = self.n_players
        scores = [0] * n

        for p in self.game.players.values():
            scores[p.id] = MAX_SCORE if p.is_victorious else -MAX_SCORE if p.has_losed else 0
        
        for u in self.game.units.values():
            uc = self.game.defs['unitClasses'][u['unitClassId']]
            val = uc.get('income', 0)
            if not val:
                val = uc.get('cost', 0) * uc.get('health', 0)
            
            scores[p.id] += val

        return scores

