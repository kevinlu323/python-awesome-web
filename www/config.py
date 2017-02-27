# /usr/bin/env python3
# -*- coding: utf-8 -*-

import config_default, logging

logging.basicConfig(level=logging.INFO)


class Dict(dict):
    '''
    A customized dict which support x.y to get value for key=y
    '''

    def __init__(self, name=(), value=(), **kwargs):
        super().__init__(**kwargs)
        for k, v in zip(name, value):
            self[k] = v

    def __getattr__(self, key):
        try:
            return self[key]
        except KeyError:
            raise AttributeError('\'Dict\' object has no attribute: %s' % key)

    def __setattr__(self, key, value):
        self[key] = value


def mergeConfig(default, override):
    merged = {}
    for k, v in default.items():
        if k in override:
            if isinstance(v, dict):
                merged[k] = mergeConfig(v, override[k])
            else:
                merged[k] = override[k]
        else:
            merged[k] = v
    return merged


def toDict(d):
    D = Dict()
    for k, v in d.items():
        D[k] = toDict(v) if isinstance(v, dict) else v
    return D


configs = config_default.config

try:
    import config_override

    config = mergeConfig(configs, config_override.configs)
except ImportError:
    logging.error('Cannot import and merge overrided configs')

configs = toDict(config)