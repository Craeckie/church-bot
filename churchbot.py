#!/usr/bin/python
# -*- coding: utf-8 -*-
import locale
import logging
import os
import traceback

import json
import re

from church.birthdays import parseGeburtstage
from church.calendar import parseCalendarByText, calendar
from church.event import parse_signup, list_events, agenda, print_event
from church.groups import group, print_group_members
from church.login_utils import button, photo, check_login
from church.markup import MARKUP_ROOMS, MARKUP_CALENDAR, MARKUP_BIRTHDAYS, MARKUP_PEOPLE, MARKUP_GROUPS, MARKUP_SONGS, \
    MARKUP_EVENTS, mainMarkup, RAUM_ZEIT_MARKUP, RAUM_EXTENDED_MARKUP, EMPTY_MARKUP, RAUM_ZEIT_MARKUP_SIMPLE, \
    RAUM_ZEIT_MARKUP_EXTENDED
from church.persons import person, printPersonGroups
from church.rooms import parseRaeumeByTime, parseRaeumeByText, room_markup
from church.ChurchToolsRequests import get_user_login_key, login, getAjaxResponse
from church.songs import song
from church.utils import send_message, mode_key

#locale.setlocale(locale.LC_ALL, 'de_DE.UTF-8')

import telegram
from telegram import ReplyKeyboardMarkup
from telegram.constants import ParseMode, ChatAction
from telegram.ext import ApplicationBuilder, AIORateLimiter, filters, MessageHandler,  CallbackQueryHandler
from church import songs, groups, redis

logger = logging.getLogger(__name__)

logging.basicConfig(level=logging.INFO,
                    format='%(name)s - %(levelname)s - %(message)s')
logging.getLogger('httpcore').setLevel(logging.WARNING)


# Don't show debug messages
tglogger = logging.getLogger("telegram.ext.ExtBot")
tglogger.setLevel(logging.INFO)


