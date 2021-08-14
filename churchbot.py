#!/usr/bin/python
# -*- coding: utf-8 -*-
import locale
import logging
import os
import traceback

import json
import re

from telegram.utils.request import Request

from church.birthdays import parseGeburtstage
from church.bot import MQBot
from church.calendar import parseCalendarByText, calendar
from church.event import parse_signup, list_events, agenda, print_event
from church.groups import group
from church.login_utils import button, photo, check_login
from church.markup import MARKUP_ROOMS, MARKUP_CALENDAR, MARKUP_BIRTHDAYS, MARKUP_PEOPLE, MARKUP_GROUPS, MARKUP_SONGS, \
    MARKUP_EVENTS, mainMarkup, RAUM_ZEIT_MARKUP, RAUM_EXTENDED_MARKUP, EMPTY_MARKUP
from church.persons import person, printPersonGroups, searchPerson
from church.rooms import parseRaeumeByTime, parseRaeumeByText, room_markup
from church.ChurchToolsRequests import get_user_login_key, login, getAjaxResponse
from church.songs import song
from church.utils import send_message, mode_key

locale.setlocale(locale.LC_ALL, 'de_DE.UTF-8')

import telegram
from telegram import ReplyKeyboardMarkup
from telegram.ext import Updater, Filters, MessageHandler, messagequeue as mq, CallbackQueryHandler
from church import songs, groups, redis

logging.basicConfig(level=logging.INFO,
                    format='%(asctime)s - %(name)s - %(levelname)s - %(mesparseGeburtstagesage)s')

logger = logging.getLogger(__name__)



