from .game.wargroove_game import *

from .observation import Observation, listToCodes
from .actions import Actions

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
        super().__init__(self.getProps())
    
    def getProps(self):
        return [
    {
        'name': 'global',
        'obs': [
            {
                'options': Phase,
                'getter': lambda _: self.game.phase
            }, {
                'options': EntryStep,
                'getter': lambda _: self.game.entryStep
            }, {
                'options': AVAILABLE_VERBS,
                'getter': lambda _: self.game.selectedVerb
            }, {
                'options': PreExecuteSel,
                'getter': lambda _: self.game.preExecuteSelection
            }, {
                'n': 2,
                'getter': lambda _: self.posToList(self.game.endPos)
            }, {
                'n': 2,
                'getter': lambda _: self.posToList(self.game.targetPos)
            }, {
                'getter': lambda _: self.game.preExecuteSteps
            }, {
                'getter': lambda _: self.game.turnNumber
            }, {
                'n': MAX_MAP_SIZE * MAX_MAP_SIZE * len(TERRAIN_LIST),
                'getter': lambda _: self.getTerrains()

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
                'getter': lambda u: self.posToList(u['pos'])
            }, {
                'n': 11,
                'getter': lambda u: self.getUnitFlags(u)
            }, {
                'n': 13,
                'getter': lambda u: self.getUnitValues(u)
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
                'getter': lambda p: self.getPlayerFlags(p)
            }, {
                'n': 2,
                'getter': lambda p: self.getPlayerValues(p)
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

    def posToList(self, pos):
        if pos == None:
            pos = { 'x': -100, 'y': -100 }
        return [pos['y'], pos['x']]

    def getUnitFlags(self, unit):
        pid = unit['playerId']
        currentPid = self.game.playerId
        unitClass = self.game.defs['unitClasses'][unit['unitClassId']]

        player = self.game.players.get(pid)
        currentPlayer = self.game.players[currentPid]

        tags = unitClass.get('tags', [])

        return [
            int(unit['id'] == self.game.selectedUnitId),  # isSelected
            int(pid == currentPid),  # isAgent
            int(player != None and player.team == currentPlayer.team),  # isAlly
            int(pid == -1),  # isNeutral
            int(unitClass.get('isCommander', False)),
            int(unitClass.get('isStructure', False)),
            int(unitClass.get('canBeCaptured', False)),
            int('type.air' in tags),
            int(unit.get('inTransport', False)),
            int(unit.get('hadTurn', False)),
            int(unit.get('canBeAttacked', True))
        ]
    
    def getUnitValues(self, unit):
        pid = unit['playerId']
        unitClass = self.game.defs['unitClasses'][unit['unitClassId']]
        groove = self.game.defs['grooves'].get(unit['grooveId'], { 'chargeBy': {} })

        return [
            unit['health'],
            100, # max Health
            unitClass.get('regeneration', 0),
            unit['grooveCharge'],
            groove.get('maxCharge', 0),
            groove.get('chargePerUse', 0),
            groove['chargeBy'].get('endOfTurn', 0),
            groove['chargeBy'].get('attack', 0),
            groove['chargeBy'].get('counter', 0),
            groove['chargeBy'].get('kill', 0),
            unitClass.get('loadCapacity', 0),
            unitClass.get('moveRange', 0),
            unitClass.get('cost', 0)
        ]
    
    def getPlayerFlags(self, player):
        pid = player.id
        currentPid = self.game.playerId
        currentPlayer = self.game.players[currentPid]

        return [
            pid == currentPid, # isAgent
            player.team == currentPlayer.team, # isAlly
            player.hasLosed,
        ]
    
    def getPlayerValues(self, player):
        return [
            player.gold,
            player.income
        ]
    
    def makeTerrains(self):
        m = self.game.map
        w = m['w']
        h = m['h']
        tiles = m['tiles']

        codes = listToCodes(TERRAIN_LIST)

        obs = np.zeros(shape=(MAX_MAP_SIZE, MAX_MAP_SIZE, len(TERRAIN_LIST)))

        for index, terrain in np.ndenumerate(tiles):
            obs[index] = codes[terrain]


        return obs
    
    def getTerrains(self):
        if not isinstance(self.terrains, np.ndarray):
            self.terrains = self.makeTerrains()
        
        return self.terrains


class WargrooveActions(Actions):

    esp = [EntryStep.end_position_selection, EntryStep.target_selection]

    def __init__(self, game):
        self.game = game
        self.getSelectables = lambda: self._getSelectables()
        super().__init__(self.getProps())
    
    def _getSelectables(self):
        s = self.game.selectables
        if s == None: s = []
        return s
    
    def getProps(self):
        
        return [{
    'condition': lambda: self.game.phase == Phase.commander_selection,
    'options': PLAYABLE_COMMANDERS,
    'getter': self.getSelectables
}, {
    'condition': lambda: self.game.phase == Phase.action_selection,
    'options': ACTIONS,
    'getter': self.getSelectables
}, {
    'condition': lambda: self.game.phase == Phase.entry_selection and len(self.getSelectables()) == 0,
    'options': ['cancel'],
    'getter': lambda: ['cancel']
}, {
    'condition': lambda: self.game.entryStep == EntryStep.verb_selection,
    'options': AVAILABLE_VERBS,
    'getter': self.getSelectables
}, {
    'condition': lambda: self.game.preExecuteSelection == PreExecuteSel.recruit_selection or self.game.entryStep == EntryStep.recruit_selection,
    'options': RECRUITABLE_UNIT_CLASSES,
    'getter': self.getSelectables
}, {
    'condition': lambda: self.game.entryStep == EntryStep.unit_selection,
    'options': POS_LIST,
    'getter': lambda: self.getUnitsPos(),
    'convert': lambda pos: self.getUnitIdFromPos(pos)
}, {
    'condition': lambda: (self.game.entryStep in self.esp) or self.game.preExecuteSelection == PreExecuteSel.target_selection,
    'options': POS_LIST,
    'getter': self.getSelectables
}]
    
    def getUnitsPos(self):
        unitIds = self.getSelectables()
        return [u['pos'] for u in self.game.units.values() if u['id'] in unitIds]
    
    def getUnitIdFromPos(self, pos):
        return next((u['id'] for u in self.game.units.values() if u['pos']['x'] == pos['x'] and u['pos']['y'] == pos['y']), None)

