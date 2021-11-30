import os, re, random, json, copy
import lupa
import numpy as np
from xxhash import xxh32_intdigest
from enum import Enum

import gc

from .path_finder import WargroovePathFinder
from .wargroove_data import *

max_uint32 = np.iinfo(np.uint32).max

def safe_list_get (l, idx, default=None):
  try: return l[idx]
  except IndexError: return default

class Phase(Enum):
    commander_selection = 0
    action_selection = 1,
    entry_selection = 2

class EntryStep(Enum):
    unit_selection = 0
    end_position_selection = 1
    verb_selection = 2
    recruit_selection = 3
    target_selection = 4
    pre_execute = 5
    pre_execute_continue = 6
    execute = 7
    #execute_continue = 8

class PreExecuteSel(Enum):
    target_selection = 0
    recruit_selection = 1
    unload_selection = 2


ENTRY_STEP_SELECTIONS = [
    EntryStep.unit_selection,
    EntryStep.end_position_selection,
    EntryStep.verb_selection,
    EntryStep.recruit_selection,
    EntryStep.target_selection
]

class WargrooveGame():
    def __init__(self):
        self.defs = DEFS
        self.lua = None

    def __del__(self):
        if self.lua: self.lua.eval('collectgarbage("collect")')
    
    def reset(
        self,
        n_players = 2,
        map_name=None,
        random_commanders=True,
        seed = None
    ):
        if seed == None: seed = np.random.randint(max_uint32, dtype=np.uint32)
        if not map_name:
            map_name = random.choice(get_map_names(n_players))

        self.n_players = n_players

        self.options = {
            'seed': seed,
            'auto_end_turn': False,
            'random_commanders': random_commanders
        }

        self.map = load_map(map_name, n_players)
        self.commanders = {}
        self.units = {}

        self.players = { i: Player(i, i, None, 0) for i in range(n_players) }

        self.phase = Phase.commander_selection
        self.selectables = None
        self.turn_number = 0
        self.player_id = 0
        self.reset_entry()
        self.continue_game()

    def start(self):
        self.api = WargrooveApi(game=self)
        self.load_lua()
        self.load_state()
        self.load_triggers()

        self.player_id = 0
        self.phase = Phase.action_selection
        self.selected_action = None

        self.api.ready = True
        self.path_finder = WargroovePathFinder(self)
        self.start_session()
        self.check_triggers('startOfMatch')
        self.next_turn(increment=False)
        self.selectables = None
        #self.continue_game()
    
    def reset_entry(self):
        self.entry_step = None
        self.pre_execute_selection = None
        self.pre_execute_steps = 0
        self.resumable_suspended = False
        
        self.selected_verb = None
        self.selected_recruit = None
        self.selected_unload = None
        #self.selectables = None
        #self.targets = None
        #self.end_turn = False
        
        self.selected_unit_id = None

        self.end_pos = None
        self.target_pos = None
        self.str_param = ""

        self.should_execute = True
        self.combat_params = None
        self.capture_params = None

    def load_state(self):
        gold = self.map.get('gold', [])
        teams = self.map.get('teams', [])

        self.players = {}
        for player_id in range(self.n_players):
            commander = self.commanders.get(player_id, random.choice(PLAYABLE_COMMANDERS))
            g = safe_list_get(gold, player_id, 0)
            team = safe_list_get(teams, player_id)
            player = Player(player_id, team, commander, g)
            self.players[player_id] = player


        self.units = {}
        for u in self.map.get('units', []):
            unit_class_id = u.get('class', None)
            player_id = u.get('player', -1)
            health = u.get('health', 100)
            groove = u.get('groove', 0)
            x = u.get('x', -1)
            y = u.get('y', -1)

            if x < 0 or y < 0 or not unit_class_id: continue

            if player_id >= 0:
                player = self.players[player_id]
                if unit_class_id == 'commander':
                    unit_class_id = DEFS['commanders'][player.commander].get('unitClassId', 'commander_mercia')
            
            if not unit_class_id in DEFS['unitClasses']: continue

            recruits = self.get_class_recruitables(unit_class_id, recruits=u.get('recruits'), banned_recruits=u.get('banned_recruits', []))
            
            unit = self.make_unit(player_id, { 'x': x, 'y': y }, unit_class_id, False, recruits=recruits)
            unit['health'] = health
            unit['grooveCharge'] = groove
            self.units[unit['id']] = unit
    
    def load_triggers(self):
        n = len(self.players)
        triggers = copy.deepcopy(TRIGGERS)

        for trigger in triggers:
            trigger['players'] = [1 if i < n else 0 for i in range(8)]
        
        self.triggers = triggers

    def load_lua(self):
        os.chdir(dir_path + '/lua')
        self.lua = lupa.LuaRuntime(unpack_returned_tuples=False)

        self.lua.eval('collectgarbage("stop")')
        # The LuaRuntime of lupa 1.10 suffers from segfaults caused by double
        # deallocations when using corutines. A fix has been provided in a PR and
        # is currently waiting to be merged: https://github.com/scoder/lupa/pull/192
        # until this issue is fixed there is no other solution than to disabled
        # the lua garabage collector
        
        self.lua.globals()['wargrooveAPI'] = self.api
        self.lua_wargroove = self.lua.require('wargroove/wargroove')[0]
        self.lua_combat = self.lua.require('wargroove/combat')[0]
        self.lua_events = self.lua.require('wargroove/events')[0]

    def get_lua_verb(self, verb):
        script_name = DEFS['verbs'][verb]['scriptName']
        res = self.lua.require(script_name)
        return res[0] if isinstance(res, tuple) else res
    
    def lua_wrapper(self, val):
        if isinstance(val, list):
            val = [self.lua_wrapper(v) for v in val]
            return self.lua.table_from(val)
        if isinstance(val, dict):
            val = { k: self.lua_wrapper(v) for k, v in val.items() }
            return self.lua.table_from(val)
        
        return val
    
    def safe_facing_position(self, pos):
        pos['facing'] = pos.get('facing', 0)
        return pos
    
    def get_class_recruitables(self, unit_class_id, recruits=None, banned_recruits=[]):
        unit_class = DEFS['unitClasses'][unit_class_id]
        recruit_tags = unit_class.get('recruitTags', None)
        if not recruit_tags: return []

        return [
            uc['id'] for uc in DEFS['unitClasses'].values()
            if (
                uc.get('isRecruitable', True) and
                not uc.get('isCommander', False) and
                any(tag in uc['tags'] for tag in recruit_tags) and
                not uc['id'] in banned_recruits and
                (not recruits or uc['id'] in recruits)
            )
        ]
    
    def make_unit(self, player_id, pos, unit_type, turn_spent=True, starting_state = [], recruits=None):
        unit_class = DEFS['unitClasses'][unit_type]

        if not recruits: recruits = self.get_class_recruitables(unit_type)

        return {
            'id': self.get_next_unit_id(),
            'playerId': player_id,
            'pos': { 'x': pos['x'], 'y': pos['y'], 'facing': 0 },
            'startPos': { 'x': pos['x'], 'y': pos['y'], 'facing': 0 },
            'unitClassId': unit_type,
            'hadTurn': turn_spent,
            #'canBeAttacked': True,
            'damageTakenPercent': 100,
            'garrisonClassId': unit_class.get('garrisonUnit', ('garrison' if unit_class.get('isStructure', False) else '')),
            'health': 100,
            'grooveCharge': 0,
            'grooveId': unit_class.get('grooveId', ''),
            'killedByLosing': False,
            'inTransport': False,
            'loadedUnits': [],
            'recruits': recruits,
            'state': starting_state,
            'transportedBy': -1,
            'attackerId': -1,
            'attackerPlayerId': -1,
            'attackerUnitClass': '',
        }
    
    def unit_from_lua(self, unit):
        u = dict(unit)

        u.pop('unitClass')
        u.pop('setHealth')
        u.pop('setGroove')

        for key in ['pos', 'startPos']:
            u[key] = dict(u[key])
        for key in ['loadedUnits', 'recruits']:
            u[key] = list(u[key].values())
        
        u['state'] = [dict(s) for s in u['state']]

        return u
    
    def make_unit_class(self, unit_class_id):
        dfn = DEFS['unitClasses'][unit_class_id]
        groove_id = dfn.get('grooveId')
        groove_dfn = DEFS['grooves'].get(groove_id, { 'maxCharge': 0 })

        table_from = self.lua.table_from

        uc = {
            'id': dfn['id'],
            'cost': dfn.get('cost', 0),
            'tags': table_from(dfn['tags']),
            'canBeCaptured': dfn.get('canBeCaptured', False),
            'canReinforce': dfn.get('canReinforce', False),
            'inAir': 'type.air' in dfn['tags'],
            'isCommander': dfn.get('isCommander', False),
            'isStructure':  dfn.get('isStructure', False),
            'loadCapacity': dfn.get('loadCapacity', 0),
            'maxGroove': groove_dfn.get('maxCharge', 0),
            'maxHealth': 100,
            'moveRange': dfn.get('moveRange', 0),
            'passiveMultiplier': dfn.get('passiveMultiplier', 1),
            'transportTags':  table_from(dfn.get('transportTags', [])),
            'weaponIds': table_from([w['id'] for w in dfn.get('weapons', [])])
        }

        return table_from(uc)
    
    def make_weapon(self, weapon_id):
        dfn = DEFS['weapons'][weapon_id]

        table_from = self.lua.table_from

        w = {
            'id': dfn['id'],
            'canMoveAndAttack': dfn.get('canMoveAndAttack', False),
            'horizontalAndVerticalOnly': dfn.get('horizontalAndVerticalOnly', False),
            'horizontalAndVerticalExtraWidth': dfn.get('horizontalAndVerticalExtraWidth', 0),
            'terrainExclusion': table_from(dfn.get('terrainExclusion', [])),
            'directionality': dfn.get('directionality', 'omni'),
            'maxRange': dfn.get('rangeMax', 1),
            'minRange': dfn.get('rangeMin', 1)
        }

        return table_from(w)

    def get_next_unit_id(self):
        i = 1
        while(i in self.units): i += 1
        return i
    
    def next_turn(self, increment=True, increment_gold=True):
        old_pid = None

        if increment:
            self.check_triggers('endOfTurn')

            while(True):
                old_pid = self.player_id
                self.player_id = (self.player_id + 1) % len(self.players)
                if self.player_id == 0: self.turn_number += 1        
                if not self.players[self.player_id].has_losed: break
        
        player = self.players[self.player_id]
        
        if increment_gold: player.gold  += player.income
        
        for unit in self.units.values():
            pid = unit['playerId']
            unit_class = DEFS['unitClasses'][unit['unitClassId']]

            unit['hadTurn'] = False

            if pid == old_pid and unit['grooveId'] != '':
                groove = DEFS['grooves'][unit['grooveId']]
                unit['grooveCharge'] += groove['chargeBy']['endOfTurn']
                if unit['grooveCharge'] > groove['maxCharge']:
                    unit['grooveCharge'] = groove['maxCharge']
                
            if pid == self.player_id:
                if 'regeneration' in unit_class:
                    unit['health'] += unit_class['regeneration']
                    if unit['health'] > 100: unit['health'] = 100
            
        # TODO: check deaths
        # apply buffs

        self.lua_wargroove.setTurnInfo(self.turn_number, self.player_id)
        self.check_triggers('startOfTurn')
    
    def can_execute_verb(self, verb_id):
        verb = DEFS['verbs'][verb_id]
        lua_verb = self.get_lua_verb(verb_id)

        unit_id = self.selected_unit_id
        end_pos = self.safe_facing_position(self.end_pos)
        str_param = self.str_param

        targets = []

        if verb.get('targetted') == True:
            targets = self.get_targets(lua_verb=lua_verb)
            if len(targets) == 0: return False

        #self.targets[verbId] = targets

        if (
            verb.get('hasResourceCost', False) and
            lua_verb.getCostAtEntry(lua_verb, unit_id, end_pos, None) > self.players[self.player_id].gold
        ): return False

        return lua_verb.canExecuteEntry(lua_verb, unit_id, end_pos, None, str_param)
    
    def get_executable_verbs(self, unit_id=None):
        if unit_id == None:
            unit_id = self.selected_unit_id
        unit = self.units[unit_id]
        verbs = VERBS_BY_CLASS[unit['unitClassId']]
        #self.targets = {}
        verbs = [verb_id for verb_id in verbs if self.can_execute_verb(verb_id)]
        return verbs

    def get_move_area(self, unit_id=None):
        if unit_id == None:
            unit_id = self.selected_unit_id
        if unit_id == None or not unit_id in self.units: return []
        return self.path_finder.set_unit_id(unit_id).get_area()
    
    def can_unit_act(self, unit_id):
        u = self.units[unit_id]
        unit_class_id = u['unitClassId']
        unit_class = DEFS['unitClasses'][unit_class_id]
        verbs = VERBS_BY_CLASS[unit_class_id]
        return (
            u['playerId'] == self.player_id and
            u['hadTurn'] == False and
            u['inTransport'] == False and
            len(verbs) > 0 and
            unit_class.get('hasTurn', True)
        )
    
    def get_selectable_units(self):
        return [u for u in self.units.values() if self.can_unit_act(u['id'])]
    
    def get_recruitables(self, recruits = None, cost_multiplier = 1):
        if not recruits:
            builder = self.units[self.selected_unit_id]
            recruits = builder['recruits']

        gold = self.players[self.player_id].gold
        recruits = [id for id in recruits if DEFS['unitClasses'][id].get('cost', 0) * cost_multiplier <= gold]
        return recruits
    
    def get_unloadables(self, used_units=[]):
        loaded_units = self.units[self.selected_unit_id]['loadedUnits']
        unloadables = [id for id in loaded_units if not id in used_units]
        return unloadables + (['wait'] if len(used_units) else [])

    def get_targets(self, lua_verb = None):
        if not lua_verb:
            lua_verb = self.get_lua_verb(self.selected_verb)

        unit_id = self.selected_unit_id
        unit = self.units[unit_id]
        start_pos = self.safe_facing_position(unit['pos'])
        end_pos = self.safe_facing_position(self.end_pos)
        str_param = self.str_param
        
        
        if self.end_pos:
            targets = lua_verb.getTargetsEntry(lua_verb, unit_id, end_pos, str_param)
        else:
            area = self.lua.table_from(self.get_move_area(unit_id))
            targets = lua_verb.getTargetsInRangeEntry(lua_verb, unit_id, start_pos, area, str_param)
        
        targets = [dict(t) for t in targets.values() if t['x'] >= 0 and t['y'] >= 0]
        return targets
    
    def get_selectables(self):
        ph = {
            Phase.commander_selection: lambda: list(PLAYABLE_COMMANDERS) if not self.options.get('random_commanders') else [random.choice(PLAYABLE_COMMANDERS)],
            Phase.action_selection: lambda: ['entry', 'end_turn']
        }

        if self.phase in ph:
            return ph[self.phase]()

        es = {
            EntryStep.unit_selection: lambda: [u['id'] for u in self.get_selectable_units()],
            EntryStep.end_position_selection: self.get_move_area,
            EntryStep.verb_selection: self.get_executable_verbs,
            EntryStep.recruit_selection: self.get_recruitables,
            EntryStep.target_selection: self.get_targets,
        }

        if self.entry_step in es:
            return es[self.entry_step]()

        pes = {
            PreExecuteSel.target_selection: self.get_targets,
            PreExecuteSel.recruit_selection: self.get_recruitables,
            PreExecuteSel.unload_selection: self.get_unloadables
        }
        
        #if self.pre_execute_selection in pes:
        #    return pes[self.pre_execute_selection]()
    
    def select(self, index):
        if self.selectables == None: return False

        selected = self.selectables[index]
        self.selectables = None

        print('selected: {}'.format(selected))

        ph = {
            Phase.commander_selection: lambda: self.commanders.update({ self.player_id: selected }),
            Phase.action_selection: lambda: setattr(self, 'selected_action', selected)
        }

        if self.phase in ph:
            ph[self.phase]()
            return True

        es = {
            EntryStep.unit_selection: lambda: setattr(self, 'selected_unit_id', selected),
            EntryStep.end_position_selection: lambda: setattr(self, 'end_pos', selected),
            EntryStep.verb_selection: lambda: setattr(self, 'selected_verb', selected),
            EntryStep.target_selection: lambda: setattr(self, 'target_pos', selected),
            EntryStep.recruit_selection: lambda: setattr(self, 'str_param', selected)
        }

        if self.entry_step in es:
            es[self.entry_step]()
            return True

        pes = {
            PreExecuteSel.target_selection: lambda: setattr(self, 'target_pos', selected),
            PreExecuteSel.recruit_selection: lambda: setattr(self, 'selected_recruit', selected),
            PreExecuteSel.unload_selection: lambda: setattr(self, 'selected_unload', selected)
        }
        
        if self.pre_execute_selection in pes:
            pes[self.pre_execute_selection]()
            return True

        return False
    
    def do_action(self, action):
        if action == 'entry':
            self.phase = Phase.entry_selection
            self.entry_step = EntryStep.unit_selection

        elif action == 'end_turn':
            self.next_turn()

        elif action == 'resign':
            self.api.eliminate(self.player_id)
            self.next_turn()

    def pre_execute(self):
        verb_id = self.selected_verb
        #verb = DEFS['verbs'][verb_id]
        lua_verb = self.get_lua_verb(verb_id)

        self.resumable_suspended = lua_verb.preExecuteEntry(lua_verb, self.selected_unit_id, self.target_pos, self.str_param, self.end_pos)
    
    def continue_pre_execute(self):
        while self.resumable_suspended and self.pre_execute_selection == None:
            self.run_resumable() 

    def finish_verb_pre_execute(self, should_execute, str_param):
        self.should_execute = bool(should_execute)
        self.str_param = str(str_param or '')

    def execute(self):
        verb_id = self.selected_verb
        lua_verb = self.get_lua_verb(verb_id)

        path = self.path_finder.get_path(self.end_pos['y'], self.end_pos['x'])
        
        target_pos = self.safe_facing_position(self.target_pos or self.end_pos)
    
        print('executing', self.selected_unit_id, self.target_pos, f"'{self.str_param}'", path)
        path = self.lua.table_from(path)
        self.resumable_suspended = lua_verb.executeEntry(lua_verb, self.selected_unit_id, target_pos, self.str_param, path)
        while self.resumable_suspended:
            self.run_resumable()
        
        if self.combat_params:
            self.execute_combat()
        
        if self.capture_params:
            self.execute_capture()
        
        self.check_triggers('endOfUnitTurn')
    
    def run_resumable(self):
        #print('resumable')
        self.resumable_suspended = self.lua_wargroove.resumeExecution(0.1)
        return self.resumable_suspended
    
    def execute_death_verb(self, unitId, killed_by_id):
        unit = self.units[unitId]
        death_verb_id =  DEFS['unitClasses'][unit['unitClassId']].get('deathVerbId')
        if not death_verb_id: return

        lua_verb = self.get_lua_verb(death_verb_id)
        self.resumable_suspended = lua_verb.executeEntry(lua_verb, unitId, unit['pos'], str(killed_by_id), self.lua.table_from([]))
        while self.resumable_suspended:
            self.run_resumable()
    
    def execute_combat(self):
        (attacker_id, defender_id, path) = self.combat_params

        attacker = self.units[attacker_id]
        defender = self.units[defender_id]

        #self.safe_facing_position(attacker['pos'])
        #self.safe_facing_position(defender['pos'])

        solve_type = 'random' if self.api.isRNGEnabled() else ''
        results = self.lua_combat.solveCombat(self.lua_combat, attacker_id, defender_id, self.lua_wrapper(path), solve_type)

        print('combat results', dict(results))

        self.lua_wargroove.doPostCombat(self.lua_wargroove, attacker_id, True)
        self.lua_wargroove.doPostCombat(self.lua_wargroove, defender_id, False)


        self.set_health(attacker_id, results['attackerHealth'], defender_id)
        self.set_health(defender_id,  results['defenderHealth'], attacker_id)

        self.set_post_combat_groove(attacker, True, results.attackerAttacked, defender['health'] < 1)
        self.set_post_combat_groove(defender, False, results.defenderAttacked, attacker['health'] < 1)
    
    def execute_capture(self):
        (attacker_id, defender_id, attackerPos) = self.capture_params

        attacker = self.units[attacker_id]
        defender = self.units[defender_id]
        pid = attacker['playerId']
        defender['playerId'] = pid
        health = max(1, int(attacker['health'] / 2))
        self.set_health(defender_id, health, -1)
        defender['hadTurn'] = True

        self.players[pid].income += DEFS['unitClasses'][defender['unitClassId']].get('income', 0)
    
    def set_health(self, unit_id, health, attacker_id):
        unit = self.units[unit_id]
        unit['health'] = health
        unit['attackerId'] = attacker_id

        if attacker_id >= 0:
            attacker = self.units[attacker_id]
            unit['attackerUnitClass'] = attacker['unitClassId']
            unit['attackerPlayerId'] = attacker['playerId']
    
    def death_check_loop(self):
        units_to_remove = {}

        ids = [id for id in self.units.keys()]

        new_removal = True
        while new_removal:
            new_removal = False
            for unit_id in ids:
                if unit_id in units_to_remove: continue
                if self.death_check(unit_id):
                    units_to_remove[unit_id] = True
                    new_removal = True
        
        for id in units_to_remove.keys():
            self.units.pop(id)

    def death_check(self, unit_id):
        if not unit_id in self.units: return False
        unit = self.units[unit_id]
        if unit['health'] >= 1: return False

        unit_class = DEFS['unitClasses'][unit['unitClassId']]
        if unit_class.get('isNeutraliseable', False):
            unit['health'] = 100
            unit['playerId'] = -1

        attacker_id = unit['attackerId']
        if unit['health'] < 1: self.execute_death_verb(unit_id, attacker_id)

        self.lua_wargroove.reportUnitDeath(unit_id, attacker_id, unit['attackerPlayerId'], unit['attackerUnitClass'])

        for loaded_unit_id in unit['loadedUnits']:
            self.set_health(loaded_unit_id, 0, attacker_id)
            #self.death_check(loaded_unit_id)

        return unit['health'] < 1
    
    def set_post_combat_groove(self, unit, isAttacker, hasAttacked, hasKilled):
        if unit['health'] < 1 or not hasAttacked: return
        groove_id = unit['grooveId']
        if groove_id == '': return
        
        groove = DEFS['grooves'][groove_id]

        if isAttacker: increment = 'kill' if hasKilled else 'attack'
        else: increment = 'counter'
        
        charge = unit['grooveCharge'] + groove['chargeBy'][increment]
        unit['grooveCharge'] =  int( max(0, min(charge, groove['maxCharge'])))
    
    def start_session(self):
        match_state = self.lua_wrapper({
            'mapFlags': [],
            'mapCounters': [],
            'campaignFlags': [],
            'triggersFired': [],
            'party': [],
            'campaignCutscenes': [],
            'creditsToPlay': None
        })
        self.lua_events.startSession(match_state)

    def check_triggers(self, state):
        self.death_check_loop()

        self.resumable_suspended = self.lua_wargroove.checkTriggers(state)
        while self.resumable_suspended:
            self.run_resumable()
        #match_state = self.lua_events.getMatchState()

    def auto_select(self):
        if self.selectables == None: return None
        n = len(self.selectables)
        if n != 1: return None

        if not (
            self.phase == Phase.commander_selection or
            self.entry_step == EntryStep.end_position_selection or
            (self.entry_step == EntryStep.verb_selection and self.selectables[0] == 'recruit')
        ): return None

        return 0
    
    def continue_game(self, selection=None):
        while True:
            if selection == None:
                selection = self.auto_select()

            if self.selectables != None and selection == None:
                #print(self.selectables)
                return

            if selection == 'cancel':
                if self.pre_execute_selection:
                    self.pre_execute_selection = None
                else:
                    self.reset_entry()
                    self.phase = Phase.action_selection

            elif selection != None:
                self.select(selection)
                self.continue_game_after_select()
            
            selection = None
        
            self.print_state()
        
            if self.phase in [Phase.commander_selection, Phase.action_selection]:
                self.selectables = self.get_selectables()
                continue

            if self.phase == Phase.entry_selection:
                if self.entry_step in ENTRY_STEP_SELECTIONS:
                    if not self.selectables:
                        self.selectables = self.get_selectables()
                        continue                    
                
                if self.entry_step == EntryStep.pre_execute:
                    self.pre_execute()
                    self.entry_step = EntryStep.pre_execute_continue

                if self.entry_step == EntryStep.pre_execute_continue:
                    self.continue_pre_execute()
                    if self.resumable_suspended: continue
                    self.entry_step = EntryStep.execute
            
                if self.entry_step == EntryStep.execute:
                    if self.should_execute:
                        self.execute()

                    self.reset_entry()
                    self.phase = Phase.action_selection
                    self.selected_action = None
                    self.selectables = self.get_selectables()
                    continue
    
    def continue_game_after_select(self):
        if self.phase == Phase.commander_selection:
            self.player_id += 1
            if self.player_id < self.n_players: return

            self.start()
            return
        
        if self.phase == Phase.action_selection:
            self.do_action(self.selected_action)
            return

        if self.entry_step == EntryStep.unit_selection:
            self.entry_step = EntryStep.end_position_selection
            return
        
        if self.entry_step == EntryStep.end_position_selection:
            self.entry_step = EntryStep.verb_selection
            return
        
        verb = DEFS['verbs'][self.selected_verb]
        
        if self.entry_step == EntryStep.verb_selection:
            self.entry_step = EntryStep.recruit_selection
            if self.selected_verb == 'recruit': return

        if self.entry_step == EntryStep.recruit_selection:
            self.entry_step = EntryStep.target_selection
            if verb.get('targetted') == True: return


        if self.entry_step == EntryStep.target_selection:
            self.entry_step = EntryStep.pre_execute if verb.get('preExecute', False) else EntryStep.execute
            return
        
        if self.pre_execute_selection != None:
            self.pre_execute_selection = None
            #self.entryStep = EntryStep.pre_execute_continue
            return

    def print_state(self):
        print('## {}, {}, {} ##'.format(self.phase, self.entry_step, self.pre_execute_selection))

    def get_unit_tables(self):
        tables = [[] for i in range(len(self.players))]

        for u in self.units.values():
            pid = u['playerId']
            if pid < 0 or u.get('garrisonClassId', '') != '': continue

            tables[pid].append({
                'pid': pid,
                'id': u['id'],
                'turn': 'X' if u['hadTurn'] else '',
                'type': u['unitClassId'],
                'hp': u['health'],
                'groove': u['grooveCharge'],
                'pos': u['pos']
            })
        
        return tables
    
    def get_board_table(self):
        m = self.map
        board = [ [ WG_SYMBOLS.get(cell, ' ') for cell in row ] for row in m['tiles']]

        COLORS = { 0: WG_SYMBOLS['red'], 1: WG_SYMBOLS['blue'], 2: WG_SYMBOLS['green'], 3: WG_SYMBOLS['yellow'], -1: WG_SYMBOLS['neutral'], -2: WG_SYMBOLS['neutral'] }

        for u in self.units.values():
            x = u['pos']['x']
            y = u['pos']['y']
            if x < 0 or y < 0: continue

            pid = u['playerId']
            ucid = u['unitClassId']
            ucid = ucid[ucid.startswith('commander_') and len('commander_'):]

            board[y][x] += f"\n{WG_SYMBOLS.get(ucid, ucid)}\n{COLORS[pid]} {u['health']}"


        return board


