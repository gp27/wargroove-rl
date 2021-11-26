import os, re, random, json, copy
import lupa
import numpy as np
from xxhash import xxh32_intdigest

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
    
    def reset(
        self,
        n_players = 2,
        map_name=None,
        random_commanders=True,
        seed = np.random.randint(max_uint32, dtype=np.uint32)
    ):
        if not map_name:
            map_name = random.choice(getMapNames(n_players))

        self.n_players = n_players

        self.options = {
            'seed': seed,
            'auto_end_turn': False,
            'random_commanders': random_commanders
        }

        self.map = loadMap(map_name, n_players)
        self.commanders = {}
        self.units = {}

        self.players = { i: Player(i, i, None, 0) for i in range(n_players) }

        self.phase = Phase.commander_selection
        self.selectables = None
        self.turnNumber = 0
        self.playerId = 0
        self.resetEntry()
        self.continueGame()

    def start(self):
        self.api = WargrooveApi(game=self)
        self.loadLua()
        self.loadState()
        self.loadTriggers()

        self.playerId = 0
        self.phase = Phase.action_selection
        self.selectedAction = None

        self.api.ready = True
        self.pathFinder = WargroovePathFinder(self)
        self.nextTurn(increment=False)
        self.selectables = None
        #self.continueGame()
    
    def resetEntry(self):
        self.entryStep = None
        self.preExecuteSelection = None
        self.preExecuteSteps = 0
        self.resumableSuspended = False
        
        #self.selectedPosition = None
        self.selectedVerb = None
        #self.selectedTarget = None
        self.selectedRecruit = None
        self.selectedUnload = None
        #self.selectables = None
        #self.targets = None
        self.endTurn = False
        
        self.selectedUnitId = None
        self.endPos = None
        self.targetPos = None
        self.strParam = ""

        self.shouldExecute = True

    def loadState(self):
        gold = self.map.get('gold', [])
        teams = self.map.get('teams', [])

        self.players = {}
        for playerId in range(self.n_players):
            commander = self.commanders.get(playerId, random.choice(PLAYABLE_COMMANDERS))
            g = safe_list_get(gold, playerId, 0)
            team = safe_list_get(teams, playerId)
            player = Player(playerId, team, commander, g)
            self.players[playerId] = player


        self.units = {}
        for u in self.map.get('units', []):
            unitClassId = u.get('class', None)
            playerId = u.get('playerId', -1)
            health = u.get('health', 100)
            grooveCharge = u.get('groove', 0)
            x = u.get('x', -1)
            y = u.get('y', -1)

            if x < 0 or y < 0 or not unitClassId: continue

            if playerId >= 0:
                player = self.players[playerId]
                if unitClassId == 'commander':
                    unitClassId = DEFS['commanders'][player.commander].get('unitClassId', 'commander_mercia')
            
            if not unitClassId in DEFS['unitClasses']: continue

            recruits = self.getClassRecruitables(unitClassId, recruits=u.get('recruits'), banned_recruits=u.get('banned_recruits', []))
            
            unit = self.makeUnit(playerId, { 'x': x, 'y': y }, unitClassId, False, recruits=recruits)
            unit['health'] = health
            unit['grooveCharge'] = grooveCharge
            self.units[unit['id']] = unit
    
    def loadTriggers(self):
        n = len(self.players)
        triggers = copy.deepcopy(TRIGGERS)

        for trigger in triggers:
            trigger['players'] = [1 if i < n else 0 for i in range(8)]
        
        self.triggers = triggers

    def loadLua(self):
        os.chdir(dir_path + '/lua')
        self.lua = lupa.LuaRuntime(unpack_returned_tuples=False)
        luaGlobal = self.lua.globals()
        luaGlobal['wargrooveAPI'] = self.api
        luaGlobal['debug'] = True
        self.luaWargroove = self.lua.require('wargroove/wargroove')[0]
        self.luaCombat = self.lua.require('wargroove/combat')[0]

    def getLuaVerb(self, verb):
        scriptName = DEFS['verbs'][verb]['scriptName']
        print(scriptName)
        res = self.lua.require(scriptName)
        return res[0] if isinstance(res, tuple) else res
    
    def luaWrapper(self, val):
        if isinstance(val, list):
            val = [self.luaWrapper(v) for v in val]
            return self.lua.table_from(val)
        if isinstance(val, dict):
            val = { k: self.luaWrapper(v) for k, v in val.items() }
            return self.lua.table_from(val)
        
        return val
    
    def getClassRecruitables(self, unitClassId, recruits=None, banned_recruits=[]):
        unitClass = DEFS['unitClasses'][unitClassId]
        recruitTags = unitClass.get('recruitTags', None)
        if not recruitTags: return []

        return [
            uc['id'] for uc in DEFS['unitClasses'].values()
            if (
                uc.get('isRecruitable', True) and
                not uc.get('isCommander', False) and
                any(tag in uc['tags'] for tag in recruitTags) and
                not uc['id'] in banned_recruits and
                (not recruits or uc['id'] in recruits)
            )
        ]
    
    
    def makeUnit(self, playerId, pos, unitType, turnSpent=True, startingState = [], recruits=None):
        unitClass = DEFS['unitClasses'][unitType]

        if not recruits: recruits = self.getClassRecruitables(unitType)

        return {
            'id': self.getNextUnitId(),
            'playerId': playerId,
            'pos': { 'x': pos['x'], 'y': pos['y'], 'facing': 0 },
            'startPos': { 'x': pos['x'], 'y': pos['y'], 'facing': 0 },
            'unitClassId': unitType,
            'hadTurn': turnSpent,
            #'canBeAttacked': True,
            'damageTakenPercent': 100,
            'garrisonClassId': unitClass.get('garrisonUnit', ('garrison' if unitClass.get('isStructure', False) else '')),
            'health': 100,
            'grooveCharge': 0,
            'grooveId': unitClass.get('grooveId', ''),
            'killedByLosing': False,
            'inTransport': False,
            'loadedUnits': [],
            'recruits': recruits,
            'state': startingState,
            'transportedBy': -1,
            'attackerId': -1,
            'attackerPlayerId': -1,
            'attackerUnitClass': '',
        }
    
    def unitFromLua(self, unit):
        u = dict(unit)

        for key in ['pos', 'startPos']:
            u[key] = dict(u[key])
        for key in ['loadedUnits', 'recruits']:
            u[key] = list(u[key].values())
        
        u['state'] = [dict(s) for s in u['state'].values()]

        return u
    
    def makeUnitClass(self, unitClassId):
        dfn = DEFS['unitClasses'][unitClassId]
        grooveId = dfn['grooveId'] if 'grooveId' in dfn else None
        grooveDfn = DEFS['grooves'][grooveId] if grooveId else { 'maxCharge': 0 }

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
            'maxGroove': grooveDfn.get('maxCharge', 0),
            'maxHealth': 100,
            'moveRange': dfn.get('moveRange', 0),
            'passiveMultiplier': dfn.get('passiveMultiplier', 1),
            'transportTags':  table_from(dfn.get('transportTags', [])),
            'weaponIds': table_from([w['id'] for w in dfn.get('weapons', [])])
        }

        return table_from(uc)
    
    def makeWeapon(self, weaponId):
        dfn = DEFS['weapons'][weaponId]

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

    def getNextUnitId(self):
        i = 1
        while(i in self.units): i += 1
        return i
    
    def nextTurn(self, increment=True, incrementGold=True):
        oldPid = None

        if increment:
            oldPid = self.playerId

            self.playerId = (self.playerId + 1) % len(self.players)

            if self.playerId == 0:
                self.turnNumber += 1
        
        player = self.players[self.playerId]
        
        if player.hasLosed:
            return self.nextTurn()
        
        if incrementGold: player.gold  += player.income
        
        for unit in self.units.values():
            pid = unit['playerId']
            unitClass = DEFS['unitClasses'][unit['unitClassId']]

            unit['hadTurn'] = False

            if pid == oldPid and unit['grooveId'] != '':
                groove = DEFS['grooves'][unit['grooveId']]
                unit['grooveCharge'] += groove['chargeBy']['endOfTurn']
                if unit['grooveCharge'] > groove['maxCharge']:
                    unit['grooveCharge'] = groove['maxCharge']
                
            if pid == self.playerId:
                if 'regeneration' in unitClass:
                    unit['health'] += unitClass['regeneration']
                    if unit['health'] > 100: unit['health'] = 100
        # TODO: check deaths
        # apply buffs

        self.luaWargroove.setTurnInfo(self.turnNumber, self.playerId)
    
    def canExecuteVerb(self, verbId):
        verb = DEFS['verbs'][verbId]
        luaVerb = self.getLuaVerb(verbId)

        unitId = self.selectedUnitId
        endPos = self.endPos
        endPos['facing'] = 0
        strParam = self.strParam

        targets = []

        if verb.get('targetted') == True:
            targets = self.getTargets(luaVerb=luaVerb)
            if len(targets) == 0: return False

        #self.targets[verbId] = targets

        if (
            verb.get('hasResourceCost', False) and
            luaVerb.getCostAtEntry(luaVerb, unitId, endPos, None) > self.players[self.playerId].gold
        ): return False

        return luaVerb.canExecuteEntry(luaVerb, unitId, endPos, None, strParam)
    
    def getExecutableVerbs(self, unitId=None):
        if unitId == None:
            unitId = self.selectedUnitId
        unit = self.units[unitId]
        verbs = VERBS_BY_CLASS[unit['unitClassId']]
        #self.targets = {}
        verbs = [verbId for verbId in verbs if self.canExecuteVerb(verbId)]
        return verbs

    def getMoveArea(self, unitId=None):
        if unitId == None:
            unitId = self.selectedUnitId
        if unitId == None or not unitId in self.units: return []
        moveArea = self.pathFinder.setUnitId(unitId).getArea()
        return moveArea
    
    def unitCanAct(self, unitId):
        u = self.units[unitId]
        unitClassId = u['unitClassId']
        unitClass = DEFS['unitClasses'][unitClassId]
        verbs = VERBS_BY_CLASS[unitClassId]
        return (
            u['playerId'] == self.playerId and
            u['hadTurn'] == False and
            u['inTransport'] == False and
            len(verbs) > 0 and
            unitClass.get('hasTurn', True)
        )
    
    def getSelectableUnits(self):
        return [u for u in self.units.values() if self.unitCanAct(u['id'])]
    
    def getRecruitables(self, recruits = None, costMultiplier = 1):
        if not recruits:
            builder = self.units[self.selectedUnitId]
            recruits = builder['recruits']

        gold = self.players[self.playerId].gold
        recruits = [id for id in recruits if DEFS['unitClasses'][id].get('cost', 0) * costMultiplier <= gold]
        return recruits

    def getTargets(self, luaVerb = None):
        if not luaVerb:
            luaVerb = self.getLuaVerb(self.selectedVerb)

        unitId = self.selectedUnitId
        unit = self.units[unitId]
        startPos = unit['pos']
        endPos = self.endPos
        strParam = self.strParam
        
        
        if self.endPos:
            targets = luaVerb.getTargetsEntry(luaVerb, unitId, endPos, strParam)
        else:
            moveRange = self.lua.table_from(self.getMoveArea(unitId))
            targets = luaVerb.getTargetsInRangeEntry(luaVerb, unitId, startPos, moveRange, strParam)
        
        targets = [dict(t) for t in targets.values()]
        return targets
    
    def getSelectables(self):
        ph = {
            Phase.commander_selection: lambda: list(PLAYABLE_COMMANDERS) if not self.options.get('random_commanders') else [random.choice(PLAYABLE_COMMANDERS)],
            Phase.action_selection: lambda: ['entry', 'end_turn']
        }

        if self.phase in ph:
            return ph[self.phase]()

        es = {
            EntryStep.unit_selection: lambda: [u['id'] for u in self.getSelectableUnits()],
            EntryStep.end_position_selection: self.getMoveArea,
            EntryStep.verb_selection: self.getExecutableVerbs,
            EntryStep.recruit_selection: self.getRecruitables,
            EntryStep.target_selection: self.getTargets,
        }

        if self.entryStep in es:
            return es[self.entryStep]()

        pes = {
            PreExecuteSel.target_selection: self.getTargets,
            PreExecuteSel.recruit_selection: self.getRecruitables,
            PreExecuteSel.unload_selection: self.getUnloadable
        }
        
        if self.preExecuteSelection in pes:
            return pes[self.preExecuteSelection]()
    
    def select(self, index):
        if self.selectables == None: return False

        selected = self.selectables[index]
        self.selectables = None

        print('selected: {}'.format(selected))

        ph = {
            Phase.commander_selection: lambda: self.commanders.update({ self.playerId: selected }),
            Phase.action_selection: lambda: setattr(self, 'selectedAction', selected)
        }

        if self.phase in ph:
            ph[self.phase]()
            return True

        es = {
            EntryStep.unit_selection: lambda: setattr(self, 'selectedUnitId', selected),
            EntryStep.end_position_selection: lambda: setattr(self, 'endPos', selected),
            EntryStep.verb_selection: lambda: setattr(self, 'selectedVerb', selected),
            EntryStep.target_selection: lambda: setattr(self, 'targetPos', selected),
            EntryStep.recruit_selection: lambda: setattr(self, 'strParam', selected)
        }

        if self.entryStep in es:
            es[self.entryStep]()
            return True

        pes = {
            PreExecuteSel.target_selection: lambda: setattr(self, 'targetPos', selected),
            PreExecuteSel.recruit_selection: lambda: setattr(self, 'selectedRecruit', selected),
            PreExecuteSel.unload_selection: lambda: setattr(self, 'selectedUnload', selected)
        }
        
        if self.preExecuteSelection in pes:
            pes[self.preExecuteSelection]()
            return True

        return False
    
    def doAction(self, action):
        if action == 'entry':
            self.phase = Phase.entry_selection
            self.entryStep = EntryStep.unit_selection

        elif action == 'end_turn':
            self.nextTurn()

        elif action == 'resign':
            #self.api.eliminate(self.playerId)
            self.players[self.playerId].hasLosed = True
            self.nextTurn()

    def preExecute(self):
        verbId = self.selectedVerb
        verb = DEFS['verbs'][verbId]
        luaVerb = self.getLuaVerb(verbId)

        self.resumableSuspended = luaVerb.preExecuteEntry(luaVerb, self.selectedUnitId, self.targetPos, self.strParam, self.endPos)
    
    def continuePreExecute(self):
        while self.resumableSuspended and self.preExecuteSelection == None:
            self.runResumable() 

    def finishVerbPreExecute(self, shouldExecute, strParam):
        self.shouldExecute = bool(shouldExecute)
        self.strParam = str(strParam or '')

    def execute(self):
        verbId = self.selectedVerb
        luaVerb = self.getLuaVerb(verbId)

        path = self.pathFinder.getPath(self.endPos['y'], self.endPos['x'])
    
        print('executing', self.selectedUnitId, self.targetPos, f"'{self.strParam}'", path)
        path = self.lua.table_from(path)
        self.resumableSuspended = luaVerb.executeEntry(luaVerb, self.selectedUnitId, self.targetPos, self.strParam, path)
        while self.resumableSuspended:
            self.runResumable()
    
    def runResumable(self):
        print('resumable')
        self.resumableSuspended = self.luaWargroove.resumeExecution(0.1)
        return self.resumableSuspended
    
    def executeDeathVerb(self, unitId, killedById):
        unit = self.units[unitId]
        deathVerbId =  DEFS['unitClasses'][unit['unitClassId']].get('deathVerbId')
        if not deathVerbId: return

        luaVerb = self.getLuaVerb(deathVerbId)
        self.resumableSuspended = luaVerb.executeEntry(luaVerb, unitId, unit['pos'], str(killedById), self.game.lua.table_from([]))
        while self.resumableSuspended:
            self.runResumable()

    def autoSelect(self):
        if self.selectables == None: return None
        n = len(self.selectables)
        if n != 1: return None

        if not (
            self.phase == Phase.commander_selection or
            self.entryStep == EntryStep.end_position_selection or
            (self.entryStep == EntryStep.verb_selection and self.selectables[0] == 'recruit')
        ): return None

        return 0
    
    def continueGame(self, selection=None):
        while True:
            if selection == None:
                selection = self.autoSelect()

            if self.selectables != None and selection == None:
                #print(self.selectables)
                return

            if selection == 'cancel':
                self.resetEntry()
                self.phase = Phase.action_selection

            elif selection != None:
                self.select(selection)
                self.continueGameAfterSelect()
            
            selection = None
        
            self.printState()
        
            if self.phase in [Phase.commander_selection, Phase.action_selection]:
                self.selectables = self.getSelectables()
                continue

            if self.phase == Phase.entry_selection:
                if self.entryStep in ENTRY_STEP_SELECTIONS:
                    if not self.selectables:
                        self.selectables = self.getSelectables()
                        continue                    
                
                if self.entryStep == EntryStep.pre_execute:
                    self.preExecute()
                    self.entryStep = EntryStep.pre_execute_continue

                if self.entryStep == EntryStep.pre_execute_continue:
                    self.continuePreExecute()
                    if self.resumableSuspended: continue
                    self.entryStep = EntryStep.execute
            
                if self.entryStep == EntryStep.execute:
                    if self.shouldExecute:
                        self.execute()

                    self.resetEntry()
                    self.phase = Phase.action_selection
                    self.selectedAction = None
                    self.selectables = self.getSelectables()
                    continue
    
    def continueGameAfterSelect(self):
        if self.phase == Phase.commander_selection:
            self.playerId += 1
            if self.playerId < self.n_players: return

            self.start()
            return
        
        if self.phase == Phase.action_selection:
            self.doAction(self.selectedAction)
            return

        if self.entryStep == EntryStep.unit_selection:
            self.entryStep = EntryStep.end_position_selection
            return
        
        if self.entryStep == EntryStep.end_position_selection:
            self.entryStep = EntryStep.verb_selection
            return
        
        verb = DEFS['verbs'][self.selectedVerb]
        
        if self.entryStep == EntryStep.verb_selection:
            self.entryStep = EntryStep.recruit_selection
            if self.selectedVerb == 'recruit': return

        if self.entryStep == EntryStep.recruit_selection:
            self.entryStep = EntryStep.target_selection
            if verb.get('targetted') == True: return


        if self.entryStep == EntryStep.target_selection:
            self.entryStep = EntryStep.pre_execute if verb.get('preExecute', False) else EntryStep.execute
            return
        
        if self.preExecuteSelection != None:
            self.preExecuteSelection = None
            #self.entryStep = EntryStep.pre_execute_continue
            return

    def printState(self):
        print('## {}, {}, {} ##'.format(self.phase, self.entryStep, self.preExecuteSelection))

    
    def getUnitTables(self):
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
    
    def getBoardTable(self):
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
    def __init__(self, id, team, commander, gold=100, basicIncome=0):
        self.id = id
        self.team = team
        self.gold = gold
        self.income = basicIncome
        self.isVictorious = False
        self.isLocal = True
        self.isHuman = False
        self.commander = commander
        self.hasLosed = False

