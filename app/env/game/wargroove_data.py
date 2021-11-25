import os, json
from enum import Enum

dir_path = os.path.dirname(os.path.realpath(__file__))
DEF_FILENAME = dir_path + '/wg_2.0.json'

with open(DEF_FILENAME) as def_file:
    DEFS = json.loads(def_file.read())

MAP_PLAYGROUND = (
    5, 5,
    'grass',
    'pppppMprppFpppFpprpMppppp',
    'p_0-2000g,p_1-2000g',
    'barracks.0.0.0.100.0,barracks.1.4.4.100.0,city.-1.3.0.100.0,city.-1.4.1.100.0,city.-1.0.3.100.0,city.-1.1.4.100.0,commander.0.1.0.30.100,commander.1.3.4.30.100,hq.0.1.1.100.0,hq.1.3.3.100.0',
    {}
)

MAP_OFFGROOVE = (
  15, 20,
  'grass',
  'rIFpppppppppppppMMMMrIppppFpprrppprrrrMMrbrrFpppprppMpfppprrIIFppppprrppppfFpppFppFMprrrpppFppFMpppFpppFpppfFpppppMMppppFMpppFppppfffrrMFFppFMFpprrpMppMprrppFMFppFFMrrfffppppFpppMFppppMMpppppFfpppFpppFpppMFppFppprrrpMFppFpppFfpppprrpppppFIIrrpppfpMpprppppFrrbrMMrrrrppprrppFppppIrMMMMpppppppppppppFIr',
  'p_0-200g,p_1-100g',
  'barracks.0.17.4.100.0,barracks.0.19.14.100.0,barracks.1.0.0.100.0,barracks.1.2.10.100.0,city.-1.0.4.100.0,city.-1.10.13.100.0,city.-1.10.4.100.0,city.-1.13.12.100.0,city.-1.13.2.100.0,city.-1.13.5.100.0,city.-1.13.8.100.0,city.-1.16.14.100.0,city.-1.16.7.100.0,city.-1.17.1.100.0,city.-1.19.10.100.0,city.-1.2.13.100.0,city.-1.3.0.100.0,city.-1.3.7.100.0,city.-1.6.12.100.0,city.-1.6.2.100.0,city.-1.6.6.100.0,city.-1.6.9.100.0,city.-1.9.1.100.0,city.-1.9.10.100.0,commander.0.16.5.15.0,commander.1.3.9.10.0,hq.0.15.10.100.0,hq.1.4.4.100.0,soldier.1.3.10.100.0,tower.-1.0.9.100.0,tower.-1.19.5.100.0',
  {}
)

MAP_STRAINING_FRONTIER_1_2  = (
  20, 20,
  'grass',
  'MppFFMpFIpppFpMFpppMMMFpFpFpIIpFpprrppfMMppfffpppbpppprppppFFFpfprrMpprpFFppFppppppfffppFrpppMpppppppFrppppprrFpppFppFprFppFppFrrppFprpprrrrFpFppFrrfpppfppppppFIIFprprpFprpppFppppppMFpFrrppebpFMrpFpFppFpFprMFpbepprrFpFMppppppFppprpFprprpFIIFppppppfpppfrrFppFpFrrrrpprpFpprrFppFppFrpFppFpppFrrppppprFpppppppMppprFppfffppppppFppFFprppMrrpfpFFFpppprppppbpppfffppMMfpprrppFpIIpFpFpFMMMpppFMpFpppIFpMFFppM',
  'p_0-300g,p_1-100g',
  'barracks.0.13.19.100.0,barracks.0.18.12.100.0,barracks.1.1.7.100.0,barracks.1.6.0.100.0,city.-1.0.15.100.0,city.-1.1.19.100.0,city.-1.10.7.100.0,city.-1.11.0.100.0,city.-1.12.14.100.0,city.-1.13.10.100.0,city.-1.13.5.100.0,city.-1.15.16.100.0,city.-1.15.2.100.0,city.-1.16.7.100.0,city.-1.18.0.100.0,city.-1.19.4.100.0,city.-1.3.12.100.0,city.-1.4.17.100.0,city.-1.4.3.100.0,city.-1.6.14.100.0,city.-1.6.9.100.0,city.-1.7.5.100.0,city.-1.8.19.100.0,city.-1.9.12.100.0,city.0.1.0.20.0,city.1.18.19.10.0,commander.0.9.16.15.0,commander.1.10.3.20.0,hideout.-1.1.2.100.0,hideout.-1.18.17.100.0,hq.0.10.16.100.0,hq.1.9.3.100.0,soldier.1.2.7.100.0,tower.-1.0.4.100.0,tower.-1.19.15.100.0',
  {}
)