async def message(update, context):
    bot = context.bot
    user_id = update.message.from_user.id
    login_key = get_user_login_key(user_id)
    login_data_str = redis.get(login_key)
    text = update.message.text
    
    # include personal information?
    include_pi = bool(os.environ.get('BOT_INCLUDE_PERSONAL_INFORMATION', default=False))

    if login_data_str:
        login_data = json.loads(login_data_str)
        success, message = await login(login_data=login_data)
        if not success:
            await check_login(context, update, text, firstTime=False)
            return
    else:
        # not logged in, check if login data sent and don't continue afterwards
        await check_login(context, update, text)
        return

    await bot.send_chat_action(chat_id=update.message.chat_id, action=ChatAction.TYPING)

    mode = redis.get(mode_key(update))
    if mode:
        mode = mode.decode('UTF-8')
        # print(f"In mode {mode}")
        redis.delete(mode_key(update))
        if mode == 'calendar':
            await calendar(context, update, login_data, mode_key(update), text)
        elif mode == 'rooms':
            if text in RAUM_ZEIT_MARKUP:
                if text in RAUM_ZEIT_MARKUP_SIMPLE:
                    if text == 'Heute':
                        msgs = await parseRaeumeByTime(login_data, None, dayRange=0)
                    elif text == 'Morgen':
                        msgs = await parseRaeumeByTime(login_data, None, dayRange=0, dayOffset=1)
                    for msg in msgs:
                        await send_message(context, update, msg, ParseMode.HTML, mainMarkup())
                elif text in RAUM_ZEIT_MARKUP_EXTENDED:
                    cur_time_markup = [[f'{text}: {r}'] for r in room_markup]
                    await send_message(context, update, "Welche Räume?", ParseMode.HTML,
                                 ReplyKeyboardMarkup(cur_time_markup))
            elif text in RAUM_EXTENDED_MARKUP:
                redis.set(mode_key(update), 'room_search')
                await send_message(context, update, "Gib den Namen der Raumbelegung (oder einen Teil ein):", None,
                             EMPTY_MARKUP)
        elif mode == 'song':
            (success, res) = songs.search(login_data, text)
            if success:
                for msg in res:
                    await send_message(context, update, msg, ParseMode.HTML, mainMarkup())
            else:
                await send_message(context, update, res, None, mainMarkup())
        elif mode == 'person':
            success = await person(context, update, text, mainMarkup(), login_data, include_pi=include_pi)
            if success is False:
                redis.set(mode_key(update), mode)
        elif mode == 'group':
            group(context, update, text, mainMarkup(), login_data=login_data)
        elif mode == 'room_search':
            msgs = parseRaeumeByText(login_data, text)
            for msg in msgs:
                await send_message(context, update, msg, ParseMode.HTML, mainMarkup())
        elif mode == 'calendar_search':
            try:
                msgs = parseCalendarByText(login_data, text)
                for msg in msgs:
                    await send_message(context, update, msg, ParseMode.HTML, mainMarkup())
            except Exception as e:
                eMsg = ''.join(traceback.format_exception(type(e), e, e.__traceback__))
                msg = f"Failed!\nException: {eMsg}"
                logger.error(msg)
                await send_message(context, update, msg, None, mainMarkup())
        elif mode == 'signup':
            parse_signup(context, update, login_data, mainMarkup(), text)

    else:  # no special mode
        m1 = re.match('([A-Za-z0-9äöü ]+): ([A-Za-zäöü]+)', text)
        m2 = re.match('/dl_([0-9]+)_([0-9]+)', text)
        mPerson = re.match('/P([0-9]+)', text)
        mPersonContact = re.match('/C([0-9]+)', text)
        mPersonGroup = re.match('/PG([0-9]+)', text)
        mGroup = re.match('/G([0-9]+)', text)
        mGroupMember = re.match('/GP([0-9]+)', text)
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
                if zeit == 'Nächste 7 Tage':
                    msgs = await parseRaeumeByTime(login_data, room, dayRange=7)
                elif text == 'Heute':
                    msgs = await parseRaeumeByTime(login_data, None, dayRange=0)
                elif text == 'Morgen':
                    msgs = await parseRaeumeByTime(login_data, None, dayRange=0, dayOffset=1)
                for msg in msgs:
                    await send_message(context, update, msg, ParseMode.HTML, mainMarkup())
            except Exception as e:
                eMsg = ''.join(traceback.format_exception(type(e), e, e.__traceback__))
                msg = f"Failed!\nException: {eMsg}"
                logger.error(msg)
                await send_message(context, update, msg, None, mainMarkup())
        elif m2:
            song_id = m2.group(1)
            file_id = m2.group(2)
            await song(context, update, file_id, login_data, mainMarkup(), song_id)
        elif mPerson:
            await person(context, update, text, mainMarkup(), login_data, include_pi=include_pi)
        elif mPersonContact:
            await person(context, update, text, mainMarkup(), login_data, include_pi=include_pi, contact=True)
        elif mPersonGroup:
            try:
                (error, data) = await getAjaxResponse("db", "getAllPersonData", login_data=login_data, timeout=24 * 3600)
                if not data:
                    msg = '<i>Konnte Daten nicht abrufen!</i>'
                else:
                    p_id = mPersonGroup.group(1)
                    p = data[p_id] if p_id in data else None
                    if p:
                        msg = await printPersonGroups(login_data, p)
                    else:
                        msg = '<i>Person nicht gefunden.</i>'
                await send_message(context, update, msg, ParseMode.HTML, mainMarkup())
            except Exception as e:
                eMsg = ''.join(traceback.format_exception(type(e), e, e.__traceback__))
                msg = f"Failed!\nException: {eMsg}"
                logger.error(msg)
                await send_message(context, update, msg, None, mainMarkup())
        elif mGroup:
            group(context, update, text, mainMarkup(), login_data=login_data)
        elif mGroupMember:
            (error, data) = await getAjaxResponse("db", "getAllPersonData", login_data=login_data, timeout=24 * 3600)
            (errorMaster, masterData) = await getAjaxResponse("db", "getMasterData", login_data=login_data, timeout=None)
            if not data or not masterData:
                parts = ['<i>Konnte Daten nicht abrufen!</i>']
            else:
                g_id = mGroupMember.group(1)
                parts = print_group_members(login_data, masterData=masterData, persons=data, g_id=g_id)
            for part in parts:
                await send_message(context, update, part, ParseMode.HTML, mainMarkup())
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
                                      parse_mode=ParseMode.HTML, reply_markup=mainMarkup(),
                                      timeout=30)
                except Exception as e:
                    await send_message(context, update,
                                 "<i>Konnte QR-Code nicht senden :(</i>\n" + str(e),
                                 ParseMode.HTML,
                                 mainMarkup())
            else:
                await send_message(context, update,
                             "<i>Konnte QR-Code nicht abrufen :(</i>\n",
                             ParseMode.HTML,
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
                await send_message(context, update, msg, ParseMode.HTML, mainMarkup())

            except Exception as e:
                eMsg = ''.join(traceback.format_exception(type(e), e, e.__traceback__))
                msg = f"Failed!\nException: {eMsg}"
                logger.error(msg)
                await send_message(context, update, msg, None, mainMarkup())
        elif mAgenda:
            a_id = mAgenda.group(1)
            agenda(context, update, login_data, a_id, mainMarkup())

        elif text == MARKUP_ROOMS:
            redis.set(mode_key(update), 'rooms')
            await send_message(context, update, "Welcher Zeitraum?", ParseMode.HTML,
                         ReplyKeyboardMarkup([RAUM_ZEIT_MARKUP, RAUM_EXTENDED_MARKUP]))
        elif text == MARKUP_CALENDAR:
            redis.set(mode_key(update), 'calendar')
            await send_message(context, update, "Welcher Zeitraum?", ParseMode.HTML,
                         ReplyKeyboardMarkup([RAUM_ZEIT_MARKUP, RAUM_EXTENDED_MARKUP]))
        elif text == MARKUP_BIRTHDAYS:
            try:
                msg = await parseGeburtstage(login_data=login_data)
                await send_message(context, update, msg, ParseMode.HTML, mainMarkup())
            except Exception as e:
                msg = f"Failed!\nException: {e}"
                logger.error(msg)
                await send_message(context, update, msg, None, mainMarkup())
        elif text == MARKUP_SONGS:
            redis.set(mode_key(update), 'song')
            await send_message(context, update, "Gib den Namen/Author (oder einen Teil davon ein):", None,
                         EMPTY_MARKUP)
        elif text == MARKUP_PEOPLE:
            redis.set(mode_key(update), 'person')
            await send_message(context, update, "Gib den Namen (oder einen Teil ein) oder eine Telefonnumer ein:",
                         None, EMPTY_MARKUP)
        elif text == MARKUP_GROUPS:
            redis.set(mode_key(update), 'group')
            await send_message(context, update, "Gib den Namen (oder einen Teil ein):", None, EMPTY_MARKUP)
        elif text == MARKUP_EVENTS:
            list_events(context, login_data, mainMarkup(), update)
        else:
            await send_message(context, update,
                         "Unbekannter Befehl, du kannst einen der Buttons unten nutzen", None, mainMarkup())


if __name__ == '__main__':
    logger.info("Telegram bot starting..")

    application = ApplicationBuilder().token(os.environ.get('BOT_TOKEN')).rate_limiter(AIORateLimiter()).build()
    
    #start_handler = CommandHandler('start', start)
    #application.add_handler(start_handler)
    application.add_handler(MessageHandler(filters.TEXT | filters.COMMAND, message))
    application.add_handler(MessageHandler(filters.PHOTO | filters.ATTACHMENT, photo))
    application.add_handler(CallbackQueryHandler(button))
    # updater.dispatcher.add_handler(CallbackQueryHandler(confirm_value))
    
    logger.info("Starting updater..")
    application.run_polling()

    #q = mq.MessageQueue(all_burst_limit=20, all_time_limit_ms=2017)
    ## set connection pool size for bot
    #request = Request(con_pool_size=8)
    #mqbot = MQBot(os.environ.get('BOT_TOKEN'),
    #              request=request,
    #              mqueue=q)
    #mqbot.logger = tglogger
    #updater = telegram.ext.updater.Updater(bot=mqbot)
    ## updater.dispatcher.add_handler(CommandHandler('start', start))


    ## updater.dispatcher.add_handler()

    #updater.start_polling()
