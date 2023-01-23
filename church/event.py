import logging
import pickle
import traceback
from datetime import datetime, timezone
from textwrap import indent

import telegram
from telegram import ReplyKeyboardMarkup

from church import groups, redis
from church.ChurchToolsRequests import getAjaxResponse, getPersonLink
from church.markup import MARKUP_SIGNUP_YES, MARKUP_SIGNUP_NO
from church.utils import send_message, loadCache, mode_key

logger = logging.getLogger(__name__)

def parse_signup(context, update, login_data, reply_markup, text):
    p_id = int(login_data['personid'])
    signup_key = groups.get_signup_key(p_id)
    signup_info = loadCache(signup_key)
    token = signup_info['token']
    g_id = signup_info['group']
    if text in [MARKUP_SIGNUP_YES, MARKUP_SIGNUP_NO]:
        redis.delete(signup_key)
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
            (error, data) = getAjaxResponse(f'publicgroups/{g_id}/signup', login_data=login_data, isAjax=False,
                                            timeout=None, **params)
            if not data:
                send_message(context, update,
                             "<b>Anmeldung fehlgeschlagen! Fehler:\n</b>" + error,
                             telegram.ParseMode.HTML, reply_markup)
            elif data and 'translatedMessage' in data and data['translatedMessage']:
                send_message(context, update, "<b>Anmeldung fehlgeschlagen! Fehler:\n</b>" + data['translatedMessage'],
                             telegram.ParseMode.HTML, reply_markup)
            else:
                send_message(context, update, "<b>Erfolgreich angemeldet!</b>",
                             telegram.ParseMode.HTML, reply_markup)
                #url = groups.get_qrcode(login_data, g_id)
                qr = groups.get_qrcode(login_data, g_id)
                if qr:
                    try:
                        context.bot.send_photo(update.effective_chat.id, photo=qr,
                                          caption="Hier ist dein QR-Code fürs Check-In",
                                          parse_mode=telegram.ParseMode.HTML, reply_markup=reply_markup,
                                          timeout=30)
                        # context.bot.send_document(update.effective_chat.id, document=url,
                        #                   caption="Hier ist dein QR-Code fürs Check-In",
                        #                   parse_mode=telegram.ParseMode.HTML, reply_markup=reply_markup,
                        #                   timeout=30)
                    except Exception as e:
                        send_message(context, update,
                                     "<i>Konnte QR-Code nicht senden :(</i>\n" + str(e),
                                     telegram.ParseMode.HTML,
                                     reply_markup)
                else:
                    send_message(context, update,
                                 "<i>Konnte QR-Code nicht abrufen :(</i>\n" + error,
                                 telegram.ParseMode.HTML,
                                 reply_markup)
        else:
            send_message(context, update, "<b>Anmeldung abgebrochen</b>", telegram.ParseMode.HTML,
                         reply_markup)
    else:
        field = groups.next_signup_field(signup_info)
        if field:
            if field['type'] == 'comment' and text == 'Kein Kommentar' or \
                    field['type'] == 'person' and text == 'Keine Angabe':
                field['value'] = ''
            else:
                field['value'] = text
        new_field = groups.next_signup_field(signup_info)
        if new_field:
            msg, field_markup = groups.get_field_info(new_field, MARKUP_SIGNUP_NO)
            markup = ReplyKeyboardMarkup(field_markup)
        else:
            msg = "<pre>Anmeldedaten</pre>\n"
            msg += f'Name: {signup_info["person"]}\n'
            for field in signup_info['form']:
                msg += f'{field["name"]}: {field["value"]}\n'
            msg += "<b>Jetzt anmelden?</b>"
            markup = ReplyKeyboardMarkup([[MARKUP_SIGNUP_YES, MARKUP_SIGNUP_NO]])
        redis.set(signup_key, pickle.dumps(signup_info))
        redis.set(mode_key(update), 'signup')
        send_message(context, update, msg, telegram.ParseMode.HTML, markup)