MAPS = [
    MAP_PLAYGROUND,
    #MAP_OFFGROOVE,
    #MAP_STRAINING_FRONTIER_1_2
]

MAX_MAP_SIZE = 30 # 96

TERRAIN_ABBR = {
    'F': 'forest',
    "I": 'river',
    "M": 'mountain',
    "R": 'reef',
    "W": 'wall',
    "b": 'bridge',
    "o": 'ocean',
    "e": 'beach',
    "f": 'cobblestone',
    "c": 'cobblestone',
    "p": 'plains',
    "r": 'road',
    "s": 'sea'
}

TERRAIN_LIST = [
    'forest',
    'river',
    'mountain',
    'reef',
    'wall',
    'bridge',
    'ocean',
    'beach',
    'cobblestone',
    'plains',
    'road',
    'sea'
]

WG_SYMBOLS = {
    'forest': '🌲',
    'river': '💧',
    'mountain': '⛰',
    'reef': '𔔉',
    'wall': '■',
    'bridge': '⬜', # '▒',
    'ocean': '〰',
    'beach': '🏖',
    'cobblestone': '▓',
    'plains': '🟩',
    'road': '🟨', #'░',
    'sea':  '〜', #'🌊'

    'red': '🔴',
    'blue': '🔵',
    'green': '🟢',
    'yellow': '🟡',
    'neutral': '⬤',

    'city': '🏠',
    'hq': '🏰',
    'tower': '🗼',
    'barracks': '🏚',
    'hideout': '⛺'

}

VERBS_BY_CLASS = {}

for classDef in DEFS['unitClasses'].values():
    verbs = list()

    if classDef.get('moveRange', 0) > 0:
        verbs.append('wait')
        
    if 'defaultAttack' in classDef:
        verbs.append(classDef['defaultAttack'])
    elif  classDef.get('canAttack', True) and len(classDef.get('weapons', [])) > 0:
        verbs.append('attack')
        
    if 'grooveId' in classDef:
        groove = DEFS['grooves'][classDef['grooveId']]
        verbs.append(groove['verb'])
        
    verbs = verbs + classDef.get('verbs', []) # + ['cancel']
    #if unit['pos']['x'] != self.endPos['x'] or unit['pos']['y'] != self.endPos['y']:
    #    verbs.append('wait')

    VERBS_BY_CLASS[classDef['id']] = verbs


PLAYABLE_COMMANDERS = filter(lambda c: c.get('playable', True), DEFS['commanders'].values())
PLAYABLE_COMMANDERS = list(map(lambda c: c['id'], PLAYABLE_COMMANDERS))
PLAYABLE_COMMANDERS.sort()

BANNED_COMMANDERS = []

AVAILABLE_UNIT_CLASSES = list(map(lambda c: c['id'], DEFS['unitClasses'].values()))
AVAILABLE_UNIT_CLASSES.sort()

RECRUITABLE_UNIT_CLASSES = filter(lambda c: not c.get('isStructure', False) and not c.get('isCommander', False) and c.get('isRecruitable', True), DEFS['unitClasses'].values())
RECRUITABLE_UNIT_CLASSES = list(map(lambda c: c['id'], RECRUITABLE_UNIT_CLASSES))
RECRUITABLE_UNIT_CLASSES.sort()


AVAILABLE_VERBS = list(map(lambda c: c['id'], DEFS['verbs'].values()))
AVAILABLE_VERBS.sort()

MAX_PLAYERS = 4
MAX_UNITS = 200

MOVE_TYPES = {}
for uc in DEFS['unitClasses'].values():
    MOVE_TYPES[uc.get('movement', '')] = True
MOVE_TYPES = list(MOVE_TYPES.keys())
MOVE_TYPES.sort()

PLAYERID_LIST = [-1, -2, 0, 1, 2, 3]

ACTIONS = ['entry', 'end_turn', 'resign']