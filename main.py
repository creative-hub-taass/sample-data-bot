import argparse
import random
import re
from datetime import datetime, timezone
from typing import Dict, Set, List

import requests
from dateutil import parser
from nameparser import HumanName
from sgqlc.endpoint.http import HTTPEndpoint

events_ids: Dict[str, str] = {}
artworks_ids: Dict[str, str] = {}
artists_ids: Dict[str, str] = {}


def main(artworks_count: int, events_count: int, posts_count: int, api_base_url: str):
    # Fetch data
    data = get_artsy_data(artworks_count, events_count)
    # Upload data
    api_token = get_creativehub_token(api_base_url)
    upload_data(api_base_url, api_token, data, posts_count)


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
        if artist["id"] in artists_ids:
            continue
        artist_name_full: str = artist["name"]
        artist_name = HumanName(artist_name_full)
        birthday_ = artist["birthday"]
        birthday_ = re.sub(r"/\d*", "", birthday_)
        birthday_ = re.sub(r"\D*", "", birthday_).strip()
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
        artists_ids[artist["id"]] = ch_id
    print("Uploaded artists")


def upload_artworks(base_url: str, token: str, artworks: dict) -> set:
    loaded_artists = set()
    print("Attempt to upload", len(artworks), "artworks")
    for _artwork in artworks:
        _artwork = _artwork["node"]
        if _artwork["id"] in artworks_ids:
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
            ch_artist_id = artists_ids[artist_id]
            creation = {
                "user": ch_artist_id,
                "artworkId": ch_id,
                "creationType": "AUTHOR"
            }
            requests.post(f"{base_url}/api/v1/publications/artworks/creations/", json=creation,
                          headers={"Authorization": f"Bearer {token}"})
            loaded_artists.add(ch_artist_id)
        artworks_ids[_artwork["id"]] = ch_id
    print("Uploaded artworks")
    return loaded_artists


def upload_events(base_url: str, token: str, shows: dict):
    print("Attempt to upload", len(shows), "events")
    for show in shows:
        show = show["node"]
        if show["id"] in events_ids:
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
        events_ids[show["id"]] = ch_id
    print("Uploaded events")


def upload_random_posts(count: int) -> Set[str]:
    print("Attempt to upload random posts")
    # TODO
    print("Uploaded random posts")
    return set()


def upload_random_follows(base_url: str, token: str, artists: Set[str]):
    follows = []
    for artist_id in artists:
        others = sorted(artists - {artist_id})
        number = random.randrange(0, len(others))
        followed = random.sample(others, number)
        follows.extend([artist_id, followed_id] for followed_id in followed)
    print(f"Attempt to upload {len(follows)} random follows")
    requests.put(f"{base_url}/api/v1/users/follows", json=follows, headers={"Authorization": f"Bearer {token}"})
    print("Uploaded random follows")


def upload_random_likes(base_url: str, token: str, publications: Set[str], artists: List[str]):
    likes = []
    for publication_id in publications:
        number = random.randrange(0, len(artists))
        users = random.sample(artists, number)
        for user_id in users:
            like = {
                "userId": user_id,
                "publicationId": publication_id,
            }
            likes.append(like)
    print(f"Attempt to upload {len(likes)} random likes")
    requests.post(f"{base_url}/api/v1/interactions/likes", json=likes, headers={"Authorization": f"Bearer {token}"})
    print("Uploaded random likes")


def upload_data(base_url: str, token: str, data: dict, posts_count: int):
    shows = data["data"]["viewer"]["showsConnection"]["edges"]
    upload_events(base_url, token, shows)
    post_ids = upload_random_posts(posts_count)
    artists = set(artists_ids.values())
    publications = set(artworks_ids.values()) | set(events_ids.values()) | post_ids
    upload_random_follows(base_url, token, artists)
    upload_random_likes(base_url, token, publications, sorted(artists))


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
    argument_parser.add_argument("--posts", help="number of posts to load", type=int, default=20)
    argument_parser.add_argument("--api-url", help="API Gateway URL", type=str, default="http://localhost:8080")
    args = argument_parser.parse_args()
    main(artworks_count=args.artworks,
         events_count=args.events,
         posts_count=args.posts,
         api_base_url=args.api_url)
