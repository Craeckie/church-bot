import pickle

from church import redis
from church.BookingParser import BookingParser
from church.ChurchToolsRequests import getAjaxResponse
from church.utils import get_cache_key


class RoomBookingParser(BookingParser):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, cache_key='room_bookings', module='resource', func='getBookings', **kwargs)

    def sortBookings(self, entries, subset='Alle', sortByRoom=False):
        sortDict = self.room_all_sorting
        if subset == 'Saal':
            entries = [e for e in entries if e['room_num'] in [7, 9, 21]]
            sortDict = self.room_saal_sorting
        elif subset == 'Nebenräume':
            entries = [e for e in entries if e['room_num'] in self.room_neben_sorting.keys()]
            sortDict = self.room_neben_sorting
        elif subset == 'Rest':
            entries = [e for e in entries if e['room_num'] in self.room_rest_sorting.keys()]
            sortDict = self.room_rest_sorting
        else:  # Alle
            for e in entries:
                if e['room_num'] not in self.room_all_sorting.keys():
                    print(f"Warning: Room {e['room_num']} is not in sort dict!")
            sortDict = self.room_all_sorting
            # text = ["Unknown room type.."]

        if sortByRoom:
            entries = sorted(entries, key=lambda b: (
                sortDict[b['room_num']] if b['room_num'] in sortDict.keys() else 999, b['start']))
        else:
            entries = sorted(entries, key=lambda b: (
                b['start'], sortDict[b['room_num']] if b['room_num'] in sortDict.keys() else 999, b['start']))
        return entries

    def getAllBookings(self):
        key = get_cache_key(self.login_data, self.cache_key, useDate=True)
        entries = self._loadCache(key)
        if not entries:
            entries = []
            (error, data) = self._ajaxResponse()
            if not data:
                return error, entries
            for b in data:
                booking = data[b]
                if int(booking['status_id']) == 99:
                    continue
                rules, start, duration = self._parseBooking(booking)
                entries.append((booking, rules, start, duration))
            if not error:
                redis.set(key, pickle.dumps(entries), ex=12 * 3600)
            return error, entries
        return None, entries

    room_saal_sorting = {
        7: 1,  # EG großer Saal [Hz]
        9: 2,  # EG Foyer [Hz]
        20: 3,  # EG 2. Foyer [Hz]
        21: 4,  # EG Küche unten
    }
    room_neben_sorting = {
        # 7: , # EG großer Saal [Hz]
        # 9: , # EG Foyer [Hz]
        # 10: , # NEC - Beamer 1
        # 11: , # Kleine Anlage (Mischpult)
        22: 1,  # EG Kükennest
        44: 2,  # EG Mehrzweckraum
        23: 3,  # EG Eckzimmer (Seminarraum)
        24: 4,  # EG Rabennest
        25: 5,  # EG Aquarium
        29: 6,  # OG Küche oben
        26: 7,  # OG Gelber Salon
        30: 8,  # OG Besprechungszimmer
        31: 9,  # OG Gesprächsraum (Offenes Ohr)
        34: 10,  # DG Entdeckerkämp
        13: 11,  # KG Minikämp-Raum
        14: 12,  # KG Jugendraum/Minikämp
        15: 13,  # KG Bar Deeper
        # 20: , # EG 2. Foyer [Hz]
        # 21: , # EG Küche unten
        # 35: , # GA Garten
        # 36: , # GA Container groß [Hz]
        # 37: , # GA Container klein [Hz]
        # 41: , # Übersetzungs-Koffer 1
        # 43: , # Reiskocher
        # 45: , # Seminarraum Büro Kaiserstr.
    }
    room_rest_sorting = {
        10: 1,  # NEC - Beamer 1
        11: 2,  # Kleine Anlage (Mischpult)

        35: 5,  # GA Garten
        36: 6,  # GA Container groß [Hz]
        37: 7,  # GA Container klein [Hz]
        41: 8,  # Übersetzungs-Koffer 1
        42: 9,  # Übersetzungs-Koffer 2
        43: 10,  # Reiskocher
        45: 11,  # Seminarraum Büro Kaiserstr.
        39: 12,  # Gemeindebüro FeG Karlsruhe
    }
    room_all_sorting = room_saal_sorting.copy()

    room_all_sorting.update({k: v + 5 for k, v in room_neben_sorting.items()})
    room_all_sorting.update({k: v + 30 for k, v in room_rest_sorting.items()})

    def _get_search_keys(self):
        return ['text', 'location', 'note', 'person_name']
