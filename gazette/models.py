# gazette_app/models.py
from django.db import models


class Users(models.Model):
    first_name = models.CharField(max_length=150, blank=True)
    last_name = models.CharField(max_length=150, blank=True)
    role = models.CharField(max_length=20, default='STAFF')
    office_or_district = models.CharField(max_length=100, blank=True) # e.g. "District 1" or "Brgy. San Jose"

    def get_councilor_name(self):
        from django.core.exceptions import ObjectDoesNotExist
        try:
            return self.councilor_profile.name
        except ObjectDoesNotExist:
            return f"{self.first_name} {self.last_name}".strip()

    class Meta:
        managed = False
        db_table = 'accounts_user'

class Document(models.Model):
    """
    OWNED MODEL: populated by LePMITS's push-sync (see gazette_sync docs on
    the LePMITS side), not read live from LePMITS's shared DB.

    `source_id` (not the local auto `id`) is LePMITS's own document id —
    the sync ingest endpoint upserts on it, and /document/<id>/ URLs
    resolve against it, so existing links keep working. Kept separate from
    the local PK rather than repurposing `id` itself, so this never has to
    touch (or risk breaking) PublicComment's existing FK to this table.

    `status` is one of three values LePMITS actually sends — "APPROVED",
    "PUBLIC_PARTICIPATION_OPEN", or "PUBLIC_PARTICIPATION_CLOSED" — never
    an internal workflow status like REFERRED/COMMITTEE/SECOND_READING;
    LePMITS translates those down to whichever of the three applies before
    sending. Public commenting is gated on
    `status == 'PUBLIC_PARTICIPATION_OPEN'` directly rather than a
    separate boolean, so there's exactly one field that can go out of
    sync with reality.
    """
    source_id = models.IntegerField(unique=True, db_index=True)

    # Denormalized display strings — the sync payload doesn't (yet) include
    # a way to resolve these to real Users/Committee records, since those
    # only exist in LePMITS's own DB. Blank until the contract is extended.
    author_name = models.CharField(max_length=200, blank=True, default='')
    committee_name = models.CharField(max_length=255, blank=True, default='')

    title = models.TextField()
    reference_no = models.CharField(max_length=100)
    doc_type = models.CharField(max_length=20)
    category = models.CharField(max_length=100, blank=True, default='')
    status = models.CharField(max_length=30)
    updated_at = models.DateTimeField(auto_now=True)

    # Kept for forward-compatibility with a possible pre-approval sync path
    # sending live draft text — always blank in practice today, since a
    # synced row already has approved_pdf or pp_pdf by definition.
    content = models.TextField(blank=True, default='')

    # LePMITS's own LibreOffice-rendered PDF for this document, captured at
    # Third Reading (or as a fallback at approval) — see approved_pdf_url.
    approved_pdf = models.CharField(max_length=255, blank=True, null=True)

    # Snapshot captured at the moment public participation opens on a still-
    # editable (not yet approved) document — see pp_pdf_url. Currently never
    # populated (no sync trigger covers this stage yet); kept so the field
    # exists once that gap is closed rather than needing a later migration.
    pp_pdf = models.CharField(max_length=255, blank=True, null=True)

    is_legacy = False

    class Meta:
        managed = True
        db_table = 'gazette_document'

    def __str__(self):
        return self.title

    @property
    def display_year(self):
        return self.updated_at.year

    @property
    def approved_pdf_url(self):
        if not self.approved_pdf:
            return None
        from django.conf import settings
        return f"{settings.LEPMITS_MEDIA_BASE_URL.rstrip('/')}/{self.approved_pdf.lstrip('/')}"

    @property
    def pp_pdf_url(self):
        if not self.pp_pdf:
            return None
        from django.conf import settings
        return f"{settings.LEPMITS_MEDIA_BASE_URL.rstrip('/')}/{self.pp_pdf.lstrip('/')}"

    def get_absolute_url(self):
        from django.urls import reverse
        return reverse('gazette_document', args=[self.source_id])


class LegacyDocument(models.Model):
    """
    OWNED MODEL: populated by LePMITS's push-sync, not read live from
    LePMITS's shared DB — see Document's docstring for the same rationale
    on `source_id` vs the local `id`. Only ever populated once a document
    has cleared signature-redaction review (public_pdf_file non-empty);
    the ingest endpoint should reject/ignore anything sent before that.
    """
    source_id = models.IntegerField(unique=True, db_index=True)

    title = models.TextField()
    reference_no = models.CharField(max_length=100)
    doc_type = models.CharField(max_length=20)
    category = models.CharField(max_length=100, blank=True, default='')
    year = models.IntegerField(null=True, blank=True)
    updated_at = models.DateTimeField(auto_now=True)

    # The original scan (pdf_file, unredacted) is intentionally never
    # mapped here — it contains real signatures and must never reach the
    # public site. Only the redacted copy, once staff have confirmed it,
    # is safe to display. Gate on public_pdf_file's presence; there is no
    # raw-scan fallback.
    public_pdf_file = models.CharField(max_length=255, blank=True, null=True)

    is_legacy = True

    class Meta:
        managed = True
        db_table = 'gazette_legacydocument'

    def __str__(self):
        return self.title

    @property
    def display_year(self):
        return self.year or self.updated_at.year

    @property
    def public_pdf_url(self):
        if not self.public_pdf_file:
            return None
        from django.conf import settings
        return f"{settings.LEPMITS_MEDIA_BASE_URL.rstrip('/')}/{self.public_pdf_file.lstrip('/')}"

    def get_absolute_url(self):
        from django.urls import reverse
        return reverse('gazette_legacy_document', args=[self.source_id])


class Session(models.Model):
    session_number = models.CharField(max_length = 20, null =True)
    council_number = models.CharField(max_length=10, null= True)
    session_time = models.CharField(max_length=10, null=True)
    previous_session_date = models.DateField(null=True, blank =True)
    invocation_by = models.CharField(max_length=50, null=True)
    session_date = models.DateField(null=True, blank=True)
    date_started = models.DateTimeField(auto_now_add=True, null=True, blank=True)
    agenda_finalized_date = models.DateTimeField(auto_now_add=True, null=True, blank=True)
    participants = models.TextField()

    class Meta:
        managed = False
        db_table = 'secretariat_session'


class PublicComment(models.Model):

    document   = models.ForeignKey(Document, on_delete=models.CASCADE, related_name='public_comments')
    name       = models.CharField(max_length=200)
    barangay   = models.CharField(max_length=100, blank=True)
    comment    = models.TextField()
    is_approved = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    tag = models.CharField(max_length=10, default='comment')
    replyTo = models.ForeignKey('self', default=None, on_delete=models.CASCADE, null=True,blank=True, related_name="replies")

    def approved_replies(self):
        return self.replies.filter(is_approved=True)

    class Meta:
        db_table = 'gazette_publiccomment'


