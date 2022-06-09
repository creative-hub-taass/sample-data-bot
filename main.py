import argparse
import random
import re
from datetime import datetime, timezone, timedelta
from typing import Dict, Set, List

import lorem
import names
import requests
from dateutil import parser
from lorem.text import TextLorem
from nameparser import HumanName
from sgqlc.endpoint.http import HTTPEndpoint

events_ids: Dict[str, str] = {}
artworks_ids: Dict[str, str] = {}
artists_ids: Dict[str, str] = {}


def main(api_base_url: str,
         artworks_count: int,
         events_count: int,
         posts_count: int,
         collab_req_count: int,
         users_count: int):
    print(f"Started sample-data-bot with url: {api_base_url}")
    # Fetch data
    data = get_artsy_data(artworks_count, events_count)
    # Upload data
    api_token = get_creativehub_token(api_base_url)
    upload_data(api_base_url, api_token, data, posts_count, collab_req_count, users_count)
    print("Finished uploading data")


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
            "price": float(price["minor"]) / 100.0 if on_sale else None,
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
            response = requests.post(f"{base_url}/api/v1/publications/artworks/creations/", json=creation,
                                     headers={"Authorization": f"Bearer {token}"})
            if not response.ok:
                response.raise_for_status()
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
                "creationType": "PARTICIPANT"
            }
            response = requests.post(f"{base_url}/api/v1/publications/events/creations/", json=creation,
                                     headers={"Authorization": f"Bearer {token}"})
            if not response.ok:
                response.raise_for_status()
        events_ids[show["id"]] = ch_id
    print("Uploaded events")


def upload_random_posts(base_url: str, token: str, count: int, artists: Set[str]) -> Set[str]:
    print(f"Attempt to upload {count} random posts")
    posts_ids = set()
    for i in range(count):
        post = {
            "title": lorem.sentence(),
            "body": lorem.text(),
        }
        response = requests.post(f"{base_url}/api/v1/publications/posts/", json=post,
                                 headers={"Authorization": f"Bearer {token}"})
        json = response.json()
        ch_id = json["id"]
        for artist_id in random.sample(sorted(artists), random.randrange(1, 3)):
            creation = {
                "user": artist_id,
                "postId": ch_id,
                "creationType": "COAUTHOR"
            }
            response = requests.post(f"{base_url}/api/v1/publications/posts/creations/", json=creation,
                                     headers={"Authorization": f"Bearer {token}"})
            if not response.ok:
                response.raise_for_status()
        posts_ids.add(ch_id)
    print("Uploaded random posts")
    return posts_ids


def upload_random_follows(base_url: str, token: str, artists: Set[str], users_ids: List[str]):
    follows = []
    potential_followers = artists.union(users_ids)
    for artist_id in artists:
        followers = sorted(potential_followers - {artist_id})
        number = random.randrange(0, len(followers))
        followers = random.sample(followers, number)
        follows.extend([follower_id, artist_id] for follower_id in followers)
    print(f"Attempt to upload {len(follows)} random follows")
    response = requests.put(f"{base_url}/api/v1/users/follows", json=follows,
                            headers={"Authorization": f"Bearer {token}"})
    if not response.ok:
        response.raise_for_status()
    print("Uploaded random follows")


def upload_random_likes(base_url: str, token: str, publications: Set[str], all_users: List[str]):
    likes = []
    for publication_id in publications:
        number = random.randrange(0, len(all_users))
        users = random.sample(all_users, number)
        for user_id in users:
            like = {
                "userId": user_id,
                "publicationId": publication_id,
            }
            likes.append(like)
    print(f"Attempt to upload {len(likes)} random likes")
    response = requests.post(f"{base_url}/api/v1/interactions/likes", json=likes,
                             headers={"Authorization": f"Bearer {token}"})
    if not response.ok:
        response.raise_for_status()
    print("Uploaded random likes")


def upload_random_comments(base_url: str, token: str, publications: Set[str], all_users: List[str]):
    comments = []
    lorem_gen = TextLorem(prange=(1, 5))
    for publication_id in publications:
        number = random.randrange(0, int(len(all_users) / 10))
        users = random.sample(all_users, number)
        for user_id in users:
            comment = {
                "userId": user_id,
                "publicationId": publication_id,
                "message": lorem_gen.paragraph()
            }
            comments.append(comment)
    print(f"Attempt to upload {len(comments)} random comments")
    response = requests.post(f"{base_url}/api/v1/interactions/comments", json=comments,
                             headers={"Authorization": f"Bearer {token}"})
    if not response.ok:
        response.raise_for_status()
    print("Uploaded random comments")


