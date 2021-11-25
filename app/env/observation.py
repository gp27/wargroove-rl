import gym
import copy
import numpy as np

def listToCodes(l):
    d = {}
    n = len(l)

    #d[None] = np.zeros(n)

    for i, val in enumerate(l):
        e = np.zeros(n)
        e[i] = 1
        d[val] = e

    return d

class Observation():

    def __init__(self, props):
        self._setupProps(props)
        self.space = gym.spaces.Box(low=-1, high=1, shape=(self.size,), dtype=np.int64)

    def _setupProps(self, props):
        props = copy.deepcopy(props)
        
        size = 0

        for prop in props:
            group_size = 0
            group_n = prop.get('n', 1)

            for ob in prop.get('obs', []):
                ob_n = ob.get('n', 1)

                if 'options' in ob:
                    opts = ob.get('options', [])
                    ob_n = len(opts)
                    ob['codes'] = listToCodes(opts)
                
                group_size += ob_n
                ob['n'] = ob_n
            
            prop['size'] = group_size
            size += group_size * group_n
        
        self.size = size
        self.props = props

    def getObservation(self):
        obs = np.zeros(self.size)

        skip = 0
        zero_getter = lambda _: 0

        for prop in self.props:
            get_iter = prop.get('get_iter', lambda: [None])
            group_size = prop.get('size', 0)
            group_n = prop.get('n', 1)

            for i, ele in enumerate(get_iter()):
                o = []

                for ob in prop.get('obs', []):
                    ob_n = ob.get('n', 1)
                    getter = ob.get('getter', zero_getter)

                    val = getter(ele)

                    if 'codes' in ob:
                        ob_n = len(ob['codes'])
                        val = ob['codes'].get(val, [0] * ob_n)

                    if isinstance(val, np.ndarray):
                        val = val.ravel().tolist()
                    
                    if not isinstance(val, list):
                        val = [val]
                    
                    o += val
                
                start = skip + i * group_size
                end = start + group_size

                obs[start:end] = o
            
            skip += group_size * group_n
        
        return obs
                


        