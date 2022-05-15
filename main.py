import argparse
import re
from datetime import datetime, timezone

import requests
from dateutil import parser
from nameparser import HumanName
from sgqlc.endpoint.http import HTTPEndpoint

loaded_elements = {}


def main(artworks_count: int, events_count: int, api_base_url: str):
    # Fetch data
    data = get_artsy_data(artworks_count, events_count)
    # Upload data
    api_token = get_creativehub_token(api_base_url)
    upload_data(api_base_url, api_token, data)


def get_artsy_data(artworks_count: int, events_count: int) -> dict:
    print("Download Artsy data")
    with open("./query.gql", "r") as file:
        artsy_graphql_query = file.read()
        endpoint = HTTPEndpoint("https://metaphysics-production.artsy.net/v2", {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:99.0) Gecko/20100101 Firefox/99.0"
        })
        data = endpoint(artsy_graphql_query, {
            "shows": events_count,
            "artworks": artworks_count
        })
        print("Downloaded Artsy data")
        return data


def upload_artists(base_url: str, token: str, artists: dict):
    print("Attempt to upload", len(artists), "artists")
    for artist in artists:
        if artist["id"] in loaded_elements:
            continue
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
                "bio": artist["biographyBlurb"]["text"] or "",
                "creatorType": "ARTIST",
                "avatar": artist["image"]["url"],
                "paymentEmail": "payments@creativehub.com"
            },
            "enabled": True
        }
        response = requests.post(f"{base_url}/api/v1/users/", json=user, headers={"Authorization": f"Bearer {token}"})
        json = response.json()
        ch_id = json["id"]
        loaded_elements[artist["id"]] = ch_id
    print("Uploaded artists")


def upload_artworks(base_url: str, token: str, artworks: dict) -> set:
    loaded_artists = set()
    print("Attempt to upload", len(artworks), "artworks")
    for _artwork in artworks:
        _artwork = _artwork["node"]
        if _artwork["id"] in loaded_elements:
            continue
        _date = re.sub(r"[\-/]\d*", "", _artwork["date"].strip()) if "date" in _artwork else ""
        _date = re.sub(r"[a-zA-Z.,]", "", _date)
        date = datetime.now()
        if _date:
            try:
                date = parser.parse(_date)
            except Exception as e:
                print(e)
        date = date.replace(tzinfo=timezone.utc).isoformat()
        unique = True if _artwork["edition_of"] is None else False
        copies = 1 if unique else int(next(iter(re.findall(r"\d+", _artwork["edition_of"])), 1))
        on_sale = _artwork["is_for_sale"] or _artwork["is_acquireable"]
        sold = _artwork["is_sold"]
        price = _artwork["price"]
        artists = _artwork["artists"]
        image = _artwork["image"]
        if (on_sale and not price) or not image or not artists:
            continue
        additional_info = _artwork["additional_information"]
        description = _artwork["meta"]["description"].strip()
        additional_info = ".\n" + additional_info[:1].upper() + additional_info[1:] if additional_info else ""
        artwork = {
            "creationDateTime": date,
            "name": _artwork["title"],
            "description": description + additional_info.strip(),
            "type": _artwork["category"],
            "copies": copies,
            "attributes": {
                "size": _artwork["dimensions"]["cm"],
                "medium": _artwork["medium"]["text"]
            },
            "images": [image["url"]],
            "onSale": on_sale,
            "price": price["minor"] if on_sale else None,
            "currency": price["currencyCode"] if on_sale else None,
            "paymentEmail": "payments@creativehub.com" if on_sale else None,
            "availableCopies": copies if on_sale and not sold else 0
        }
        upload_artists(base_url, token, artists)
        response = requests.post(f"{base_url}/api/v1/publications/artworks/", json=artwork,
                                 headers={"Authorization": f"Bearer {token}"})
        json = response.json()
        ch_id = json["id"]
        for artist in artists:
            artist_id = artist["id"]
            ch_artist_id = loaded_elements[artist_id]
            creation = {
                "user": ch_artist_id,
                "artworkId": ch_id,
                "creationType": "AUTHOR"
            }
            requests.post(f"{base_url}/api/v1/publications/artworks/creations/", json=creation,
                          headers={"Authorization": f"Bearer {token}"})
            loaded_artists.add(ch_artist_id)
    print("Uploaded artworks")
    return loaded_artists


def upload_events(base_url: str, token: str, shows: dict):
    print("Attempt to upload", len(shows), "events")
    for show in shows:
        show = show["node"]
        if show["id"] in loaded_elements:
            continue
        location = show["location"]
        partner = show["partner"]
        href = show["href"]
        artworks = show["artworksConnection"]["edges"]
        if not partner or not location or not location["coordinates"] or not href or not artworks:
            continue
        address = map(lambda it: it.strip(), filter(None, [location["address"], location["city"], location["country"]]))
        address = ", ".join(address)
        event = {
            "name": show["name"],
            "description": show["description"],
            "image": show["coverImage"]["url"],
            "locationName": partner["name"].strip() + ", " + address,
            "coordinates": {
                "latitude": location["coordinates"]["lat"],
                "longitude": location["coordinates"]["lng"]
            },
            "startDateTime": show["start"],
            "endDateTime": show["end"],
            "bookingURL": "https://www.artsy.net" + href
        }
        loaded_artists = upload_artworks(base_url, token, artworks)
        response = requests.post(f"{base_url}/api/v1/publications/events/", json=event,
                                 headers={"Authorization": f"Bearer {token}"})
        json = response.json()
        ch_id = json["id"]
        for artist_id in loaded_artists:
            creation = {
                "user": artist_id,
                "eventId": ch_id,
                "creationType": "COAUTHOR"
            }
            requests.post(f"{base_url}/api/v1/publications/events/creations/", json=creation,
                          headers={"Authorization": f"Bearer {token}"})
    print("Uploaded events")


def upload_data(base_url: str, token: str, data: dict):
    shows = data["data"]["viewer"]["showsConnection"]["edges"]
    upload_events(base_url, token, shows)


def get_creativehub_token(base_url: str) -> str:
    print("Get creativeHub token")
    auth_data = {
        "email": "root@creativehub.com",
        "password": "root"
    }
    response = requests.post(f"{base_url}/api/v1/users/-/auth/login", json=auth_data)
    headers = response.headers
    token = headers["X-ACCESS-TOKEN"]
    print("Got creativeHub token:", token)
    return token


if __name__ == '__main__':
    argument_parser = argparse.ArgumentParser("sample-data-bot", description="creativeHub sample data bot")
    argument_parser.add_argument("--artworks", help="number of artworks per event to load", type=int, default=20)
    argument_parser.add_argument("--events", help="number of events to load", type=int, default=20)
    argument_parser.add_argument("--api-url", help="API Gateway URL", type=str, default="http://localhost:8080")
    args = argument_parser.parse_args()
    main(artworks_count=args.artworks, events_count=args.events, api_base_url=args.api_url)
