import numpy as np
import tcod

def toPos(l):
    return { 'y': l[0], 'x': l[1] }

class WargroovePathFinder():

    def __init__(self, game):
        self.game = game
        self.unit_id = None
        self.move_costs = {}
        self.units_pos = None
        self.cost = None
        self.dist = None
    
    def _get_movement_cost(self, movement):
        c = self.move_costs.get(movement, None)

        if not isinstance(c, np.ndarray):
            m = self.game.map
            c = np.empty((m['h'], m['w']), dtype=np.int8)
            terrains = self.game.defs['terrains']

            for index, terrain in np.ndenumerate(m['tiles']):
                c[index] = terrains[terrain]['movementCost'].get(movement, 0)
            
            self.move_costs[movement] = c
        
        return np.copy(c)
    
    def _get_units_pos(self, unitId):
        p = np.zeros((self.game.map['h'], self.game.map['w']), dtype=np.int8)

        u = self.game.units[unitId]
        playerId = u['playerId']
        up = self.game.players[playerId]

        unpassable = [-2] + [p.id for p in self.game.players.values() if up.team != p.team]
        for u in self.game.units.values():
            x = u['pos']['x']
            y = u['pos']['y']

            if x < 0 or y < 0: continue

            if u['id'] == unitId:
                p[y, x] = 0 # empty or self
            elif u['playerId'] in unpassable:
                p[y, x] = -1 # non ally
            else:
                p[y, x] = 1 # ally or neutral
        
        return p
        
    
    def _set_units_pos_cost(self, cost, unitsPos):
        for index, t in np.ndenumerate(unitsPos):
            if t == -1: cost[index] = 0
  
    def set_unit_id(self, unitId):
        self.unit_id = unitId
        self.calculate()
        return self
    
    def calculate(self):
        defs = self.game.defs
        u = self.game.units[self.unit_id]
        unitClass = defs['unitClasses'][u['unitClassId']]
        movement = unitClass['movement']

        x = u['pos']['x']
        y = u['pos']['y']

        dist = tcod.path.maxarray((self.game.map['h'], self.game.map['w']), dtype=np.int32)

        if y >= 0 and x >= 0: dist[y,x] = 0

        cost = self._get_movement_cost(movement)
        unitsPos = self._get_units_pos(self.unit_id)
        self._set_units_pos_cost(cost, unitsPos)

        tcod.path.dijkstra2d(dist, cost, 1, 0, out=dist)

        self.cost = cost
        self.units_pos = unitsPos
        self.dist = dist
        self.moveRange = unitClass.get('moveRange', 0)

    def get_path(self, y, x):
        path = tcod.path.hillclimb2d(self.dist, (y, x), True, False)
        path = path[::-1].tolist()
        return list(map(toPos, path))
    
    def get_area(self):
        area = []
        for index, dist in np.ndenumerate(self.dist):
            if dist <= self.moveRange and self.units_pos[index] == 0:
                area += [index]

        return list(map(toPos, area))




