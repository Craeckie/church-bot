import logging
import re
import traceback
from datetime import datetime
from io import BytesIO
from urllib.parse import urljoin

import phonenumbers
import requests
import telegram
import vobject
from telegram import Contact

from church.ChurchToolsRequests import getAjaxResponse, logger, getPersonLink
from church.utils import send_message

logger = logging.getLogger(__name__)


def _parseNumber(num):
    if num:
        try:
            num = num.replace(' ', '').replace('/', '').replace('-', '')
            if num:
                num = phonenumbers.parse(num, region='DE')
                num_type = phonenumbers.number_type(num)
                if phonenumbers.is_valid_number(num) and num_type in [
                    phonenumbers.PhoneNumberType.FIXED_LINE,
                    phonenumbers.PhoneNumberType.PERSONAL_NUMBER,
                    phonenumbers.PhoneNumberType.MOBILE,
                    phonenumbers.PhoneNumberType.FIXED_LINE_OR_MOBILE]:
                    return phonenumbers.format_number(num, phonenumbers.PhoneNumberFormat.E164)
        except phonenumbers.NumberParseException as e:
            logger.warning(f'Number "{num}" caused an exception: ' + str(e))
    return None


_keyNameMap = {
    'telefonhandy': 'Handy',
    'telefonprivat': 'Privat',
    'telefongeschaeftlich': 'Geschäftlich',
    'email': 'E-Mail',
    'beruf': 'Beruf',
}
_all2detail = {
    'em': 'email',
    'p_id': 'id',
}


def _printPerson(login_data, p, extraData=None, personList=False, onlyName=False, additionalName=''):
    groups = p['groupmembers'] if 'groupmembers' in p else None
    if extraData is None and (type(p) is str or not personList and not onlyName):
        p_id = p['p_id'] if 'p_id' in p else p
        (error, extraData) = getAjaxResponse("db", "getPersonDetails", login_data=login_data, timeout=24 * 3600,
                                             id=p_id)
    if extraData:
        p = dict([(k, v) for (k, v) in extraData.items() if v])
    else:
        p = dict([(_all2detail[k], v) if k in _all2detail.keys() else (k, v) for k, v in p.items() if v])
    t = getPersonLink(login_data, p['id'])
    t += f"{p['vorname']} {p['name']}"
    if 'int_name' in p:
        t += f" ({p['int_name']})"
    if 'spitzname' in p:
        t += f" ({p['spitzname']})"
    gender_key = 'geschlecht_no'
    if gender_key in p:
        t += ' ♂' if p[gender_key] == '1' else \
             ' ♀' if p[gender_key] == '2' else \
             ' ⚧' if p[gender_key] == '3' else ''
    t += '</a>'
    if additionalName:
        t += f"<i> ({additionalName})</i>"
    if personList:
        t += f" /P{p['id']}"
    if onlyName:
        return t
    t += "\n"
    # Adresse
    if all(k in p and p[k] for k in ['strasse', 'plz', 'ort']):
        t += f"\n{p['strasse']}\n{p['plz']} {p['ort']}\n"

    t += "\n"

    # Contact information
    t += '\n'.join([f"{_keyNameMap[k]}: {p[k]}" for k in _keyNameMap.keys() if k in p])
    t += '\n'

    # Birthday
    birthday_str = p['geb'] if 'geb' in p else (p['geburtsdatum'] if 'geburtsdatum' in p else None)
    if birthday_str:
        birthday = datetime.strptime(birthday_str.split(' ')[0], '%Y-%m-%d')
        today = datetime.today()
        age = today.year - birthday.year - ((today.month, today.day) < (birthday.month, birthday.day))
        t += f'Geburtstag: {birthday.strftime("%d.%m.%Y")} ({age})\n'

    t += '\n'

    # Relatives
    if 'rels' in p and p['rels']:
        t += '<pre>Verwandschaft</pre>\n'
        for rel in p['rels']:
            rel_id = rel['vater_id'] if rel['vater_id'] != p['id'] else rel['kind_id']
            (error, rel_person) = getAjaxResponse("db", "getPersonDetails",
                                                  login_data=login_data,
                                                  timeout=24 * 3600,
                                                  id=rel_id)
            if rel_person:
                rel_name = f'{rel_person["vorname"]} {rel_person["name"]}'
            else:
                rel_name = f'{rel["name"]}'

            rel_type = rel['beziehungstyp_id']
            if rel_type == '1':
                if rel['vater_id'] == rel_id:  # is parent of current person
                    if rel_person and gender_key in rel_person and rel_person['geschlecht_no']:
                        t += 'Vater' if rel_person[gender_key] == '1' else \
                            'Mutter' if rel_person[gender_key] == '2' else \
                                'Elternteil'
                    else:
                        t += 'Elternteil'
                elif rel['kind_id'] == rel_id:  # is child of current person
                    if rel_person and gender_key in rel_person and rel_person['geschlecht_no']:
                        t += 'Sohn' if rel_person[gender_key] == '1' else \
                            'Tochter' if rel_person[gender_key] == '2' else \
                                'Kind'
                    else:
                        t += 'Kind'

                t += f': {getPersonLink(login_data, rel_id)}{rel_name}</a> /P{rel_id}'
            elif rel_type == '2':
                t += f'Verheiratet mit {getPersonLink(login_data, rel_id)}{rel_name}</a> /P{rel_id}'
                wedding_key = 'hochzeitsdatum'
                if extraData and wedding_key in extraData and extraData[wedding_key]:
                    try:
                        birthday = datetime.strptime(extraData[wedding_key].split(' ')[0], '%Y-%m-%d')
                        t += f' (seit {birthday.strftime("%d.%m.%Y")})'
                    except:
                        pass
            t += '\n'
        t += '\n'

    # Groups
    if groups:
        t += f'Gruppen: /PG{p["id"]}\n\n'

    if 'telefonhandy' in p or 'telefonprivat' in p:
        t += f'<i>Kontakt speichern: </i>/C{p["id"]}'

    if extraData:
        if 'guid' in extraData:
            t += f'\nChatte mit {p["vorname"]} auf <a href="https://matrix.to/#/@ct_{extraData["guid"].lower()}:chat.church.tools">Matrix!</a> (oder in der ChurchTools-App)'
    return t


