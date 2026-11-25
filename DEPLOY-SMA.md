# Lychee - Deployment, Seed, and Verification Notes

## Quick Start

```bash
./tester-env deploy    # Build the upstream Dockerfile from source, start the container, create admin
./tester-env seed      # Import seed/photos + apply the fixed library metadata
./tester-env verify    # Assert the seeded library through the app API
./tester-env reset     # Remove container + data volumes (image kept)
```

## Baseline

- Pinned SHA: `ef9339bac648a30557fb4e8dfda65af9d3e67268` (= tag `v7.13.1`, latest stable release).
- Image: upstream `Dockerfile` unchanged; built from editable source in the fork worktree.
- Single service: FrankenPHP + Octane, SQLite at `/data/database.sqlite` (`lychee-data`
  volume), `public/uploads` on the `lychee-uploads` volume, `QUEUE_CONNECTION=sync`
  (image processing inline), `AI_VISION_ENABLED=false`, v7 (PrimeVue) UI.
- `APP_URL` must be the origin the browser visits: `TESTER_ENV_BROWSER_ORIGIN` when set,
  otherwise the Docker bridge gateway origin (never bare `localhost`). Lychee bakes it
  into the SPA `<base href>` and into every absolute media URL.
- Port: 8157 by default (`--port`/`PORT`), container name `tester-env-lychee[-<run-id>]`.

## Credentials

| User | Password | Role |
| --- | --- | --- |
| `admin` | `tester1234` | administrator, owner of every seeded album |
| `mara` | `tester1234` | regular user (may upload, may edit own settings, not admin) |

Created through `docker/scripts/create-admin-user.sh` and
`POST /api/v2/UserManagement`; the web installer is never used.

## Fixtures

`seed/photos/` holds 17 committed JPEGs (800x600, ~220 KB total, no EXIF) arranged as
album directories; `lychee:sync` turns directories into albums (nested directories into
child albums) and the filename stem into the photo title. Regenerate them with
`seed/generate-fixtures.sh` (host ImageMagick, same commands -> same images).

Photo dates are not read from EXIF: `seed` sets `taken_at` and `upload_date`
(`created_at`) explicitly through `PATCH /api/v2/Photo`, so dates and sort order do not
depend on fixture mtimes.

## Seed

```bash
./tester-env seed
```

1. `lychee:sync /seed/<entry> --owner_id=1 --skip_duplicates=1` for each top-level
   fixture directory (one per root album).
2. `tester-env-seed.py seed` (HTTP API, admin session):
   - create `mara` if missing;
   - set each album's description (`PATCH /api/v2/Album`);
   - make `Archive 2024` public (`Album::updateProtectionPolicy`);
   - share `Studio Sessions` with `mara` (`POST /api/v2/Sharing`, grants_edit);
   - for every photo: title, description, tags, taken/upload dates (`PATCH /api/v2/Photo`),
     rating (`Photo::setRating`), highlight flag (`Photo::highlight`).
3. Idempotent: sync skips duplicates, PATCH/setRating/highlight overwrite, Sharing
   replaces the previous permission. Re-running `seed` on a seeded library leaves the
   verify signature unchanged.

Seeded state (stable, verify prints a SHA-256 signature over it):

| Album | Parent | Photos | Description |
| --- | --- | --- | --- |
| `Nordic Coast 2026` | - | 5 | Field notes and coastal studies from the September 2026 Norway trip. |
| `Lofoten Islands` | Nordic Coast 2026 | 4 | Selected frames from the Lofoten leg of the trip. |
| `Studio Sessions` | - | 4 | Client selects from the autumn product and portrait sessions. (shared with mara, edit) |
| `Archive 2024` | - | 4 | Older work kept for reference and licensing requests. (public) |

- Users: 2 (`admin`, `mara`); albums: 4; photos: 17; Unsorted: 0.
- Dates: 13 photos taken 2026-09-12..2026-10-03, 4 taken 2024-01-18..2024-09-09
  (two Timeline year groups); `created_at` one day-ish later, fixed.
- Ratings (admin, 0 = unrated): 4 photos at 5, 3 at 4, 3 at 3, 3 at 2, 2 at 1, 2 at 0.
- Highlights: `Fjord at Blue Hour`, `Reine Harbour Reflections`,
  `Northern Lights over Vestfjorden`, `Portrait with Window Light`.
- Tags: 31 distinct (e.g. `fjord`, `aurora`, `portrait`, `archive`, `product`).
- Five photos intentionally have an empty description (`Sea Stack from the Ferry`,
  `Sheep on the Coastal Road`, `Empty Pier at Dawn`, `Snow on the Fire Escape`,
  `Market Street in Motion`) as the realistic missing-optional-field edge case; the
  other 12 carry descriptions.

`favourites` are not seedable: Lychee v7 keeps them client-side in localStorage, and the
metrics counter that would be visible server-side is disabled by default and skips
admins. Use the highlight flag and ratings as deterministic per-photo markers.

## Verify

```bash
./tester-env verify
```

Asserts, through the same API the SPA uses: admin login, user list, root album titles,
nested child album, album descriptions/counts, exact photo titles per album, taken/upload
dates, descriptions, tags, per-photo rating, highlight flags, Unsorted == 0, sharing of
`Studio Sessions` with `mara`, guest access to the public `Archive 2024` (and denial for
`Studio Sessions`), `mara` login and shared-album visibility, and that every non-null
image variant URL sits on `APP_URL` and returns `200 image/*`.

It prints a canonical JSON signature plus its SHA-256 prefix; reset+deploy+seed must
reproduce the same signature (observed `8bcc58001dee8c78`).

## Browser-visible assertions for smoke verification

- Login `admin / tester1234` lands on a populated gallery: Albums shows
  `Nordic Coast 2026` (5 photos, 1 sub-album), `Studio Sessions` (4), `Archive 2024` (4).
- Open `Nordic Coast 2026` -> thumbnails render; child album `Lofoten Islands` is listed
  and opens with 4 photos.
- Open `Northern Lights over Vestfjorden`: detail view shows description
  "First clear aurora of the trip.", tags aurora/night, taken date 2026-09-17, and the
  highlight (flag) state.
- Highlighted smart album shows the 4 highlighted photos; ratings filter (5 stars)
  shows 4 photos; Unsorted is empty.
- `Archive 2024` opens with a guest session (public).

## Reset

```bash
./tester-env reset && ./tester-env deploy && ./tester-env seed && ./tester-env verify
```

`reset` removes the container plus `lychee-data` and `lychee-uploads` (the image is kept);
it also clears the file cache, and with it the login throttle counter. Known caveat: ten
admin/mara logins from the same host IP within an hour trigger Lychee's own
`throttle:10,60,login` and API calls return 429 until a reset or the window expires.
