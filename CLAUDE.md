# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this is

A Django 6 app ("Gazette") that is a **public-facing read companion** to a separate system called **LePMITS** (a legislative document tracking system).

The architecture is mid-transition. Historically this project shared LePMITS's PostgreSQL database (`Final_LePMITS`) directly, reading LePMITS-owned tables live via unmanaged shadow models. `Document` and `LegacyDocument` have since moved off that pattern entirely — they're now real, independently-managed Gazette tables (`gazette_document`/`gazette_legacydocument`) populated by a push-sync from LePMITS: a signed HTTP POST to `gazette.sync.sync_ingest` (`/sync/ingest/`, see `gazette/sync.py`) whenever a document is approved, public participation opens/closes on it, or a legacy scan clears redaction review — never a live DB read. This was driven by the planned move to hosting Gazette separately (e.g. AWS Lightsail) — a public-facing app should not have live read access to LePMITS's full internal schema (drafts, staff records, session data), only to the specific subset that's actually meant to be public. The PDF files themselves are pushed in the same request and stored under Gazette's own `MEDIA_ROOT`, not linked back to LePMITS's media server.

**`/sync/ingest/` is meant to be reachable only from LePMITS, never the public listener** (over Tailscale, per the design doc on LePMITS's side) — that's a deployment/network-layer concern (reverse proxy or firewall config), not something `gazette/sync.py` enforces itself. The view's own defenses are HMAC-SHA256 signature verification (`GAZETTE_SYNC_SECRET`, shared out-of-band, fails closed if unset), a replay-protection timestamp window, and strict allow-list payload validation (unknown fields/wrong types/out-of-contract enum values all rejected, not merged in).

`Users`, `Session`, `Councilors`, and `Committee` have **not** made this transition yet and are still unmanaged shadow models reading live from the shared DB — they have the same "won't exist in a separate database" problem `Document`/`LegacyDocument` used to have, unresolved as of this writing.

## Commands

```powershell
# Activate the existing venv (Windows)
venv\Scripts\Activate.ps1

# Install deps
pip install -r requirements.txt

# Run the dev server
python manage.py runserver

# Migrations (only councilors/gazette-owned tables get real migrations — see Data model below)
python manage.py makemigrations
python manage.py migrate

# Tests (currently just empty boilerplate in gazette/tests.py and councilors/tests.py — no real tests exist yet)
python manage.py test
```

There is no linter/formatter config in the repo currently.

## Data model: shadow models vs. owned models

`gazette.Users`, `gazette.Session`, `councilors.Councilors`, and `councilors.Committee` are still **shadow models** (`Meta.managed = False`) mapping onto tables owned and live-read from LePMITS's shared DB (`accounts_user`, `secretariat_session`, `councilors_councilor`, `committees_committee`). Because these are unmanaged, **do not add/alter fields casually** — a mismatch with LePMITS's actual schema will break at query time, not at migration time.

`gazette.Document`, `gazette.LegacyDocument`, and `gazette.PublicComment` are **owned models** — real Gazette tables (`gazette_document`, `gazette_legacydocument`, `gazette_publiccomment`) with real migrations. Document/LegacyDocument are populated by LePMITS's push-sync rather than written by this app directly; PublicComment is written directly by `gazette_submit_comment` when a visitor comments.

Because Document/LegacyDocument are sync-populated, not FK-linked into LePMITS's own `Users`/`Committee` tables (which won't exist once Gazette has its own separate database), author and committee are **denormalized plain strings** (`Document.author_name`, `Document.committee_name`) rather than foreign keys — populated only if/when the sync payload includes them, which it doesn't yet as of this writing (a known gap, not a bug). PDFs (`Document.approved_pdf`/`pp_pdf`, `LegacyDocument.public_pdf_file`) are plain path strings under `MEDIA_ROOT`, saved by the sync ingest endpoint itself (`gazette/sync.py`) and resolved into URLs via `settings.MEDIA_URL` (`gazette.models._media_url`) — this app no longer depends on reaching LePMITS's media server for anything.

