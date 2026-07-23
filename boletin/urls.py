from django.urls import path, include
from .views import *
from .apiviews import *
from rest_framework.routers import DefaultRouter

from django.conf import settings # <-- NUEVO
from django.conf.urls.static import static 

router = DefaultRouter()
router.register(r'usuarios', UsuarioViewSet, basename='usuario')
router.register(r'juzgados', JuzgadoViewSet, basename='juzgado')
router.register(r'expedientes', ExpedienteViewSet, basename='expediente')
router.register(r'acuerdos', AcuerdoViewSet, basename='acuerdo')
router.register(r'adjuntos', AdjuntoViewSet, basename='adjunto')

urlpatterns = [
    path('api/consultar-expediente/', consultar_expediente, name='consultar_expediente'),
    path('api/scraper-masivo/', scraper_masivo, name='scraper_masivo'),
    path('api/login/', LoginAPIView.as_view(), name='api-login'),
    path('api/dashboard/', DashboardStatsAPIView.as_view(), name='api-dashboard'),
    
    path('api/', include(router.urls))
]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)