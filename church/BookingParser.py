import datetime
import json
import pickle
from collections import namedtuple

from dateutil.rrule import rruleset, rrule, DAILY, WEEKLY, MONTHLY, weekday, YEARLY

from church import redis
from church.ChurchToolsRequests import getAjaxResponse, logging
from church.config import BOOKINGS_SEARCH_MAX
from church.utils import get_cache_key

logger = logging.getLogger(__name__)


class BookingParser:
    Range = namedtuple('Range', ['start', 'end'])

    def __init__(self, login_data, module, func, cache_key):
        self.login_data = login_data
        self.module = module
        self.func = func
        self.cache_key = cache_key

    def sortBookings(self, entries):
        return sorted(entries, key=lambda b: (b['start'].date(), b['start']))

    def getEntries(self, dayRange=8, dayOffset=0, **kwargs):
        key = get_cache_key(self.login_data, self.cache_key, dayRange=dayRange, dayOffset=dayOffset, useDate=True, **kwargs)
        logger.debug(key)
        entries = self._loadCache(key)
        error = None
        if entries is None:
            (error, bookings) = self.getAllBookings()
            #logger.debug(bookings)
            if not bookings:
                return error if error else 'Konnte Buchungen nicht laden', None
            Range = namedtuple('Range', ['start', 'end'])
            # week = Range(start=datetime.now(), end=datetime.now() + timedelta(days=8))
            entries = []
            for booking, rules, start, duration in bookings:
                # print(list(rules))
                search_range_start = datetime.datetime.combine(datetime.datetime.now().date() + datetime.timedelta(days=dayOffset), datetime.time(0, 0))
                search_range_end = datetime.datetime.combine(datetime.datetime.now().date() + datetime.timedelta(days=dayOffset + dayRange), datetime.time(23, 59))

                # Check if previous range overlaps
                rule = rules.before(search_range_start, inc=False)
                if rule:
                    rule_start = datetime.datetime.combine(rule, start.time())
                    rule_end = rule_start + duration
                    if rule_end > search_range_start:
                        for day in range(min((rule_end.date() - search_range_start.date()).days, dayRange) + 1):
                            r = Range(start=search_range_start + datetime.timedelta(days=day), end=rule_start + duration)
                            entries.append(self._make_entry(r, booking))

                # Check if rule is inside of search range
                for rule in rules.between(search_range_start, search_range_end, inc=True):
                    rule_start = datetime.datetime.combine(rule, start.time())
                    r = Range(start=rule_start, end=rule_start + duration)
                    entries.append(self._make_entry(r, booking))
            entries = self.sortBookings(entries, **kwargs)
            if not error:
                redis.set(key, pickle.dumps(entries), ex=24 * 3600)
        return error, entries

    def searchEntries(self, text):
        text = text.lower()
        entries = []
        error, bookings = self.getEntries(dayRange=365)
        toomany = False
        for booking in bookings:
            if 'status_id' in booking and int(booking['status_id']) == 99:
                continue
            actual_booking = booking['booking']

            if any(key in actual_booking and actual_booking[key] and text in actual_booking[key].lower()
                   for key in self._get_search_keys()):
                #entries += self._parseBookings(booking)
                entries.append(booking)
                if len(entries) >= BOOKINGS_SEARCH_MAX:
                    toomany = True
                    break
        # entries = self.sortBookings(entries)
        toomanymsg = f"Zu viele Ergebnisse, zeige die ersten {BOOKINGS_SEARCH_MAX}."
        if toomany:
            error = error + toomanymsg if error else toomanymsg
        return error, entries

    def _loadCache(self, key):
        entr_str = redis.get(key)
        return pickle.loads(entr_str) if entr_str else None
    def _parseBookings(self, booking):
        rules, start, duration = self._parseBooking(booking)
        entr = []
        for rule in rules:
            rule_start = datetime.datetime.combine(rule, start.time())
            r = self.Range(start=rule_start, end=rule_start + duration)
            entr.append(self._make_entry(r, booking))
        return entr

    def getAllBookings(self, *args, **kwargs):
        raise NotImplementedError('getAllBookings is not implemented!')

    def getBooking(self, key, value):
        (error, entries) = self.getAllBookings()
        for (booking, rules, start, duration) in entries:
            if booking[key] == value:
                return booking
        return None

    def _ajaxResponse(self, **kwargs):
        return getAjaxResponse(self.module, self.func, login_data=self.login_data, **kwargs)

    def _date_parse(self, t):
        return datetime.datetime.strptime(t, "%Y-%m-%d %H:%M:%S")

    def check_range(week, r):
        latest_start = max(r.start, week.start)
        earliest_end = min(r.end, week.end)
        overlap = (earliest_end - latest_start).days + 1
        return overlap > 0

    def _parseBooking(self, booking):
        start = self._date_parse(booking['startdate'])
        # if start.date() != date(2017,12, 11):
        #   continue
        # print(json.dumps(booking, indent=2))
        start_date = datetime.datetime.combine(start, datetime.time(0, 0))
        end = self._date_parse(booking['enddate'])
        duration = end - start
        rules = rruleset()
        repeat_id = int(booking['repeat_id'])
        if repeat_id != 0 and repeat_id != 999:
            repeat_until = self._date_parse(booking['repeat_until'])
            repeat_freq = int(booking['repeat_frequence'])
            # print("Type: %s, Freq: %s, Start: %s, Until: %s" % (repeat_id, repeat_freq, start, repeat_until))
            if repeat_id == 1:  # daily
                rules.rrule(rrule(DAILY, dtstart=start_date, until=repeat_until, interval=repeat_freq))
            if repeat_id == 7:  # weekly
                # print("Start: %s\nUntil: %s\nInterval: %s" % (start, repeat_until, repeat_freq))
                rules.rrule(rrule(WEEKLY, dtstart=start_date, interval=repeat_freq, until=repeat_until))
            elif repeat_id == 31:  # monthly by datetime
                rules.rrule(rrule(MONTHLY, dtstart=start_date, until=repeat_until, interval=repeat_freq))
            elif repeat_id == 32:  # monthly by weekday
                repeat_option_id = int(booking['repeat_option_id']) if booking['repeat_option_id'] else 0
                if repeat_option_id == 6:
                    raise NotImplementedError(
                        "Error: repeat_option_id == 6 not implemented! Booking:\n%s" % json.dumps(booking, indent=2))

                # nthweekOfMonth = (start.day - 1) // 7 + 1
                nthweekOfMonth = repeat_option_id
                # print(nthweekOfMonth)
                rule = rrule(MONTHLY,
                             dtstart=start_date,
                             until=repeat_until,
                             interval=repeat_freq,
                             byweekday=weekday(start.weekday())(+nthweekOfMonth))
                # print(rule)
                rules.rrule(rule)
            elif repeat_id == 365:
                rules.rrule(rrule(YEARLY, dtstart=start_date, until=repeat_until, interval=repeat_freq))
        elif repeat_id in [0, 999]:
            # print("Simple: %s" % start_date)
            rules.rdate(start_date)
        else:
            raise NotImplementedError(
                "Error: Repeat Frequency is not implemented! Booking:\n%s" % json.dumps(booking, indent=2))
            print("Error: Repeat Frequency %s:\n%s" % (repeat_freq, json.dumps(booking, indent=2)))
        if 'additions' in booking and booking['additions']:
            adds = booking['additions']
            for a in adds:
                addition = adds[a]
                add_date = datetime.datetime.combine(self._date_parse(addition['add_date']), datetime.time(0, 0))
                # print("Addition: %s" % add_date)
                rules.rdate(add_date)
        if 'exceptions' in booking and booking['exceptions']:
            # print(booking)
            exceptions = booking['exceptions']
            for exc in exceptions:
                exception = exceptions[exc]

                exc_start = self._date_parse(exception['except_date_start'])
                exc_end = self._date_parse(exception['except_date_end'])
                # print("Exception: %s" % exc_start)
                if exc_start != exc_end:
                    print("Exception has different start and end: %s" % exception)
                rules.exdate(datetime.datetime.combine(exc_start, datetime.time(0, 0)))
        return rules, start, duration

    def _make_entry(self, r, booking):
        return {
            'start': r.start,
            'end': r.end,
            'descr': booking['text'],
            'accepted': booking['status_id'] == '2',
            'room': booking['bezeichnung'].strip(),
            'room_num': int(booking['resource_id']),
            'booking': booking,
        }
    def _get_search_keys(self):
        return []