def list_events(context, login_data, reply_markup, update):
    (errorBlock, blockData) = getAjaxResponse("home", "getBlockData", login_data=login_data, timeout=None)
    (errorMaster, masterData) = getAjaxResponse("db", "getMasterData", login_data=login_data, timeout=None)
    (errorPerson, persons) = getAjaxResponse("db", "getAllPersonData", login_data=login_data, timeout=24 * 3600)
    grouplist = masterData['groups']
    if blockData and masterData and persons:
        try:
            membership_data = blockData['blocks']['managemymembership']['data']
            availableEventIDs = membership_data['chosable']
            activeEventIDs = membership_data['member']
            msg = '<b>Aktuelle Veranstaltungen</b>\n'
            cur_groups = []
            msg += '<pre>Verfügbare</pre>\n'
            for eventID in reversed(availableEventIDs):
                cur_group = grouplist[eventID]
                if 'gruppentyp_id' in cur_group and cur_group['gruppentyp_id'] == '4' \
                        and ('treffzeit' in cur_group and cur_group['treffzeit'] or
                             'parents' in cur_group and '655' in cur_group['parents'] or
                             'notiz' in cur_group and cur_group['notiz']) \
                        and not any(
                    cur_group["bezeichnung"].startswith(x) for x in ['Abo ', 'Antrag ', 'Zugang zu ChurchTools']):
                    # msg += f'{cur_group["bezeichnung"]} /G{cur_group["id"]}\n'
                    cur_groups.append(cur_group)
            if len(cur_groups) == 0:
                msg += "<i>Keine Veranstaltungen gefunden</i>\n"
            else:
                for cur_group in cur_groups:
                    msg += ''.join(groups.printGroup(login_data=login_data, group=cur_group, persons=persons,
                                             masterData=masterData, list=True,
                                             onlyName=True)) + '\n'
            msg += '\n<pre>Angemeldete</pre>\n'
            numActive = 0
            for eventID in reversed(activeEventIDs):
                cur_group = grouplist[eventID]
                msg += ''.join(groups.printGroup(login_data=login_data, group=cur_group, persons=persons, masterData=masterData,
                                         list=True, onlyName=True)) + '\n'
                numActive += 1
            if numActive == 0:
                msg += "<i>Keine Veranstaltungen gefunden</i>\n"
            send_message(context, update, msg, telegram.ParseMode.HTML, reply_markup)
        except Exception as e:
            msg = f"Failed!\nException: {e}"
            logger.error(msg)
            send_message(context, update, msg, None, reply_markup)
    else:
        if errorMaster:
            send_message(context, update, "Konnte Master-Daten nicht abrufen:\n" + errorMaster,
                         None, reply_markup)
        elif errorBlock:
            send_message(context, update, "Konnte Block-Daten nicht abrufen:\n" + errorBlock,
                         None, reply_markup)
        elif errorPerson:
            send_message(context, update, "Konnte Personen-Daten nicht abrufen:\n" + errorPerson,
                         None, reply_markup)
        else:
            send_message(context, update, "Konnte Daten nicht abrufen", None, reply_markup)


