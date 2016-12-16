
import conf.config_default

class Dict(dict):
    '''
        Simple dict but support access as x.y style.
    '''
    def __init__(self, name=(), values=(), **kw):
        super(Dict, self).__init__(**kw)
        for k,v in zip(name, values):
            self[k] = v

    def __getattr__(self, item):
        try:
            return self[item]
        except KeyError:
            raise AttributeError(r"'Dict' object has no attribute '%s'" % item)

    def __setattr__(self, key, value):
        self[key] = value


def merge(default, override):
    r = {}
    for k, v in default.items():
        if k in override:
            if isinstance(v, dict):
                r[k] = merge(v, override[k])
            else:
                r[k] = override[k]
        else:
            r[k] = v
    return r

def toDic(d):
    D = Dict()
    for k, v in d.items():
        if isinstance(v, dict):
            D[k] = toDic(v)
        else:
            D[k] = v
    return D

configs = conf.config_default.configs

# try:
#     import conf.config_override
#     configs = merge(configs, conf.config_override.configs)
# except ImportError:
#     pass

configs = toDic(configs)
print('end')