class Player():
    def __init__(self, id, team, commander, gold=100, basic_income=0):
        self.id = id
        self.team = team
        self.gold = gold
        self.income = basic_income
        self.is_victorious = False
        self.is_local = True
        self.is_human = False
        self.commander = commander
        self.has_losed = False

class WargrooveApi():
    def __init__(self, game: WargrooveGame):
        self.game = game
        self.ready = False

    def isApiReady(self):
        return self.ready
    
    def getWeapon(self, id, unitClassId=None):
        return self.game.make_weapon(id)
    
    def getUnitClass(self, id):
        return self.game.make_unit_class(id)
    
    def getAllUnits(self):
        return self.game.lua.table_from(self.game.units.keys())
    
    def getUnitById(self, id):
        if not id in self.game.units: return None
        unit = self.game.units[id]
        if unit:
            self.game.safe_facing_position(unit['pos'])
            self.game.safe_facing_position(unit['startPos'])
        return self.game.lua_wrapper(unit)
    
    def getUnitIdAt(self, x, y):
        return next((u['id'] for u in self.game.units.values() if u['pos']['x'] == x and u['pos']['y'] == y), -1)
        
    def getAllGizmos(self): return {}

    def getGizmoState(self, pos):
        return None
    
    def setGizmoState(self, pos, state):
        return None
    
    def getGizmoAt(self, pos):
        return None
    
    def getPlayerTeam(self, playerId):
        p =  self.game.players.get(playerId, None)
        if p: return p.team
        return -1

    def getPlayerChildOf(self, playerId):
        return None

    def setPlayerTeam(self, playerId, teamId):
        self.game.players[playerId].team = teamId

    def startCombat(self, attackerId, defenderId, path):
        path = [{ 'x': p['x'], 'y': p['y'] } for p in path.values()]
        self.game.combat_params = (attackerId, defenderId, path)

    def startCapture(self, attackerId, defenderId, attackerPos):
        self.game.capture_params = (attackerId, defenderId, attackerPos)

    def spawnUnit(self, playerId, pos, unitType, turnSpent, startAnimation, startingState, factionOverride):
        unit = self.game.make_unit(playerId, pos, unitType, turnSpent, startingState)
        id = unit['id']
        self.game.units[id] = unit
        return id

    def updateUnit(self, unit):
        u = self.game.unit_from_lua(unit)
        self.game.units[u['id']] = u

    def removeUnit(self, unitId):
        self.game.units.pop(unitId, None) # TODO: finish

    def doLuaDeathCheck(self, unitId):
        if not unitId in self.game.units: return
        if self.game.death_check(unitId):
            self.game.units.pop(unitId)

    def getMoney(self, playerId):
        return self.game.players[playerId].gold

    def setMoney(self, playerId, money):
        self.game.players[playerId].gold = money

    def canStandAt(self, unitClass, pos):
        uc = DEFS['unitClasses'][unitClass]
        return uc.get('movement','') in self.getTerrainMovementCostAt(pos)

    def hasCompatibleMovementType(self, unitClass, pos):
        return self.canStandAt(unitClass, pos)

    def isWater(self, pos):
        terrain = self.getTerrainNameAt(pos)
        return DEFS['terrains'][terrain]['movementGroupType'] == 'water'

    def getWeaponDamage(self, weaponId, targetClassId, targetPosX, targetPosY):
        weapon = DEFS['weapons'][weaponId]
        unit_class = DEFS['unitClasses'][targetClassId]
        tags = unit_class['tags']
        in_air = 'type.air' in tags
        terrain = 'sky' if in_air else self.getTerrainNameAt({ 'x': targetPosX, 'y': targetPosY })
        movement_group_type = DEFS['terrains'][terrain]['movementGroupType']

        tag_damages = weapon.get('tagDamage', {})
        tag_id = next(filter(lambda tag: tag in tags, tag_damages.keys()), None)

        base_damage = weapon.get('baseDamage', {}).get(movement_group_type, 0)
        tag_damage = tag_damages.get(tag_id, 0)

        return base_damage * tag_damage * unit_class.get('damageMultiplier', 1)

    def getWeaponDamageForceGround(self, weaponId, targetClassId, targetPosX, targetPosY):
        weapon = DEFS['weapons'][weaponId]
        tag_damage = weapon.get('tagDamage', {}).get(targetClassId, 0)
        return tag_damage

    def loadInTransport(self, transportId, unitId): return

    def unloadFromTransport(self, transportId, unitId, pos): return

    def getTerrainByName(self, name):
        terrain = DEFS['terrains'][name]
        terrain['defence'] = terrain['defenceBonus']
        return self.game.lua_wrapper(terrain)

    def getTerrainNameAt(self, pos):
        try: return self.game.map['tiles'][pos['y']][pos['x']]
        except IndexError: return 'wall'

    def getTerrainDefenceAt(self, pos):
        return self.getTerrainByName(self.getTerrainNameAt(pos))['defence']

    def isTerrainImpassableAt(self, pos):
        return len(self.getTerrainMovementCostAt(pos)) == 0

    def getTerrainMovementCostAt(self, pos):
        terrain = DEFS['terrains'][self.getTerrainNameAt(pos)]
        return self.game.lua.table_from(terrain['movementCost'])

    def getAllUnitsForPlayer(self, playerId, includeChildren):
        all_units_ids = [u['id'] for u in self.game.units.values() if u['playerId'] == playerId]
        return self.game.lua.table_from(all_units_ids)

    def getCurrentWeather(self):
        return None #self.game.weather # None

    def getGroove(self, grooveId):
        if not grooveId in DEFS['grooves']: return None
        return self.game.lua_wrapper(DEFS['grooves'][grooveId])

    def getMapTriggers(self):
        return self.game.lua_wrapper(self.game.triggers)

    def getLocationById(self, locationId): return

    def setMetaLocation(self, id, area): return

    def startCutscene(self, id): return

    def giveVictory(self, playerId):
        team = self.game.players[playerId].team
        for player in self.game.players.values():
            if player.team == team:
                player.is_victorious = True

    def eliminate(self, playerId):
        self.game.players[playerId].has_losed = True
        # TODO: kill everything decap structures

    def getNumberOfOpponents(self, playerId):
        team = self.game.players[playerId].team
        return sum([0 if p.team == team or p.has_losed else 1 for p in self.game.players.values()])

    def showMessage(self, string): return

    def showDialogueBox(self, expression, character, message, shout): return

    def getMapVariables(self, id): return {}

    def trackCameraTo(self, pos): return

    def isCameraTracking(self): return False
    
    def lockTrackCamera(self, unitId): return
    
    def unlockTrackCamera(self): return

    def spawnMapAnimation(self, pos, name, sequence, layer, offset, facing): return

    def spawnPaletteSwappedMapAnimation(self, pos, name, playerId, sequence, layer, offset): return

    def playUnitAnimation(self, unitId, sequence): return

    def playUnitAnimationOnce(self, unitId, sequence): return

    def playUnitDeathAnimation(self, unitId): return

    def isRNGEnabled(self): return True

    def pseudoRandomFromString(self, str):
        num = xxh32_intdigest(str, self.game.options['seed'])
        r = num * (1.0 / (max_uint32 + 1))
        return r

    def canPlayerSeeTile(self, player, tile): return True

    def canCurrentlySeeTile(self, tile): return True

    def canPlayerRecruit(self, player, unitClassId): return unitClassId in RECRUITABLE_UNIT_CLASSES

    def setAIProfile(self, player, profile): return

    def setWeather(self, weatherFrequency, daysAhead): return

    def setAIRestriction(self, unitId, restriction): return

    def forceAction(self, selectableUnitIds, endPositions, targetPositions, action, autoEnd, expression, commander, dialogue): return

    def forceOpenTutorial(self, tutorialId, selectableTargets, expression, commander, dialogue, mapFlag, mapFlagValue): return

    def queueForceAction(self, selectableUnitIds, endPositions, targetPositions, action, autoEnd, expression, commander, dialogue): return

    def queueForceOpenTutorial(self, tutorialId, selectableTargets, expression, commander, dialogue, mapFlag, mapFlagValue): return

    def addTutorial(self, tutorialId, selectableTargets, mapFlag, mapFlagValue): return
    
    def playMapSound(self, sound, pos): return

    def playPositionlessSound(self, sound): return

    def playCutsceneSFX(self, sound, pos): return

    def playPositionlessCutsceneSFX(self, sound): return

    def openRecruitMenu(self, player, recruitBaseId, recruitBasePos, unitClassId, units, costMultiplier, unbannableUnits, factionOverride):
        units = list(units.values())
        unbannableUnits = list(unbannableUnits.values())
        recruits = list(set(units + unbannableUnits))

        self.game.selected_recruit = None
        self.game.pre_execute_selection =  PreExecuteSel.recruit_selection
        self.game.selectables = self.game.get_recruitables(recruits = recruits, cost_multiplier = costMultiplier)

    def recruitMenuIsOpen(self): return self.game.pre_execute_selection == PreExecuteSel.recruit_selection

    def popRecruitedUnitClass(self): return self.game.selected_recruit

    def openUnloadMenu(self, usedUnits):
        self.game.selected_unload = None
        self.game.pre_execute_selection == PreExecuteSel.unload_selection
        self.game.selectables = self.game.get_unloadables(usedUnits)

    def unloadMenuIsOpen(self): return self.game.pre_execute_selection == PreExecuteSel.unload_selection

    def getUnloadedUnitId(self):
        return self.game.selected_unload if not self.game.selected_unload in ['cancel', 'wait', None] else -1

    def getUnloadVerb(self):
        return self.game.selected_unload if self.game.selected_unload in ['cancel', 'wait'] else ''

    def finishVerbPreExecute(self, shouldExecute, strParam):
        self.game.finish_verb_pre_execute(shouldExecute, strParam)

    def cancelVerbExecute(self):
        self.game.reset_entry()
        self.game.phase = Phase.action_selection

    def selectTarget(self):
        self.game.target_pos = None
        self.game.pre_execute_selection = PreExecuteSel.target_selection
        self.game.selectables = self.game.get_targets()

    def waitingForSelectedTarget(self): return self.game.pre_execute_selection == PreExecuteSel.target_selection

    def getSelectedTarget(self):
        target = self.game.target_pos
        if not target: return None
        return self.game.lua.table_from(target)

    def setSelectedTarget(self, targetPos):
        self.game.target_pos = dict(targetPos)

    def clearSelectedTarget(self):
        self.game.target_pos = None

    def displayTarget(self, targetPos): return

    def clearDisplayTargets(self): return

    def displayBuffVisualEffect(self, parentId, playerId, animation, startSequence, alpha, effectPositions, layer, offset, startSequenceIsLooping): return

    def displayBuffVisualEffectAtPosition(self, parentId, position, playerId, animation, startSequence, alpha, effectPositions, layer, offset, startSequenceIsLooping): return

    def clearBuffVisualEffect(self, parentId): return

    def setBuffVisualEffectsOwner(self, oldParentId, newParentId): return

    def playBuffVisualEffectSequence(self, unitId, position, animation, newSequence): return

    def playBuffVisualEffectSequenceOnce(self, unitId, position, animation, newSequence): return

    def getBestUnitToRecruit(self, fromUnits, unbannableUnits): return # TODO: implement

    def getAIUnitRecruitScore(self, unitClassId, position): return # TODO: implement

    def getAILocationScore(self, unitClassId, position): return # TODO: implement

    def getAIUnitValue(self, unitId, position): return # TODO: implement

    def getAICanLookAhead(self, unitId): return # TODO: implement

    def getAIUnitValueWithHealth(self, unitId, position, health): return # TODO: implement

    def getAIBraveryBonus(self): return # TODO: implement

    def getAIAttackBias(self): return # TODO: implement

    def moveUnitToOverride(self, unitId, endPos, offsetX, offsetY, speed): return # TODO: implement

    def isLuaMoving(self, unitId): return False

    def spawnUnitEffect(self, parentUnitId, name, sequence, startAnimation, inFront, paletteSwap): return

    def deleteUnitEffect(self, entityId, endAnimation): return

    def deleteUnitEffectByAnimation(self, parentUnitId, animation, endAnimation): return

    def hasUnitEffect(self, parentUnitId, animation): return # TODO: implement

    def setIsUsingGroove(self, unitId, isUsing): return # TODO: implement

    def playGrooveCutscene(self, unitId, verb, commanderOverride): return

    def playGrooveCutsceneForCharacter(self, character): return

    def playGrooveEffect(self): return

    def setVisibleOverride(self, unitId, visible): return

    def unsetVisibleOverride(self, unitId): return

    def setShadowVisible(self, unitId, visible): return

    def unsetShadowVisible(self, unitId): return

    def playCutscene(self, cutsceneId): return

    def isCutscenePlaying(self): return False

    def setFacingOverride(self, unitId, newFacing):
        #self.game.units[unitId]['pos']['facing'] = newFacing
        return

    def highlightLocation(self, location, highlightId, colour, hideOnSelection, hideOnAction, showOnUnitSelection, showOnEndPosSelection, showOnActionSelected): return

    def isPlayerVictorious(self, playerId):
        return self.game.players[playerId].is_victorious

    def getNumberOfStars(self): return 1

    def getNumberOfStarsAfterVictory(self, turnN): return 1

    def chooseFish(self, unitPos): return

    def openFishingUI(self, unitPos, fishId): return

    def isLocalPlayer(self, playerId):
        return self.game.players[playerId].is_local

    def getNumPlayers(self, independentOnly):
        if not independentOnly:
            return len(self.game.players)
        
        return sum([1 if p.child else 0 for p in self.game.players.values()])

    def playCredits(self, creditsType): return

    def setMatchSeed(self, matchSeed):
        self.game.options['seed'] = matchSeed
        #random.seed(matchSeed)

    def updateFogOfWar(self): return

    def changeObjective(self, objective): return

    def showObjective(self): return

    def moveLocationTo(self, locationId, position): return # TODO: implement

    def setMapMusic(self, music): return

    def getMapSize(self):
        m = self.game.map
        return self.game.lua.table_from({ 'x': m['w'], 'y': m['h'] })

    def isHuman(self, playerId):
        return self.game.players[playerId].is_human

    def getNetworkVersion(self): return '200000'

    def notifyEvent(self, event, playerId): return # TODO: implement

    def getOrderId(self):
        return 0 #self.game.order['id']

    def setThreatMap(self, unitId, threats): return # TODO: implement

    def getBiome(self):
        return self.game.map['biome']

    def getSplashEffect(self): return

"""
class WargrooveApiInvokations():
    def __init__(): return

    def setTurnInfo(turnNumber, currentPlayerId)

    def checkTriggers(state)

    def checkConditions(state)

    def runActions(actions)

    def setMapFlag(flagId, value)

    def reportUnitDeath(id, attackerId, attackerPlayerId, attackerUnitClass)

    def resumeExecution(time)

class WargrooveVerbInvokations():
    def __init__(): return

    def getTargetsEntry(unitId, endPos, strParam)

    def getTargetsInRangeEntry(unitId, startPos, moveRange, strParam)

    def getMaximumRangeEntry(unitId, endPos)

    def canExecuteEntry(unitId, endPos, targetPos, strParam)

    def preExecuteEntry(unitId, targetPos, strParam, endPos)

    def executeEntry(unitId, targetPos, strParam, path)

    def getCostAtEntry(unitId, endPos, targetPos)

    def generateOrders(unitId, canMove)

    def getScore(unitId, order)
"""