def agenda(context, update, login_data, a_id, reply_markup):
    try:
        (error, data) = getAjaxResponse(f'events/{a_id}/agenda', login_data=login_data, isAjax=False, timeout=600)
        if data and 'data' in data:
            data = data['data']

            try:
                (error, masterData) = getAjaxResponse("service", "getMasterData", login_data=login_data, timeout=None)

                (error, eventData) = getAjaxResponse("service", "getAllEventData", login_data=login_data, timeout=600)
                event = eventData[a_id]

                msg = f'<b>{event["bezeichnung"]}</b>\n'

                masterService = masterData['service']
                masterServiceGroups = masterData['servicegroup']
                servicegroups = [None] * (
                        max([int(masterServiceGroups[x]['sortkey']) for x in masterServiceGroups]) + 1
                )
                for service in event['services']:
                    if service['name']:
                        name = service['name']
                        if 'cdb_person_id' in service:
                            p_id = service['cdb_person_id']
                            name_msg = f'{getPersonLink(login_data, p_id)}{name}</a> /P{p_id}'
                        else:
                            name_msg = name
                        service_id = service['service_id']
                        info = masterService[service_id]
                        service_group = masterServiceGroups[info['servicegroup_id']]
                        group_id = int(service_group['sortkey'])
                        if not servicegroups[group_id]:
                            servicegroups[group_id] = (service_group['bezeichnung'], {})

                        service_name = info['bezeichnung']
                        group_name, services = servicegroups[group_id]
                        if service_name not in services:
                            services[service_name] = name_msg
                        else:
                            services[service_name] += ', ' + name_msg

                for name, services in [x for x in servicegroups if x]:
                    if services:
                        msg += f'<pre>{name}</pre>\n'
                        for k, v in services.items():
                            msg += f'{k}: {v}\n'
                msg += '\n'
            except Exception as e:
                eMsg = ''.join(traceback.format_exception(type(e), e, e.__traceback__))
                msg = f"Failed!\nException: {eMsg}"
                logger.error(msg)
                send_message(context, update, msg, None, reply_markup)

            msg += f'<b>{data["name"]}</b>\n'
            isBeforeEvent = False
            for item in data['items']:
                if item:
                    date = datetime.strptime(item['start'], "%Y-%m-%dT%H:%M:%SZ")
                    date = date.replace(tzinfo=timezone.utc).astimezone(tz=None)
                    event_type = item['type'] if 'type' in item else None
                    part = ''
                    if isBeforeEvent and not item['isBeforeEvent']:
                        msg += "\n<b>Eventstart</b>\n"
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
                        part += '🎵 ' + song['title'] + f' /S{song["songId"]}_{song["arrangementId"]}'
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
        send_message(context, update, msg, telegram.ParseMode.HTML, reply_markup)
    except Exception as e:
        eMsg = ''.join(traceback.format_exception(type(e), e, e.__traceback__))
        msg = f"Failed!\nException: {eMsg}"
        logger.error(msg)
        send_message(context, update, msg, None, reply_markup)


def print_event(context, update, g_id, login_data, reply_markup):
    p_id = int(login_data['personid'])
    (error, data) = getAjaxResponse(f'publicgroups/{g_id}/token', login_data=login_data, isAjax=False, timeout=None,
                                    personId=p_id, clicked=[p_id])
    # TODO: WTH?
    if data and 'data' in data and 'token' in data['data'] and data['data']['token']:
        token = data['data']['token']
        signup_key = groups.get_signup_key(p_id)
        signup_info = {
            'token': token,
            'group': g_id
        }

        (error, data) = getAjaxResponse(f'publicgroups/{g_id}/form?token={token}', login_data=login_data, isAjax=False,
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
                        # msg += "Wie möchtest du dich anmelden?\n"
                        # signup_info['form'] = {}
                        # for option in sitzplatz['options']:
                        #    msg += f'<b>Für {option["name"]} anmelden: /E{g_id}_{option["id"]}'
                    signup_info['form'] = signup_form

                field = groups.next_signup_field(signup_info)
                if field:
                    field_msg, field_markup = groups.get_field_info(field, MARKUP_SIGNUP_NO)
                    msg += field_msg
                    markup = ReplyKeyboardMarkup(field_markup)
                redis.set(signup_key, pickle.dumps(signup_info))
                redis.set(mode_key(update), 'signup')
                send_message(context, update, msg, telegram.ParseMode.HTML, markup)
            except Exception as e:
                msg += "<i>Leider ist folgender Fehler aufgetreten:\n" + str(e)
                send_message(context, update, msg, telegram.ParseMode.HTML, reply_markup)
        else:
            msg = "<i>Konnte Anmelde-Informationen nicht abrufen"
            if error:
                msg += ":\n" + error
            msg += "</i>"
            send_message(context, update, msg, telegram.ParseMode.HTML, reply_markup)
    else:
        msg = "<i>Konnte Anmelde-Token nicht abrufen"
        if error:
            msg += ":\n" + error
        msg += "</i>"
        send_message(context, update, msg, telegram.ParseMode.HTML, reply_markup)