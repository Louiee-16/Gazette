"""
Ingest endpoint for LePMITS's push-sync: receives a signed POST whenever a
document is approved, public participation opens/closes on it, or a legacy
scan clears signature-redaction review, and upserts the corresponding
gazette_document/gazette_legacydocument row.

This is the *only* way those tables get written outside the Django admin —
Gazette itself never reads LePMITS's DB directly for this data. See
Document/LegacyDocument's docstrings in models.py, and CLAUDE.md, for the
architecture this replaces (shared-DB shadow models).

Security model: HMAC-SHA256 over "<timestamp>.<raw payload bytes>" using a
secret shared out-of-band (GAZETTE_SYNC_SECRET), verified in constant time.
A stale timestamp is rejected (replay protection). The payload is validated
against a strict allow-list — unknown fields, wrong types, or enum values
outside the documented contract are all rejected outright, not merged in.
CSRF is intentionally not applied here: this is a server-to-server webhook
authenticated by the HMAC signature, not a browser form submission, and no
browser session/cookie is ever involved. Network-level restriction (this
should only be reachable from LePMITS over Tailscale, never the public
listener) is a deployment concern outside what this Django view can
enforce by itself — must be configured at the reverse-proxy/firewall layer.
"""

import hashlib
import hmac
import json
import time

from django.conf import settings
from django.core.files.base import ContentFile
from django.core.files.storage import default_storage
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST

from .models import Document, LegacyDocument

MAX_TIMESTAMP_SKEW_SECONDS = 300  # 5 minutes, matches the contract's "a few minutes' window"
MAX_PAYLOAD_BYTES = 16 * 1024  # payload is a handful of short fields; nothing legitimate is ever this large
PDF_MAGIC = b'%PDF-'

ALLOWED_DOC_TYPES = {'ORDINANCE', 'RESOLUTION'}

# field name -> (required, type-check) for each source_type's payload.
DOCUMENT_FIELDS = {
    'source_type': (True, str),
    'source_id': (True, int),
    'reference_no': (True, str),
    'title': (True, str),
    'doc_type': (True, str),
    'category': (True, str),
    'year': (True, (int, type(None))),
    'status': (True, str),
}
LEGACY_DOCUMENT_FIELDS = {
    'source_type': (True, str),
    'source_id': (True, int),
    'reference_no': (True, str),
    'title': (True, str),
    'doc_type': (True, str),
    'category': (True, str),
    'year': (True, (int, type(None))),
    'status': (True, str),
}
DOCUMENT_STATUSES = {'APPROVED', 'PUBLIC_PARTICIPATION_OPEN', 'PUBLIC_PARTICIPATION_CLOSED'}
LEGACY_STATUSES = {'REDACTED', 'NO_REDACTION_NEEDED'}


class SyncError(Exception):
    def __init__(self, status, message):
        self.status = status
        self.message = message


def _verify_signature(timestamp_str, payload_bytes, signature):
    secret = settings.GAZETTE_SYNC_SECRET
    if not secret:
        return False
    if not signature or not timestamp_str:
        return False
    message = timestamp_str.encode('utf-8') + b'.' + payload_bytes
    expected = hmac.new(secret.encode('utf-8'), message, hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, signature)


def _check_timestamp(timestamp_str):
    try:
        ts = int(timestamp_str)
    except (TypeError, ValueError):
        raise SyncError(400, 'invalid timestamp')
    if abs(time.time() - ts) > MAX_TIMESTAMP_SKEW_SECONDS:
        raise SyncError(400, 'stale timestamp')


def _validate_payload(payload, fields, allowed_statuses):
    if not isinstance(payload, dict):
        raise SyncError(400, 'payload must be a JSON object')
    unknown = set(payload.keys()) - set(fields.keys())
    if unknown:
        raise SyncError(400, f'unexpected field(s): {sorted(unknown)}')
    for name, (required, type_check) in fields.items():
        if name not in payload:
            if required:
                raise SyncError(400, f'missing field: {name}')
            continue
        if not isinstance(payload[name], type_check):
            raise SyncError(400, f'field {name} has wrong type')
    if payload['doc_type'] not in ALLOWED_DOC_TYPES:
        raise SyncError(400, 'invalid doc_type')
    if payload['status'] not in allowed_statuses:
        raise SyncError(400, 'invalid status')
    if payload['source_id'] <= 0:
        raise SyncError(400, 'invalid source_id')


def _save_pdf(uploaded_file, subdir, source_id):
    """Save the uploaded PDF at a deterministic path (so a resend/redo
    overwrites cleanly instead of accumulating renamed copies), after
    checking it's actually a PDF. Returns the stored relative path."""
    head = uploaded_file.read(len(PDF_MAGIC))
    uploaded_file.seek(0)
    if head != PDF_MAGIC:
        raise SyncError(400, 'file is not a PDF')
    path = f'sync/{subdir}/{source_id}.pdf'
    if default_storage.exists(path):
        default_storage.delete(path)
    default_storage.save(path, ContentFile(uploaded_file.read()))
    return path


@csrf_exempt
@require_POST
def sync_ingest(request):
    try:
        signature = request.POST.get('signature', '')
        timestamp_str = request.POST.get('timestamp', '')
        payload_str = request.POST.get('payload', '')
        payload_bytes = payload_str.encode('utf-8')

        if len(payload_bytes) > MAX_PAYLOAD_BYTES:
            raise SyncError(400, 'payload too large')
        if not _verify_signature(timestamp_str, payload_bytes, signature):
            raise SyncError(401, 'invalid signature')
        _check_timestamp(timestamp_str)

        try:
            payload = json.loads(payload_str)
        except (json.JSONDecodeError, TypeError):
            raise SyncError(400, 'payload is not valid JSON')

        source_type = payload.get('source_type')
        uploaded_file = request.FILES.get('file')

        if source_type == 'document':
            _validate_payload(payload, DOCUMENT_FIELDS, DOCUMENT_STATUSES)
            defaults = {
                'reference_no': payload['reference_no'],
                'title': payload['title'],
                'doc_type': payload['doc_type'],
                'category': payload['category'],
                'status': payload['status'],
            }
            if uploaded_file is not None:
                path = _save_pdf(uploaded_file, 'document', payload['source_id'])
                if payload['status'] == 'APPROVED':
                    defaults['approved_pdf'] = path
                else:  # PUBLIC_PARTICIPATION_OPEN (only other status a file arrives with)
                    defaults['pp_pdf'] = path
            # PUBLIC_PARTICIPATION_CLOSED with no file: deliberately leave
            # approved_pdf/pp_pdf untouched (update_or_create only applies
            # keys present in defaults) — the frozen pp_pdf, if any, stays
            # visible read-only rather than being cleared.
            Document.objects.update_or_create(source_id=payload['source_id'], defaults=defaults)

        elif source_type == 'legacy_document':
            _validate_payload(payload, LEGACY_DOCUMENT_FIELDS, LEGACY_STATUSES)
            defaults = {
                'reference_no': payload['reference_no'],
                'title': payload['title'],
                'doc_type': payload['doc_type'],
                'category': payload['category'],
                'year': payload['year'],
            }
            if uploaded_file is not None:
                defaults['public_pdf_file'] = _save_pdf(uploaded_file, 'legacy_document', payload['source_id'])
            LegacyDocument.objects.update_or_create(source_id=payload['source_id'], defaults=defaults)

        else:
            raise SyncError(400, 'invalid source_type')

    except SyncError as e:
        return JsonResponse({'error': e.message}, status=e.status)

    return JsonResponse({'ok': True})
