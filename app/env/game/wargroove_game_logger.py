from math import floor
from copy import deepcopy
import json, os

from utils.diff import diff

class WargrooveGameLogger():

    def __init__(self, game: 'WargrooveGame', usernames={}) -> None:
        self.game = game
        self.usernames = usernames
    
    def start(self):
        self.started = False
        self.match_id = self.get_id()
        self.current_state = None
        self.deltas = []
        self.cached_data = None
        self.is_fog = None
    
    def check_triggers(self, state):
        if state in ['startOfTurn', 'endOfUnitTurn']:
            self.update()
    
    def victory(self):
        self.update(force_update=True)
    
    def generate_state(self):
        gold = {}
        units = {}
        unit_classes = {}

        for p in self.game.players.values():
            gold[f'p_{p.id}'] = p.gold
        
        for u in self.game.units.values():
            unit_classes[u['unitClassId']] = self.game.get_unit_class(u['unitClassId'])
            id = u['id']
            units[f'u_{id}'] = deepcopy(u)

        return {
            'gold': gold,
            'units': units,
            'unitClasses': unit_classes,
            'playerId': self.game.player_id,
            'turnNumber': self.game.turn_number
        }
    
    def generate_delta(self):
        new_state = self.generate_state()
        return diff(self.current_state, new_state), new_state, self.current_state
    
    def push_delta(self, delta):
        self.deltas.append(delta)
    
    def check_is_fog(self):
        return False # self.game.is_fog

    def update_match_data(self):
        self.cached_data = {
            'match_id': self.match_id,
            'state': self.current_state,
            'map': self.get_map(),
            'players': self.get_players(),
            'deltas': self.deltas,
            'is_fog': self.get_fog()
        }
    
    def get_id(self):
        return str(floor(self.game.api.pseudoRandomFromString('wgml') * 4294967295))
    
    def get_fog(self):
        if self.is_fog != None: return self.is_fog
        self.is_fog = self.check_is_fog()
        return self.is_fog
    
    def get_map(self):
        m = self.game.map
        return {
            'size': { 'x': m.get('w', 0), 'y': m.get('h', 0) },
            'biome': m.get('biome', 'grass'),
            'tiles': m.get('tiles', '')
        }
    
    def get_players(self):
        ps = [ self.game.players[i] for i in range(self.game.n_players) ]

        return [
            {
                'id': p.id,
                'team': p.team,
                'is_victorious': p.is_victorious,
                'is_human': p.is_human,
                'username': self.usernames.get(p.id, None)
            } for p in ps
        ]
    
    def get_match_data(self):
        if self.cached_data == None:
            self.update_match_data()
        return self.cached_data
    

    def update(self, force_update = False):
        if not self.current_state:
            s = self.generate_state()
            self.current_state = s
            delta, new_state, old_state = None, s, s
        else:
            delta, new_state, old_state = self.generate_delta()


        if delta != None:
            self.push_delta(delta)
            self.current_state = new_state
            force_update = True
        
        if force_update:
            self.update_match_data()
            return True
        
        return False
    
    def save(self, dir_path, name=None):
        data = self.get_match_data()

        if name == None:
            name = f'{self.match_id}.json'

        file_path = os.path.join(dir_path, name)

        with open(file_path, 'w') as f:
            json.dump(data, f)
