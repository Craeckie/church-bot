#!/usr/bin/python
# -*- coding: utf-8 -*-
import locale
import os
import pickle
import traceback
from datetime import datetime, timezone
from io import BytesIO
from textwrap import indent

import json
import re
import redis
import requests

from PIL import Image
from pyzbar.pyzbar import decode

from telegram.utils.request import Request
from church.birthdays import parseGeburtstage
from church.bot import MQBot
from church.calendar import parseCalendarByTime, parseCalendarByText
from church.persons import searchPerson
from church.rooms import parseRaeumeByTime, parseRaeumeByText, room_markup
from church.utils import get_user_login_key, getAjaxResponse

locale.setlocale(locale.LC_ALL, 'de_DE.UTF-8')


import telegram
from telegram import ReplyKeyboardMarkup, ReplyKeyboardRemove
from telegram.ext import Updater, Filters, MessageHandler, messagequeue as mq
from church import utils
from church import songs, groups

utils.logging.basicConfig(level=utils.logging.INFO,
                          format='%(asctime)s - %(name)s - %(levelname)s - %(mesparseGeburtstagesage)s')

logger = utils.logging.getLogger(__name__)

r = redis.Redis(
    host=os.environ.get('REDIS_HOST', 'localhost'),
    port=int(os.environ.get('REDIS_PORT', 6379)),
    db=int(os.environ.get('REDIS_DB', 0)))
r.set_response_callback('HGET', json.loads)

main_url = os.environ.get('CHURCH_URL', 'https://feg-karlsruhe.church.tools/')

MARKUP_ROOMS = '🏠 Räume'
MARKUP_CALENDAR = '🗓 Kalender'
MARKUP_BIRTHDAYS = u'\U0001F382 Geburtstage'
MARKUP_PEOPLE = u'\U0001F464 Personen'
MARKUP_GROUPS = u'\U0001F465 Gruppen'
MARKUP_SONGS = u'\U0001F3BC Lieder'
MARKUP_EVENTS = '\U0001F465 Veranstaltungen'

MARKUP_PC = u'💻 PC'
MARKUP_PHONE = u'\U0001F4F1 Handy'

MARKUP_SIGNUP_YES = u'✅ Anmelden'
MARKUP_SIGNUP_NO = u'❌ Abbrechen'

def _getMarkup():
    custom_keyboard = [[MARKUP_ROOMS,
                        MARKUP_CALENDAR,
                        MARKUP_BIRTHDAYS],
                       [MARKUP_PEOPLE, MARKUP_SONGS, MARKUP_GROUPS],
                       [MARKUP_EVENTS]]
    return ReplyKeyboardMarkup(custom_keyboard)


def send_message(bot, chat_id, text, parse_mode, reply_markup):
    try:
        bot.send_message(chat_id, text=text, parse_mode=parse_mode, reply_markup=reply_markup,
                         disable_web_page_preview=True)
    except Exception as e:
        logger.error(f"Sending Message as {parse_mode} failed!\n{text}")
        logger.error(e)


def person(redis, bot, update, text, reply_markup, login_data, contact=False):
    try:
        res = searchPerson(redis, login_data, text)
        logger.debug(res)
        if contact and 'contact' in res:
            bot.send_contact(update.effective_chat.id, **res['contact'], reply_markup=reply_markup)
        else:
            if 'photo_raw' in res:
                try:
                    bot.send_photo(update.effective_chat.id, photo=BytesIO(res['photo_raw']), caption=res['msg'],
                                   parse_mode=telegram.ParseMode.HTML, reply_markup=reply_markup, timeout=30)
                except Exception as e:
                    res[
                        'msg'] += f'\n<i>Couldn\'t send photo :(\nYou can open it </i><a href="{res["photo_url"]}">here</a>.'
                    send_message(bot, update.effective_chat.id, res['msg'], telegram.ParseMode.HTML, reply_markup)
            else:
                send_message(bot, update.effective_chat.id, res['msg'], telegram.ParseMode.HTML, reply_markup)
    except Exception as e:
        eMsg = ''.join(traceback.format_exception(type(e), e, e.__traceback__))
        msg = f"Ein Fehler ist aufgetreten :(\nException: {eMsg}"
        logger.error(msg)
        send_message(bot, update.message.chat_id, msg, None, reply_markup)


