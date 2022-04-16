import re
import uuid
from datetime import datetime, timedelta, timezone
from random import Random

import requests
from dateutil import parser
from nameparser import HumanName


def main():
    artworks_count = 20
    events_count = 20
    artsy_token = get_artsy_token()
    artworks, artists = get_artworks_artists(artsy_token, artworks_count)
    events = get_events(artsy_token, events_count)
    print("artworks:", len(artworks))
    print("artists:", len(artists))
    print("events:", len(events))
    creativehub_token = get_creativehub_token()
    load_artists(creativehub_token, artists)
    load_artworks(creativehub_token, artworks, artists)


def get_artworks_artists(token, count):
    response = requests.get(f"https://api.artsy.net/api/artworks?size={count}", headers={"X-XAPP-Token": token})
    json = response.json()
    _artworks = list(json["_embedded"]["artworks"])
    artists = {}
    artworks = {}
    for artwork in _artworks:
        response = requests.get(artwork["_links"]["artists"]["href"], headers={"X-XAPP-Token": token})
        json = response.json()
        _artists = list(json["_embedded"]["artists"])
        if _artists:
            for artist in _artists:
                if artist["id"] not in artists:
                    artist["image"] = artist["_links"]["thumbnail"]["href"]
                    del artist["_links"]
                    artists[artist["id"]] = artist
            artwork["artists_ids"] = [artist["id"] for artist in _artists]
            artwork["image"] = artwork["_links"]["thumbnail"]["href"]
            del artwork["_links"]
            artworks[artwork["id"]] = artwork
    return artworks, artists


def get_events(token, count):
    response = requests.get(f"https://api.artsy.net/api/shows?status=upcoming&size={count}",
                            headers={"X-XAPP-Token": token})
    json = response.json()
    _shows = list(json["_embedded"]["shows"])
    shows = {}
    for show in _shows:
        start_date = datetime.fromisoformat(show["start_at"])
        end_date = datetime.fromisoformat(show["end_at"])
        now = datetime.now(tz=timezone.utc)
        lower_bound = now - timedelta(days=365)
        upper_bound = now + timedelta(days=365)
        if (lower_bound < start_date < upper_bound) and (lower_bound < end_date < upper_bound):
            del show["_links"]
            shows[show["id"]] = show
    return shows


def get_artsy_token():
    auth_data = {
        "client_id": "f31d4faf871963e30f66",
        "client_secret": "2b56cd64b94facd6356cc623dd789048"
    }
    response = requests.post("https://api.artsy.net/api/tokens/xapp_token", data=auth_data)
    json = response.json()
    return json["token"]


def load_artists(creativehub_token, artists):
    for artist in artists.values():
        artist_name_full: str = artist["name"]
        artist_name = HumanName(artist_name_full)
        birthday_ = re.sub(r"/\d*", "", artist["birthday"].strip())
        birthday = parser.parse(birthday_) if birthday_ else datetime.now()
        user = {
            "username": artist["slug"],
            "nickname": artist_name_full,
            "email": "artist-" + artist["slug"] + "@creativehub.com",
            "password": artist["slug"],
            "role": "USER",
            "creator": {
                "name": artist_name.first,
                "surname": artist_name.surnames,
                "birthDate": birthday.date().isoformat(),
                "bio": artist["biography"] or "",
                "creatorType": "ARTIST",
                "avatar": artist["image"],
                "paymentEmail": "payments@creativehub.com"
            },
            "enabled": True
        }
        response = requests.post("http://localhost:8080/api/v1/users/", json=user,
                                 headers={"X-ACCESS-TOKEN": creativehub_token})
        json = response.json()
        artist["creativehub-id"] = json["id"]


def load_artworks(creativehub_token, artworks, artists):
    random = Random()
    for _artwork in artworks.values():
        _date = re.sub(r"[\-/]\d*", "", _artwork["date"].strip())
        _date = re.sub(r"[a-zA-Z.,]", "", _date)
        date = parser.parse(_date) if _date else datetime.now()
        date = date.replace(tzinfo=timezone.utc).isoformat()
        unique = bool(_artwork["unique"] or "true")
        copies = 1 if unique else random.randint(2, 10)
        onsale = random.choice([_artwork["can_acquire"], True, False])
        artwork = {
            "creationDateTime": date,
            "name": _artwork["title"],
            "description": _artwork["medium"] + " " + _artwork["collecting_institution"],
            "type": _artwork["category"],
            "copies": copies,
            "attributes": {
                "size": _artwork["dimensions"]["cm"]["text"]
            },
            "images": [_artwork["image"]],
            "onSale": onsale,
            "price": round(random.random() * 900 + 100, 2) if onsale else None,
            "currency": "EUR" if onsale else None,
            "paymentEmail": "payments@creativehub.com" if onsale else None,
            "availableCopies": copies - random.randint(0, 10) if onsale else 0
        }
        response = requests.post("http://localhost:8080/api/v1/publications/artworks/", json=artwork,
                                 headers={"X-ACCESS-TOKEN": creativehub_token})
        json = response.json()
        creativehub_id = json["id"]
        for artist_id in _artwork["artists_ids"]:
            artist = artists[artist_id]
            creation = {
                "user": artist.get("creativehub-id") or str(uuid.uuid4()),
                "artworkId": creativehub_id,
                "creationType": "AUTHOR"
            }
            requests.post("http://localhost:8080/api/v1/publications/artworks/creations/", json=creation,
                          headers={"X-ACCESS-TOKEN": creativehub_token})


def get_creativehub_token():
    auth_data = {
        "email": "root@creativehub.com",
        "password": "root"
    }
    response = requests.post("http://localhost:8080/api/v1/users/auth/login", json=auth_data)
    headers = response.headers
    return headers["X-ACCESS-TOKEN"]


if __name__ == '__main__':
    main()
