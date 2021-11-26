import os, json
from enum import Enum
import numpy as np

dir_path = os.path.dirname(os.path.realpath(__file__))
DEFS_FILENAME = dir_path + '/wg_2.0.json'

with open(DEFS_FILENAME) as def_file:
    DEFS = json.loads(def_file.read())

TRIGGERS_FILENAME = dir_path + '/wg_triggers.json'
with open(TRIGGERS_FILENAME) as triggers_files:
    TRIGGERS = json.loads(triggers_files.read())

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

def getMapNames(n_players = 2):
    p_dir = f'maps/{n_players}p/'
    path = f'{dir_path}/{p_dir}'
    return [(file) for file in os.listdir(path) if file.endswith('.json')]

def loadMap(name, n_players = 2):
    p_dir = f'maps/{n_players}p/'
    path = f'{dir_path}/{p_dir}/{name}'
    with open(path) as map_file:
        map_data = json.loads(map_file.read())
    
    tiles = map_data['tiles']
    tiles = [TERRAIN_ABBR.get(t, 'plains') for t in tiles]
    tiles = np.array(tiles).reshape(map_data['h'], map_data['w'])
    map_data['tiles'] = tiles
    
    return map_data

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

    VERBS_BY_CLASS[classDef['id']] = verbs


PLAYABLE_COMMANDERS = [c['id'] for c in DEFS['commanders'].values() if c.get('playable', True)]
PLAYABLE_COMMANDERS.sort()

BANNED_COMMANDERS = []

AVAILABLE_UNIT_CLASSES = [c['id'] for c in DEFS['unitClasses'].values()]
AVAILABLE_UNIT_CLASSES.sort()

RECRUITABLE_UNIT_CLASSES = [
    c['id'] for c in DEFS['unitClasses'].values()
    if not c.get('isStructure', False) and not c.get('isCommander', False) and c.get('isRecruitable', True)
]
RECRUITABLE_UNIT_CLASSES.sort()


AVAILABLE_VERBS = [c['id'] for c in DEFS['verbs'].values()]
AVAILABLE_VERBS.sort()

MOVE_TYPES = {}
for uc in DEFS['unitClasses'].values():
    MOVE_TYPES[uc.get('movement', '')] = True
MOVE_TYPES = list(MOVE_TYPES.keys())
MOVE_TYPES.sort()

PLAYERID_LIST = [-1, -2, 0, 1, 2, 3]

ACTIONS = ['entry', 'end_turn', 'resign']

MAX_PLAYERS = 4
MAX_UNITS = 200
MAX_MAP_SIZE = 30 # 96