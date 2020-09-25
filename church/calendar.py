import datetime
import pickle
import re

from church.CalendarBookingParser import CalendarBookingParser

def parseCalendarByText(redis, login_data, search):
    parser = CalendarBookingParser(redis, login_data)
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

def parseCalendarByTime(redis, login_data, dayRange=7, dayOffset=0):
    parser = CalendarBookingParser(redis, login_data)

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
            new_text = "{start}-{end}: {descr}".format(start=start.strftime("%H:%M"), end=end_str, room=e['category'],
                                                       descr=e['descr'][:30])
            if e['event_id']:
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
