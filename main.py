from pprint import pprint

import requests

artsy_auth = {
    "client_id": "f31d4faf871963e30f66",
    "client_secret": "2b56cd64b94facd6356cc623dd789048"
}
artists_count = 10
artworks_count = 50
events_count = 10


def main():
    artsy_token = get_artsy_token()
    artworks, artists = get_data(artsy_token)
    print("artworks:", len(artworks))
    print("artists:", len(artists))
    pprint(artworks, compact=True, depth=2)
    pprint(artists, compact=True, depth=2)


def get_data(artsy_token):
    response = requests.get(f"https://api.artsy.net/api/artworks?size={artworks_count}",
                            headers={"X-XAPP-Token": artsy_token})
    json = response.json()
    _artworks = list(json["_embedded"]["artworks"])
    artists = {}
    artworks = {}
    for artwork in _artworks:
        response = requests.get(artwork["_links"]["artists"]["href"], headers={"X-XAPP-Token": artsy_token})
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


def get_artsy_token():
    response = requests.post("https://api.artsy.net/api/tokens/xapp_token", data=artsy_auth)
    json = response.json()
    return json["token"]


if __name__ == '__main__':
    main()
