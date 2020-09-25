import pickle
from datetime import datetime

from church.BookingParser import BookingParser
from church.utils import get_cache_key


class CalendarBookingParser(BookingParser):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, cache_key='calendar_bookings', module='cal', func='getCalPerCategory', **kwargs)

    # def searchEntries(self, text):
    #     text = text.lower()
    #     key = get_cache_key(self.cache_key + ':search', text)
    #     entry_data = self._loadCache(key)
    #     if entry_data is None:
    #         entries = []
    #         toomany = False
    #         bookings = self.getEntries(dayRange=365)
    #         for booking in bookings:
    #             if any(key in booking and booking[key] and text in booking[key].lower()
    #                    for key in ['descr', 'place', 'note']):
    #                 entries.append(booking)
    #                 if len(entries) >= 10:
    #                     toomany = True
    #                     break
    #         self.redis.set(key, pickle.dumps((entries, toomany)), ex=12*3600)
    #     else:
    #         entries, toomany = entry_data
    #     return entries, toomany

    def getAllBookings(self):
        self.categories, cat_params = self._getCategories()

        key = get_cache_key(self.login_data, self.cache_key, useDate=True)
        entries = self._loadCache(key)
        if not entries:
            (error, data) = self._ajaxResponse(**cat_params)

            if not data:
                return error, data
            entries = []
            for c in data:
                category = data[c]
                for b in category:
                    booking = category[b]
                    rules, start, duration = self._parseBooking(booking)
                    entries.append((booking, rules, start, duration))
            if not error:
                self.redis.set(key, pickle.dumps(entries), ex=3600 * 12)
            return error, entries
        return None, entries

    def _getCategories(self):
        key = get_cache_key(self.login_data, self.cache_key + 'master_data')
        cat_data = self._loadCache(key)
        if not cat_data:
            (error, data) = super()._ajaxResponse(func='getMasterData', timeout=30 * 24 * 3600)
            if not data:
                return error, data
            categories = data['category']
            cat_params = {}
            ctr = 0
            for c in categories:
                cat_params[f'category_ids[{ctr}]'] = c
                ctr += 1
            cat_data = categories, cat_params
            self.redis.set(key, pickle.dumps(cat_data), ex=7 * 24 * 3600)

        return cat_data

    def sortBookings(self, entries, sortByCategory=True):
        seen = set()
        unique = []
        for entr in entries:
            key = (entr['start'], entr['end'], entr['category'], entr['descr'])
            if key not in seen:
                unique.append(entr)
                seen.add(key)

        if sortByCategory:
            unique = sorted(unique, key=lambda b: (b['start'].date(), b['category_id'], b['start'], b['descr']))
        else:
            unique = sorted(unique, key=lambda b: (b['start'].date(), b['start'], b['descr']))

        return unique

    def _make_entry(self, r, booking):
        event_id = None
        if 'csevents' in booking and booking['csevents']:
            for event_key in booking['csevents']:
                event = booking['csevents'][event_key]
                event_start = self._date_parse(event['startdate'])
                if event_start == r.start:
                    event_id = event_key

        return {
            'id': booking['id'],
            'start': r.start,
            'end': r.end,
            'descr': booking['bezeichnung'],
            'accepted': True,
            'place': booking['ort'].strip() if 'ort' in booking else None,
            'category': self.categories[booking['category_id']]['bezeichnung'],
            'category_id': booking['category_id'],
            'note': booking['notizen'] if 'notizen' in booking else None,
            'booking': booking,
            'event_id': event_id,
        }