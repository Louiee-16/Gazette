# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this is

A Django 6 app ("Gazette") that is a **public-facing read companion** to a separate system called **LePMITS** (a legislative document tracking system). This project and LePMITS share the same PostgreSQL database (`Final_LePMITS`); LePMITS owns most of the schema, and this app mostly reads from it.

## Commands

```powershell
# Activate the existing venv (Windows)
venv\Scripts\Activate.ps1

# Install deps (see "requirements.txt encoding" gotcha below)
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

Most models in `gazette/models.py` and `councilors/models.py` are **shadow models** (`Meta.managed = False`) that map onto tables owned by LePMITS, not by this Django project:

- `gazette.Users` → `accounts_user`
- `gazette.Document` → `documents_document`
- `gazette.LegacyDocument` → `documents_legacydocument`
- `gazette.Session` → `secretariat_session`
- `councilors.Councilors` → `councilors_councilor`
- `councilors.Committee` → `committees_committee`

Because these are unmanaged, **do not add/alter fields casually** — a mismatch with LePMITS's actual schema will break at query time, not at migration time. This app also has **no filesystem access to LePMITS media** — legacy-document PDFs are served by LePMITS itself and linked to via `settings.LEPMITS_MEDIA_BASE_URL` (see `LegacyDocument.pdf_url`).

The one table this project actually owns and migrates is `gazette.PublicComment` (`gazette_publiccomment`), used for public comment threads on documents.

### Document vs LegacyDocument

Two distinct sources feed the public gazette listing, merged manually in `gazette_index` (`gazette/views.py`) since they don't share a schema:

- `Document` — goes through a workflow (`status`: `APPROVED`/`REFERRED`/etc., `public_participation` flag gates public commenting). This is the live LePMITS workflow data.
- `LegacyDocument` — pre-system or scanned bills, always public, no workflow/status field, has `ocr_processed`/`extracted_text` from OCR ingestion.

Both expose `updated_at` and `display_year` so they can be sorted/paginated together as a single Python list (not a DB query) in `gazette_index`.

### Comment threading

`PublicComment.tag` (`"comment"` vs `"reply"`) plus the self-referential `replyTo` FK implement one level of reply threading — see `gazette_submit_comment` in `gazette/views.py`.

## Templates

Templates live in a top-level `Templates/` directory (capitalized, not the Django-conventional `templates/`), wired via `TEMPLATES[0]['DIRS']` in `config/settings.py` (alongside `APP_DIRS = True`). Layout:

- `Templates/gazette/` — index, hearings, base layout
- `Templates/Documents/` — per-document pages (`gazette_document.html`, `legacy_document.html`, `PPdocument.html` for public-participation documents)

## Known gotchas

- `requirements.txt` is saved as **UTF-16** (with BOM), not UTF-8 — if editing it by hand, preserve that encoding or `pip install -r` may fail to parse it.
- `gazette_download` (PDF export) imports `xhtml2pdf` lazily inside the view and catches `ImportError` to return a 500 with a plain message — `xhtml2pdf` is not in `requirements.txt`, so PDF download is expected to be unavailable unless it's installed separately.
- `config/settings.py` has `DEBUG = True`, `ALLOWED_HOSTS = ['*']`, and hardcoded DB credentials — this is dev-only configuration, not hardened for production.
- The `councilors` app's `admin.py`/`views.py` are still empty boilerplate (no URLs wired up); its models are currently only consumed from `gazette` (e.g. `Document.referred_committee` → `councilors.Committee`).