def printPersonGroups(login_data, person):
    from church.groups import printGroup

    t = 'Gruppen von ' + _printPerson(login_data, person, personList=True, onlyName=True) + '\n'
    groups = person['groupmembers'] if 'groupmembers' in person else None
    if not groups:
        t += '<i>Keine Gruppen gefunden.</i>'
        return t
    (error, master_data) = getAjaxResponse("db", "getMasterData", login_data=login_data, timeout=None)
    if master_data:
        group_types = {}
        for group_id in groups:
            group = master_data['groups'][group_id]
            group_type_id = group['gruppentyp_id']
            if group_type_id in group_types:
                group_types[group_type_id].append(group)
            else:
                group_types[group_type_id] = [group]
        for group_type_id, groups in group_types.items():
            group_type = master_data['groupTypes'][group_type_id]['bezeichnung']
            t += f'\n<pre>{group_type}</pre>\n'
            for group in groups:
                parts = printGroup(login_data, group, list=True, onlyName=True)
                t += f'- {parts[0]}\n'
        t += '\n'
    else:
        t += '<i>Konnte Gruppenteilnahme nicht abrufen</i>\n'
    return t


def _printPersons(login_data, ps):
    texts = []
    ps = sorted(ps, key=lambda p: p['vorname'])
    ps = sorted(ps, key=lambda p: p['name'])
    for p in ps:
        texts.append(_printPerson(login_data, p, personList=len(ps) > 1, onlyName=len(ps) > 5))
    return '\n\n'.join(texts)


def _getContact(p, photo_raw):
    j = vobject.vCard()
    phone = None
    if 'telefonprivat' in p and p['telefonprivat']:
        phone = p['telefonprivat']
        # t = j.add('tel')
        # t.value = p['telefonprivat']
        # t.type = 'home'
    if 'telefonhandy' in p and p['telefonhandy']:
        phone = p['telefonhandy']
        # t = j.add('tel')
        # t.value = p['telefonhandy']
        # t.type = 'cell'
    if not phone:
        return None
    first_name = p['vorname']
    last_name = p['name']

    # j.add('n').value = vobject.vcard.Name(family=last_name, given=first_name)
    j.add('fn').value = first_name + ' ' + last_name
    if 'em' in p and p['em']:
        email = j.add('email')
        email.value = p['em']
        email.type_param = 'INTERNET'

    # if photo_raw:
    #     attr = j.add('photo')
    #     attr.type_param = 'jpeg'
    #     attr.encoding_param = 'b'
    #     attr.value = photo_raw
    # -> Is "rate limited" because it's too large :(

    # return Contact(first_name=first_name, last_name=last_name, phone_number=_parseNumber(phone)) #, vcard=j.serialize())

    # add 'vcard': j.serialize() when the rate-limiting bug is fixed..
    return {
        'phone_number': str(_parseNumber(phone)),
        'first_name': first_name,
        'last_name': last_name
    }


