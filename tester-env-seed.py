#!/usr/bin/env python3
"""Deterministic seed + verify for the Lychee tester environment.

`seed` imports the committed fixtures with `lychee:sync` (see tester-env) and
then makes the library look like a used installation: album descriptions, a
second regular user, sharing, a public album, fixed photo titles/taken dates,
tags, descriptions, ratings and highlights. Every step is idempotent, so
`seed` can be re-run on an already seeded library.

`verify` asserts the seeded state through the same HTTP API the browser uses
and prints a canonical signature that must not change across resets.
"""
import argparse
import hashlib
import http.cookiejar
import json
import sys
import urllib.error
import urllib.parse
import urllib.request

REGULAR_USER = {"username": "mara", "password": "tester1234", "may_upload": True, "may_edit_own_settings": True}

ALBUMS = [
    {
        "title": "Nordic Coast 2026",
        "parent": None,
        "description": "Field notes and coastal studies from the September 2026 Norway trip.",
        "public": False,
    },
    {
        "title": "Lofoten Islands",
        "parent": "Nordic Coast 2026",
        "description": "Selected frames from the Lofoten leg of the trip.",
        "public": False,
    },
    {
        "title": "Studio Sessions",
        "parent": None,
        "description": "Client selects from the autumn product and portrait sessions.",
        "public": False,
        "share_with": "mara",
    },
    {
        "title": "Archive 2024",
        "parent": None,
        "description": "Older work kept for reference and licensing requests.",
        "public": True,
    },
]

PHOTOS = [
    # Nordic Coast 2026
    dict(album="Nordic Coast 2026", title="Fjord at Blue Hour", taken="2026-09-12T19:42:00+00:00",
         upload="2026-09-13T09:10:00+00:00", rating=5, highlighted=True,
         description="Calm water at Reine after sunset.", tags=["fjord", "norway", "blue-hour"]),
    dict(album="Nordic Coast 2026", title="Driftwood at Haukland Beach", taken="2026-09-13T08:15:00+00:00",
         upload="2026-09-13T20:30:00+00:00", rating=4, highlighted=False,
         description="Weathered timber left by the last storm.", tags=["beach", "driftwood"]),
    dict(album="Nordic Coast 2026", title="Sea Stack from the Ferry", taken="2026-09-14T11:05:00+00:00",
         upload="2026-09-14T21:00:00+00:00", rating=3, highlighted=False,
         description="", tags=["ferry", "coast"]),
    dict(album="Nordic Coast 2026", title="Rorbu Cabins in the Rain", taken="2026-09-14T17:20:00+00:00",
         upload="2026-09-15T08:45:00+00:00", rating=0, highlighted=False,
         description="Red cabins along the harbour wall.", tags=["cabins", "rain"]),
    dict(album="Nordic Coast 2026", title="Trail Marker Above the Village", taken="2026-09-15T09:30:00+00:00",
         upload="2026-09-15T19:20:00+00:00", rating=2, highlighted=False,
         description="A quiet switchback trail marker above the village, photographed on the way to the ridge.",
         tags=["hiking", "trail"]),
    # Lofoten Islands (child album)
    dict(album="Lofoten Islands", title="Reine Harbour Reflections", taken="2026-09-16T07:50:00+00:00",
         upload="2026-09-16T18:15:00+00:00", rating=5, highlighted=True,
         description="Still water between the moored boats.", tags=["harbour", "reflection", "lofoten"]),
    dict(album="Lofoten Islands", title="Sheep on the Coastal Road", taken="2026-09-16T13:10:00+00:00",
         upload="2026-09-16T21:40:00+00:00", rating=1, highlighted=False,
         description="", tags=["road", "wildlife"]),
    dict(album="Lofoten Islands", title="Northern Lights over Vestfjorden", taken="2026-09-17T23:40:00+00:00",
         upload="2026-09-18T10:05:00+00:00", rating=5, highlighted=True,
         description="First clear aurora of the trip.", tags=["aurora", "night"]),
    dict(album="Lofoten Islands", title="Empty Pier at Dawn", taken="2026-09-18T06:05:00+00:00",
         upload="2026-09-18T17:30:00+00:00", rating=3, highlighted=False,
         description="", tags=["pier", "dawn"]),
    # Studio Sessions (shared with mara)
    dict(album="Studio Sessions", title="Ceramic Mug on Linen", taken="2026-10-02T10:00:00+00:00",
         upload="2026-10-02T16:20:00+00:00", rating=4, highlighted=False,
         description="Second layout for the ceramics catalogue.", tags=["product", "ceramics"]),
    dict(album="Studio Sessions", title="Portrait with Window Light", taken="2026-10-02T14:25:00+00:00",
         upload="2026-10-02T19:10:00+00:00", rating=5, highlighted=True,
         description="Test frame from the north window setup.", tags=["portrait", "studio"]),
    dict(album="Studio Sessions", title="Linen Swatches on Oak", taken="2026-10-03T09:40:00+00:00",
         upload="2026-10-03T15:00:00+00:00", rating=2, highlighted=False,
         description="Colour check under the softbox.", tags=["product", "textiles"]),
    dict(album="Studio Sessions", title="Backdrop Test Frame", taken="2026-10-03T16:55:00+00:00",
         upload="2026-10-03T20:25:00+00:00", rating=0, highlighted=False,
         description="Reference frame before the final lighting change.", tags=["studio", "test"]),
    # Archive 2024 (public)
    dict(album="Archive 2024", title="Snow on the Fire Escape", taken="2024-01-18T08:20:00+00:00",
         upload="2024-01-18T18:00:00+00:00", rating=3, highlighted=False,
         description="", tags=["archive", "winter"]),
    dict(album="Archive 2024", title="Rooftop Water Tanks", taken="2024-04-06T15:45:00+00:00",
         upload="2024-04-06T19:30:00+00:00", rating=1, highlighted=False,
         description="Roof survey for the old block.", tags=["archive", "rooftop"]),
    dict(album="Archive 2024", title="Market Street in Motion", taken="2024-06-21T12:30:00+00:00",
         upload="2024-06-21T18:40:00+00:00", rating=2, highlighted=False,
         description="", tags=["archive", "street"]),
    dict(album="Archive 2024", title="Dock Crane at Sunset", taken="2024-09-09T19:15:00+00:00",
         upload="2024-09-09T22:05:00+00:00", rating=4, highlighted=False,
         description="Harbour redevelopment reference.", tags=["archive", "sunset"]),
]


