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
    SHADOW MODEL: Matches the 'documents_document' table in LePMITS.
    We only define the fields we actually want to show on the website.
    """
    author = models.ForeignKey(Users, on_delete=models.DO_NOTHING, db_column='author_id')
    title = models.TextField()
    reference_no = models.CharField(max_length=100)
    content = models.TextField()
    doc_type = models.CharField(max_length=20)
    status = models.CharField(max_length=20)
    created_at = models.DateTimeField()
    updated_at = models.DateTimeField(auto_now=True)
    public_participation = models.BooleanField(default=False)
    referred_committee = models.ForeignKey('councilors.Committee', on_delete=models.DO_NOTHING, db_column='referred_committee_id')

    # LePMITS's own LibreOffice-rendered PDF for this document, captured at
    # Third Reading (or as a fallback at approval) — see approved_pdf_url.
    # Not populated for documents approved before this field existed, so
    # templates must fall back to rendering `content` when this is empty.
    approved_pdf = models.CharField(max_length=255, blank=True, null=True)

    # Snapshot captured at the moment public participation opens on a still-
    # editable (not yet approved) document — see pp_pdf_url. Frozen at
    # open time (re-captured fresh on a later reopen), so it can go stale
    # relative to `content` if staff amend the draft while PP stays open;
    # that's deliberate, not a bug. Gate visibility on this being non-empty
    # or on public_participation, never on status (unlike approved_pdf,
    # this can be set on a document that's still REFERRED/COMMITTEE).
    pp_pdf = models.CharField(max_length=255, blank=True, null=True)

    is_legacy = False

    class Meta:
        managed = False
        db_table = 'documents_document'

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
        return reverse('gazette_document', args=[self.id])


class LegacyDocument(models.Model):
    """
    SHADOW MODEL: Matches the 'documents_legacydocument' table in LePMITS.
    Already-passed bills (pre-system or scanned) uploaded directly by staff.
    No status/workflow field — every row is a permanent, public record.
    """
    title = models.TextField()
    reference_no = models.CharField(max_length=100)
    doc_type = models.CharField(max_length=20)
    year = models.IntegerField(null=True, blank=True)
    # The original scan (pdf_file, unredacted) is intentionally NOT mapped
    # here — it contains real signatures and must never reach the public
    # site. Only the redacted copy, once staff have confirmed it, is safe
    # to display. Gate on public_pdf_file's presence; never fall back to
    # the raw scan.
    public_pdf_file = models.CharField(max_length=255, blank=True, null=True)
    extracted_text = models.TextField(blank=True)
    ocr_processed = models.BooleanField(default=False)
    uploaded_at = models.DateTimeField()

    is_legacy = True

    class Meta:
        managed = False
        db_table = 'documents_legacydocument'

    def __str__(self):
        return self.title

    @property
    def updated_at(self):
        return self.uploaded_at

    @property
    def display_year(self):
        return self.year or self.uploaded_at.year

    @property
    def public_pdf_url(self):
        if not self.public_pdf_file:
            return None
        from django.conf import settings
        return f"{settings.LEPMITS_MEDIA_BASE_URL.rstrip('/')}/{self.public_pdf_file.lstrip('/')}"

    def get_absolute_url(self):
        from django.urls import reverse
        return reverse('gazette_legacy_document', args=[self.id])


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


