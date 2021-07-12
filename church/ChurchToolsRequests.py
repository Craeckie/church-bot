import json
import logging
import pickle
from datetime import datetime
from io import BytesIO
from urllib.parse import urljoin
import requests

from church import redis
from church.utils import get_cache_key, loadCache

logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
                    level=logging.DEBUG)

logger = logging.getLogger(__name__)


def cc_login(cookies, login_data):
    url = urljoin(login_data['url'], '?q=login/ajax')
    resp = requests.post(url, {
        'func': 'loginWithToken',
        'token': login_data['token'],
        'id': login_data['personid']
    }, timeout=45, cookies=cookies)
    return resp


def cc_func(module, func, cookies, login_data, params={}):
    url = urljoin(login_data['url'], f'?q=church{module}/ajax')
    data = {'func': func, **params}
    response = requests.post(url, data=data, cookies=cookies, timeout=30)
    if json:
        return response.json()
    else:
        return response


def cc_api(path, cookies, login_data, returnJson=True, params=None):
    url = urljoin(urljoin(login_data['url'], 'api/'), path)
    if params:
        response = requests.post(url, json=params, cookies=cookies, timeout=30)
    else:
        response = requests.get(url, cookies=cookies, timeout=30)
    if response.status_code != 200:
        return {
            "status": "success",
            "message": f'{response.status_code}: {response.reason}\n' + response.text
        }
    elif returnJson:
        return {
            "status": "success",
            "data": response.json()
        }
    else:
        return response


def get_user_login_key(user_id):
    return f'login:{user_id}'


def login(login_data=None, updateCache=False, login_token=False):
    key = get_cache_key(login_data, 'login_cookies', usePerson=True)
    cookies_pickle = redis.get(key)
    cookies = pickle.loads(cookies_pickle) if cookies_pickle else None

    # Check if session cookie still valid
    if cookies and not updateCache:
        data = cc_func('resource', 'pollForNews', cookies, login_data=login_data)
        if not data or 'data' not in data or ('userid' in data['data'] and str(data['data']['userid']) == '-1'):
            cookies = None
        else:
            data = data['data']
            userid = data['userid']
            if not userid or userid == -1:
                cookies = None

    if not cookies or updateCache: # need to login using permanent login key
        logger.info(f"Cookie is invalid for {login_data['personid']}")
        key_token = get_cache_key(login_data, 'login_token', usePerson=True)
        login_key_pickle = redis.get(key_token)
        login_key = pickle.loads(login_key_pickle) if login_key_pickle else None
        resp1 = requests.head(login_data['url'])
        cookies = resp1.cookies
        if not login_key or login_token: # login key not valid, try login token
            logger.info(f"Getting new login token for {login_data['personid']}")
            # oder /api/whoami?loginstr=..&id=..:
            login_url = urljoin(login_data['url'], f"?loginstr={login_data['token']}&id={login_data['personid']}")
            resp = requests.get(login_url, cookies=cookies)

            if 'Der verwendete Login-Link ist nicht mehr aktuell und kann deshalb nicht mehr verwendet werden.' in resp.text:
                redis.delete(get_user_login_key(login_data['telegramid']))
                return False, 'Login fehlgeschlagen, versuchs es mit einem neuen QR-Code.'
            else: # get new login key & cookies using login token
                data = cc_api(f'persons/{login_data["personid"]}/logintoken', cookies=cookies, login_data=login_data, returnJson=True)
                if data['status'] == 'success' and ('message' not in data or '401: Unauthorized' not in data['message']):
                    inner_data = data['data']
                    # cookies = resp.cookies.get_dict()
                    redis.set(key_token, pickle.dumps(inner_data['data']))
                    redis.set(key, pickle.dumps(cookies.get_dict()))
                else:
                    return False, 'Login fehlgeschlagen, bitte log dich neu ein.'
        else: # get new cookies using login key
            try:
                token_url = f'whoami?login_token={login_key}&user_id={login_data["personid"]}'
                data = cc_api(token_url, cookies, login_data=login_data, returnJson=True)
                if data['status'] == 'success' and ('message' not in data or '401: Unauthorized' not in data['message']):
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


def download_file(login_data, url):
    key = get_cache_key(login_data, 'song:download', url)
    res = loadCache(key)
    if not res:
        (success, res) = login(login_data)
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


def getAjaxResponse(*args, login_data, isAjax=True, timeout=10, additionalCacheKey=None, **params):
    key = get_cache_key(login_data, *args, additionalCacheKey=additionalCacheKey, **params)
    if timeout:
        resp_str = redis.get(key)
        resp = json.loads(resp_str.decode('utf-8')) if resp_str else None
    if not timeout or not resp:
        relogin = False
        while True:

            (success, cookies) = login(login_data, updateCache=relogin)
            if not success:
                return cookies, None
            try:
                if isAjax:
                    resp = cc_func(*args, cookies=cookies, login_data=login_data, params=params)
                else:
                    resp = cc_api(*args, cookies=cookies, login_data=login_data, params=params)
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
                return resp['message'], None
            else:
                return str(resp), None
        else:
            resp_str = json.dumps(resp)
            redis.set(key, resp_str, ex=timeout)
            redis.set(key + "_latest", resp_str)
            redis.set(key + "_latest:time", datetime.now().timestamp())
    return None, resp['data']
