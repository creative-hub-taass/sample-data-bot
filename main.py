import argparse
import re
import uuid
from datetime import datetime, timezone
from random import Random

import requests
from dateutil import parser
from nameparser import HumanName
from sgqlc.endpoint.http import HTTPEndpoint


def main(artworks_count: int, events_count: int, api_base_url: str):
    # Fetch data
    data = get_artsy_data(artworks_count, events_count)
    # Upload data
    api_token = get_creativehub_token(api_base_url)
    load_data(api_base_url, api_token, data)


def load_data(base_url: str, token: str, data: dict):
    shows = data["data"]["viewer"]["showsConnection"]["edges"]
    print("Attempt to upload", len(shows), "events")
    for show in shows:
        show = show["node"]
        location = show["location"]
        partner = show["partner"]
        href = show["href"]
        artworks = show["artworksConnection"]["edges"]
        if not partner or not location or not href or not artworks:
            continue
        address = location["address"] + ", " + location["city"] + ", " + location["country"]
        event = {
            "name": show["name"],
            "description": show["description"],
            "image": show["coverImage"]["url"],
            "locationName": partner["name"] + ", " + address,
            "coordinates": {
                "latitude": location["coordinates"]["lat"],
                "longitude": location["coordinates"]["lng"]
            },
            "startDateTime": show["start"],
            "endDateTime": show["end"],
            "bookingURL": "https://www.artsy.net" + href
        }
        print("Attempt to upload", len(artworks), "artworks")
        for _artwork in artworks:
            _artwork = _artwork["node"]
            _date = re.sub(r"[\-/]\d*", "", _artwork["date"].strip()) if "date" in _artwork else ""
            _date = re.sub(r"[a-zA-Z.,]", "", _date)
            date = parser.parse(_date) if _date else datetime.now()
            date = date.replace(tzinfo=timezone.utc).isoformat()
            unique = True if _artwork["edition_of"] is None else False
            copies = 1 if unique else int(next(iter(re.findall(r"\d+", _artwork["edition_of"])), 1))
            on_sale = _artwork["is_for_sale"] or _artwork["is_acquireable"]
            sold = _artwork["is_sold"]
            price = _artwork["price"]
            artists = _artwork["artists"]
            if on_sale and not price:
                continue
            additional_information = _artwork["additional_information"]
            description = _artwork["meta"]["description"]
            artwork = {
                "creationDateTime": date,
                "name": _artwork["title"],
                "description": description + (".\n" + additional_information if additional_information else ""),
                "type": _artwork["category"],
                "copies": copies,
                "attributes": {
                    "size": _artwork["dimensions"]["cm"],
                    "medium": _artwork["medium"]["text"]
                },
                "images": [_artwork["image"]["url"]],
                "onSale": on_sale,
                "price": price["minor"] if on_sale else None,
                "currency": price["currencyCode"] if on_sale else None,
                "paymentEmail": "payments@creativehub.com" if on_sale else None,
                "availableCopies": copies if on_sale and not sold else 0
            }
            for _artist in artists:
                artist_name_full: str = _artist["name"]
                artist_name = HumanName(artist_name_full)
                birthday_ = re.sub(r"/\d*", "", _artist["birthday"].strip())
                birthday = parser.parse(birthday_) if birthday_ else datetime.now()
                user = {
                    "username": _artist["slug"],
                    "nickname": artist_name_full,
                    "email": "artist-" + _artist["slug"] + "@creativehub.com",
                    "password": _artist["slug"],
                    "role": "USER",
                    "creator": {
                        "name": artist_name.first,
                        "surname": artist_name.surnames,
                        "birthDate": birthday.date().isoformat(),
                        "bio": _artist["biographyBlurb"]["text"] or "",
                        "creatorType": "ARTIST",
                        "avatar": _artist["image"]["url"],
                        "paymentEmail": "payments@creativehub.com"
                    },
                    "enabled": True
                }
                response = requests.post(f"{base_url}/api/v1/users/", json=user,
                                         headers={"Authorization": f"Bearer {token}"})
            # response = requests.post(f"{base_url}/api/v1/publications/artworks/", json=artwork, headers={"Authorization": f"Bearer {token}"})
        # requests.post(f"{base_url}/api/v1/publications/events/", json=event, headers={"Authorization": f"Bearer {token}"})
    print("Uploaded all data")


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
    group = argument_parser.add_mutually_exclusive_group()
    group.add_argument("--api-base-url", default="http://localhost:8080")
    group.add_argument("--local", dest="api_base_url", action="store_const", const="http://localhost:8080")
    group.add_argument("--okteto", dest="api_base_url", action="store_const",
                       const="https://api-gateway-taass-acontenti.cloud.okteto.net")
    args = argument_parser.parse_args()
    main(artworks_count=args.artworks_count, events_count=args.events_count, api_base_url=args.api_base_url)
