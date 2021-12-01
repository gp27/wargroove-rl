import numpy as np
from .observation import Observation, list_to_codes
from .actions import Actions

from .game.wargroove_game import WargrooveGame, Phase, EntryStep, PreExecuteSel
from .game.wargroove_data import AVAILABLE_VERBS, TERRAIN_LIST, AVAILABLE_UNIT_CLASSES, PLAYERID_LIST, MOVE_TYPES, AVAILABLE_COMMANDERS, RECRUITABLE_UNIT_CLASSES, ACTIONS

from config import MAX_PLAYERS, MAX_UNITS, MAX_MAP_SIZE

class PosList():
    def __init__(self, h, w):
        self._h = h
        self._w = w

    def __len__(self):
        return self._w * self._h

    def __getitem__(self, ii):
        if ii >= len(self):
            raise IndexError('list index out of range')
        x = ii % self._w
        y = int(ii / self._w)
        return {'x': x, 'y': y}
    
    def __contains__(self, val):
        if not isinstance(val, dict): return False

        x = val.get('x', -1)
        y = val.get('y', -1)

        if x < 0 or y < 0 or x >= self._w or y >= self._h:
            return False

        return True
    
    def index(self, val):
        if not val in self:
            raise ValueError('{} is not in list'.format(val))
        return self._w * val.get('y') + val.get('x')

POS_LIST = PosList(MAX_MAP_SIZE, MAX_MAP_SIZE)

class WargrooveObservation(Observation):

    def __init__(self, game):
        self.game = game
        self.terrains = None
        super().__init__(self.get_props())
    
    def get_props(self):
        return [
    {
        'name': 'global',
        'obs': [
            {
                'options': Phase,
                'getter': lambda _: self.game.phase
            }, {
                'options': EntryStep,
                'getter': lambda _: self.game.entry_step
            }, {
                'options': AVAILABLE_VERBS,
                'getter': lambda _: self.game.selected_verb
            }, {
                'options': PreExecuteSel,
                'getter': lambda _: self.game.pre_execute_selection
            }, {
                'n': 2,
                'getter': lambda _: self.pos_to_list(self.game.end_pos)
            }, {
                'n': 2,
                'getter': lambda _: self.pos_to_list(self.game.target_pos)
            }, {
                'getter': lambda _: self.game.pre_execute_steps
            }, {
                'getter': lambda _: self.game.turn_number
            }, {
                'n': MAX_MAP_SIZE * MAX_MAP_SIZE * len(TERRAIN_LIST),
                'getter': lambda _: self.get_terrains()

            }
        ]
    }, {
        'name': 'unit',
        'n': MAX_UNITS,
        'get_iter': lambda: self.game.units.values(),
        'obs': [
            {
                'options': AVAILABLE_UNIT_CLASSES,
                'getter': lambda u: u['unitClassId']
            }, {
                'options': PLAYERID_LIST,
                'getter': lambda u: u['playerId']
            }, {
                'n': 2,
                'getter': lambda u: self.pos_to_list(u['pos'])
            }, {
                'n': 11,
                'getter': lambda u: self.get_unit_flags(u)
            }, {
                'n': 13,
                'getter': lambda u: self.get_unit_values(u)
            }, {
                'options': MOVE_TYPES,
                'getter': lambda u: self.game.defs['unitClasses'][u['unitClassId']].get('movement','')
            }
        ]
    }, {
        'name': 'player',
        'n': MAX_PLAYERS,
        'get_iter': lambda: self.game.players.values(),
        'obs': [
            {
                'options': [0, 1, 2, 3],
                'getter': lambda p: p.team
            },
            {
                'n': 3,
                'getter': lambda p: self.get_player_flags(p)
            }, {
                'n': 2,
                'getter': lambda p: self.get_player_values(p)
            }
        ]
    }
    #, {
    #    'name': 'buffs',
    #    'n': 100,
    #    'obs': [{
    #        'n': 2,
    #        'getter': lambda b: self.posToList(b.pos)
    #    }, {
    #        'getter': lambda b: b.radius
    #    }]
    #}
]

    def pos_to_list(self, pos):
        if pos == None:
            pos = { 'x': -100, 'y': -100 }
        return [pos['y'], pos['x']]

    def get_unit_flags(self, unit):
        pid = unit['playerId']
        current_pid = self.game.player_id
        unit_class = self.game.defs['unitClasses'][unit['unitClassId']]

        player = self.game.players.get(pid)
        current_player = self.game.players[current_pid]

        tags = unit_class.get('tags', [])

        return [
            int(unit['id'] == self.game.selected_unit_id),  # isSelected
            int(pid == current_pid),  # isAgent
            int(player != None and player.team == current_player.team),  # isAlly
            int(pid == -1),  # isNeutral
            int(unit_class.get('isCommander', False)),
            int(unit_class.get('isStructure', False)),
            int(unit_class.get('canBeCaptured', False)),
            int('type.air' in tags),
            int(unit.get('inTransport', False)),
            int(unit.get('hadTurn', False)),
            int(unit.get('canBeAttacked', True))
        ]
    
    def get_unit_values(self, unit):
        pid = unit['playerId']
        unit_class = self.game.defs['unitClasses'][unit['unitClassId']]
        groove = self.game.defs['grooves'].get(unit['grooveId'], { 'chargeBy': {} })

        return [
            unit['health'],
            100, # max Health
            unit_class.get('regeneration', 0),
            unit['grooveCharge'],
            groove.get('maxCharge', 0),
            groove.get('chargePerUse', 0),
            groove['chargeBy'].get('endOfTurn', 0),
            groove['chargeBy'].get('attack', 0),
            groove['chargeBy'].get('counter', 0),
            groove['chargeBy'].get('kill', 0),
            unit_class.get('loadCapacity', 0),
            unit_class.get('moveRange', 0),
            unit_class.get('cost', 0)
        ]
    
    def get_player_flags(self, player):
        pid = player.id
        current_pid = self.game.player_id
        current_player = self.game.players[current_pid]

        return [
            pid == current_pid, # isAgent
            player.team == current_player.team, # isAlly
            player.has_losed,
        ]
    
    def get_player_values(self, player):
        return [
            player.gold,
            player.income
        ]
    
    def make_terrains(self):
        m = self.game.map
        w = m['w']
        h = m['h']
        tiles = m['tiles']

        codes = list_to_codes(TERRAIN_LIST)

        obs = np.zeros(shape=(MAX_MAP_SIZE, MAX_MAP_SIZE, len(TERRAIN_LIST)))

        for index, terrain in np.ndenumerate(tiles):
            obs[index] = codes[terrain]


        return obs
    
    def get_terrains(self):
        if not isinstance(self.terrains, np.ndarray):
            self.terrains = self.make_terrains()
        
        return self.terrains


