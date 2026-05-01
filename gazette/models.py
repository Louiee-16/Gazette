# gazette_app/models.py
from django.db import models


class Users(models.Model):
    role = models.CharField(max_length=20, default='STAFF')
    office_or_district = models.CharField(max_length=100, blank=True) # e.g. "District 1" or "Brgy. San Jose"
    def get_councilor_name(self):
        try:
            return self.councilor_profile.name
        except:
            return self.username
        
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

    class Meta:
        managed = False            
        db_table = 'documents_document' 

    def __str__(self):
        return self.title



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
    document   = models.ForeignKey(Document, on_delete=models.CASCADE)
    name       = models.CharField(max_length=200)
    barangay   = models.CharField(max_length=100, blank=True)
    comment    = models.TextField()
    is_approved = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    ip_address = models.GenericIPAddressField(null=True, blank=True)
