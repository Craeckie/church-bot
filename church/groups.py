import logging
import pickle
import re
from io import BytesIO
from urllib.parse import urljoin

import telegram
import qrcode

from church import redis
from church.persons import _printPerson
from church.ChurchToolsRequests import getAjaxResponse
from church.utils import get_cache_key, loadCache, send_message

logger = logging.getLogger(__name__)


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


def printGroup(login_data, group, persons=None, masterData=None, list=False, onlyName=False):
    g_id = group['id']
    url = urljoin(login_data['url'], f'?q=churchdb#GroupView/searchEntry:#{g_id}')
    parts = []
    cur_part = f'<a href="{url}">'
    cur_part += f"{group['bezeichnung']}</a>"
    if list:
        cur_part += f" /G{g_id}"
    if onlyName:
        return [cur_part]
    if masterData:
        type = _getGroupType(masterData['groupTypes'], group['gruppentyp_id'])
        cur_part += "\n"
        cur_part += f"Typ: <b>{type}</b>\n"
    cur_part += _printEntry(group, description='Zeit: ', key='treffzeit', bold=True)
    cur_part += _printEntry(group, description='Max. Teilnehmer: ', key='max_teilnehmer', bold=True)
    cur_part += "\n"
    parts.append(cur_part)

    cur_part = '<pre>Beschreibung</pre>\n\n'
    cur_part += _printEntry(group, key='notiz', italic=False)
    cur_part = re.sub('\[([^\]]+)\]\((https?://[^)]+)\)', '<a href="\g<2>">\g<1></a>', cur_part)
    cur_part = cur_part.replace('\\*', '*')
    cur_part = re.sub('\*\*(.*?)\*\*', '<b>\g<1></b>', cur_part)
    cur_part = cur_part.replace('<br/>', '')
    if list and len(cur_part) > 120:
        cur_part = cur_part[:100] + "..."
    parts.append(cur_part)

    if persons:
        persons_in_group = [persons[p_id]
                            for p_id in persons
                            if 'groupmembers' in persons[p_id]
                            if g_id in persons[p_id]['groupmembers']]
        if len(persons_in_group) <= 20:
            parts += print_group_members(login_data, masterData, persons, g_id)
        else:
            parts.append(f'<b>Teilnehmer</b>: <b>/GP{g_id}</b>\n')

    if 'places' in group and group['places']:
        cur_part = "\n<pre>Treffpunkte</pre>\n"
        places = ''
        for place in group['places']:
            if places:
                places += '\n'
            city = ' '.join([place[key] for key in ['postalcode', 'city'] if place[key]])
            if place["district"]:
                city += f' ({place["district"]})'
            places += '\n'.join([info for info in [place['meetingby'], place['street'], city] if info])
            places += '\n'
        parts.append(cur_part + places)

    # https://feg-karlsruhe.church.tools/api/publicgroups/1036
    if not list:
        (error, data) = getAjaxResponse(f'publicgroups/{g_id}', login_data=login_data, isAjax=False, timeout=600)
        if data and 'data' in data:
            # TODO: WTH?
            data = data['data']
            cur_part = '\n<pre>Anmeldung</pre>\n'
            cur_part += _printEvent(data)
            if 'canSignUp' in data and data['canSignUp']:
                p_id = int(login_data['personid'])
                (error, data) = getAjaxResponse(f'groups/{g_id}/qrcodecheckin/{p_id}', login_data=login_data,
                                                isAjax=False, timeout=None)
                if data and 'data' in data and data['data']:
                    cur_part += f'\n<b>Bereits angemeldet.\nQR-Code abrufen: /Q{g_id}</b>'
                else:
                    cur_part += f'\n<b>Jetzt anmelden: /E{g_id}</b>'
        else:
            cur_part += "\n<i>Konnte Veranstaltungsdaten nicht abrufen: " + error + "</i>"
        parts.append(cur_part)

    return parts


