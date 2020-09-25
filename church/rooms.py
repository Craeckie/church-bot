import pickle
import re
from collections import namedtuple
from datetime import time, timedelta, datetime
from urllib.parse import urljoin

from church import utils
from church.RoomBookingParser import RoomBookingParser

logger = utils.logging.getLogger(__name__)

room_markup = ['Alle',
               'Saal',
               'Nebenräume',
               'Rest']

def _get_day_link(login_data, date):
    return urljoin(login_data['url'], f'?q=churchresource&curdate={date:%Y-%m-%d}')

def printRaeumeEntries(login_data, entr, withWeekNumbers=False, sortByRoom=False, printHeute=True, fullDate=False):
    now = datetime.now()
    cur_part = ''
    cur_date = now.date()
    cur_room = None
    not_accepted_hint = False
    parts = []
    firstEntry = True
    for e in entr:
        start = e['start']
        end = e['end']
        # print(e)
        if firstEntry and (start.date() == cur_date or (start.date() != cur_date and printHeute)):
            cur_part = f'<a href="{_get_day_link(login_data, now)}">{now:%A} (Heute)</a>\n'
        if start.date() != cur_date:
            if firstEntry and printHeute:
                cur_part += "<i>Keine Einträge</i>\n"
            if len(cur_part) > 2000:
                print(f"cur_part ({len(cur_part)}): {cur_part}")
                parts.append(cur_part)
                cur_part = ""
            if withWeekNumbers:
                weekNum = start.weekday() + 1
                cur_part += f'\n<a href="{_get_day_link(login_data, start)}">{start:%A} ({weekNum})</a>\n'
            else:
                cur_part += f'\n<a href="{_get_day_link(login_data, start)}">{start:%A}'
                if abs(start.date() - cur_date) > timedelta(days=1):
                    cur_part += " (%s)" % start.strftime("%d.%m.%y" if fullDate else "%d.%m")
                cur_part += "</a>\n"
            cur_date = start.date()
            cur_room = None

        firstEntry = False
        if start.date() == end.date():
            end_str = end.strftime("%H:%M")
        else:
            end_str = end.strftime("%d.%m %H:%M")

        if sortByRoom:
            if cur_room != e['room']:
                cur_part += f"<code>{e['room']}</code>\n"
                cur_room = e['room']
            new_text = "{start}-{end}: {descr}".format(start=start.strftime("%H:%M"), end=end_str, room=e['room'],
                                                       descr=e['descr'][:30])
        else:
            new_text = "{start}-{end} <code>{room}</code>: {descr}".format(start=start.strftime("%H:%M"), end=end_str,
                                                                           room=e['room'], descr=e['descr'][:30])
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

def parseRaeumeByText(redis, login_data, search):
    parser = RoomBookingParser(redis, login_data)
    error, entr = parser.searchEntries(search)
    if not entr:
        return ["Konnte Daten nicht abrufen!"]

    text = printRaeumeEntries(login_data, entr, withWeekNumbers=False, sortByRoom=False, printHeute=False, fullDate=True)
    if not text:
        text = ["Keine Buchungen gefunden!"]
    text[0] = f"Suche nach <b>{search}</b>:\n" + text[0]
    if error:
        text[-1] = text[-1] + f'\n<i>{error}</i>'
    return text

def parseRaeumeByTime(redis, login_data, subset, dayRange=7, dayOffset=0):
    parser = RoomBookingParser(redis, login_data)
    error, entr = parser.getEntries(dayRange, dayOffset, subset=subset, sortByRoom=dayRange == 0)
    if entr is None:
        return ["Konnte Daten nicht abrufen!"]

    logger.debug(error)
    logger.debug(entr)

    text = printRaeumeEntries(login_data, entr, withWeekNumbers=True, sortByRoom=dayRange == 0, printHeute=dayOffset == 0)

    if not text:
        text = ["Keine Buchungen!"]
    text[0] = f"<b>{subset}</b>\n" + text[0]
    if error:
        text[-1] = text[-1] + f'\n<i>{error}</i>'
    return text

