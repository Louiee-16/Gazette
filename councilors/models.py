from django.db import models
from gazette.models import Users

class Councilors(models.Model):
    user = models.OneToOneField(Users, on_delete=models.CASCADE, db_column='user_id')
    name = models.CharField(max_length=50, blank=True)
    email = models.EmailField(max_length=50, blank=False, null=False)
    district = models.IntegerField(choices=[(1, 'District 1'), (2, 'District 2')])
    profile_picture = models.ImageField(upload_to='councilors/', null=True, blank=True)

    is_active = models.BooleanField(default=True, help_text="Uncheck if they are no longer in office")

    class Meta:
        managed = False
        db_table = 'councilors_councilor'
        
    def __str__(self):
        return self.name
    
    
class Committee(models.Model):
    name = models.CharField(max_length=255, unique=True)
    description = models.TextField(blank=True)

    chairman = models.ForeignKey(
        Councilors, 
        on_delete=models.SET_NULL,
        null=True,
        related_name='chaired_committees'
    )
    vice_chairman = models.ForeignKey(
        Councilors, 
        on_delete=models.SET_NULL, 
        null=True,
        related_name='vice_chaired_committees'
    )
    member = models.ForeignKey(
        Councilors, 
        on_delete=models.SET_NULL, 
        null=True,
        related_name='member_committees'
    )

    class Meta:
        managed = False
        db_table = 'committees_committee'

