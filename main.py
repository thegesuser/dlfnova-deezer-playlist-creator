import fileinput
import json
import os
import sqlite3

import deezer
import requests
from bs4 import BeautifulSoup, PageElement, ResultSet
from dotenv import load_dotenv

load_dotenv()

app_Id = os.getenv('APP_ID')
app_secret = os.getenv('APP_SECRET')
redirect_uri = os.getenv('REDIRECT_URI')

con = sqlite3.connect("values.sqlite")
cur = con.cursor()
cur.execute("CREATE TABLE IF NOT EXISTS properties (prop_name VARCHAR(255) PRIMARY KEY, prop_val VARCHAR(255));")


def read_dlf_nova_tracks():
    page = requests.get("https://www.deutschlandfunknova.de/playlist")
    soup = BeautifulSoup(page.content, "html.parser")
    tracks: ResultSet[PageElement] = soup.find_all('figcaption', class_='playlist__title')[:10]

    print("done parsing dlf playlist. found {} tracks".format(len(tracks)))

    # As radio stations repeat tracks, we only care for unique tracks
    unique_tracks = set()
    for single_track in tracks:
        title = single_track.find('div', class_='title').text
        artist = single_track.find('div', class_='artist').text
        unique_tracks.add((title, artist))
    return unique_tracks


def get_auth_token():
    db_token = cur.execute("SELECT prop_val FROM properties WHERE prop_name = 'token'").fetchone()
    if db_token[0] is not None:
        return db_token[0]

    print(
        f"Please open https://connect.deezer.com/oauth/auth.php?app_id={app_Id}&redirect_uri={redirect_uri}&perms=basic_access,email,manage_library,offline_access")
    print("Afterwards, please paste the code into this terminal")
    for line in fileinput.input():
        auth_params = {
            "app_id": app_Id,
            "secret": app_secret,
            "code": line.rstrip(),
            "output": "json"
        }
        auth_response = requests.get('https://connect.deezer.com/oauth/access_token.php', params=auth_params)
        new_token = json.loads(auth_response.content)['access_token']
        cur.execute("INSERT INTO properties VALUES ('token', '{}')".format(new_token))
        con.commit()
        return new_token


token = get_auth_token()
client = deezer.Client(access_token=token)

# search for deezer track ids using the parsed results
deezerTrackIds = set()
for singleTrack in read_dlf_nova_tracks():
    result: deezer.PaginatedList[deezer.Track] = client.search(track=singleTrack[0], artist=singleTrack[1], strict=True)
    if len(result) > 0:
        deezerTrackIds.add(result[0].id)

playlist_id = cur.execute("SELECT prop_val FROM properties WHERE prop_name = 'playlist_id'").fetchone()
if playlist_id is None:
    playlist_id = client.create_playlist("Deutschlandfunk Nova Playlist")
    cur.execute("INSERT INTO properties VALUES ('playlist_id', '{}')".format(playlist_id))
    con.commit()
else:
    playlist_id = playlist_id[0]

trackIds = ','.join(map(str, deezerTrackIds))
client.request("POST", f"playlist/{playlist_id}/tracks", songs=trackIds)
