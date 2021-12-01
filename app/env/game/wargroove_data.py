import os, json
import numpy as np

_dir_path = os.path.dirname(os.path.realpath(__file__))
_defs_filename = _dir_path + '/wg_2.0.json'

with open(_defs_filename) as def_file:
    DEFS = json.loads(def_file.read())

_triggers_filename = _dir_path + '/wg_triggers.json'
with open(_triggers_filename) as triggers_files:
    TRIGGERS = json.loads(triggers_files.read())

WG_LUA_FOLDER = _dir_path + '/lua'

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

def get_map_names(n_players = 2):
    p_dir = f'maps/{n_players}p/'
    path = f'{_dir_path}/{p_dir}'
    return [(file) for file in os.listdir(path) if file.endswith('.json')]

def load_map(name, n_players = 2):
    p_dir = f'maps/{n_players}p/'
    path = f'{_dir_path}/{p_dir}/{name}'
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

AVAILABLE_COMMANDERS = [c['id'] for c in DEFS['commanders'].values() if c.get('playable', True)]
AVAILABLE_COMMANDERS.sort()

AVAILABLE_UNIT_CLASSES = [c['id'] for c in DEFS['unitClasses'].values()]
AVAILABLE_UNIT_CLASSES.sort()

RECRUITABLE_UNIT_CLASSES = [
    c['id'] for c in DEFS['unitClasses'].values()
    if not c.get('isStructure', False) and not c.get('isCommander', False) and c.get('isRecruitable', True)
]
RECRUITABLE_UNIT_CLASSES.sort()


AVAILABLE_VERBS = [c['id'] for c in DEFS['verbs'].values()]
AVAILABLE_VERBS.sort()

VERBS_BY_CLASS = {}
RECRUITS_BY_CLASS = {}

for class_def in DEFS['unitClasses'].values():
    # check class verbs
    verbs = list()

    if class_def.get('moveRange', 0) > 0:
        verbs.append('wait')
    
    if class_def.get('canBeReinforced', True):
        verbs.append('reinforce')
        
    if 'defaultAttack' in class_def:
        verbs.append(class_def['defaultAttack'])
    elif  class_def.get('canAttack', True) and len(class_def.get('weapons', [])) > 0:
        verbs.append('attack')
        
    if 'grooveId' in class_def:
        groove = DEFS['grooves'][class_def['grooveId']]
        groove_verb = groove['verb']
        if not isinstance(groove_verb, list): groove_verb = [groove_verb]
        verbs = verbs + groove_verb
        
    verbs = verbs + class_def.get('verbs', []) # + ['cancel']

    VERBS_BY_CLASS[class_def['id']] = verbs

    # check class recruits
    recruit_tags = class_def.get('recruitTags', None)
    if not recruit_tags: continue
    recruits = [
        uc['id'] for uc in DEFS['unitClasses'].values()
        if (
            uc['id'] in RECRUITABLE_UNIT_CLASSES and
            any(tag in uc['tags'] for tag in recruit_tags)
        )
    ]

    RECRUITS_BY_CLASS[class_def['id']] = recruits

MOVE_TYPES = {}
for uc in DEFS['unitClasses'].values():
    MOVE_TYPES[uc.get('movement', '')] = True
MOVE_TYPES = list(MOVE_TYPES.keys())
MOVE_TYPES.sort()

PLAYERID_LIST = [-1, -2, 0, 1, 2, 3]

ACTIONS = ['entry', 'end_turn', 'resign']