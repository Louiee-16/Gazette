from django.urls import path
from . import views
 
urlpatterns = [
    path('',views.gazette_index,name='gazette_index'),
    path('document/<int:doc_id>/',views.gazette_document,name='gazette_document'),
    path('PPdocument/<int:doc_id>/',views.public_participation_document,name='public-participation-document'),

    path('document/<int:doc_id>/download/',views.gazette_download,name='gazette_download'),
    path('document/<int:doc_id>/comment/',views.gazette_submit_comment,name='gazette_submit_comment'),
    path('hearings/',views.gazette_hearings,name='gazette_hearings'),
]