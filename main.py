import argparse
import re
import uuid
from datetime import datetime, timezone
from random import Random

import requests
from dateutil import parser
from nameparser import HumanName
from sgqlc.endpoint.http import HTTPEndpoint


def main(artworks_count: int, events_count: int, artsy_client_id: str, artsy_client_secret: str, api_base_url: str):
    # Fetch data
    data = get_artsy_data(artworks_count, events_count)
    # Upload data
    # api_token = get_creativehub_token(api_base_url)
    # load_artists(api_base_url, api_token, artists)
    # load_artworks(api_base_url, api_token, artworks, artists)
    # load_events(api_base_url, api_token, events)


def get_artsy_data(artworks_count: int, events_count: int) -> dict:
    with open("./query.gql", "r") as file:
        artsy_graphql_query = file.read()
        endpoint = HTTPEndpoint("https://metaphysics-production.artsy.net/v2", {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:99.0) Gecko/20100101 Firefox/99.0"
        })
        data = endpoint(artsy_graphql_query, {
            "shows": events_count,
            "artworks": artworks_count
        })
        return data


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
    for _event in events.values():
        event = {
            "name": _event["name"],
            "description": _event["description"],
            "image": _event["image"],
            "locationName": "",
            "coordinates": {
                "latitude": "",
                "longitude": ""
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