def print_group_members(login_data, masterData, persons, g_id):
    max_people = 100
    persons_in_group = [persons[p_id]
                        for p_id in persons
                        if 'groupmembers' in persons[p_id]
                        if g_id in persons[p_id]['groupmembers']]
    persons_in_group = sorted(persons_in_group, key=lambda p: p['vorname'])
    persons_in_group = sorted(persons_in_group, key=lambda p: p['name'])
    mem_count = len(persons_in_group)
    members_by_status = {}
    for person in persons_in_group:
        p_group = person['groupmembers'][g_id]
        status_id = p_group['groupmemberstatus_id']
        registered_by_key = 'registered_by'
        registered_by = None
        if registered_by_key in p_group:
            registered_by_id = p_group[registered_by_key]
            if registered_by_id and registered_by_id != person['p_id']:
                if registered_by_id in persons:
                    registered_by_person = persons[p_group[registered_by_key]]
                    registered_by = ' '.join(registered_by_person[k] for k in ['vorname', 'name'])
                else:
                    registered_by = f'N/A (/P{registered_by_id})'
        if status_id in members_by_status:
            members_by_status[status_id].append((person, registered_by))
        else:
            members_by_status[status_id] = [(person, registered_by)]

    parts = []
    if mem_count == 0:
        parts.append('<i>Keine Teilnehmer gefunden</i>\n')
    else:
        for status_id, people in members_by_status.items():
            typeStatus = masterData['grouptypeMemberstatus'][status_id]['bezeichnung']
            cur_part = f'<pre>{typeStatus}</pre>\n'
            last_letter = ''
            num_cur_part = 0
            for person, registered_by in people:
                person_text = _printPerson(login_data, person, personList=True, onlyName=True,
                                           additionalName=f'von {registered_by}' if registered_by else None)
                if len(people) > 50:
                    new_letter = person['name'][0]
                    if new_letter != last_letter:
                        cur_part += f'<b>{new_letter}</b>\n'
                        last_letter = new_letter
                cur_part += person_text + '\n'
                num_cur_part += 1

                if num_cur_part > max_people:
                    parts.append(cur_part)
                    cur_part = ''
                    num_cur_part = 0
            cur_part += '\n'
            parts.append(cur_part)
    return parts


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


def findGroup(login_data, name):
    key = get_cache_key(login_data, 'group:find', name)
    res = loadCache(key)
    error = None
    if not res or True:
        (error, data) = getAjaxResponse("db", "getMasterData", login_data=login_data, timeout=None)
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
            (error, persons) = getAjaxResponse("db", "getAllPersonData", login_data=login_data, timeout=24 * 3600)

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
                    # t.append(f'<a href="{url}">{g["bezeichnung"]}</a>\n')
                    t += printGroup(login_data=login_data, group=g, persons=persons, masterData=data, list=False,
                                    onlyName=False)
                    img_id = g['groupimage_id']
                    if img_id:
                        try:
                            img_data = getAjaxResponse(f'files/{img_id}/metadata', login_data=login_data, isAjax=False,
                                                       timeout=24 * 3600)
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


def get_qrcode(login_data, group_id):
    p_id = int(login_data['personid'])
    (error, data) = getAjaxResponse(f'groups/{group_id}/qrcodecheckin', login_data=login_data, isAjax=False,
                                    timeout=None)
    if data and 'data' in data and data['data'] and 'token' in data['data'][0] and data['data'][0]['token']:
        token = data['data'][0]['token']
        person_id = data['data'][0]['personId']
        domainId = data['data'][0]['domainId']
        qr_data = '/'.join([str(x) for x in [token, person_id, domainId]])
        qr = qrcode.make(qr_data, box_size=10, border=3)
        b = BytesIO()
        qr.save(b, format='PNG')
        b.seek(0)
        return b
    else:
        return None
    # (error, data) = getAjaxResponse(f'groups/{group_id}/qrcodecheckin/{p_id}/pdf', login_data=login_data, isAjax=False,
    #                                timeout=None)
    # url = None
    # if data and 'data' in data and data['data'] and 'url' in data['data'] and data['data']['url']:
    #    url = data['data']['url']
    # return url


def group(context, update, text, reply_markup, login_data):
    res = None
    try:
        res = findGroup(login_data, text)
    except Exception as e:
        msg = f"Failed!\nException: {e}"
        logger.error(msg)
        send_message(context, update, msg, telegram.ParseMode.HTML, reply_markup)
        return

    # Combine lines to messages
    cur_part = ''
    num_lines = 0
    messages = []
    has_photo = 'photo' in res and res['photo']
    for line in res['msg']:
        cur_part += line
        num_lines += 1
        if num_lines > 80 or len(cur_part) > 5000 or (has_photo and num_lines == 1 and len(cur_part) > 150):
            messages.append(cur_part)
            cur_part = ''
            num_lines = 0
    messages.append(cur_part)
    try:
        msg = messages[0]
        if has_photo:
            context.bot.send_photo(update.message.chat_id, photo=res['photo'], caption=msg,
                                   parse_mode=telegram.ParseMode.HTML, reply_markup=reply_markup)
            messages.pop(0)
    except Exception as e:
        msg = f"Failed!\nException: {e}"
        logger.error(msg)
    for msg in messages:
        send_message(context, update, msg, telegram.ParseMode.HTML, reply_markup)