class Api:
    def __init__(self, base):
        self.base = base.rstrip("/")
        self.jar = http.cookiejar.CookieJar()
        self.opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(self.jar))

    def _xsrf(self):
        for cookie in self.jar:
            if cookie.name == "XSRF-TOKEN":
                return urllib.parse.unquote(cookie.value)
        return ""

    def request(self, method, path, body=None, expect=(200, 201, 204), retry_csrf=True):
        url = f"{self.base}/{path}"
        data = json.dumps(body).encode() if body is not None else None
        headers = {"Accept": "application/json", "Content-Type": "application/json", "X-XSRF-TOKEN": self._xsrf()}
        req = urllib.request.Request(url, data=data, headers=headers, method=method)
        try:
            with self.opener.open(req, timeout=60) as resp:
                raw = resp.read()
                status = resp.status
        except urllib.error.HTTPError as exc:
            raw = exc.read()
            status = exc.code
        if status == 419 and retry_csrf:
            self.prime()
            return self.request(method, path, body, expect, retry_csrf=False)
        if status not in expect:
            raise SystemExit(f"{method} {path} -> {status}: {raw[:400].decode(errors='replace')}")
        return json.loads(raw) if raw else None

    def prime(self):
        """Load the SPA shell to receive the XSRF-TOKEN cookie."""
        with self.opener.open(urllib.request.Request(f"{self.base.split('/api/')[0]}/", headers={"Accept": "text/html"})) as resp:
            resp.read()

    def login(self, username, password):
        # Prime the CSRF cookie, then log in through the SPA's own API.
        self.prime()
        self.request("POST", "Auth::login", {"username": username, "password": password}, expect=(204,))
        user = self.request("GET", "Auth::user")
        if user["username"] != username:
            raise SystemExit(f"login as {username} returned {user!r}")
        return user


def root_albums(api, include_shared=False):
    data = api.request("GET", "Albums")
    keys = ("albums", "pinned_albums") + (("shared_albums",) if include_shared else ())
    albums = {}
    for key in keys:
        for album in data.get(key) or []:
            albums[album["title"]] = album
    return albums, data


