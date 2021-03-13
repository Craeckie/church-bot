import pickle
import re
from urllib.parse import urljoin

import requests

from church.persons import _printPerson
from church.utils import getAjaxResponse, get_cache_key, loadCache


def _printEntry(dict, key, description='', italic=False, bold=False):
    t = ""
    if key in dict and dict[key] and dict[key] != 'null':
        if description:
            t += description
        t += "<i>" if italic else "<b>" if bold else ""
        t += dict[key]
        t += "</i>" if italic else "</b>" if bold else ""
        t += "\n"
    return t


def _printGroup(login_data, dict, g, list=False, onlyName=False):
    url = urljoin(login_data['url'], f'?q=churchdb#GroupView/searchEntry:#{g["id"]}')
    t = f'<a href="{url}">'
    t += f"{g['bezeichnung']}</a>"
    if list:
        t += f" /g_{g['id']}"
    if onlyName:
        return t
    type = _getGroupType(dict, g['gruppentyp_id'])
    t += "\n"
    t += f"Typ: <b>{type}</b>\n"
    t += _printEntry(g, description='Zeit: ', key='treffzeit', bold=True)
    t += _printEntry(g, description='Max. Teilnehmer:', key='max_teilnehmer')
    t += "\n"
    t += _printEntry(g, key='notiz', italic=True)
    return t


def _getGroupType(data, id):
    types = data['groupTypes']
    return types[id]['bezeichnung']


def findGroup(redis, login_data, name):
    key = get_cache_key(login_data, 'group:find', name)
    res = loadCache(redis, key)
    error = None
    if not res:
        (error, data) = getAjaxResponse(redis, "db", "getMasterData", login_data=login_data, timeout=2 * 3600)
        if not data:  # or 'groups':
            return {
                'success': False,
                'msg': error,
            }
        res = {
            'success': False,
            'msg': [f"No group found with the name {name} :("],
        }
        matches = []
        groups = data['groups']
        if re.match('/G([0-9]+)', name):
            g_id = name[2:]
            if g_id in groups:
                matches.append(groups[g_id])
        else:
            name = name.lower()
            for g in data['groups']:
                group = groups[g]
                bez = group['bezeichnung']
                if name in bez.lower():
                    matches.append(group)
        t = []
        if len(matches) == 0:
            pass
        elif len(matches) < 10:
            (error, persons) = getAjaxResponse(redis, "db", "getAllPersonData", login_data=login_data, timeout=24 * 3600)

            if not persons:
                return {
                    'success': False,
                    'msg': error
                }
            for g in matches:
                g_id = g['id']
                if t:
                    t[-1] += '\n\n'
                url = urljoin(login_data['url'], f'?q=churchdb#GroupView/searchEntry:#{g_id}')
                if len(matches) == 1:
                    t.append(f'<a href="{url}">{g["bezeichnung"]}</a>\n')
                    img_id = g['groupimage_id']
                    if img_id:
                        try:
                            img_data = getAjaxResponse(redis, f'files/{img_id}/metadata', login_data=login_data, isAjax=False, timeout=24 * 3600)
                            res['photo'] = urljoin(login_data['url'], img_data[1]['url'])
                        except:
                            pass
                else:
                    t.append(f'<a href="{url}">{g["bezeichnung"]}</a> /G{g_id}\n')
                t.append("\n<b>Teilnehmer</b>\n")
                mem_count = 0
                for p_id in persons:
                    p = persons[p_id]
                    if 'groupmembers' in p:
                        p_groups = p['groupmembers']
                        if g_id in p_groups:
                            p_group = p_groups[g_id]
                            typeStatus = data['grouptypeMemberstatus'][p_group['groupmemberstatus_id']]['bezeichnung']
                            t.append(_printPerson(redis, login_data, p, personList=True, onlyName=True, additionalName=f'{typeStatus}') + '\n')
                            mem_count += 1
                            if len(matches) > 1 and mem_count >= 5 or mem_count > 100:
                                t.append("...")
                                break
                if 'places' in g:
                    t.append("\n<b>Treffpunkte</b>\n")
                    places = ''
                    for place in g['places']:
                        if places:
                            places += '\n'
                        city = ' '.join([place[key] for key in ['postalcode', 'city'] if place[key]])
                        if place["district"]:
                            city += f' ({place["district"]})'
                        places += '\n'.join([info for info in [place['meetingby'], place['street'], city] if info])
                        places += '\n'
                    t.append(places)
            res.update({
                'msg': t,
                'success': True
            })

        elif len(matches) <= 50:
            for g in matches:
                g_id = g['id']
                url = urljoin(login_data['url'], f'?q=churchdb#GroupView/searchEntry:#{g_id}')
                t.append(f'<a href="{url}">{g["bezeichnung"]}</a> /G{g_id}\n')
                res.update({
                    'msg': t,
                    'success': True
                })
        else:
            res.update({
                'msg': ['Zu viele Gruppen gefunden! Bitte Suche verfeinern'],
                'success': False
            })

    if error:
        res['msg'].append(f'\n<i>{error}</i>')
    else:
        redis.set(key, pickle.dumps(res), ex=7 * 24 * 3600)
    return res
