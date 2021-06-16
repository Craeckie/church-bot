from urllib.parse import urljoin

from .ChurchToolsRequests import getAjaxResponse
from .ChurchToolsRequests import logger


def _print_arrangements(song_id, j, arrangement_id=None):
    ret = ""
    for k in j:
        if not arrangement_id or arrangement_id == k:
            ar = j[k]
            if 'files' not in ar:
                continue
            ret += "\n"

            ret += f"<code>{ar['bezeichnung']}</code>"
            if ar['tonality']:
                ret += f" (<b>{ar['tonality']}</b>)"
            ret += "\n"

            files = ar['files']
            for kf in files:
                file = files[kf]
                ret += f"{file['bezeichnung']} /dl_{song_id}_{file['id']}\n"
                # print(f"{kf}: {files[kf]}")
    return ret

def byID(redis, login_data, song_id, arrangement_id=None):
    (error, data) = getAjaxResponse(redis, 'service', 'getAllSongs', login_data=login_data, timeout=24 * 3600)
    if not data or 'songs' not in data:
        return False, error
    else:
        l = data['songs']
        for k in l:
            if not k:
                continue
            song = l[k]
            if song['id'] == song_id:
                return True, _print_song(song, login_data, arrangement_id=arrangement_id)
    return False, 'Dieses Lied wurde nicht gefunden.'

def search(redis, login_data, name):
    (error, data) = getAjaxResponse(redis, 'service', 'getAllSongs', login_data=login_data, timeout=24 * 3600)
    if not data or 'songs' not in data:
        return False, error
    else:
        l = data['songs']
        songs = []
        for k in l:
            if not k:
                continue
            song = l[k]
            bez = song['bezeichnung']
            author = song['author']
            if name.lower() in bez.lower() or name.lower() in author.lower():
                songs.append(song)

        msgs = []
        cur_msg = ''
        if len(songs) > 20:
            return False, "Zu viele Lieder gefunden. Klicke auf Lieder, um deine Suche zu verfeinern."
        elif len(songs) > 0:
            for song in songs:
                part = _print_song(song, login_data, short=len(songs) > 2)
                if not part:
                    continue
                if cur_msg:
                    cur_msg += "\n"
                cur_msg += part
                if len(cur_msg) > 1500:
                    msgs.append(cur_msg)
                    cur_msg = ""
        else:
            cur_msg = "Kein Lied gefunden."

        if error:
            cur_msg += f'\n<i>{error}</i>'
        if cur_msg:
            msgs.append(cur_msg)
        if msgs:
            return True, msgs
        else:
            return False, msgs


def _print_song(song, login_data, short=False, arrangement_id=None):
    songid = song["id"]
    url = urljoin(login_data['url'], f'?q=churchservice#/SongView/searchEntry:#{songid}')
    text = f'<a href="{url}">{song["bezeichnung"]}</a> /S{songid}\n'
    if song['author']:
        text += f"<i>{song['author']}</i>\n"

    if not short:
        arr = _print_arrangements(songid, song['arrangement'], arrangement_id=arrangement_id)
        if not arr:
            return None
        text += arr

    return text


def download(redis, login_data, song_id, file_id):
    (error, data) = getAjaxResponse(redis, 'service', 'getAllSongs', login_data=login_data, timeout=24 * 3600)
    if error or not data or 'songs' not in data:
        return {'msg': error}
    else:
        l = data['songs']
        if song_id in l:
            song = l[str(song_id)]
            ars = song['arrangement']
            for k in ars:
                ar = ars[k]
                if 'files' in ar:
                    files = ar['files']
                    if file_id in files:
                        file = files[str(file_id)]
                        logger.debug(file)
                        file_hash = file['filename']
                        url = urljoin(login_data['url'], f'?q=public/filedownload&filename={file_hash}')
                        name = file['bezeichnung']
                        logger.info(f"Url: {url}\nFile: {name}")
                        return {
                            'file': url,
                            'msg': name,
                        }
