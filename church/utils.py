import pickle
from datetime import datetime


def get_cache_key(login_data, *args, useDate=False, usePerson=False, **kwargs):
    parts = list(args) + [login_data['url']]
    if usePerson:
        parts.append(login_data['personid'])
    if useDate:
        parts.append(str(datetime.today().date()))
        parts.insert(0, 'temporary')
    parts.append(','.join([f'{k}:{kwargs.get(k)}' for k in kwargs.keys()]))
    return ':'.join(parts)


def loadCache(redis, key):
    entr_str = redis.get(key)
    return pickle.loads(entr_str) if entr_str else None