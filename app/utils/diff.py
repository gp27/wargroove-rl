def _is_table(x):
    return isinstance(x, dict) or isinstance(x, list)

def _table_diff(A, B):
    A_n = len(A)
    B_n = len(B)

    if (A_n == 0 and B_n > 0) or (A_n > 0 and B_n == 0):
        return [A, B]

    diff = {}
    is_array = False

    if isinstance(A, list):
        is_array = True
        A = { k: v for k,v in enumerate(A) }
    
    if isinstance(B, list):
        B = { k: v for k,v in enumerate(B) }
    
    for k, a in A.items():
        b = B.get(k)

        if b != None and _is_table(a) and _is_table(b):
            diff[k] = _table_diff(a, b)
        elif b == None:
            diff[k] = [a, 0, 0]
        elif b != a:
            diff[k] = [a, b]
    
    for k, b in B.items():
        a = A.get(k)

        if diff.get('k') != None:
            pass
        elif a != None and _is_table(a) and _is_table(b):
            diff[k] = _table_diff(b, a)
        elif b != a:
            diff[k] = [b]
    
    if len(diff) == 0:
        diff = None
    elif is_array:
        diff['_t'] = 'a'
    
    return diff

diff = _table_diff