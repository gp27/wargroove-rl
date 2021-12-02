
import numpy as np
from .game.wargroove_game import WargrooveGame

MAX_SCORE = 100000

class WargrooveReward():
    __init__(self, game: WargrooveGame):
        self.game = game
    
    def get_rewards(self):
        scores = self.get_scores()

        team_scores = {}
        tot = 0

        players = self.game.players

        for p in players.values():
            team = p.team
            score = scores[p.id]
            if not team in team_scores: team_scores[team] = 0
            team_scores[team] += score
            tot += score
        
        n = len(team_scores)
        m = n -1

        zero_sum_team_scores = { team: (team_scores[team] * n - tot) / m for team in team_scores.keys() }


        return [
            scores[p.id] / team_scores[p.team] * zero_sum_team_scores[p.team]
            for p in players.values()
        ]
    

    def get_scores(self):
        n = self.n_players
        scores = [0] * n

        for p in self.game.players.values():
            scores[p.id] = 1 if p.is_victorious else -1 if p.has_losed else 0

        return np.interp(scores, [-MAX_SCORE,MAX_SCORE], [-1, 1]).tolist()

