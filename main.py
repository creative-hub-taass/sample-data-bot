import argparse
import re
import sys
import uuid
from datetime import datetime, timedelta, timezone
from random import Random

import requests
from dateutil import parser
from geopy import Nominatim
from nameparser import HumanName

cities = ['Aarhus', 'Alicante', 'Amsterdam', 'Andorra la Vella', 'Antwerp', 'Athens', 'Barcelona', 'Bari',
          'Belgrade', 'Berlin', 'Bern', 'Bielefeld', 'Bilbao', 'Bologna', 'Bonn', 'Bratislava', 'Bremen', 'Brno',
          'Brussels', 'Bucharest', 'Budapest', 'Catania', 'Chisinau', 'Cologne', 'Copenhagen', 'Córdoba',
          'Dortmund', 'Dresden', 'Dublin', 'Duisburg', 'Düsseldorf', 'Essen', 'Florence', 'Frankfurt am Main',
          'Gdańsk', 'Genoa', 'Gothenburg', 'Hamburg', 'Hanover', 'Helsinki', 'Karlsruhe', 'Kraków', 'Las Palmas',
          'Leipzig', 'Lisbon', 'Ljubljana', 'London', 'Lublin', 'Luxembourg', 'Lyon', 'Madrid', 'Malmö', 'Mannheim',
          'Marseille', 'Milan', 'Minsk', 'Monaco', 'Moscow', 'Munich', 'Murcia', 'Málaga', 'Münster', 'Nantes',
          'Naples', 'Nice', 'Nicosia', 'Nuremberg', 'Oslo', 'Palermo', 'Palma de Mallorca', 'Paris', 'Podgorica',
          'Poznań', 'Prague', 'Reykjavik', 'Riga', 'Rome', 'Rotterdam', 'San Marino', 'Sarajevo', 'Seville',
          'Sintra', 'Skopje', 'Sofia', 'Stockholm', 'Stuttgart', 'Szczecin', 'Tallinn', 'The Hague', 'Thessaloniki',
          'Tirana', 'Toulouse', 'Turin', 'Utrecht', 'Vaduz', 'Valencia', 'Valletta', 'Varna', 'Vienna',
          'Vila Nova de Gaia', 'Vilnius', 'Warsaw', 'Wrocław', 'Wuppertal', 'Zagreb', 'Zaragoza', 'Łódź'
          ]


def main(artworks_count: int, events_count: int, artsy_client_id: str, artsy_client_secret: str, api_base_url: str):
    # Fetch data
    artsy_token = get_artsy_token(artsy_client_id, artsy_client_secret)
    artworks, artists = get_artworks_artists(artsy_token, artworks_count)
    events = get_events(artsy_token, events_count)
    # Upload data
    api_token = get_creativehub_token(api_base_url)
    load_artists(api_base_url, api_token, artists)
    load_artworks(api_base_url, api_token, artworks, artists)
    load_events(api_base_url, api_token, events)


def get_artworks_artists(token: str, count: int) -> tuple:
    print("Attempt to get", count, "artworks with relative artists")
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
            sys.stdout.write("\033[K")
            print("\rGot artwork:", artwork["title"], end="")
    sys.stdout.write("\033[K")
    print("\rGot", len(artworks), "artworks", "and", len(artists), "artists")
    return artworks, artists


def get_events(token: str, count: int) -> dict:
    print("Attempt to get", count, "events")
    response = requests.get(f"https://api.artsy.net/api/shows?status=current&size={count}",
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
            show["image"] = show["_links"]["thumbnail"]["href"] if "thumbnail" in show["_links"] else ""
            show["link"] = show["_links"]["permalink"]["href"]
            del show["_links"]
            shows[show["id"]] = show
            sys.stdout.write("\033[K")
            print("\rGot event:", show["name"], end="")
    sys.stdout.write("\033[K")
    print("\rGot", len(shows), "events")
    return shows


def get_artsy_token(client_id: str, client_secret: str) -> str:
    print("Get Artsy token")
    auth_data = {
        "client_id": client_id,
        "client_secret": client_secret
    }
    response = requests.post("https://api.artsy.net/api/tokens/xapp_token", data=auth_data)
    json = response.json()
    token = json["token"]
    print("Got Artsy token:", token)
    return token


def load_artists(base_url: str, token: str, artists: dict):
    print("Attempt to upload", len(artists), "artists")
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
        response = requests.post(f"{base_url}/api/v1/users/", json=user, headers={"Authorization": f"Bearer {token}"})
        json = response.json()
        artist["creativehub-id"] = json["id"]
    print("Uploaded all artists")


def load_artworks(base_url: str, token: str, artworks: dict, artists: dict):
    print("Attempt to upload", len(artworks), "artworks")
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
        response = requests.post(f"{base_url}/api/v1/publications/artworks/", json=artwork,
                                 headers={"Authorization": f"Bearer {token}"})
        json = response.json()
        creativehub_id = json["id"]
        for artist_id in _artwork["artists_ids"]:
            artist = artists[artist_id]
            creation = {
                "user": artist.get("creativehub-id") or str(uuid.uuid4()),
                "artworkId": creativehub_id,
                "creationType": "AUTHOR"
            }
            requests.post(f"{base_url}/api/v1/publications/artworks/creations/", json=creation,
                          headers={"Authorization": f"Bearer {token}"})
    print("Uploaded all artworks")


def load_events(base_url: str, token: str, events: dict):
    print("Attempt to upload", len(events), "events")
    geolocator = Nominatim(user_agent="creative-hub/sample-data-bot")
    random = Random()
    for _event in events.values():
        place = random.choice(cities)
        location = geolocator.geocode(place)
        event = {
            "name": _event["name"],
            "description": _event["description"],
            "image": _event["image"],
            "locationName": place + ": " + location.address,
            "coordinates": {
                "latitude": location.latitude,
                "longitude": location.longitude
            },
            "startDateTime": _event["start_at"],
            "endDateTime": _event["end_at"],
            "bookingURL": _event["link"]
        }
        requests.post(f"{base_url}/api/v1/publications/events/", json=event,
                      headers={"Authorization": f"Bearer {token}"})
    print("Uploaded all events")


def get_creativehub_token(base_url: str) -> str:
    print("Get creativeHub token")
    auth_data = {
        "email": "root@creativehub.com",
        "password": "root"
    }
    response = requests.post(f"{base_url}/api/v1/users/auth/login", json=auth_data)
    headers = response.headers
    token = headers["X-ACCESS-TOKEN"]
    print("Got creativeHub token:", token)
    return token


if __name__ == '__main__':
    argument_parser = argparse.ArgumentParser("sample-data-bot", description="creativeHub sample data bot")
    argument_parser.add_argument("--artworks-count", type=int, default=20)
    argument_parser.add_argument("--events-count", type=int, default=20)
    argument_parser.add_argument("--artsy-client-id", default="f31d4faf871963e30f66")
    argument_parser.add_argument("--artsy-client-secret", default="2b56cd64b94facd6356cc623dd789048")
    group = argument_parser.add_mutually_exclusive_group()
    group.add_argument("--api-base-url", default="http://localhost:8080")
    group.add_argument("--local", dest="api_base_url", action="store_const", const="http://localhost:8080")
    group.add_argument("--okteto", dest="api_base_url", action="store_const",
                       const="https://api-gateway-taass-acontenti.cloud.okteto.net")
    args = argument_parser.parse_args()
    main(artworks_count=args.artworks_count,
         events_count=args.events_count,
         artsy_client_id=args.artsy_client_id,
         artsy_client_secret=args.artsy_client_secret,
         api_base_url=args.api_base_url)
