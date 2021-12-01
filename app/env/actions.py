import gym
import copy
import numpy as np

def get_index(options, ele):
    try:
        return options.index(ele)
    except ValueError:
        return None

class Actions():

    def __init__(self, props):
        self._setup_props(props)
        self.space = gym.spaces.Discrete(self.size)
    
    def _setup_props(self, props):
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
    
    def get_action_masks(self):
        action_masks = np.full(self.size, False, dtype=bool)

        skip = 0
        false_cond = lambda: False

        for prop in self.props:
            group_size = prop.get('size', 0)
            cond = prop.get('condition', false_cond)
            if cond():
                options = prop.get('options', [])
                getter = prop.get('getter')
                for ele in getter():
                    i = get_index(options, ele)
                    if i != None: action_masks[skip + i] = True

            skip += group_size
        
        return action_masks
    
    def convert_action_index(self, action_index):
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