`source_id` (not the local auto `id`) is LePMITS's own document id on both models — the sync ingest upserts on it, and it's what `/document/<id>/`-style URLs resolve against (`get_object_or_404(Document, source_id=doc_id)`, not `id=doc_id`). This is deliberate, not a shortcut: repurposing the real PK for this would have required altering a column `PublicComment`'s FK already depends on.

### Document vs LegacyDocument

Two distinct sources feed the public gazette listing, merged manually in `gazette_index` (`gazette/views.py`) since they don't share a schema:

- `Document` — `status` is always one of exactly three values LePMITS sends: `APPROVED`, `PUBLIC_PARTICIPATION_OPEN`, or `PUBLIC_PARTICIPATION_CLOSED` — never an internal LePMITS workflow status (REFERRED/COMMITTEE/SECOND_READING/etc. are translated down to one of the three before sending). `status` is the single source of truth for gating public commenting (`gazette_submit_comment`) and `gazette_hearings`'s "open for comment" list — there is no separate boolean for this. `approved_pdf` is set at `APPROVED`; `pp_pdf` is set at `PUBLIC_PARTICIPATION_OPEN` and deliberately left untouched (not cleared) at `PUBLIC_PARTICIPATION_CLOSED`, so a closed measure's document stays visible read-only rather than disappearing.
- `LegacyDocument` — pre-system or scanned bills. `public_pdf_file` is only ever populated once LePMITS staff confirm a document's real signatures have been redacted from the scan — every view (`gazette_index`, the year filter, `gazette_legacy_document`, related-documents) filters to that being non-empty, so an unreviewed scan is absent from listings and 404s on direct URL access. There is intentionally no fallback to the raw scan.

Both expose `updated_at` and `display_year` so they can be sorted/paginated together as a single Python list (not a DB query) in `gazette_index`.

### Comment threading

`PublicComment.tag` (`"comment"` vs `"reply"`) plus the self-referential `replyTo` FK implement one level of reply threading — see `gazette_submit_comment` in `gazette/views.py`.

## Templates

Templates live in a top-level `Templates/` directory (capitalized, not the Django-conventional `templates/`), wired via `TEMPLATES[0]['DIRS']` in `config/settings.py` (alongside `APP_DIRS = True`). Layout:

- `Templates/gazette/` — index, hearings, base layout
- `Templates/Documents/` — per-document pages (`gazette_document.html`, `legacy_document.html`, `PPdocument.html` for public-participation documents)

## Known gotchas

- `gazette_download` (PDF export) imports `xhtml2pdf` lazily inside the view and catches `ImportError` to return a 500 with a plain message — `xhtml2pdf` is not in `requirements.txt`, so PDF download is expected to be unavailable unless it's installed separately. Left intentionally dormant/unlinked from the UI.
- Secrets (`DJANGO_SECRET_KEY`, `DB_PASSWORD`, `GAZETTE_SYNC_SECRET`) come from environment variables via a minimal built-in `.env` loader in `config/settings.py` (no `python-dotenv` dependency) — copy `.env.example` to `.env` and fill in real values. `DB_PASSWORD` fails loudly at startup if unset; `GAZETTE_SYNC_SECRET` fails closed (rejects every sync request) instead, since the app should still start without it configured. `config/settings.py` still defaults `DEBUG`/`ALLOWED_HOSTS` to permissive dev values (`True`/`*`) unless overridden — not hardened for production as-is.
- The `councilors` app's `admin.py`/`views.py` are still empty boilerplate (no URLs wired up); its models are no longer consumed from `gazette` at all now that `Document.committee_name` is a plain string rather than an FK to `councilors.Committee`.
- Local dev media serving (`MEDIA_URL`/`MEDIA_ROOT`) only works because `config/urls.py` adds a `static()` fallback when `DEBUG=True` — a real deployment needs the web server itself (nginx etc.) serving `MEDIA_ROOT`, Django doesn't do this safely outside `DEBUG`.