def _getPhoto(login_data, extraData):
    photo = None
    if 'imageurl' in extraData and extraData['imageurl']:
        img_id = extraData['imageurl']
        url = urljoin(login_data['url'], f'?q=public/filedownload&filename={img_id}&type=image')
        # return (url, None)
        try:
            r = requests.get(url)
            if r.ok:
                # p = j.add('photo')
                # p.type_param = 'JPEG'
                # p.encoding_param = 'b'
                # p.value = r.content
                # p.value = f'https://feg-karlsruhe.de/intern/?q=public/filedownload&filename={img_id}&type=image'
                photo = r.content
                r.close()
                return url, photo
            else:
                return url, None
        except Exception as e:
            logger.warning('Couldn\'t download photo: ' + str(e))
            return url, None
    return None, None


def _getPersonInfo(login_data, person, extraData=None):
    if not extraData:
        (error, extraData) = getAjaxResponse("db", "getPersonDetails",
                                             login_data=login_data, timeout=24 * 3600,
                                             id=person['p_id'])
    res = {'msg': _printPerson(login_data, person, extraData=extraData)}

    photo_raw = None
    if extraData:
        photo_url, photo_raw = _getPhoto(login_data, extraData)
        if photo_url:
            res['photo_url'] = photo_url
        if photo_raw:
            res['photo_raw'] = photo_raw

    contact = _getContact(person, photo_raw)
    if contact:
        res['contact'] = contact
    return res