def child_albums(api, album_id):
    return api.request("GET", f"Album::albums?album_id={album_id}")["data"]


def album_photos(api, album_id):
    photos, page = [], 1
    while True:
        data = api.request("GET", f"Album::photos?album_id={album_id}&page={page}")
        photos.extend(data["photos"])
        if page >= data["last_page"]:
            return photos
        page += 1


def album_by_title(api, title):
    albums, _ = root_albums(api)
    if title in albums:
        return albums[title]
    for album in albums.values():
        for child in child_albums(api, album["id"]):
            if child["title"] == title:
                return child
    raise SystemExit(f"verification expected album {title!r} but it is missing")


def photo_index(api):
    index = {}
    albums, _ = root_albums(api)
    for album in albums.values():
        for photo in album_photos(api, album["id"]):
            index[(album["title"], photo["title"])] = photo
        for child in child_albums(api, album["id"]):
            for photo in album_photos(api, child["id"]):
                index[(child["title"], photo["title"])] = photo
    return index


def album_payload(album, title, description):
    return {
        "album_id": album["id"], "title": title, "slug": None, "license": "none",
        "description": description, "photo_sorting_column": None, "photo_sorting_order": None,
        "album_sorting_column": None, "album_sorting_order": None, "album_aspect_ratio": None,
        "photo_layout": None, "copyright": None, "tags": [], "header_id": None, "cover_id": None,
        "is_compact": False, "is_map_header": False, "is_pinned": False,
        "album_timeline": None, "photo_timeline": None,
    }


def ensure_user(api):
    users = api.request("GET", "UserManagement")
    for user in users:
        if user["username"] == REGULAR_USER["username"]:
            return user
    return api.request("POST", "UserManagement", REGULAR_USER, )


def run_seed(api, user_id):
    albums, _ = root_albums(api)
    for spec in ALBUMS:
        title = spec["title"]
        if spec["parent"] is None:
            album = albums.get(title)
        else:
            parent = albums[spec["parent"]]
            album = next((c for c in child_albums(api, parent["id"]) if c["title"] == title), None)
        if album is None:
            raise SystemExit(f"lychee:sync did not import album {title!r}; check the fixtures")
        api.request("PATCH", "Album", album_payload(album, title, spec["description"]), )
        if spec.get("public"):
            api.request("POST", "Album::updateProtectionPolicy", {
                "album_id": album["id"], "is_public": True, "is_link_required": False, "is_nsfw": False,
                "grants_download": True, "grants_full_photo_access": True, "grants_upload": False,
            }, )
        if spec.get("share_with"):
            api.request("POST", "Sharing", {
                "album_ids": [album["id"]], "user_ids": [user_id], "group_ids": [],
                "grants_download": True, "grants_full_photo_access": True, "grants_upload": False,
                "grants_edit": True, "grants_delete": False, "grants_move": False,
            }, )

    index = photo_index(api)
    missing = [f"{p['album']}/{p['title']}" for p in PHOTOS if (p["album"], p["title"]) not in index]
    if missing:
        raise SystemExit(f"lychee:sync is missing seeded photos: {missing}")

    for spec in PHOTOS:
        photo = index[(spec["album"], spec["title"])]
        album_id = photo["album_id"]
        api.request("PATCH", f"Photo?photo_id={photo['id']}&from_id={album_id}", {
            "title": spec["title"], "description": spec["description"], "tags": spec["tags"],
            "license": "reserved", "upload_date": spec["upload"], "taken_at": spec["taken"],
        }, )
        api.request("POST", "Photo::setRating", {"photo_id": photo["id"], "rating": spec["rating"]}, )

    highlighted = [index[(p["album"], p["title"])]["id"] for p in PHOTOS if p["highlighted"]]
    unhighlighted = [index[(p["album"], p["title"])]["id"] for p in PHOTOS if not p["highlighted"]]
    api.request("POST", "Photo::highlight", {"photo_ids": highlighted, "is_highlighted": True}, )
    api.request("POST", "Photo::highlight", {"photo_ids": unhighlighted, "is_highlighted": False}, )
    print(f"==> Seeded {len(PHOTOS)} photos, {len(ALBUMS)} albums, {len(highlighted)} highlights, user {REGULAR_USER['username']}")


