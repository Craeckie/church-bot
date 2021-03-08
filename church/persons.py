import re
from datetime import datetime
from io import BytesIO
from urllib.parse import urljoin

import phonenumbers
import requests
import vobject
from telegram import Contact

from church.utils import getAjaxResponse, logger, getPersonLink


def _parseNumber(num):
    if num:
        m = re.search("([0-9 /-]+)", num)
        if m:
            num = m.group(0).replace(' ', '').replace('/', '').replace('-', '')
            if num:
                num = phonenumbers.parse(num, None if num[0] == '+' else 'DE')

                return phonenumbers.format_number(num, phonenumbers.PhoneNumberFormat.E164)

    return None

_keyNameMap = {
    'telefonhandy': 'Handy',
    'telefonprivat': 'Privat',
    'email': 'E-Mail',
    'beruf': 'Beruf',
}
_all2detail = {
    'em': 'email',
    'p_id': 'id',
}

def _printPerson(redis, login_data, p, personList=False, onlyName=False, additionalName=''):
    data = None
    if not personList and not onlyName:
        (error, data) = getAjaxResponse(redis, "db", "getPersonDetails", login_data=login_data, id=p['p_id'],
                                        timeout=7 * 24 * 3600)
    if data:
        p = dict([(k, v) for (k, v) in data.items() if v])
    else:
        p = dict([(_all2detail[k], v) if k in _all2detail.keys() else (k, v) for k, v in p.items() if v])
    t = getPersonLink(login_data, p['id'])
    t += f"{p['vorname']} {p['name']}</a>"
    if 'spitzname' in p:
        t += f" ({p['spitzname']})"
    if additionalName:
        t += f" ({additionalName})"
    if personList:
        t += f" /P{p['id']}"
    if onlyName:
        return t
    t += "\n"
    # Adresse
    if all(k in p and p[k] for k in ['strasse', 'plz', 'ort']):
        t += f"\n{p['strasse']}\n{p['plz']} {p['ort']}\n"

    t += "\n"
    if 'geburtsdatum' in p and p['geburtsdatum']:
        birthday = datetime.strptime(p['geburtsdatum'], '%Y-%m-%d %H:%M:%S')
        t += f'Geburtstag: {birthday.strftime("%d.%m.%Y")}\n'
    # Weitere Daten
    t += '\n'.join([f"{_keyNameMap[k]}: {p[k]}" for k in _keyNameMap.keys() if k in p])

    t += f'\n\n<i>Kontakt speichern: </i>/C{p["id"]}'
    return t

def _printPersons(redis, login_data, t, ps):
    texts = []
    for p in ps:
        texts.append(_printPerson(redis, login_data, p, personList=len(ps) > 1, onlyName=len(ps) > 5))
    return t + '\n\n'.join(texts)


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

    #j.add('n').value = vobject.vcard.Name(family=last_name, given=first_name)
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

    #return Contact(first_name=first_name, last_name=last_name, phone_number=_parseNumber(phone)) #, vcard=j.serialize())

    # add 'vcard': j.serialize() when the rate-limiting bug is fixed..
    return {
        'phone_number': str(_parseNumber(phone)),
        'first_name': first_name,
        'last_name': last_name
    }


def _getPhoto(redis, login_data, p):
    id = p['p_id']
    photo = None
    (error, data) = getAjaxResponse(redis, "db", "getPersonDetails", login_data=login_data, id=id, timeout=7 * 24 * 3600)
    if data:
        if 'imageurl' in data and data['imageurl']:
            img_id = data['imageurl']
            url = urljoin(login_data['url'], f'?q=public/filedownload&filename={img_id}&type=image')
            #return (url, None)
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
                logger.warning('Couldn\'t download photo: ' + e)
                return url, None
    else:
        logger.warning(f"Couldn't get photo for {id}: {error}")
    return None, None


def _getPersonInfo(redis, login_data, person):
    res = {'msg': _printPerson(redis, login_data, person)}

    photo_url, photo_raw = _getPhoto(redis, login_data, person)
    if photo_url:
        res['photo_url'] = photo_url
    if photo_raw:
        res['photo_raw'] = photo_raw

    contact = _getContact(person, photo_raw)
    if contact:
        res['contact'] = contact
    return res


def searchPerson(redis, login_data, text):
    (error, data) = getAjaxResponse(redis, "db", "getAllPersonData", login_data=login_data, timeout=7 * 24 * 3600)

    if not data:
        return {
            'success': False,
            'msg': error
        }
    elif re.match('/(P|C)([0-9]+)', text):
        pid = text[2:]
        logger.info(f"Searching for id {pid}")
        for n in data:
            person = data[n]
            if not person:
                continue
            if person['p_id'] == pid:
                logger.info("Found it!")
                res = _getPersonInfo(redis, login_data, person)
                if error:
                    res['msg'] += f'\n<i>{error}</i>'
                return res

    elif re.match('\+?[0-9 /-]+', text):
        logger.info(f"Searching through {len(data)} persons..")
        try:
            cur = phonenumbers.parse(text, None if text[0] == '+' else 'DE')

            for n in data:
                person = data[n]
                if not person:
                    continue
                privat = _parseNumber(person['telefonprivat'])
                handy = _parseNumber(person['telefonhandy'])
                if (privat and privat == cur) or (handy and handy == cur):
                    logger.info(f"Found: {person}")
                    return _getPersonInfo(redis, login_data, person)
                # elif handy:
                #    logger.info(f"Not {person['vorname']} {person['name']}: {handy}")
            return {
                'msg': f"No one found for number {text} :("
            }
        except phonenumbers.NumberParseException:  # not a phone number
            pass
    res = {
        'success': False,
        'msg': f"No one found with the name {text} :(",
    }
    searchNameParts = [t.lower() for t in text.split(' ')]
    partialMatches = []
    fullMatches = []
    for n in data:
        person = data[n]
        if not person:
            continue
        nameParts = [person['name'].lower(), person['vorname'].lower(), person['spitzname'].lower()]
        if all(s in nameParts for s in searchNameParts):
            logger.debug(f"Found full match: {person}")
            fullMatches.append(person)
        elif any(s in p for p in nameParts for s in searchNameParts):
            logger.debug(f"Found partial match: {person}")
            partialMatches.append(person)
        if len(fullMatches) + len(partialMatches) > 30:
            res['msg'] = f"Found more then 30 people. Please refine your search phrase"
            return res

    if fullMatches:
        res.update({
            'success': True,
            'msg': _printPersons(redis, login_data, "", fullMatches)
        })
        if len(fullMatches) == 1:
            photo_url, photo_raw = _getPhoto(redis, login_data, fullMatches[0])
            if photo_url:
                res['photo_url'] = photo_url
            if photo_raw:
                res['photo_raw'] = photo_raw

            contact = _getContact(fullMatches[0], photo_raw)
            if contact:
                res['contact'] = contact
    elif partialMatches:
        res.update({
            'success': True,
            'msg': _printPersons(redis, login_data, "", partialMatches)
        })
        if len(partialMatches) == 1:
            photo_url, photo_raw = _getPhoto(redis, login_data, partialMatches[0])
            if photo_url:
                res['photo_url'] = photo_url
            if photo_raw:
                res['photo_raw'] = photo_raw

            contact = _getContact(partialMatches[0], photo_raw)
            if contact:
                res['contact'] = contact
    if error:
        res['msg'] += f'\n<i>{error}</i>'
    return res