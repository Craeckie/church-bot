import json
import pickle
import re
from datetime import date

from church.utils import getAjaxResponse, getPersonLink, get_cache_key, loadCache


def parseGeburtstage(redis, login_data):
    key = get_cache_key(login_data, 'birthdays', useDate=True)
    msg = loadCache(redis, key)
    if not msg:
        (error, data) = getAjaxResponse(redis, 'home', 'getBlockData', login_data=login_data, timeout=1800)

        if not data:
            print(error)
            return error
        else:
            try:
                html = data['blocks']['birthday']['html']
                # soup = BeautifulSoup(html, 'html.parser')
                # comments = soup.find_all(string=lambda text:isinstance(text, Comment))
                # [comment.extract() for comment in comments]
                # row = str(soup.table.tr)
                split = re.split(
                    "<td><a (data-person-id='[^']+')[^>]+><img[^>]*></a><td[^>]*><a class='tooltip-person'[^>]*>([^<]+)</a><td[^>]*>([0-9]+)</?[^>]+>",
                    html)
                msg = ""
                p_id = None
                for line in split:
                    if not line:
                        continue
                    m = re.search('<th colspan="3">([^<]+)<tr>', line)
                    m2 = re.match('data-person-id=\'([^\']+)\'', line)
                    if m:
                        msg += "<i>%s</i>\n" % m.group(1)
                    elif m2:
                        p_id = m2.group(1)
                        msg += getPersonLink(login_data, p_id)
                    elif re.match('[0-9]+', line):
                        if p_id:
                            msg += f"{line} /P{p_id}\n"
                        else:
                            msg += f"{line}\n"
                        p_id = None
                    elif re.match('[^<>]+', line):
                        msg += "%s</a>: " % line
                if error:
                    msg += f"\n<i>{error}</i>"
                else:
                    redis.set(key, pickle.dumps(msg), ex=3600 * 24)
            except Exception as e:
                return "Error while parsing: %s" % e
    return msg