def iso_date(value):
    return (value or "")[:10]


def run_verify(api, app_url):
    failures = []

    def check(condition, message):
        if not condition:
            failures.append(message)

    admin = api.request("GET", "Auth::user")
    check(admin.get("may_administrate") is True, "admin is not an administrator")

    users = api.request("GET", "UserManagement")
    check(sorted(u["username"] for u in users) == ["admin", REGULAR_USER["username"]], f"unexpected users: {[u['username'] for u in users]}")
    mara = next(u for u in users if u["username"] == REGULAR_USER["username"])
    check(mara["may_administrate"] is False, "seeded regular user is an administrator")

    albums, root = root_albums(api)
    expected_roots = sorted(a["title"] for a in ALBUMS if a["parent"] is None)
    check(sorted(albums) == expected_roots, f"root albums {sorted(albums)} != {expected_roots}")
    for album in albums.values():
        children = child_albums(api, album["id"])
        if album["title"] == "Nordic Coast 2026":
            check([c["title"] for c in children] == ["Lofoten Islands"], f"children of Nordic Coast 2026: {[c['title'] for c in children]}")

    signature_albums = []
    for spec in ALBUMS:
        album = album_by_title(api, spec["title"])
        photos = album_photos(api, album["id"])
        expected = sorted(p["title"] for p in PHOTOS if p["album"] == spec["title"])
        check(sorted(p["title"] for p in photos) == expected, f"photos in {spec['title']}: {sorted(p['title'] for p in photos)}")
        check(album["description"] == spec["description"], f"description of {spec['title']}: {album['description']!r}")
        check(album["is_public"] is spec["public"], f"is_public of {spec['title']}: {album['is_public']}")
        signature_albums.append({
            "title": spec["title"], "parent": spec["parent"], "description": album["description"],
            "is_public": album["is_public"], "num_photos": album["num_photos"], "num_subalbums": album["num_subalbums"],
        })

    unsorted = next((a for a in root["smart_albums"] if a["title"].lower() == "unsorted"), None)
    check(unsorted is not None, "Unsorted smart album missing")
    if unsorted is not None:
        unsorted_photos = api.request("GET", f"Album::photos?album_id={unsorted['id']}&page=1")
        check(unsorted_photos["total"] == 0, f"Unsorted has {unsorted_photos['total']} photos")

    index = photo_index(api)
    check(len(index) == len(PHOTOS), f"library has {len(index)} photos, expected {len(PHOTOS)}")
    signature_photos = []
    for spec in PHOTOS:
        photo = index.get((spec["album"], spec["title"]))
        if photo is None:
            failures.append(f"missing photo {spec['album']}/{spec['title']}")
            continue
        check(iso_date(photo["taken_at"]) == iso_date(spec["taken"]), f"taken_at of {spec['title']}: {photo['taken_at']}")
        check(iso_date(photo["created_at"]) == iso_date(spec["upload"]), f"created_at of {spec['title']}: {photo['created_at']}")
        check(photo["description"] == spec["description"], f"description of {spec['title']}: {photo['description']!r}")
        check(sorted(t["name"] for t in photo["tags"]) == sorted(spec["tags"]), f"tags of {spec['title']}: {[t['name'] for t in photo['tags']]}")
        check(photo["rating"]["rating_user"] == spec["rating"], f"rating of {spec['title']}: {photo['rating']}")
        check(photo["is_highlighted"] is spec["highlighted"], f"highlight of {spec['title']}: {photo['is_highlighted']}")
        signature_photos.append({
            "album": spec["album"], "title": photo["title"], "taken_at": iso_date(photo["taken_at"]),
            "created_at": iso_date(photo["created_at"]), "description": photo["description"],
            "tags": sorted(t["name"] for t in photo["tags"]), "rating": photo["rating"]["rating_user"],
            "highlighted": photo["is_highlighted"],
        })
    check(sum(1 for p in signature_photos if p["highlighted"]) == 4, "highlight count changed")

    studio = album_by_title(api, "Studio Sessions")
    shares = api.request("GET", f"Sharing?album_id={studio['id']}")
    check([(s["username"], s["grants_edit"]) for s in shares] == [(REGULAR_USER["username"], True)],
          f"shares of Studio Sessions: {[(s['username'], s['grants_edit']) for s in shares]}")

    archive = album_by_title(api, "Archive 2024")
    guest = Api(api.base)
    head = guest.request("GET", f"Album::head?album_id={archive['id']}")
    policy = head["resource"]["policy"]
    check(policy["is_public"] is True, f"guest album head for Archive 2024: {policy.get('is_public')}")
    check(head["resource"]["num_photos"] == 4, f"guest album head photo count: {head['resource']['num_photos']}")
    guest_photos = guest.request("GET", f"Album::photos?album_id={archive['id']}&page=1")
    check(guest_photos["total"] == 4, f"guest sees {guest_photos['total']} archive photos")
    guest_denied = False
    try:
        guest.request("GET", f"Album::photos?album_id={studio['id']}&page=1", )
    except SystemExit:
        guest_denied = True
    check(guest_denied, "guest can read the private Studio Sessions album")

    mara_api = Api(api.base)
    mara_api.login(REGULAR_USER["username"], REGULAR_USER["password"])
    mara_albums, mara_root = root_albums(mara_api, include_shared=True)
    check("Studio Sessions" in [a["title"] for a in mara_albums.values()], f"shared albums for mara: {sorted(mara_albums)}")
    check("Studio Sessions" in [a["title"] for a in mara_root["shared_albums"]],
          f"Studio Sessions is not in mara's shared_albums: {[a['title'] for a in mara_root['shared_albums']]}")
    mara_photos = mara_api.request("GET", f"Album::photos?album_id={studio['id']}&page=1")
    check(mara_photos["total"] == 4, f"mara sees {mara_photos['total']} studio photos")

    checked_urls = 0
    for spec in ALBUMS:
        album = album_by_title(api, spec["title"])
        photos = album_photos(api, album["id"])
        for photo in photos:
            urls = [data["url"] for data in photo["size_variants"].values()
                    if data is not None and str(data["url"]).startswith("http")]
            check(bool(urls), f"no browser-served image variant for {photo['title']}")
            check(all(url.startswith(app_url.rstrip("/") + "/") for url in urls),
                  f"image variant of {photo['title']} is not on APP_URL")
        photo = photos[0]
        for variant, data in photo["size_variants"].items():
            if data is None or not str(data["url"]).startswith("http"):
                continue
            url = data["url"]
            check(url.startswith(app_url.rstrip("/") + "/"), f"{variant} URL not on APP_URL: {url}")
            try:
                with urllib.request.urlopen(url, timeout=20) as resp:
                    check(resp.status == 200 and resp.headers.get_content_type().startswith("image/"),
                          f"{url} -> {resp.status} {resp.headers.get_content_type()}")
            except urllib.error.HTTPError as exc:
                failures.append(f"{url} -> {exc.code}")
            checked_urls += 1

    signature = {
        "users": sorted(u["username"] for u in users),
        "albums": sorted(signature_albums, key=lambda a: a["title"]),
        "photos": sorted(signature_photos, key=lambda p: (p["album"], p["title"])),
        "shares": [{"album": "Studio Sessions", "username": s["username"], "grants_edit": s["grants_edit"]} for s in shares],
        "public_album": "Archive 2024",
    }
    digest = hashlib.sha256(json.dumps(signature, sort_keys=True).encode()).hexdigest()
    print(json.dumps(signature, sort_keys=True, indent=1))
    print(f"==> SIGNATURE {digest[:16]} ({len(signature_photos)} photos, {len(signature_albums)} albums, {checked_urls} media URLs checked)")

    if failures:
        print("VERIFY FAIL:", file=sys.stderr)
        for failure in failures:
            print(f"  - {failure}", file=sys.stderr)
        raise SystemExit(1)
    print("==> VERIFY PASS")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("seed", "verify"))
    parser.add_argument("--api", default="http://localhost:8157/api/v2")
    parser.add_argument("--app-url", default=None)
    args = parser.parse_args()

    api = Api(args.api)
    api.login("admin", "tester1234")
    if args.command == "seed":
        run_seed(api, ensure_user(api)["id"])
    else:
        run_verify(api, args.app_url or args.api.split("/api/")[0])


if __name__ == "__main__":
    main()
