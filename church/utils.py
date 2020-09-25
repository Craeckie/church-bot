import json
import logging
import pickle
import shutil
from datetime import datetime
from io import BytesIO
from urllib.parse import urlparse, urljoin

import requests
from urllib3.exceptions import NewConnectionError

logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
                    level=logging.DEBUG)

logger = logging.getLogger(__name__)


# def cc_login(user, password):
#
#     resp = requests.post('https://feg-karlsruhe.de/intern/?q=login/ajax', {
#         'func': 'login',
#         'email': user,
#         'password': password
#     }, timeout=30 * 60)
#     return resp


def cc_func(module, func, cookies, login_data, params={}):
    url = urljoin(login_data['url'], f'?q=church{module}/ajax')
    data = {'func': func, **params}
    response = requests.post(url, data, cookies=cookies, timeout=30)
    if json:
        return response.json()
    else:
        return response


def cc_api(path, cookies, login_data, json=True):
    url = urljoin(urljoin(login_data['url'], 'api/'), path)
    response = requests.get(url, cookies=cookies, timeout=30)
    if json:
        return {
            'status': 'success',
            'data': response.json()
        }
    else:
        return response


def get_user_login_key(user_id):
    return f'login:{user_id}'


def login(redis, login_data=None, updateCache=False, login_token=False):
    key = get_cache_key(login_data, 'login_cookies', usePerson=True)
    cookies_pickle = redis.get(key)
    cookies = pickle.loads(cookies_pickle) if cookies_pickle else None
    if not cookies or updateCache:
        logger.info(f"Cookie is invalid for {login_data['personid']}")
        key_token = get_cache_key(login_data, 'login_token', usePerson=True)
        login_key_pickle = redis.get(key_token)
        login_key = pickle.loads(login_key_pickle) if login_key_pickle else None
        resp1 = requests.head(login_data['url'])
        cookies = resp1.cookies
        if not login_key or login_token:
            logger.info(f"Getting new login token for {login_data['personid']}")
            login_url = urljoin(login_data['url'], f"?q=profile&loginstr={login_data['token']}&id={login_data['personid']}")
            resp = requests.get(login_url, cookies=cookies)

            if 'Der verwendete Login-Link ist nicht mehr aktuell und kann deshalb nicht mehr verwendet werden.' in resp.text:
                redis.delete(get_user_login_key(login_data['telegramid']))
                return False, 'Login fehlgeschlagen, versuchs es mit einem neuen Link.'
            else:
                data = cc_api(f'persons/{login_data["personid"]}/logintoken', cookies=cookies, login_data=login_data, json=True)
                if data['status'] == 'success':
                    inner_data = data['data']
                    # cookies = resp.cookies.get_dict()
                    redis.set(key_token, pickle.dumps(inner_data['data']))
                    redis.set(key, pickle.dumps(cookies.get_dict()))
                else:
                    return False, 'Login fehlgeschlagen, bitte log dich neu ein.'
        else:
            try:
                token_url = f'whoami?login_token={login_key}&user_id={login_data["personid"]}'
                data = cc_api(token_url, cookies, login_data=login_data, json=True)
                if data['status'] == 'success':
                    logger.info(data)
                    redis.set(key, pickle.dumps(cookies.get_dict()))
                else:
                    logger.warning(data)
                    return False, f'Login fehlgeschlagen, bitte log dich neu ein.'
            except Exception as e:
                return False, f'Could not renew token:\n{str(e)}'
            # redis.delete(get_user_login_key(login_data['telegramid']))
            # return False, 'Login fehlgeschlagen, versuchs es mit einem neuen Link.'

    return True, cookies


def download_file(redis, login_data, url):
    key = get_cache_key(login_data, 'song:download', url)
    res = loadCache(redis, key)
    if not res:
        (success, res) = login(redis, login_data)
        if not success:
            return False, res
        try:
            # path = 'temp_file'
            logger.info(f"Donwloading {url}")
            r = requests.get(url, cookies=res, stream=True, timeout=20)
            if r.status_code == 200:
                res = {}

                if url.endswith('.txt') or url.endswith('.sng'):
                    if url.endswith('.txt'):
                        msg = [r.text]
                    else:  # sng
                        msg = [r.text]

                    res.update({
                        'type': 'msg',
                        'msg': msg,
                    })
                else:
                    bio = BytesIO(r.content)
                    res.update({
                        'type': 'file',
                        'file': bio,
                    })
            else:
                logger.warning(r)
                res['msg'] = r.text[:50]
                return False, res
        except Exception as e:
            logger.warning(e)
            res['msg'] = e
            return False, res
        redis.set(key, pickle.dumps(res))
    return True, res


def getPersonLink(login_data, id):
    url = urljoin(login_data['url'], f'?q=churchdb#PersonView/searchEntry:#{id}')
    return f'<a href="{url}">'


def getAjaxResponse(redis, *args, login_data, isAjax=True, timeout=3600 * 2, additionalCacheKey=None, **params):
    key = get_cache_key(login_data, *args, additionalCacheKey=additionalCacheKey, **params)
    resp_str = redis.get(key)
    resp = json.loads(resp_str.decode('utf-8')) if resp_str else None
    if not resp or True: # ToDo: re-enable caching
        relogin = False
        while True:

            (success, cookies) = login(redis, login_data, updateCache=relogin)
            if not success:
                return cookies, None
            try:
                if isAjax:
                    resp = cc_func(*args, cookies=cookies, login_data=login_data, params=params)
                else:
                    resp = cc_api(*args, cookies=cookies, login_data=login_data)
            except Exception as e:
                resp_str = redis.get(key + "_latest")
                if resp_str:
                    resp_time = float(redis.get(key + "_latest:time"))
                    resp = json.loads(resp_str.decode('utf-8'))
                    msg = f'Server unavailable. Data is from {datetime.fromtimestamp(resp_time)}'
                    return msg, resp['data']
                else:
                    return "Error: Server unavailable!", None
            if resp['status'] == 'success':
                break
            elif relogin:
                break
            else:  # retry
                relogin = True
        if resp['status'] != 'success' or 'data' not in resp:
            if 'message' in resp:
                return "Error: %s" % resp['message'], None
            else:
                return "Error: %s" % str(resp), None
        else:
            resp_str = json.dumps(resp)
            redis.set(key, resp_str, ex=timeout)
            redis.set(key + "_latest", resp_str)
            redis.set(key + "_latest:time", datetime.now().timestamp())
    return None, resp['data']


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
