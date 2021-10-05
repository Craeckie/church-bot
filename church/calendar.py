import datetime
import logging
import pickle
import re
import traceback

import telegram

from church import redis
from church.CalendarBookingParser import CalendarBookingParser
from church.config import CALENDAR_LIST_DESCRIPTION_LIMIT
from church.markup import RAUM_ZEIT_MARKUP, mainMarkup, EMPTY_MARKUP
from church.utils import send_message

logger = logging.getLogger(__name__)

def calendar(context, update, login_data, mode_key, text):
    try:
        if text in RAUM_ZEIT_MARKUP:
            if text == 'Heute':
                msgs = parseCalendarByTime(login_data, dayRange=0)
            elif text == 'Nächste 7 Tage':
                msgs = parseCalendarByTime(login_data, dayRange=7)
            elif text == 'Morgen':
                msgs = parseCalendarByTime(login_data, dayRange=0, dayOffset=1)
            for msg in msgs:
                send_message(context, update, msg, telegram.ParseMode.HTML, mainMarkup())
        elif text == 'Suche':
            redis.set(mode_key, 'calendar_search')
            send_message(context, update,
                         "Gib den Namen des Kalendereintrags (oder einen Teil davon ein):",
                         None,
                         EMPTY_MARKUP)
    except Exception as e:
        eMsg = ''.join(traceback.format_exception(type(e), e, e.__traceback__))
        msg = f"Failed!\nException: {eMsg}"
        logger.error(msg)
        send_message(context, update, msg, None, mainMarkup())

def parseCalendarByText(login_data, search):
    parser = CalendarBookingParser(login_data)
    error, entr = parser.searchEntries(search)
    if entr is None:
        return ["Konnte Daten nicht abrufen!"]

    text = printCalendarEntries(entr,  withWeekNumbers=False, printHeute=False, fullDate=True)
    if not text:
        text = ["Keine Einträge gefunden!"]
    text[0] = f"Suche nach <b>{search}</b>:\n" + text[0]
    if error:
        text[-1] = text[-1] + f'\n<i>{error}</i>'
    return text

def parseCalendarByTime(login_data, dayRange=7, dayOffset=0):
    parser = CalendarBookingParser(login_data)

    error, entries = parser.getEntries(dayRange, dayOffset)
    if entries is None:
        return ["Konnte Daten nicht abrufen!"]

    text = printCalendarEntries(entries, printHeute=dayOffset == 0)
    if error:
        text[-1] = text[-1] + f'\n<i>{error}</i>'
    return text


def printCalendarEntries(entr, sortByCategory=True, withWeekNumbers=False, printHeute=True, fullDate=False):
    now = datetime.datetime.now()
    cur_part = "<i>%s (Heute)</i>\n" % now.strftime("%A") if printHeute else ''
    cur_date = now.date()
    not_accepted_hint = False
    parts = []
    isEmpty = True
    cur_category = None
    for e in entr:
        start = e['start']
        end = e['end']
        # print(e)
        if start.date() != cur_date:
            if isEmpty and printHeute:
                cur_part += "<i>Keine Einträge</i>\n"
            if len(cur_part) > 2000:
                # print(f"cur_part ({len(cur_part)}): {cur_part}")
                parts.append(cur_part)
                cur_part = ""
            if withWeekNumbers:
                weekNum = start.weekday() + 1
                cur_part += "\n<i>%s (%s)</i>\n" % (start.strftime("%A"), weekNum)
            else:
                cur_part += "\n<i>%s" % start.strftime("%A")
                if abs(start.date() - cur_date) > datetime.timedelta(days=1):
                    cur_part += " (%s)" % start.strftime("%d.%m.%y" if fullDate else "%d.%m")
                cur_part += "</i>\n"
            cur_date = start.date()
            cur_category = None
        isEmpty = False
        if start.date() == end.date():
            end_str = end.strftime("%H:%M")
        else:
            end_str = end.strftime("%d.%m %H:%M")

        if sortByCategory:
            if cur_category != e['category']:
                cur_part += f"<code>{e['category']}</code>\n"
                cur_category = e['category']
            description = e['descr']
            if len(description) > CALENDAR_LIST_DESCRIPTION_LIMIT:
                description = description[:CALENDAR_LIST_DESCRIPTION_LIMIT - 5] + '..'
            new_text = "{start}-{end}: {descr}".format(start=start.strftime("%H:%M"), end=end_str, room=e['category'],
                                                       descr=description)
            if e['event_id']:
                event_id = e['event_id']
                booking = e['booking']
                if 'csevents' in booking and event_id in booking['csevents'] \
                    and 'eventTemplate' in booking['csevents'][event_id] and booking['csevents'][event_id]['service_texts']:
                    new_text += f" /A{e['event_id']}"
        else:
            new_text = "{start}-{end} <code>{room}</code>: {descr}".format(start=start.strftime("%H:%M"), end=end_str,
                                                                           room=e['category'], descr=e['descr'][:30])
        # new_text = "{start}-{end}: {descr}".format(start=start.strftime("%H:%M"), end=end_str, descr=e['descr'][:30])
        if e['accepted'] == False:
            # print("Not accepted")
            new_text = "<i>%s*</i>" % re.sub(r'</?code>', '', new_text, flags=re.IGNORECASE)  # italic text
            not_accepted_hint = True
        # print(new_text)
        cur_part += "%s\n" % new_text
    if not entr:
        cur_part += "<i>Keine Einträge</i>"
    if not_accepted_hint:
        cur_part += "<i>* nicht bestätigt</i>\n"

    if cur_part:
        parts.append(cur_part)
    return parts