def searchPerson(login_data, text):
    (error, data) = getAjaxResponse("db", "getAllPersonData", login_data=login_data, timeout=24 * 3600)

    regex_id = '/(P|C|PG)([0-9]+)'
    regex_phone = '\+?[0-9 /()-]+'
    if not data:
        return {
            'success': False,
            'msg': error
        }
    elif re.match(regex_id, text):
        pid = re.match(regex_id, text).group(2)
        logger.debug(f"Searching for id {pid}")
        for n in data:
            person = data[n]
            if not person:
                continue
            if person['p_id'] == pid:
                logger.debug("Found it!")
                res = _getPersonInfo(login_data, person)
                if error:
                    res['msg'] += f'\n<i>{error}</i>'
                return res

    elif re.match(regex_phone, text):
        logger.debug(f"Searching through {len(data)} persons..")
        try:
            cur = _parseNumber(text)
            if cur:
                matches = []
                for n in data:
                    person = data[n]
                    if not person:
                        continue
                    privat = _parseNumber(person['telefonprivat'])
                    handy = _parseNumber(person['telefonhandy'])
                    geschäftlich = _parseNumber(person['telefongeschaeftlich'])
                    if (privat and privat == cur) or \
                            (handy and handy == cur) or \
                            (geschäftlich and geschäftlich == cur):
                        logger.debug(f"Found: {person}")
                        matches.append(person)
                    # elif handy:
                    #    logger.info(f"Not {person['vorname']} {person['name']}: {handy}")
                if len(matches) == 1:
                    return _getPersonInfo(login_data, matches[0])
                elif len(matches) > 1:
                    return {
                        'success': True,
                        'msg': _printPersons(login_data, matches)
                    }
                else:
                    return {
                        'msg': f"Mit der Nummer {text} wurde keiner gefunden :("
                    }

            else:
                return {
                    'success': False,
                    'msg': f'Eingegebene Nummer ist ungültig. (Beispiele: 0721 12 34 56, 015771234567 oder +1 201/555 0123)'
                }
        except phonenumbers.NumberParseException as e:  # not a phone number
            logger.warning(str(e))

    # Search by text
    res = {
        'success': False,
        'msg': f'Niemand gefunden mit dem Namen "{text}" :('
    }
    searchNameParts = [t.lower() for t in text.split(' ')]
    fullMatches = []
    for n in data:
        person = data[n]
        if not person:
            continue
        nameParts = [person['name'].lower(), person['vorname'].lower(), person['spitzname'].lower()]
        if all(s in nameParts for s in searchNameParts):
            logger.debug(f"Found full match: {person}")
            fullMatches.append(person)
        elif len(searchNameParts) > 1 and (
                searchNameParts[0] in nameParts[0] and searchNameParts[1] in nameParts[1] or
                searchNameParts[1] in nameParts[0] and searchNameParts[0] in nameParts[0]):
            fullMatches.append(person)
        # elif any(s in p for p in nameParts for s in searchNameParts):
        #    logger.debug(f"Found partial match: {person}")
        #    partialMatches.append(person)
        if len(fullMatches) > 50:
            res['msg'] = f"Found more then 50 people. Please refine your search phrase"
            return res

    if fullMatches:
        res['success'] = True
        if len(fullMatches) == 1:
            p_id = fullMatches[0]['p_id']
            (error, extraData) = getAjaxResponse("db", "getPersonDetails",
                                                 login_data=login_data, timeout=24 * 3600,
                                                 id=p_id)
            if extraData:
                photo_url, photo_raw = _getPhoto(login_data=login_data, extraData=extraData)
                if photo_url:
                    res['photo_url'] = photo_url
                if photo_raw:
                    res['photo_raw'] = photo_raw

            contact = _getContact(fullMatches[0], photo_raw)
            if contact:
                res['contact'] = contact
            res.update(_getPersonInfo(login_data, fullMatches[0], extraData=extraData))
            res['success'] = True
        else:
            res['msg'] = _printPersons(login_data, fullMatches)
    else:
        (error, data) = getAjaxResponse(f'search?query={text}', login_data=login_data, isAjax=False,
                                        timeout=24 * 3600)
        matches = []
        if data and 'data' in data:
            results = data['data']
            for result in results:
                if 'domainType' in result and result['domainType'] == 'person':
                    if 'domainIdentifier' in result:
                        p_id = result['domainIdentifier']
                        matches.append(p_id)
        if matches:
            texts = []
            if len(matches) == 1:
                p_id = matches[0]
                (error, data) = getAjaxResponse("db", "getPersonDetails", login_data=login_data, timeout=24 * 3600,
                                                id=p_id)
                if data:
                    photo_url, photo_raw = _getPhoto(login_data=login_data, extraData=data)
                    if photo_url:
                        res['photo_url'] = photo_url
                    if photo_raw:
                        res['photo_raw'] = photo_raw
                    contact = _getContact(data, photo_raw)
                    if contact:
                        res['contact'] = contact
                res['msg'] = _printPerson(login_data, p_id, personList=False, onlyName=False)
            else:
                for p_id in matches:
                    texts.append(_printPerson(login_data, p_id, personList=len(matches) > 1, onlyName=len(matches) > 5))
                res['msg'] = '\n\n'.join(texts)

    # elif partialMatches:
    #    res['success'] = True
    #    if len(partialMatches) == 1:
    #        (error, extraData) = getAjaxResponse("db", "getPersonDetails",
    #                                             login_data=login_data, timeout=24 * 3600,
    #                                             id=fullMatches[0]['p_id'])
    #        if extraData:
    #            photo_url, photo_raw = _getPhoto(login_data, partialMatches[0], extraData)
    #            if photo_url:
    #                res['photo_url'] = photo_url
    #            if photo_raw:
    #                res['photo_raw'] = photo_raw

    #        contact = _getContact(p=partialMatches[0], photo_raw=photo_raw)
    #        if contact:
    #            res['contact'] = contact
    #        res.update(_getPersonInfo(login_data, partialMatches[0], extraData=extraData))
    #    else:
    #        res['msg'] = _printPersons(login_data, partialMatches)
    if error:
        res['msg'] += f'\n<i>{error}</i>'
    return res


def person(context, update, text, reply_markup, login_data, contact=False):
    try:
        res = searchPerson(login_data, text)
        logger.debug(res)
        if contact and 'contact' in res:
            context.bot.send_contact(update.effective_chat.id, **res['contact'], reply_markup=reply_markup)
        else:
            if 'photo_raw' in res:
                try:
                    context.bot.send_photo(update.effective_chat.id, photo=BytesIO(res['photo_raw']),
                                           caption=res['msg'],
                                           parse_mode=telegram.ParseMode.HTML, reply_markup=reply_markup, timeout=30)
                except Exception as e:
                    res[
                        'msg'] += f'\n<i>Couldn\'t send photo :(\nYou can open it </i><a href="{res["photo_url"]}">here</a>.'
                    send_message(context, update, res['msg'], telegram.ParseMode.HTML, reply_markup)
            else:
                send_message(context, update, res['msg'], telegram.ParseMode.HTML, reply_markup)
    except Exception as e:
        eMsg = ''.join(traceback.format_exception(type(e), e, e.__traceback__))
        msg = f"Ein Fehler ist aufgetreten :(\nException: {eMsg}"
        logger.error(msg)
        send_message(context, update, msg, None, reply_markup)