def upload_random_users(base_url: str, token: str, count: int) -> List[str]:
    print(f"Attempt to upload {count} random users")
    users_ids = []
    for i in range(count):
        first_name = names.get_first_name()
        last_name = names.get_last_name()
        slug = (first_name + "-" + last_name).lower()
        user = {
            "username": slug,
            "nickname": first_name + " " + last_name,
            "email": slug + "@creativehub.com",
            "password": slug,
            "role": "USER",
            "enabled": True
        }
        response = requests.post(f"{base_url}/api/v1/users/", json=user, headers={"Authorization": f"Bearer {token}"})
        json = response.json()
        ch_id = json["id"]
        users_ids.append(ch_id)
        if random.random() >= 0.9:
            upload_random_upgrade_request(base_url, token, json)
    print("Uploaded random users")
    return users_ids


def upload_random_collab_requests(base_url: str, token: str, artists: List[str], count: int):
    print(f"Attempt to upload {count} random collab requests")
    lorem_gen = TextLorem(prange=(1, 5))
    for i in range(count):
        sender = random.choice(artists)
        recipient = random.choice(artists) if random.choice([True, False]) else None
        request = {
            "senderId": sender,
            "receiverId": recipient,
            "title": lorem_gen.sentence(),
            "description": lorem_gen.paragraph(),
            "contact": "collab@creativehub.com",
            "category": "Art",
            "status": random.choice(["OPEN", "CLOSED"])
        }
        response = requests.post(f"{base_url}/api/v1/interactions/collabs/request", json=request,
                                 headers={"Authorization": f"Bearer {token}"})
        if not response.ok:
            response.raise_for_status()
    print("Uploaded random collab requests")


def upload_random_upgrade_request(base_url: str, token: str, user: dict):
    print(f"Attempt to upload random upgrade request")
    lorem_gen = TextLorem(prange=(1, 5))
    name, surname = str(user["nickname"]).split(" ")
    now = round(datetime.now().timestamp())
    diff = now - random.randrange(0, 2 * now)
    date = datetime(1970, 1, 1) + timedelta(seconds=diff)
    request = {
        "user": user,
        "name": name,
        "surname": surname,
        "bio": lorem_gen.paragraph(),
        "portfolio": lorem_gen.paragraph(),
        "motivationalText": lorem_gen.paragraph(),
        "artName": user["nickname"],
        "birthDate": date.replace(tzinfo=timezone.utc).isoformat(),
        "username": name.lower() + surname,
        "avatar": "https://upload.wikimedia.org/wikipedia/commons/thumb/5/59/User-avatar.svg/768px-User-avatar.svg.png",
        "paymentEmail": "payments@creativehub.com",
        "status": "REJECTED" if random.random() >= 0.9 else "OPEN",
        "creatorType": "ARTIST",
    }
    response = requests.post(f"{base_url}/api/v1/users/upgrade/request", json=request,
                             headers={"Authorization": f"Bearer {token}"})
    if not response.ok:
        response.raise_for_status()
    print("Uploaded random upgrade request")


def upload_data(base_url: str, token: str, data: dict, posts_count: int, collab_req_count: int, users_count: int):
    shows = data["data"]["viewer"]["showsConnection"]["edges"]
    upload_events(base_url, token, shows)
    artists = set(artists_ids.values())
    post_ids = upload_random_posts(base_url, token, posts_count, artists)
    publications = set(artworks_ids.values()) | set(events_ids.values()) | post_ids
    upload_random_collab_requests(base_url, token, sorted(artists), collab_req_count)
    users_ids = upload_random_users(base_url, token, users_count)
    upload_random_follows(base_url, token, artists, users_ids)
    all_users = sorted(artists) + users_ids
    upload_random_likes(base_url, token, publications, all_users)
    upload_random_comments(base_url, token, publications, all_users)


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
    argument_parser.add_argument("--users", help="number of users to load", type=int, default=100)
    argument_parser.add_argument("--collab-req", help="number of collab requests to load", type=int, default=20)
    argument_parser.add_argument("--api-url", help="API Gateway URL", type=str, default="http://localhost:8080")
    args = argument_parser.parse_args()
    main(
        api_base_url=args.api_url,
        artworks_count=args.artworks,
        events_count=args.events,
        posts_count=args.posts,
        collab_req_count=args.collab_req,
        users_count=args.users
    )