class WargrooveApi():
    def __init__(self, game):
        self.game = game
        self.ready = False

    def isApiReady(self):
        return self.ready
    
    def getWeapon(self, id, unitClassId=None):
        return self.game.makeWeapon(id)
    
    def getUnitClass(self, id):
        return self.game.makeUnitClass(id)
    
    def getAllUnits(self):
        return self.game.lua.table_from(self.game.units.keys())
    
    def getUnitById(self, id):
        if not id in self.game.units: return None
        return self.game.luaWrapper(self.game.units[id])
    
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
        attacker = self.game.units[attackerId]
        defender = self.game.units[defenderId]


        solveType = 'random' if self.isRNGEnabled() else ''
        results = self.game.luaCombat.solveCombat(self.game.luaCombat, attackerId, defenderId, path, solveType)

        print('combat results', dict(results))

        ## --- Start section ---
        # Unclear if the following code should be called here 
        # and in what order, but it must definitely be called
        # maybe in a trigger?
        # If run here, changes on the attackker might get overridden
        # by Wargroove.updateUnit(unit) in Verb:executeEntry
        # as soon as fis function finishes

        attacker['health'] = results['attackerHealth']
        defender['health'] = results['defenderHealth']

        self.doLuaDeathCheck(attackerId)
        self.doLuaDeathCheck(defenderId)

        self.setPostCombatGroove(attacker, True, results.attackerAttacked, defender['health'] < 0)
        self.setPostCombatGroove(defender, False, results.defenderAttacked, attacker['health'] < 0)

        self.game.luaWargroove.doPostCombat(self.game.luaWargroove, attackerId, True)
        self.game.luaWargroove.doPostCombat(self.game.luaWargroove, defenderId, False)
        ## --- End section ---
    
    def setPostCombatGroove(self, unit, isAttacker, hasAttacked, hasKilled):
        if unit['health'] < 1 or not hasAttacked: return
        grooveId = unit['grooveId']
        if grooveId == '': return
        
        groove = DEFS['grooves'][grooveId]

        if isAttacker: increment = 'kill' if hasKilled else 'attack'
        else: increment = 'counter'
        
        charge = unit['grooveCharge'] + groove['chargeBy'][increment]
        unit['grooveCharge'] =  int( max(0, min(charge, groove['maxCharge'])))
            

    def startCapture(self, attackerId, defenderId, attackerPos):
        attacker = self.game.units[attackerId]
        defender = self.game.units[defenderId]
        pid = attacker['playerId']
        defender['playerId'] = pid
        defender['health'] = max(1, int(attacker['health'] / 2))
        defender['hadTurn'] = True

        self.game.players[pid].income += DEFS['unitClasses'][defender['unitClassId']].get('income', 0)

    def spawnUnit(self, playerId, pos, unitType, turnSpent, startAnimation, startingState, factionOverride):
        unit = self.game.makeUnit(playerId, pos, unitType, turnSpent, startingState)
        self.game.units[unit['id']] = unit

    def updateUnit(self, unit):
        u = self.game.unitFromLua(unit)
        #print('so you got the unit from lua')
        self.game.units[u['id']] = u
        #print('and you assigned it')

    def removeUnit(self, unitId):
        self.game.units.pop(unitId, None) # TODO: finish

    def doLuaDeathCheck(self, unitId):
        if not unitId in self.game.units: return

        unit = self.game.units[unitId]
        if unit['health'] > 0: return

        unitClass = DEFS['unitClasses'][unit['unitClassId']]
        if unitClass.get('isNeutraliseable', False):
            unit['health'] = 100
            unit['playerId'] = -1
            return


        self.game.executeDeathVerb(unitId, unit['attackerId'])
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
        unitClass = DEFS['unitClasses'][targetClassId]
        tags = unitClass['tags']
        inAir = 'type.air' in tags
        terrain = 'sky' if inAir else self.getTerrainNameAt({ 'x': targetPosX, 'y': targetPosY })
        movementGroupType = DEFS['terrains'][terrain]['movementGroupType']

        tagDamages = weapon.get('tagDamage', {})
        tagId = next(filter(lambda tag: tag in tags, tagDamages.keys()), None)

        baseDamage = weapon.get('baseDamage', {}).get(movementGroupType, 0)
        tagDamage = tagDamages.get(tagId, 0)

        return baseDamage * tagDamage * unitClass.get('damageMultiplier', 1)


    def getWeaponDamageForceGround(self, weaponId, targetClassId, targetPosX, targetPosY):
        weapon = DEFS['weapons'][weaponId]
        tagDamage = weapon.get('tagDamage', {}).get(targetClassId, 0)
        return tagDamage

    def loadInTransport(self, transportId, unitId): return

    def unloadFromTransport(self, transportId, unitId, pos): return

    def getTerrainByName(self, name):
        terrain = DEFS['terrains'][name]
        terrain['defence'] = terrain['defenceBonus']
        return self.game.lua.table_from(terrain)

    def getTerrainNameAt(self, pos):
        return self.game.map['tiles'][pos['y']][pos['x']]

    def getTerrainDefenceAt(self, pos):
        return self.getTerrainByName(self.getTerrainNameAt(pos))['defence']

    def isTerrainImpassableAt(self, pos):
        return len(self.getTerrainMovementCostAt(pos)) == 0

    def getTerrainMovementCostAt(self, pos):
        return self.game.lua.table_from(self.getTerrainByName(self.getTerrainNameAt(pos))['movementCost'])

    def getAllUnitsForPlayer(self, playerId, includeChildren):
        allUnitsIds = [u['id'] for u in self.game.units.values() if u['playerId'] == playerId]
        return self.game.lua.table_from(allUnitsIds)

    def getCurrentWeather(self):
        return None #self.game.weather # None

    def getGroove(self, grooveId):
        return DEFS['grooves'][grooveId]

    def getMapTriggers(self):
        return self.game.luaWrapper(self.game.triggers)

    def getLocationById(self, locationId): return

    def setMetaLocation(self, id, area): return

    def startCutscene(self, id): return

    def giveVictory(self, playerId):
        team = self.game.players[playerId].team
        for player in self.game.players.values():
            player.isVictorious = True

    def eliminate(self, playerId):
        self.game.players[playerId].isEliminated = True
        # TODO: kill everything decap structures

    def getNumberOfOpponents(self, playerId):
        team = self.game.players[playerId].team
        return sum([0 if p.team == team else 1 for p in self.game.players.values()])

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

        self.game.selectedRecruit = None
        self.game.preExecuteSelection =  PreExecuteSel.recruit_selection
        self.game.selectables = self.game.getRecruitables(recruits = recruits, costMultiplier = costMultiplier)

    def recruitMenuIsOpen(self): return self.game.preExecuteSelection == PreExecuteSel.recruit_selection

    def popRecruitedUnitClass(self): return self.game.selectedRecruit

    def openUnloadMenu(self, usedUnits):
        self.game.selectedUnload = None
        self.game.preExecuteSelection == PreExecuteSel.unload_selection

    def unloadMenuIsOpen(self): return self.game.preExecuteSelection == PreExecuteSel.unload_selection

    def getUnloadedUnitId(self):
        return self.game.selectedUnload if not self.game.selectedUnload in ['cancel', 'wait', None] else -1

    def getUnloadVerb(self):
        return self.game.selectedUnload if self.game.selectedUnload in ['cancel', 'wait'] else ''

    def finishVerbPreExecute(self, shouldExecute, strParam):
        self.game.finishVerbPreExecute(shouldExecute, strParam)

    def cancelVerbExecute(self):
        self.game.resetEntry()
        self.game.phase = Phase.action_selection

    def selectTarget(self):
        self.game.targetPos = None
        self.game.preExecuteSelection = PreExecuteSel.target_selection
        self.game.selectables = self.game.getTargets()

    def waitingForSelectedTarget(self): return self.game.preExecuteSelection == PreExecuteSel.target_selection

    def getSelectedTarget(self):
        return self.game.lua.table_from(self.game.targetPos)

    def setSelectedTarget(self, targetPos):
        self.game.targetPos = dict(targetPos)

    def clearSelectedTarget(self):
        self.game.targetPos = None

    def displayTarget(self, targetPos): return

    def clearDisplayTargets(self): return

    def displayBuffVisualEffect(self, parentId, playerId, animation, startSequence, alpha, effectPositions, layer, startSequenceIsLooping): return

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
        self.game.units[unitId]['pos']['facing'] = newFacing

    def highlightLocation(self, location, highlightId, colour, hideOnSelection, hideOnAction, showOnUnitSelection, showOnEndPosSelection, showOnActionSelected): return

    def isPlayerVictorious(self, playerId):
        return self.game.players[playerId].isVictorious

    def getNumberOfStars(self): return 1

    def getNumberOfStarsAfterVictory(self, turnN): return 1

    def chooseFish(self, unitPos): return

    def openFishingUI(self, unitPos, fishId): return

    def isLocalPlayer(self, playerId):
        return self.game.players[playerId].isLocal

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
        return self.game.players[playerId].isHuman

    def getNetworkVersion(self): return '200000'

    def notifyEvent(self, event, playerId): return # TODO: implement

    def getOrderId(self):
        return 0 #self.game.order['id']

    def setThreatMap(unitId, threats): return # TODO: implement

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