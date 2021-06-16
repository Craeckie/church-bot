import pickle
import re
from urllib.parse import urljoin

from church.persons import _printPerson
from church.ChurchToolsRequests import getAjaxResponse
from church.utils import get_cache_key, loadCache


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


def printGroup(redis, login_data, group, persons, masterData, list=False, onlyName=False):
    g_id = group['id']
    url = urljoin(login_data['url'], f'?q=churchdb#GroupView/searchEntry:#{g_id}')
    t = f'<a href="{url}">'
    t += f"{group['bezeichnung']}</a>"
    if list:
        t += f" /G{g_id}"
    if onlyName:
        return t
    type = _getGroupType(masterData['groupTypes'], group['gruppentyp_id'])
    t += "\n"
    t += f"Typ: <b>{type}</b>\n"
    t += _printEntry(group, description='Zeit: ', key='treffzeit', bold=True)
    t += _printEntry(group, description='Max. Teilnehmer:', key='max_teilnehmer')
    t += "\n"

    description = _printEntry(group, key='notiz', italic=False)
    description = re.sub('\*\*(.*?)\*\*', '<b>\g<1></b>', description)
    if list and len(description) > 120:
        description = description[:100] + "..."
    t += description

    t += "\n<pre>Teilnehmer</pre>\n"
    mem_count = 0
    for p_id in persons:
        p = persons[p_id]
        if 'groupmembers' in p:
            p_groups = p['groupmembers']
            if g_id in p_groups:
                p_group = p_groups[g_id]
                typeStatus = masterData['grouptypeMemberstatus'][p_group['groupmemberstatus_id']]['bezeichnung']
                t += _printPerson(redis, login_data, p, personList=True, onlyName=True,
                                      additionalName=f'{typeStatus}') + '\n'
                mem_count += 1
                if list and mem_count >= 5 or mem_count > 100:
                    t += "..."
                    break
    if mem_count == 0:
        t += '<i>Keine Teilnehmer gefunden</i>\n'

    if 'places' in group and group['places']:
        t += "\n<pre>Treffpunkte</pre>\n"
        places = ''
        for place in group['places']:
            if places:
                places += '\n'
            city = ' '.join([place[key] for key in ['postalcode', 'city'] if place[key]])
            if place["district"]:
                city += f' ({place["district"]})'
            places += '\n'.join([info for info in [place['meetingby'], place['street'], city] if info])
            places += '\n'
        t += places

    # https://feg-karlsruhe.church.tools/api/publicgroups/1036
    if not list:
        (error, data) = getAjaxResponse(redis,
                                        f'publicgroups/{g_id}',
                                        login_data=login_data,
                                        isAjax=False,
                                        timeout=600)
        if data and 'data' in data:
            # TODO: WTH?
            data = data['data']
            t += '\n<pre>Anmeldung</pre>\n'
            t += _printEvent(data)
            if 'canSignUp' in data and data['canSignUp']:
                p_id = int(login_data['personid'])
                (error, data) = getAjaxResponse(redis,
                                                f'groups/{g_id}/qrcodecheckin/{p_id}',
                                                login_data=login_data,
                                                isAjax=False,
                                                timeout=None)
                if data and 'data' in data and data['data']:
                    t += f'\n<b>Bereits angemeldet.\nQR-Code abrufen: /Q{g_id}</b>'
                else:
                    t += f'\n<b>Jetzt anmelden: /E{g_id}</b>'
        else:
            t += "<i>Konnte Veranstaltungsdaten nicht abrufen: " + error + "</i>"

    return t


def _printEvent(data):
    t = ''
    if 'information' in data:
        info = data['information']
        time = ''
        if 'weekday' in info and info['weekday'] and 'nameTranslated' in info['weekday']:
            time += info['weekday']['nameTranslated']
            if time:
                time += ' · '
        if 'meetingTime' in info and info['meetingTime']:
            time += info['meetingTime']
        if time:
            t += f'Zeitpunkt: <b>{time}</b>\n'
    max_mem = data['maxMemberCount']
    cur_mem = data['currentMemberCount']
    if max_mem:
        free_mem = max(0, max_mem - cur_mem)
        t += f'Plätze: <b>{free_mem}/{max_mem}</b> frei\n'
    else:
        t += f'Plätze: <b>{cur_mem}/♾</b> belegt\n'
    return t


def _getGroupType(types, id):
    return types[id]['bezeichnung']


def findGroup(redis, login_data, name):
    key = get_cache_key(login_data, 'group:find', name)
    res = loadCache(redis, key)
    error = None
    if not res or True:
        (error, data) = getAjaxResponse(redis, "db", "getMasterData", login_data=login_data, timeout=None)
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
                    #t.append(f'<a href="{url}">{g["bezeichnung"]}</a>\n')
                    t.append(printGroup(
                        redis=redis,
                        login_data=login_data,
                        group=g,
                        persons=persons,
                        masterData=data,
                        list=False,
                        onlyName=False
                        ))
                    img_id = g['groupimage_id']
                    if img_id:
                        try:
                            img_data = getAjaxResponse(redis, f'files/{img_id}/metadata', login_data=login_data, isAjax=False, timeout=24 * 3600)
                            res['photo'] = urljoin(login_data['url'], img_data[1]['url'])
                        except:
                            pass
                else:
                    t.append(f'<a href="{url}">{g["bezeichnung"]}</a> /G{g_id}\n')

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


def get_signup_key(user_id):
    return f'{user_id}:signup'


def next_signup_field(signup_info):
    signup_form = signup_info['form']
    needs_filling = [field for field in signup_form if field['value'] == None]
    msg = ''
    markup = None
    if len(needs_filling) > 0:
        field = needs_filling[0]
        signup_info['cur_field'] = field['id']
        return field
    else:
        return None

def get_field_info(field, cancel_markup):
    markup = [[]]
    name = field["name"]
    if field['type'] == 'custom':
        markup = [[opt['id'] for opt in field['options']]]
        msg = f'<b>Wähle {name}</b>\n'
    elif field['type'] == 'comment':
        markup = [['Kein Kommentar', cancel_markup]]
        msg = f'<b>Ein Kommentar? ({name})</b>'
    elif field['type'] == 'person':
        markup = [['Keine Angabe', cancel_markup]]
        msg = f'<b>Bitte gib "{name}" an:</b>'
    else:
        msg = f'Unbekannter Feldtyp: {field["type"]}\n'
    return msg, markup


def get_qrcode(redis, login_data, group_id):
    p_id = int(login_data['personid'])
    (error, data) = getAjaxResponse(redis,
                                    f'groups/{group_id}/qrcodecheckin/{p_id}/pdf',
                                    login_data=login_data,
                                    isAjax=False,
                                    timeout=None)
    url = None
    if data and 'data' in data and data['data'] and 'url' in data['data'] and data['data']['url']:
        url = data['data']['url']
    return url