def group(redis, bot, update, text, reply_markup, login_data):
    res = None
    try:
        res = groups.findGroup(redis, login_data, text)
    except Exception as e:
        msg = f"Failed!\nException: {e}"
        logger.error(msg)
        return

    # Combine lines to messages
    cur_part = ''
    num_lines = 0
    messages = []
    for line in res['msg']:
        cur_part += line
        num_lines += 1
        if num_lines > 80 or len(cur_part) > 5000:
            messages.append(cur_part)
            cur_part = ''
            num_lines = 0
    messages.append(cur_part)
    try:
        msg = messages[0]
        if 'photo' in res and res['photo']:
            bot.send_photo(update.message.chat_id, photo=res['photo'], caption=msg,
                           parse_mode=telegram.ParseMode.HTML, reply_markup=reply_markup)
            messages.pop(0)
    except Exception as e:
        msg = f"Failed!\nException: {e}"
        logger.error(msg)
    for msg in messages:
        send_message(bot, update.message.chat_id, msg, telegram.ParseMode.HTML, reply_markup)


def message(update, context):
    bot = context.bot
    user_id = update.message.from_user.id
    login_key = get_user_login_key(user_id)
    login_data_str = r.get(login_key)
    text = update.message.text
    reply_markup = _getMarkup()
    empty_markup = ReplyKeyboardRemove()
    login_markup = ReplyKeyboardMarkup([[MARKUP_PC, MARKUP_PHONE]])
    if login_data_str:
        login_data = json.loads(login_data_str)
    elif text in [MARKUP_PC, MARKUP_PHONE]:
        if text == MARKUP_PHONE:
            with open('church/login-help.png', 'rb') as f:
                msg = f'Geh auf die <a href="{main_url}">Webseite von Churchtools</a>\n.' \
                      "Log dich dort ein, dann\n(1) rechts oben auf deinen Namen/Bild->ChurchTools App:\n" \
                      "(2) Lange auf den blauen Link klicken, URL <b>kopieren</b> und hier als Nachricht schicken\n" \
                      "Falls das nicht geht, kannst du auch die PC-Variante probieren\n" \
                      "Bei Fragen/Problemen kannst du mir gerne ne Nachricht schreiben: @craeckie"
                bot.send_photo(update.message.chat_id, photo=f, caption=msg,
                               parse_mode=telegram.ParseMode.HTML, reply_markup=login_markup)
        else:  # PC
            with open('church/login-help-pc.png', 'rb') as f:
                msg = f'Geh auf die <a href="{main_url}">Webseite von Churchtools</a>\n.' \
                      "Log dich dort ein, dann\n(1) Namen->ChurchTools App:\n" \
                      'Dann mach einen Screenshot (mit der "Drucken"-Taste).\n' \
                      "(2) Rechts-klick auf QR-Code wie im Bild, Bild öffnen, dann nochmal Rechts-klick-><b>kopieren</b>\n" \
                      "Dann hier als Photo an den Bot schicken (einfach STRG+V im Textfeld).\n" \
                      "Falls das nicht geht, kannst du auch mit deinem Handy ein Photo vom QR-Code machen.\n" \
                      "Bei Fragen/Problemen kannst du mir gerne ne Nachricht schreiben: @craeckie"
                bot.send_photo(update.message.chat_id, photo=f, caption=msg,
                               parse_mode=telegram.ParseMode.HTML, reply_markup=login_markup)
        return
    elif not text.startswith('churchtools://'):
        send_message(bot, update.message.chat_id,
                     "Willkommen beim inoffiziellen ChurchTools-Bot!\nZuerst musst du dich einloggen.\nWas benutzt du gerade?",
                     None, reply_markup=login_markup)
        return

    mode_key = f'{user_id}:mode'
    raum_zeit_markup = ['Heute', 'Morgen', 'Nächste 7 Tage']
    raum_extended_markup = ['Suche']

    bot.send_chat_action(chat_id=update.message.chat_id, action=telegram.ChatAction.TYPING)

    mode = r.get(mode_key)
    if mode:
        mode = mode.decode('UTF-8')
        # print(f"In mode {mode}")
        r.delete(mode_key)
        if mode == 'calendar':
            try:
                if text in raum_zeit_markup:
                    if text == 'Heute':
                        msgs = parseCalendarByTime(r, login_data, dayRange=0)
                    elif text == 'Nächste 7 Tage':
                        msgs = parseCalendarByTime(r, login_data, dayRange=7)
                    elif text == 'Morgen':
                        msgs = parseCalendarByTime(r, login_data, dayRange=0, dayOffset=1)
                    for msg in msgs:
                        send_message(bot, update.message.chat_id, msg, telegram.ParseMode.HTML, reply_markup)
                elif text == 'Suche':
                    r.set(mode_key, 'calendar_search')
                    send_message(bot, update.message.chat_id,
                                 "Gib den Namen des Kalendereintrags (oder einen Teil davon ein):",
                                 None,
                                 empty_markup)
            except Exception as e:
                eMsg = ''.join(traceback.format_exception(type(e), e, e.__traceback__))
                msg = f"Failed!\nException: {eMsg}"
                logger.error(msg)
                send_message(bot, update.message.chat_id, msg, None, reply_markup)
        elif mode == 'rooms':
            if text in raum_zeit_markup:
                cur_time_markup = [[f'{text}: {r}'] for r in room_markup]
                send_message(bot, update.message.chat_id, "Welche Räume?", telegram.ParseMode.HTML,
                             ReplyKeyboardMarkup(cur_time_markup))
            elif text in raum_extended_markup:
                r.set(mode_key, 'room_search')
                send_message(bot, update.message.chat_id, "Gib den Namen der Raumbelegung (oder einen Teil ein):", None,
                             empty_markup)
        elif mode == 'song':
            (success, res) = songs.search(r, login_data, text)
            if success:
                for msg in res:
                    send_message(bot, update.message.chat_id, msg, telegram.ParseMode.HTML, reply_markup)
            else:
                send_message(bot, update.message.chat_id, res, None, reply_markup)
        elif mode == 'person':
            success = person(r, bot, update, text, reply_markup, login_data)
            if success is False:
                r.set(mode_key, mode)
        elif mode == 'group':
            group(r, bot, update, text, reply_markup, login_data=login_data)
        elif mode == 'room_search':
            msgs = parseRaeumeByText(r, login_data, text)
            for msg in msgs:
                send_message(bot, update.message.chat_id, msg, telegram.ParseMode.HTML, reply_markup)
        elif mode == 'calendar_search':
            try:
                msgs = parseCalendarByText(r, login_data, text)
                for msg in msgs:
                    send_message(bot, update.message.chat_id, msg, telegram.ParseMode.HTML, reply_markup)
            except Exception as e:
                eMsg = ''.join(traceback.format_exception(type(e), e, e.__traceback__))
                msg = f"Failed!\nException: {eMsg}"
                logger.error(msg)
                send_message(bot, update.message.chat_id, msg, None, reply_markup)
        elif mode == 'signup':
            p_id = int(login_data['personid'])
            signup_key = groups.get_signup_key(p_id)
            signup_info = utils.loadCache(r, signup_key)
            token = signup_info['token']
            g_id = signup_info['group']

            if text in [MARKUP_SIGNUP_YES, MARKUP_SIGNUP_NO]:
                r.delete(signup_key)
                if text == MARKUP_SIGNUP_YES:
                    # Signup
                    form = []
                    for field in signup_info['form']:
                        type = field['type']
                        value = field['value']
                        if type == 'comment' and value == '':
                            value = None
                        form.append({
                            'id': str(field['id']),
                            'type': type,
                            'value': value,
                        })
                    params = {
                        'token': token,
                        'forms': [
                            {
                                "personId": p_id,
                                "form": form
                            }
                        ]
                    }
                    (error, data) = getAjaxResponse(r,
                                                    f'publicgroups/{g_id}/signup',
                                                    login_data=login_data,
                                                    isAjax=False,
                                                    **params,
                                                    timeout=None)
                    if not data:
                        send_message(bot, update.message.chat_id,
                                     "<b>Anmeldung fehlgeschlagen! Fehler:\n</b>" + error,
                                     telegram.ParseMode.HTML, reply_markup)
                    elif data and 'translatedMessage' in data and data['translatedMessage']:
                        send_message(bot, update.message.chat_id, "<b>Anmeldung fehlgeschlagen! Fehler:\n</b>" + data['translatedMessage'],
                                     telegram.ParseMode.HTML, reply_markup)
                    else:
                        send_message(bot, update.message.chat_id, "<b>Erfolgreich angemeldet!</b>",
                                     telegram.ParseMode.HTML, reply_markup)
                else:
                    send_message(bot, update.message.chat_id, "<b>Anmeldung abgebrochen</b>", telegram.ParseMode.HTML,
                                 reply_markup)
            else:
                field = groups.next_signup_field(signup_info)
                if field:
                    if field['type'] == 'comment' and text == 'Kein Kommentar':
                        field['value'] = ''
                    else:
                        field['value'] = text
                new_field = groups.next_signup_field(signup_info)
                if new_field:
                    msg, field_markup = groups.get_field_info(new_field)
                    markup = ReplyKeyboardMarkup(field_markup)
                else:
                    msg = "<pre>Anmeldedaten</pre>\n"
                    msg += f'Name: {signup_info["person"]}\n'
                    for field in signup_info['form']:
                        msg += f'{field["name"]}: {field["value"]}\n'
                    msg += "<b>Jetzt anmelden?</b>"
                    markup = ReplyKeyboardMarkup([[MARKUP_SIGNUP_YES, MARKUP_SIGNUP_NO]])
                r.set(signup_key, pickle.dumps(signup_info))
                r.set(mode_key, 'signup')
                send_message(bot, update.message.chat_id, msg, telegram.ParseMode.HTML, markup)


    else:  # no special mode
        m1 = re.match('([A-Za-z0-9äöü ]+): ([A-Za-zäöü]+)', text)
        m2 = re.match('/dl_([0-9]+)_([0-9]+)', text)
        mPerson = re.match('/P([0-9]+)', text)
        mPersonContact = re.match('/C([0-9]+)', text)
        mGroup = re.match('/G([0-9]+)', text)
        mEvent = re.match('/E([0-9]+)', text)
        mAgenda = re.match('/A([0-9]+)', text)
        mSong1 = re.match('/S([0-9]+)$', text)
        mSong2 = re.match('/S([0-9]+)_([0-9]+)', text)
        if m1:
            zeit = m1.group(1)
            room = m1.group(2)
        if m1 and zeit in raum_zeit_markup and room in room_markup:
            try:
                if zeit == 'Heute':
                    msgs = parseRaeumeByTime(r, login_data, room, dayRange=0)
                elif zeit == 'Nächste 7 Tage':
                    msgs = parseRaeumeByTime(r, login_data, room, dayRange=7)
                elif zeit == 'Morgen':
                    msgs = parseRaeumeByTime(r, login_data, room, dayRange=0, dayOffset=1)
                for msg in msgs:
                    send_message(bot, update.message.chat_id, msg, telegram.ParseMode.HTML, reply_markup)
            except Exception as e:
                eMsg = ''.join(traceback.format_exception(type(e), e, e.__traceback__))
                msg = f"Failed!\nException: {eMsg}"
                logger.error(msg)
                send_message(bot, update.message.chat_id, msg, None, reply_markup)
        elif m2:
            song_id = m2.group(1)
            file_id = m2.group(2)
            try:
                res = songs.download(r, login_data, song_id, file_id)
                if res and 'msg' in res:
                    msg = res['msg']
                    if 'file' in res:
                        (success, res) = utils.download_file(r, login_data, res['file'])
                        if success:
                            if res['type'] == 'file':
                                bot.send_document(chat_id=update.message.chat_id, document=res['file'],
                                                  filename=msg,
                                                  parse_mode=telegram.ParseMode.HTML)
                            elif res['type'] == 'msg':
                                for msg in res['msg']:
                                    send_message(bot, update.message.chat_id, msg, None, reply_markup)
                            else:  # file
                                send_message(bot, update.message.chat_id, res['file'], None, reply_markup)
                        else:
                            send_message(bot, update.message.chat_id, res, None, reply_markup)
                    else:
                        send_message(bot, update.message.chat_id, msg, None, reply_markup)
            except Exception as e:
                eMsg = ''.join(traceback.format_exception(type(e), e, e.__traceback__))
                msg = f"Failed!\nException: {eMsg}"
                logger.error(msg)
                send_message(bot, update.message.chat_id, msg, None, reply_markup)
        elif mPerson:
            person(r, bot, update, text, reply_markup, login_data)
        elif mPersonContact:
            person(r, bot, update, text, reply_markup, login_data, contact=True)
        elif mGroup:
            group(r, bot, update, text, reply_markup, login_data=login_data)
        elif mEvent:
            g_id = mEvent.group(1)
            p_id = int(login_data['personid'])
            (error, data) = getAjaxResponse(r,
                                            f'publicgroups/{g_id}/token',
                                            login_data=login_data,
                                            isAjax=False,
                                            personId=p_id,
                                            clicked=[p_id],
                                            timeout=None)
            # TODO: WTH?
            if data and 'data' in data and 'token' in data['data'] and data['data']['token']:
                token = data['data']['token']
                signup_key = groups.get_signup_key(p_id)
                signup_info = {
                    'token': token,
                    'group': g_id
                }

                (error, data) = getAjaxResponse(r,
                                                f'publicgroups/{g_id}/form?token={token}',
                                                login_data=login_data,
                                                isAjax=False,
                                                timeout=None)
                if data and 'data' in data and 'group' in data['data']:
                    # TODO: WTH?
                    data = data['data']
                    cur_group = data['group']
                    msg = f'Anmeldung zu: <b>{cur_group["name"]}</b>\n'
                    msg += groups._printEvent(cur_group) + '\n'
                    try:
                        markup = [MARKUP_SIGNUP_YES, MARKUP_SIGNUP_NO]
                        signup_form = []
                        if 'signUpPersons' in data and data['signUpPersons']:
                            cur_person = data['signUpPersons'][0]['person']
                            signup_info['person'] = cur_person["title"]
                            # msg += f'{cur_person["title"]} anmelden?\n'
                        if 'form' in data:
                            form = data['form']
                            for field in form:
                                signup_form.append({
                                    'id': field['id'],
                                    'name': field['name'],
                                    'options': field['options'],
                                    'type': field['type'],
                                    'value': None,
                                })
                                #msg += "Wie möchtest du dich anmelden?\n"
                                #signup_info['form'] = {}
                                #for option in sitzplatz['options']:
                                #    msg += f'<b>Für {option["name"]} anmelden: /E{g_id}_{option["id"]}'
                            signup_info['form'] = signup_form

                        field = groups.next_signup_field(signup_info)
                        if field:
                            field_msg, field_markup = groups.get_field_info(field)
                            msg += field_msg
                            markup = ReplyKeyboardMarkup(field_markup)
                        r.set(signup_key, pickle.dumps(signup_info))
                        r.set(mode_key, 'signup')
                        send_message(bot, update.message.chat_id, msg, telegram.ParseMode.HTML, markup)
                    except Exception as e:
                        msg += "<i>Leider ist folgender Fehler aufgetreten:\n" + str(e)
                        send_message(bot, update.message.chat_id, msg, telegram.ParseMode.HTML, reply_markup)
                else:
                    msg = "<i>Konnte Anmelde-Informationen nicht abrufen"
                    if error:
                        msg += ":\n" + error
                    msg += "</i>"
                    send_message(bot, update.message.chat_id, msg, telegram.ParseMode.HTML, reply_markup)
            else:
                msg = "<i>Konnte Anmelde-Token nicht abrufen"
                if error:
                    msg += ":\n" + error
                msg += "</i>"
                send_message(bot, update.message.chat_id, msg, telegram.ParseMode.HTML, reply_markup)
        elif mSong1 or mSong2:
            try:
                arrId = None
                if mSong1:
                    songid = mSong1.group(1)
                else:
                    songid = mSong2.group(1)
                    arrId = mSong2.group(2)
                (success, msg) = songs.byID(r, login_data, song_id=songid, arrangement_id=arrId)
                send_message(bot, update.message.chat_id, msg, telegram.ParseMode.HTML, reply_markup)

            except Exception as e:
                eMsg = ''.join(traceback.format_exception(type(e), e, e.__traceback__))
                msg = f"Failed!\nException: {eMsg}"
                logger.error(msg)
                send_message(bot, update.message.chat_id, msg, None, reply_markup)
        elif mAgenda:
            a_id = mAgenda.group(1)
            try:
                (error, data) = getAjaxResponse(r, f'events/{a_id}/agenda', login_data=login_data, isAjax=False,
                                                timeout=600)
                if 'data' in data:
                    data = data['data']

                    msg = ''
                    try:
                        (error, masterData) = getAjaxResponse(r, "service", "getMasterData", login_data=login_data,
                                                              timeout=None)

                        (error, eventData) = getAjaxResponse(r, "service", "getAllEventData", login_data=login_data,
                                                             timeout=600)
                        event = eventData[a_id]

                        msg = f'<b>{event["bezeichnung"]}</b>\n'

                        masterService = masterData['service']
                        masterServiceGroups = masterData['servicegroup']
                        servicegroups = [None] * max(
                            [int(masterServiceGroups[x]['sortkey']) for x in masterServiceGroups])
                        for service in event['services']:
                            if service['name']:
                                name = service['name']
                                service_id = service['service_id']
                                info = masterService[service_id]
                                service_group = masterServiceGroups[info['servicegroup_id']]
                                group_id = int(service_group['sortkey'])
                                if not servicegroups[group_id]:
                                    servicegroups[group_id] = (service_group['bezeichnung'], {})

                                service_name = info['bezeichnung']
                                group_name, services = servicegroups[group_id]
                                if service_name not in services:
                                    services[service_name] = name
                                else:
                                    services[service_name] += ', ' + name

                        for name, services in [x for x in servicegroups if x]:
                            if services:
                                msg += f'<pre>{name}</pre>'
                                for k, v in services.items():
                                    msg += f'{k}: {v}\n'
                        msg += '\n'
                    except Exception as e:
                        eMsg = ''.join(traceback.format_exception(type(e), e, e.__traceback__))
                        msg = f"Failed!\nException: {eMsg}"
                        logger.error(msg)
                        send_message(bot, update.message.chat_id, msg, None, reply_markup)

                    msg += f'<b>{data["name"]}</b>\n'
                    isBeforeEvent = False
                    for item in data['items']:
                        if item:
                            date = datetime.strptime(item['start'], "%Y-%m-%dT%H:%M:%SZ")
                            date = date.replace(tzinfo=timezone.utc).astimezone(tz=None)
                            event_type = item['type'] if 'type' in item else None
                            part = ''
                            if isBeforeEvent and not item['isBeforeEvent']:
                                msg += "<pre>Eventstart</pre>\n"
                                isBeforeEvent = False
                            if event_type != 'header':
                                if item['isBeforeEvent']:
                                    part += '<i>'
                                    isBeforeEvent = True
                                part += date.strftime('%H:%M') + ' '
                            elif event_type == 'header':
                                if msg:
                                    part += '\n'
                                part += '<pre>'
                            if 'song' in item and item['song']:
                                song = item['song']
                                part += '<i>Lied: </i>' + song['title'] + f' /S{song["songId"]}_{song["arrangementId"]}'
                            else:
                                part += item['title']
                            if 'note' in item and item['note']:
                                part += '\n' + indent(item['note'], ' ' * 3)
                            if event_type == 'header':
                                part += '</pre>'
                            elif isBeforeEvent:
                                part += '</i>'
                            msg += part + "\n"
                else:  # no data
                    msg = '<i>Für diese Veranstaltung gibt es keinen Ablaufplan</i>'
                send_message(bot, update.message.chat_id, msg, telegram.ParseMode.HTML, reply_markup)
            except Exception as e:
                eMsg = ''.join(traceback.format_exception(type(e), e, e.__traceback__))
                msg = f"Failed!\nException: {eMsg}"
                logger.error(msg)
                send_message(bot, update.message.chat_id, msg, None, reply_markup)

        elif text == MARKUP_ROOMS:
            r.set(mode_key, 'rooms')
            send_message(bot, update.message.chat_id, "Welcher Zeitraum?", telegram.ParseMode.HTML,
                         ReplyKeyboardMarkup([raum_zeit_markup, raum_extended_markup]))
        elif text == MARKUP_CALENDAR:
            r.set(mode_key, 'calendar')
            send_message(bot, update.message.chat_id, "Welcher Zeitraum?", telegram.ParseMode.HTML,
                         ReplyKeyboardMarkup([raum_zeit_markup, raum_extended_markup]))
        elif text == MARKUP_BIRTHDAYS:
            try:
                msg = parseGeburtstage(r, login_data=login_data)
                send_message(bot, update.message.chat_id, msg, telegram.ParseMode.HTML, reply_markup)
            except Exception as e:
                msg = f"Failed!\nException: {e}"
                logger.error(msg)
                send_message(bot, update.message.chat_id, msg, None, reply_markup)
        elif text == MARKUP_SONGS:
            r.set(mode_key, 'song')
            send_message(bot, update.message.chat_id, "Gib den Namen/Author (oder einen Teil davon ein):", None,
                         empty_markup)
        elif text == MARKUP_PEOPLE:
            r.set(mode_key, 'person')
            send_message(bot, update.message.chat_id, "Gib den Namen (oder einen Teil ein) oder eine Telefonnumer ein:",
                         None, empty_markup)
        elif text == MARKUP_GROUPS:
            r.set(mode_key, 'group')
            send_message(bot, update.message.chat_id, "Gib den Namen (oder einen Teil ein):", None, empty_markup)
        elif text == MARKUP_EVENTS:
            (errorBlock, blockData) = getAjaxResponse(r, "home", "getBlockData", login_data=login_data,
                                                      timeout=None)
            (errorMaster, masterData) = getAjaxResponse(r, "db", "getMasterData", login_data=login_data,
                                                        timeout=None)
            (errorPerson, persons) = getAjaxResponse(r, "db", "getAllPersonData", login_data=login_data,
                                                     timeout=24 * 3600)
            grouplist = masterData['groups']
            if blockData and masterData and persons:
                try:
                    availableEventIDs = blockData['blocks']['managemymembership']['data']['chosable']
                    msg = '<b>Aktuelle Veranstaltungen für dich</b>\n'
                    cur_groups = []
                    for eventID in reversed(availableEventIDs):
                        cur_group = grouplist[eventID]
                        if 'gruppentyp_id' in cur_group and cur_group['gruppentyp_id'] == '4' \
                                and ('treffzeit' in cur_group and cur_group['treffzeit'] or \
                                     'parents' in cur_group and '655' in cur_group['parents'] or \
                                     'notiz' in cur_group and cur_group['notiz']) \
                                and not any(cur_group["bezeichnung"].startswith(x) for x in ['Abo ', 'Antrag ', 'Zugang zu ChurchTools']):
                            #msg += f'{cur_group["bezeichnung"]} /G{cur_group["id"]}\n'
                            cur_groups.append(cur_group)
                    if len(cur_groups) == 0:
                        msg += "<i>Keine Veranstaltungen gefunden</i>\n"
                    else:
                        for cur_group in cur_groups:
                            msg += groups._printGroup(redis=r,
                                                      login_data=login_data,
                                                      group=cur_group,
                                                      persons=persons,
                                                      masterData=masterData,
                                                      list=len(cur_groups) > 1,
                                                      onlyName=len(cur_groups) > 2) + '\n'
                    send_message(bot, update.message.chat_id, msg, telegram.ParseMode.HTML, reply_markup)
                except Exception as e:
                    msg = f"Failed!\nException: {e}"
                    logger.error(msg)
                    send_message(bot, update.message.chat_id, msg, None, reply_markup)
            else:
                if errorMaster:
                    send_message(bot, update.message.chat_id, "Konnte Master-Daten nicht abrufen:\n" + errorMaster,
                                 None, reply_markup)
                elif errorBlock:
                    send_message(bot, update.message.chat_id, "Konnte Block-Daten nicht abrufen:\n" + errorBlock,
                                 None, reply_markup)
                elif errorPerson:
                    send_message(bot, update.message.chat_id, "Konnte Personen-Daten nicht abrufen:\n" + errorPerson,
                                 None, reply_markup)
                else:
                    send_message(bot, update.message.chat_id, "Konnte Daten nicht abrufen", None, reply_markup)
        else:  # search for person #re.match('\+?[0-9]+', text) is not None and
            m = re.match("churchtools://login\?instanceurl=([^&]+)&loginstring=([^&]+)&personid=([0-9]+)", text)
            if m:
                login_data = {
                    'url': m.group(1),
                    'token': m.group(2),
                    'personid': m.group(3),
                    'telegramid': user_id,
                }
                login(bot, update, login_data)
            else:
                send_message(bot, update.message.chat_id,
                             "Unbekannter Befehl, du kannst einen der Buttons unten nutzen", None, reply_markup)


