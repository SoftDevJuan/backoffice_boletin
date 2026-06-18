from django.urls import path
from .views import *

urlpatterns = [
    path('api/consultar-expediente/', consultar_expediente, name='consultar_expediente'),
    path('api/scraper-masivo/', scraper_masivo, name='scraper_masivo'),
]