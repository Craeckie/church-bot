import logging
import pickle
from datetime import datetime

from church import redis

logger = logging.getLogger(__name__)

def get_cache_key(login_data, *args, useDate=False, usePerson=False, **kwargs):
    parts = list(args) + [login_data['url']]
    if usePerson:
        parts.append(str(login_data['personid']))
    if useDate:
        curDate = str(datetime.today().date())
        parts.append(curDate)
        parts.insert(0, 'temporary')
    parts.append(','.join([f'{k}:{kwargs.get(k)}' for k in kwargs.keys()]))
    return ':'.join(parts)


def loadCache(key):
    entr_str = redis.get(key)
    return pickle.loads(entr_str) if entr_str else None


def send_message(context, update, text, parse_mode, reply_markup):
    try:
        context.bot.send_message(update.message.chat_id, text=text, parse_mode=parse_mode, reply_markup=reply_markup,
                         disable_web_page_preview=True)
    except Exception as e:
        logger.error(f"Sending Message as {parse_mode} failed!\n{text}")
        logger.error(e)


def mode_key(update):
    return f'{update.message.from_user.id}:mode'
