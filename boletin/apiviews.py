from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.authtoken.models import Token
from django.contrib.auth import authenticate
from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from .models import Expediente, Usuario, Juzgado, Notificacion, Acuerdo
from rest_framework import viewsets
from .serializers import *
from django.db.models import Q
from rest_framework.parsers import MultiPartParser, FormParser

class LoginAPIView(APIView):
    def post(self, request):
        telefono = request.data.get('telefono')
        password = request.data.get('password')
        
        # Django usará nuestro CustomUserModel para validar con teléfono y password
        user = authenticate(username=telefono, password=password)
        
        if user is not None:
            # Generamos o traemos el Token de acceso seguro
            token, created = Token.objects.get_or_create(user=user)
            return Response({
                'token': token.key,
                'user': {
                    'id': user.id,
                    'nombre': user.nombre,
                    'telefono': user.telefono,
                    'role': 'admin' if user.is_superuser else 'user'
                }
            })
        else:
            return Response(
                {'detail': 'Credenciales incorrectas o usuario inactivo.'}, 
                status=status.HTTP_401_UNAUTHORIZED
            )



class DashboardStatsAPIView(APIView):
    permission_classes = [IsAuthenticated] # Solo usuarios logueados pueden entrar

    def get(self, request):
        user = request.user
        is_admin = user.is_superuser

        if is_admin:
            stats = {
                'expedientes_count': Expediente.objects.count(),
                'usuarios_count': Usuario.objects.count(),
                'juzgados_count': Juzgado.objects.count(),
                'alertas_count': Notificacion.objects.filter(estatus='fallido').count(),
            }
            ultimos_acuerdos = Acuerdo.objects.select_related('expediente__juzgado').order_by('-created_at')[:5]
            recent_items = [
                {
                    'id': a.id,
                    'titulo': f"Expediente {a.expediente.numero_expediente}",
                    'subtitulo': f"{a.expediente.juzgado.nombre} • {a.fecha_acuerdo.strftime('%Y-%m-%d')}",
                } for a in ultimos_acuerdos
            ]
        else:
            stats = {
                'expedientes_count': Expediente.objects.filter(usuarios=user).count(),
                'alertas_count': Notificacion.objects.filter(usuario=user, estatus='pendiente').count(),
            }
            ultimas_notif = Notificacion.objects.filter(usuario=user).select_related('acuerdo__expediente__juzgado').order_by('-fecha_intento')[:5]
            recent_items = [
                {
                    'id': n.id,
                    'titulo': f"Expediente {n.acuerdo.expediente.numero_expediente if n.acuerdo else 'N/A'}",
                    'subtitulo': f"Estado: {n.get_estatus_display()} • {n.fecha_intento.strftime('%Y-%m-%d')}",
                } for n in ultimas_notif
            ]

        return Response({
            'stats': stats,
            'recent_items': recent_items
        })



class UsuarioViewSet(viewsets.ModelViewSet):
    queryset = Usuario.objects.all().order_by('-created_at')
    serializer_class = UsuarioSerializer
    permission_classes = [IsAuthenticated] # Proteger los endpoints
    
    # Solo los administradores deberían poder gestionar usuarios
    def get_queryset(self):
        user = self.request.user
        if user.is_superuser:
            return Usuario.objects.all().order_by('-created_at')
        return Usuario.objects.filter(id=user.id)



class JuzgadoViewSet(viewsets.ModelViewSet):
    serializer_class = JuzgadoSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        # Solo admin puede gestionar juzgados. 
        # (Si los usuarios normales solo deben verlos, puedes ajustar los permisos luego)
        queryset = Juzgado.objects.all().order_by('materia', 'id_boletin')
        
        # Filtros provenientes de React
        materia = self.request.query_params.get('materia', None)
        search = self.request.query_params.get('search', None)

        if materia:
            queryset = queryset.filter(materia=materia)
        if search:
            queryset = queryset.filter(
                Q(nombre__icontains=search) | Q(id_boletin__icontains=search)
            )
            
        return queryset


class ExpedienteViewSet(viewsets.ModelViewSet):
    serializer_class = ExpedienteSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        user = self.request.user
        
        # 1. Filtro por Rol
        if user.is_superuser:
            queryset = Expediente.objects.all().select_related('juzgado').order_by('-created_at')
        else:
            queryset = Expediente.objects.filter(usuarios=user).select_related('juzgado').order_by('-created_at')

        # 2. Parámetros de búsqueda de React
        juzgado_id = self.request.query_params.get('juzgado', None)
        search = self.request.query_params.get('search', None)

        if juzgado_id:
            queryset = queryset.filter(juzgado_id=juzgado_id)
        if search:
            queryset = queryset.filter(
                Q(numero_expediente__icontains=search) | 
                Q(partes__icontains=search)
            )
            
        return queryset


class AcuerdoViewSet(viewsets.ModelViewSet):
    serializer_class = AcuerdoSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        queryset = Acuerdo.objects.all().order_by('-fecha_acuerdo', '-created_at')
        # Filtramos por el expediente que el usuario está viendo
        expediente_id = self.request.query_params.get('expediente', None)
        if expediente_id:
            queryset = queryset.filter(expediente_id=expediente_id)
        return queryset

class AdjuntoViewSet(viewsets.ModelViewSet):
    serializer_class = AdjuntoSerializer
    permission_classes = [IsAuthenticated]
    parser_classes = [MultiPartParser, FormParser] # <-- CRÍTICO: Permite recibir form-data (archivos)

    def get_queryset(self):
        return Adjunto.objects.all()