def message(update, context):
    bot = context.bot
    user_id = update.message.from_user.id
    login_key = get_user_login_key(user_id)
    login_data_str = redis.get(login_key)
    text = update.message.text

    if login_data_str:
        login_data = json.loads(login_data_str)
        success, message = login(login_data=login_data)
        if not success:
            check_login(context, update, text, firstTime=False)
            return
    else:
        # not logged in, check if login data sent and don't continue afterwards
        check_login(context, update, text)
        return

    bot.send_chat_action(chat_id=update.message.chat_id, action=telegram.ChatAction.TYPING)

    mode = redis.get(mode_key(update))
    if mode:
        mode = mode.decode('UTF-8')
        # print(f"In mode {mode}")
        redis.delete(mode_key(update))
        if mode == 'calendar':
            calendar(context, update, login_data, mode_key(update), text)
        elif mode == 'rooms':
            if text in RAUM_ZEIT_MARKUP:
                cur_time_markup = [[f'{text}: {r}'] for r in room_markup]
                send_message(context, update, "Welche Räume?", telegram.ParseMode.HTML,
                             ReplyKeyboardMarkup(cur_time_markup))
            elif text in RAUM_EXTENDED_MARKUP:
                redis.set(mode_key(update), 'room_search')
                send_message(context, update, "Gib den Namen der Raumbelegung (oder einen Teil ein):", None,
                             EMPTY_MARKUP)
        elif mode == 'song':
            (success, res) = songs.search(login_data, text)
            if success:
                for msg in res:
                    send_message(context, update, msg, telegram.ParseMode.HTML, mainMarkup())
            else:
                send_message(context, update, res, None, mainMarkup())
        elif mode == 'person':
            success = person(context, update, text, mainMarkup(), login_data)
            if success is False:
                redis.set(mode_key(update), mode)
        elif mode == 'group':
            group(context, update, text, mainMarkup(), login_data=login_data)
        elif mode == 'room_search':
            msgs = parseRaeumeByText(login_data, text)
            for msg in msgs:
                send_message(context, update, msg, telegram.ParseMode.HTML, mainMarkup())
        elif mode == 'calendar_search':
            try:
                msgs = parseCalendarByText(login_data, text)
                for msg in msgs:
                    send_message(context, update, msg, telegram.ParseMode.HTML, mainMarkup())
            except Exception as e:
                eMsg = ''.join(traceback.format_exception(type(e), e, e.__traceback__))
                msg = f"Failed!\nException: {eMsg}"
                logger.error(msg)
                send_message(context, update, msg, None, mainMarkup())
        elif mode == 'signup':
            parse_signup(context, update, login_data, mainMarkup(), text)


    else:  # no special mode
        m1 = re.match('([A-Za-z0-9äöü ]+): ([A-Za-zäöü]+)', text)
        m2 = re.match('/dl_([0-9]+)_([0-9]+)', text)
        mPerson = re.match('/P([0-9]+)', text)
        mPersonContact = re.match('/C([0-9]+)', text)
        mPersonGroup = re.match('/PG([0-9]+)', text)
        mGroup = re.match('/G([0-9]+)', text)
        mEvent = re.match('/E([0-9]+)', text)
        mQR = re.match('/Q([0-9]+)', text)
        mAgenda = re.match('/A([0-9]+)', text)
        mSong1 = re.match('/S([0-9]+)$', text)
        mSong2 = re.match('/S([0-9]+)_([0-9]+)', text)
        if m1:
            zeit = m1.group(1)
            room = m1.group(2)
        if m1 and zeit in RAUM_ZEIT_MARKUP and room in room_markup:
            try:
                if zeit == 'Heute':
                    msgs = parseRaeumeByTime(login_data, room, dayRange=0)
                elif zeit == 'Nächste 7 Tage':
                    msgs = parseRaeumeByTime(login_data, room, dayRange=7)
                elif zeit == 'Morgen':
                    msgs = parseRaeumeByTime(login_data, room, dayRange=0, dayOffset=1)
                for msg in msgs:
                    send_message(context, update, msg, telegram.ParseMode.HTML, mainMarkup())
            except Exception as e:
                eMsg = ''.join(traceback.format_exception(type(e), e, e.__traceback__))
                msg = f"Failed!\nException: {eMsg}"
                logger.error(msg)
                send_message(context, update, msg, None, mainMarkup())
        elif m2:
            song_id = m2.group(1)
            file_id = m2.group(2)
            song(context, update, file_id, login_data, mainMarkup(), song_id)
        elif mPerson:
            person(context, update, text, mainMarkup(), login_data)
        elif mPersonContact:
            person(context, update, text, mainMarkup(), login_data, contact=True)
        elif mPersonGroup:
            try:
                (error, data) = getAjaxResponse("db", "getAllPersonData", login_data=login_data, timeout=24 * 3600)
                if not data:
                    msg = '<i>Konnte Daten nicht abrufen!</i>'
                else:
                    p_id = mPersonGroup.group(1)
                    p = data[p_id] if p_id in data else None
                    if p:
                        msg = printPersonGroups(login_data, p)
                    else:
                        msg = '<i>Person nicht gefunden.</i>'
                send_message(context, update, msg, telegram.ParseMode.HTML, mainMarkup())
            except Exception as e:
                eMsg = ''.join(traceback.format_exception(type(e), e, e.__traceback__))
                msg = f"Failed!\nException: {eMsg}"
                logger.error(msg)
                send_message(context, update, msg, None, mainMarkup())
        elif mGroup:
            group(context, update, text, mainMarkup(), login_data=login_data)
        elif mEvent:
            g_id = mEvent.group(1)
            print_event(context, update, g_id, login_data, mainMarkup())
        elif mQR:
            g_id = mQR.group(1)
            qr = groups.get_qrcode(login_data, g_id)
            if qr:
                try:
                    bot.send_photo(update.effective_chat.id, photo=qr,
                                      caption="QR-Code fürs Check-In",
                                      parse_mode=telegram.ParseMode.HTML, reply_markup=mainMarkup(),
                                      timeout=30)
                except Exception as e:
                    send_message(context, update,
                                 "<i>Konnte QR-Code nicht senden :(</i>\n" + str(e),
                                 telegram.ParseMode.HTML,
                                 mainMarkup())
            else:
                send_message(context, update,
                             "<i>Konnte QR-Code nicht abrufen :(</i>\n",
                             telegram.ParseMode.HTML,
                             mainMarkup())
        elif mSong1 or mSong2:
            try:
                arrId = None
                if mSong1:
                    songid = mSong1.group(1)
                else:
                    songid = mSong2.group(1)
                    arrId = mSong2.group(2)
                (success, msg) = songs.byID(login_data, song_id=songid, arrangement_id=arrId)
                send_message(context, update, msg, telegram.ParseMode.HTML, mainMarkup())

            except Exception as e:
                eMsg = ''.join(traceback.format_exception(type(e), e, e.__traceback__))
                msg = f"Failed!\nException: {eMsg}"
                logger.error(msg)
                send_message(context, update, msg, None, mainMarkup())
        elif mAgenda:
            a_id = mAgenda.group(1)
            agenda(context, update, login_data, a_id, mainMarkup())

        elif text == MARKUP_ROOMS:
            redis.set(mode_key(update), 'rooms')
            send_message(context, update, "Welcher Zeitraum?", telegram.ParseMode.HTML,
                         ReplyKeyboardMarkup([RAUM_ZEIT_MARKUP, RAUM_EXTENDED_MARKUP]))
        elif text == MARKUP_CALENDAR:
            redis.set(mode_key(update), 'calendar')
            send_message(context, update, "Welcher Zeitraum?", telegram.ParseMode.HTML,
                         ReplyKeyboardMarkup([RAUM_ZEIT_MARKUP, RAUM_EXTENDED_MARKUP]))
        elif text == MARKUP_BIRTHDAYS:
            try:
                msg = parseGeburtstage(login_data=login_data)
                send_message(context, update, msg, telegram.ParseMode.HTML, mainMarkup())
            except Exception as e:
                msg = f"Failed!\nException: {e}"
                logger.error(msg)
                send_message(context, update, msg, None, mainMarkup())
        elif text == MARKUP_SONGS:
            redis.set(mode_key(update), 'song')
            send_message(context, update, "Gib den Namen/Author (oder einen Teil davon ein):", None,
                         EMPTY_MARKUP)
        elif text == MARKUP_PEOPLE:
            redis.set(mode_key(update), 'person')
            send_message(context, update, "Gib den Namen (oder einen Teil ein) oder eine Telefonnumer ein:",
                         None, EMPTY_MARKUP)
        elif text == MARKUP_GROUPS:
            redis.set(mode_key(update), 'group')
            send_message(context, update, "Gib den Namen (oder einen Teil ein):", None, EMPTY_MARKUP)
        elif text == MARKUP_EVENTS:
            list_events(context, login_data, mainMarkup(), update)
        else:
            send_message(context, update,
                         "Unbekannter Befehl, du kannst einen der Buttons unten nutzen", None, mainMarkup())


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
    updater.dispatcher.add_handler(MessageHandler(Filters.photo | Filters.document, photo))
    updater.dispatcher.add_handler(CallbackQueryHandler(button))
    # updater.dispatcher.add_handler(CallbackQueryHandler(confirm_value))

    # updater.dispatcher.add_handler()

    logger.info("Starting updater..")
    updater.start_polling()
    updater.idle()