class WargrooveActions(Actions):

    def __init__(self, game: WargrooveGame):
        self.game = game
        self.get_selectables = lambda: self._get_selectables()
        super().__init__(self.get_props())
    
    def _get_selectables(self):
        s = self.game.selectables
        if s == None: s = []
        return s
    
    def get_props(self):
        
        return [{
    'condition': lambda: self.game.phase == Phase.commander_selection,
    'options': AVAILABLE_COMMANDERS,
    'getter': self.get_selectables
}, {
    'condition': lambda: self.game.phase == Phase.action_selection,
    'options': ACTIONS,
    'getter': self.get_selectables
}, {
    'condition': lambda: self.allow_cancel(),
    'options': ['cancel'],
    'getter': lambda: ['cancel']
}, {
    'condition': lambda: self.game.entry_step == EntryStep.verb_selection,
    'options': AVAILABLE_VERBS,
    'getter': self.get_selectables
}, {
    'condition': lambda: self.game.pre_execute_selection == PreExecuteSel.recruit_selection or self.game.entry_step == EntryStep.recruit_selection,
    'options': RECRUITABLE_UNIT_CLASSES,
    'getter': self.get_selectables
}, {
    'condition': lambda: self.is_position_selection(),
    'options': POS_LIST,
    'getter': lambda: self.get_positions(),
    'convert': lambda pos: self.convert_position(pos)
}]
   
    def is_position_selection(self):
        return (
            self.game.entry_step in [EntryStep.unit_selection, EntryStep.end_position_selection, EntryStep.target_selection] or
            self.game.pre_execute_selection == PreExecuteSel.target_selection
        )
    
    def allow_cancel(self):
        s = self.get_selectables()
        return self.game.phase == Phase.entry_selection and len(s) == 0

    
    def get_positions(self):
        if self.game.entry_step == EntryStep.unit_selection:
            return self.get_units_pos()
        
        return self.get_selectables()
    
    def convert_position(self, pos):
        if self.game.entry_step == EntryStep.unit_selection:
            return self.get_unit_id_from_pos(pos)
        
        return pos
    
    def get_units_pos(self):
        unitIds = self.get_selectables()
        return [u['pos'] for u in self.game.units.values() if u['id'] in unitIds]
    
    def get_unit_id_from_pos(self, pos):
        return next((u['id'] for u in self.game.units.values() if u['pos']['x'] == pos['x'] and u['pos']['y'] == pos['y']), None)

