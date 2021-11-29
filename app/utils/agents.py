import sys
import numpy as np
np.set_printoptions(threshold=sys.maxsize)
import random
import string

import config

def sample_action(action_probs):
    action = np.random.choice(len(action_probs), p = action_probs)
    return action


def mask_actions(legal_actions, action_probs):
    masked_action_probs = np.multiply(legal_actions, action_probs)
    masked_action_probs = masked_action_probs / np.sum(masked_action_probs)
    return masked_action_probs

class Agent():
    def __init__(self, name, model = None):
        self.name = name
        self.id = self.name + '_' + ''.join(random.choice(string.ascii_lowercase) for x in range(5))
        self.model = model
        self.points = 0

    def choose_action(self, env, choose_best_action, mask_invalid_actions):
        if self.name == 'rules':
            action_probs = np.array(env.rules_move())
            if mask_invalid_actions:
                action_probs = mask_actions(env.legal_actions, action_probs)
        
            return sample_action(action_probs)
    
        action_masks = env.legal_actions if mask_invalid_actions else None
        action, _ = self.model.predict(env.observation, action_masks=action_masks)
        return action



