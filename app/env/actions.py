import gym
import copy
import numpy as np

def getIndex(options, ele):
    try:
        return options.index(ele)
    except ValueError:
        return None

class Actions():

    def __init__(self, props):
        self._setupProps(props)
        self.space = gym.spaces.Discrete(self.size)
    
    def _setupProps(self, props):
        props = copy.deepcopy(props)

        size = 0

        for prop in props:
            group_size = prop.get('size', 0)
            if 'options' in prop:
                group_size = len(prop.get('options', []))
            
            prop['size'] = group_size
            size += group_size
        
        self.size = size
        self.props = props
    
    def getLegalActions(self):
        legal_actions = np.zeros(self.size)

        skip = 0
        false_cond = lambda: False

        for prop in self.props:
            group_size = prop.get('size', 0)
            cond = prop.get('condition', false_cond)
            if cond():
                options = prop.get('options', [])
                getter = prop.get('getter')
                for ele in getter():
                    i = getIndex(options, ele)
                    if i != None: legal_actions[skip + i] = 1

            skip += group_size
        
        return legal_actions
    
    def convertActionIndex(self, action_index):
        skip = 0

        default_conv = lambda a: a

        for prop in self.props:
            group_size = prop.get('size', 0)
            group_index = action_index - skip
            if group_index < group_size:
                options = prop.get('options', [])
                convert = prop.get('convert', default_conv)
                return convert(options[group_index])
            
            skip += group_size
