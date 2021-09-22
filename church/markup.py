import os

from telegram import InlineKeyboardMarkup, InlineKeyboardButton, ReplyKeyboardMarkup, ReplyKeyboardRemove

MAIN_URL = os.environ.get('CHURCH_URL', 'https://feg-karlsruhe.church.tools/')

MARKUP_ROOMS = '🏠 Räume'
MARKUP_CALENDAR = '🗓 Kalender'
MARKUP_BIRTHDAYS = u'\U0001F382 Geburtstage'
MARKUP_PEOPLE = u'\U0001F464 Personen'
MARKUP_GROUPS = u'\U0001F465 Gruppen'
MARKUP_SONGS = u'\U0001F3BC Lieder'
MARKUP_EVENTS = '\U0001F465 Veranstaltungen (Beta)'
MARKUP_PC = u'Jetzt einloggen!'
MARKUP_PHONE = u'\U0001F4F1 Handy'
MARKUP_SIGNUP_YES = u'✅ Anmelden'
MARKUP_SIGNUP_NO = u'❌ Abbrechen'
LOGIN_MARKUP = InlineKeyboardMarkup([[
        InlineKeyboardButton(MARKUP_PC, callback_data='PC')]])


def mainMarkup():
    custom_keyboard = [[MARKUP_ROOMS,
                        MARKUP_CALENDAR,
                        MARKUP_BIRTHDAYS],
                       [MARKUP_PEOPLE, MARKUP_SONGS, MARKUP_GROUPS],
                       [MARKUP_EVENTS]]
    return ReplyKeyboardMarkup(custom_keyboard)


RAUM_ZEIT_MARKUP_SIMPLE = ['Heute', 'Morgen']
RAUM_ZEIT_MARKUP_EXTENDED = ['Nächste 7 Tage']
RAUM_ZEIT_MARKUP = RAUM_ZEIT_MARKUP_SIMPLE + RAUM_ZEIT_MARKUP_EXTENDED
RAUM_EXTENDED_MARKUP = ['Suche']
EMPTY_MARKUP = ReplyKeyboardRemove()