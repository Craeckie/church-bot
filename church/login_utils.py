import json
import re
from io import BytesIO

import telegram
from PIL import Image
from pyzbar.pyzbar import decode
from pyzbar.wrapper import ZBarSymbol
from telegram import Update, InlineKeyboardMarkup, InlineKeyboardButton, InputMediaPhoto
from telegram.ext import CallbackContext

from church import ChurchToolsRequests, redis
from church.ChurchToolsRequests import get_user_login_key

from church.utils import send_message
from church.markup import MARKUP_PC, MARKUP_PHONE, mainMarkup, LOGIN_MARKUP, MAIN_URL


def button(update: Update, context: CallbackContext) -> None:
    query = update.callback_query

    # CallbackQueries need to be answered, even if no notification to the user is needed
    # Some clients may have trouble otherwise. See https://core.telegram.org/bots/api#callbackquery
    query.answer()

    if query.data == 'PHONE':
        photo_path = 'church/login-help.png'
        markup = InlineKeyboardMarkup([[InlineKeyboardButton(MARKUP_PC, callback_data='PC')]])
        msg = 'Geh auf die Webseite von Churchtools. ' \
              f'Für die FeG-Karlsruhe ist das <a href="{MAIN_URL}">{MAIN_URL}</a>.\n' \
              "Log dich dort ein, dann\n(1) rechts oben auf deinen Namen/Bild->ChurchTools App:\n" \
              "(2) Lange auf den blauen Link klicken, (3) URL <b>kopieren</b> und hier als Nachricht schicken\n" \
              "Falls das nicht geht, kannst dus auch mit " + MARKUP_PC + " probieren\n" \
              "Bei Fragen/Problemen kannst du mir gerne ne Nachricht schreiben: @craeckie"

    else:  # PC
        photo_path = 'church/QR-Photo.jpg'
        markup = InlineKeyboardMarkup([[InlineKeyboardButton(MARKUP_PHONE, callback_data='PHONE')]])
        msg = 'Zum 🔑Einloggen brauchst du den QR-Code für die ChurchTools-App. Die ChurchTools-App selber brauchst du nicht.\n' \
              '(1) Geh auf die Webseite von Churchtools. ' \
              f'Für die FeG-Karlsruhe ist das <a href="{MAIN_URL}">{MAIN_URL}</a>.\n' \
              'Log dich dort ein, dann geh auf Namen->ChurchTools App.\n' \
              'Dann hast du zwei Möglichkeiten:\n' \
              '(2a) Einen Screenshot (mit der "Druck"-Taste) machen. Der QR-Code muss vollständig sichtbar sein.\n' \
              '(2b) Oder: Mach mit deinem \U0001F4F1Handy ein 📸Photo vom QR-Code.\n' \
              '(3) Dann sende den Screenshot/Photo vom QR-Code hier als Nachricht. Dann bist du eingeloggt 😊\n\n' \
              'Bei Fragen oder Problemen kannst du mir gerne ne Nachricht schreiben: @craeckie\n\n' \
              '<i>Findest du das auch sehr umständlich?😳 Dann gib mir im ' \
              '<a href="https://forum.church.tools/topic/7564/feature-request-login-mit-oauth">ChurchTools-Forum</a> ein 👍, damit sie das verbessern 🙃</i>'

    with open(photo_path, 'rb') as f:
        if query.message.photo:
            query.edit_message_media(media=InputMediaPhoto(media=f, caption=msg, parse_mode=telegram.ParseMode.HTML))
        else:
            query.delete_message()
            context.bot.send_photo(update.effective_message.chat_id, photo=f, caption=msg,
                           parse_mode=telegram.ParseMode.HTML)


def photo(update, context):
    # try:
    bot = context.bot
    ps = update.message.photo
    if len(ps) >= 1:
        for p in reversed(ps):
            try:
                file = context.bot.get_file(p.file_id)
                file_data = BytesIO(file.download_as_bytearray())
                data = decode(Image.open(file_data), symbols=[ZBarSymbol.QRCODE])
                login_data = None
                if len(data) >= 1:
                    login_data = parseQRData(data[0].data, update.message.from_user.id)
                if login_data:
                    login(context, update, login_data)
                    return
            except Exception as e:
                pass

    send_message(context, update,
                 "Konnte keinen QR-Code finden.\nBitte erneut versuchen.", None,
                 reply_markup=mainMarkup())
    #
    # except


def parseQRData(data, user_id):
    login_data = None
    try:
        json_data = json.loads(data)
        login_data = {
            'url': json_data['instanceUrl'],
            'token': json_data['loginstring'],
            'personid': json_data['personId'],
            'telegramid': user_id,
        }
    except:
        pass
    return login_data


def check_login(context, update, text, firstTime=True):
    if text.strip().startswith('churchtools://'):
        m = re.match("churchtools://login\?instanceurl=([^&]+)&loginstring=([^&]+)&personid=([0-9]+)", text)
        if m:
            login_data = {
                'url': m.group(1),
                'token': m.group(2),
                'personid': m.group(3),
                'telegramid': update.message.from_user.id,
            }
            login(context, update, login_data)
    elif text.strip().startswith('{') and text.strip().endswith('}'):
        login_data = parseQRData(data=text.strip(), user_id=update.message.from_user.id)
        if login_data:
            login(context, update, login_data)
        else:
            send_message(context, update,
                         "Die Daten scheinen ungültig zu sein. Sende am besten ein Foto vom QR-Code.", None, reply_markup=LOGIN_MARKUP)
    else:
        if firstTime:
            msg = "Willkommen beim inoffiziellen ChurchTools-Bot!\n" \
                  "Zuerst musst du dich bei ChurchTools <b>einloggen</b>, das musst du nur <b>einmal</b> machen.\n" \
                  "Dafür brauchst du einen Laptop oder PC\n"
        else:
            msg = "Leider ist dein Login-Token nicht mehr gültig (hast du dein Passwort geändert?) und du musst dich neu einloggen.\n"
        send_message(context, update,
                     msg + "Klicke auf den Knopf unten, um mit dem Login fortzufahren:",
                     parse_mode=telegram.ParseMode.HTML, reply_markup=LOGIN_MARKUP)


def login(context, update, login_data):
    login_key = get_user_login_key(update.message.from_user.id)
    reply_markup = mainMarkup()
    try:
        success, cookies = ChurchToolsRequests.login(login_data, updateCache=True, login_token=True)
        if success:
            redis.set(login_key, json.dumps(login_data))
            msg = "Du bist erfolgreich eingeloggt! :)\n" \
                  "Du kannst jetzt die Buttons unten nutzen, um Funktionen von ChurchTools aufzurufen. " \
                  "Falls da keine Buttons sind, musst den im Bild markierten Knopf drücken."
            with open('church/logged-in.png', 'rb') as f:
                context.bot.send_photo(update.message.chat_id, photo=f, caption=msg,
                               parse_mode=telegram.ParseMode.HTML, reply_markup=reply_markup)
        else:
            redis.delete(login_key)
            send_message(context, update,
                         "Login fehlgeschlagen!\nBitte versuch es nochmal mit einem neuen Link.", None,
                         reply_markup)
    except Exception as e:
        send_message(context, update,
                     "Login fehlgeschlagen!\nBitte versuch es nochmal mit einem neuen Link.", None,
                     reply_markup)