def login(bot, update, login_data):
    login_key = get_user_login_key(update.message.from_user.id)
    reply_markup = _getMarkup()
    try:
        success, cookies = utils.login(r, login_data, updateCache=True, login_token=True)
        if success:
            r.set(login_key, json.dumps(login_data))
            send_message(bot, update.message.chat_id,
                         "Erfolgreich eingeloggt!\nDu kannst jetzt die Buttons unten nutzen, um Funktionen von ChurchTools aufzurufen.",
                         None, reply_markup)
        else:
            r.delete(login_key)
            send_message(bot, update.message.chat_id,
                         "Login fehlgeschlagen!\nBitte versuch es nochmal mit einem neuen Link.", None,
                         reply_markup)
    except Exception as e:
        send_message(bot, update.message.chat_id,
                     "Login fehlgeschlagen!\nBitte versuch es nochmal mit einem neuen Link.", None,
                     reply_markup)


def photo(update, context):
    # try:
    bot = context.bot
    ps = update.message.photo
    if len(ps) >= 1:
        url = context.bot.get_file(ps[0].file_id)['file_path']
        response = requests.get(url)
        data = decode(Image.open(BytesIO(response.content)))
        if len(data) >= 1:
            data = json.loads(data[0].data)
            login_data = {
                'url': data['instanceUrl'],
                'token': data['loginstring'],
                'personid': data['personId'],
                'telegramid': update.message.from_user.id,
            }
            login(bot, update, login_data)
            return

    send_message(bot, update.message.chat_id,
                 "Konnte keinen QR-Code finden.\nBitte erneut versuchen.", None,
                 reply_markup=_getMarkup())
    #
    # except


if __name__ == '__main__':
    logger.info("Telegram bot starting..")

    q = mq.MessageQueue(all_burst_limit=20, all_time_limit_ms=2017)
    # set connection pool size for bot
    request = Request(con_pool_size=8)
    mqbot = MQBot(os.environ.get('BOT_TOKEN'),
                  request=request,
                  mqueue=q)
    updater = telegram.ext.updater.Updater(bot=mqbot)
    # updater.dispatcher.add_handler(CommandHandler('start', start))

    updater.dispatcher.add_handler(MessageHandler(Filters.text | Filters.command, message))
    updater.dispatcher.add_handler(MessageHandler(Filters.photo, photo))
    # updater.dispatcher.add_handler(CallbackQueryHandler(confirm_value))

    # updater.dispatcher.add_handler()

    logger.info("Starting updater..")
    updater.start_polling()
    updater.idle()
