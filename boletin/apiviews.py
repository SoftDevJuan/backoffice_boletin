from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.authtoken.models import Token
from django.contrib.auth import authenticate
from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from .models import Expediente, Usuario, Juzgado, Notificacion, Acuerdo
from rest_framework import viewsets
from .serializers import *
from .utils import *
from django.db.models import Q
from rest_framework.parsers import MultiPartParser, FormParser
from rest_framework.decorators import action
from rest_framework.permissions import AllowAny
from rest_framework.parsers import MultiPartParser, FormParser, JSONParser

class LoginAPIView(APIView):
    permission_classes = [AllowAny]
    
    def post(self, request):
        # Ahora recibimos 'credencial', que puede ser cualquiera de las 3 cosas
        credencial = request.data.get('credencial') 
        password = request.data.get('password')
        
        if not credencial or not password:
            return Response({'detail': 'Faltan credenciales.'}, status=status.HTTP_400_BAD_REQUEST)

        try:
            # Magia de Django: Busca coincidencia exacta en cualquiera de las 3 columnas
            user = Usuario.objects.get(
                Q(telefono=credencial) | Q(email=credencial) | Q(username=credencial)
            )
        except Usuario.DoesNotExist:
            return Response(
                {'detail': 'El usuario, correo o teléfono no existe.'}, 
                status=status.HTTP_401_UNAUTHORIZED
            )
        
        # Si el usuario existe, validamos directamente la contraseña y que esté activo
        if user.check_password(password) and getattr(user, 'esta_activo', True):
            token, created = Token.objects.get_or_create(user=user)
            return Response({
                'token': token.key,
                'user': {
                    'id': user.id,
                    'nombre': user.nombre,
                    'telefono': user.telefono,
                    'email': user.email,
                    'username': user.username,
                    'role': 'admin' if user.is_staff else 'user',
                    # NUEVO: Pasamos la foto. Request construye la URL completa
                    'foto': request.build_absolute_uri(user.foto.url) if user.foto else None
                }
            })
        else:
            return Response(
                {'detail': 'Contraseña incorrecta o cuenta inactiva.'}, 
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
    parser_classes = [MultiPartParser, FormParser, JSONParser]
    
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

    # --- DIAGNÓSTICO DE ENTRADA ---
    def dispatch(self, request, *args, **kwargs):
        print(f"\n[DEBUG DISPATCH] -----------------------------------------")
        print(f"[DEBUG DISPATCH] Método recibido: {request.method}")
        print(f"[DEBUG DISPATCH] Ruta solicitada: {request.path}")
        print(f"[DEBUG DISPATCH] Usuario autenticado: {request.user} (is_staff: {getattr(request.user, 'is_staff', 'N/A')})")
        print(f"[DEBUG DISPATCH] -----------------------------------------")
        return super().dispatch(request, *args, **kwargs)

    def get_serializer_context(self):
        context = super().get_serializer_context()
        context['request'] = self.request
        return context

    def get_queryset(self):
        user = self.request.user
        if user.is_staff or user.is_superuser:
            queryset = Expediente.objects.all().select_related('juzgado').order_by('-created_at')
        else:
            queryset = Expediente.objects.filter(usuarios=user).select_related('juzgado').order_by('-created_at')

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

    @action(detail=False, methods=['post'], url_path='gestionar-suscripcion')
    def gestionar_suscripcion(self, request):
        print("[DEBUG] ¡Entró a gestionar_suscripcion!")
        
        if not request.user.is_staff:
            return Response({"error": "No autorizado."}, status=status.HTTP_403_FORBIDDEN)
        
        expediente_id = request.data.get('expediente_id')
        usuario_id = request.data.get('usuario_id')
        accion = request.data.get('accion')

        try:
            expediente = Expediente.objects.get(id=expediente_id)
            usuario = Usuario.objects.get(id=usuario_id)
            
            if accion == 'agregar':
                expediente.usuarios.add(usuario)
            elif accion == 'remover':
                expediente.usuarios.remove(usuario)
                
            return Response({"message": "Suscripción actualizada correctamente."}, status=status.HTTP_200_OK)
        except Exception as e:
            return Response({"error": str(e)}, status=status.HTTP_400_BAD_REQUEST)

    
    @action(detail=False, methods=['post'])
    def suscribir(self, request):
        print("[DEBUG] ¡Entró a suscribir!")
        numero_expediente = request.data.get('numero_expediente')
        usuario = request.user

        if not numero_expediente:
            return Response({"error": "Debes proporcionar el número de expediente."}, status=status.HTTP_400_BAD_REQUEST)

        try:
            expediente = Expediente.objects.filter(numero_expediente__iexact=numero_expediente.strip()).first()
            if not expediente:
                return Response({"error": "El expediente no se encuentra registrado."}, status=status.HTTP_404_NOT_FOUND)

            # 1. Vinculamos al usuario con el expediente
            expediente.usuarios.add(usuario)
            
            # 2. LA SOLUCIÓN A TU OBSERVACIÓN:
            # Disparamos el motor inteligente en este instante. 
            # Como este usuario es nuevo, la función detectará que le faltan TODOS los acuerdos 
            # históricos y se los enviará en un solo bloque de bienvenida.
            try:
                procesar_notificaciones_lote(expediente)
            except Exception as e:
                print(f"Error al enviar historial a nuevo suscriptor: {e}")

            return Response({"message": "Suscripción solicitada con éxito. Recibirás el historial en breve."}, status=status.HTTP_200_OK)
        except Exception as e:
            return Response({"error": str(e)}, status=status.HTTP_400_BAD_REQUEST)


        
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

    def perform_create(self, serializer):
        # 1. Se guarda el nuevo acuerdo en la base de datos
        acuerdo = serializer.save()
        
        # 2. Le pasamos el expediente asociado a nuestra función inteligente.
        # La función cruzará los datos y enviará por WhatsApp solo lo que le falte a cada usuario.
        try:
            procesar_notificaciones_lote(acuerdo.expediente)
        except Exception as e:
            print(f"❌ Error al disparar notificaciones automáticas: {e}")

class AdjuntoViewSet(viewsets.ModelViewSet):
    serializer_class = AdjuntoSerializer
    permission_classes = [IsAuthenticated]
    parser_classes = [MultiPartParser, FormParser] # <-- CRÍTICO: Permite recibir form-data (archivos)

    def get_queryset(self):
        return Adjunto.objects.all()

    

class NotificacionViewSet(viewsets.ReadOnlyModelViewSet):
    """
    Usamos ReadOnlyModelViewSet porque los usuarios no deberían crear ni editar 
    notificaciones manualmente desde la app, solo leerlas.
    """
    serializer_class = NotificacionSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        user = self.request.user
        
        # El admin puede ver el historial de todas las notificaciones enviadas
        if user.is_staff or user.is_superuser:
            return Notificacion.objects.all().select_related(
                'acuerdo__expediente', 'usuario'
            ).order_by('-id') # Ordenamos por las más recientes
            
        # El cliente solo ve las suyas
        return Notificacion.objects.filter(usuario=user).select_related(
            'acuerdo__expediente'
        ).order_by('-id')

    @action(detail=False, methods=['post'], url_path='reintentar-por-expediente')
    def reintentar_por_expediente(self, request):
        # Solo los administradores deberían poder reintentar envíos masivos fallidos
        if not request.user.is_staff:
            return Response({"error": "No autorizado."}, status=status.HTTP_403_FORBIDDEN)
        
        expediente_id = request.data.get('expediente_id')
        if not expediente_id:
            return Response({"error": "Falta el ID del expediente."}, status=status.HTTP_400_BAD_REQUEST)

        # Buscamos exclusivamente las notificaciones que fallaron de ese expediente
        notificaciones_fallidas = Notificacion.objects.filter(
            acuerdo__expediente_id=expediente_id,
            estatus='fallido'
        ).select_related('usuario', 'acuerdo__expediente')

        if not notificaciones_fallidas.exists():
            return Response({"message": "No hay notificaciones fallidas pendientes para este expediente."}, status=status.HTTP_200_OK)

        exitosos = 0
        fallidos = 0

        for notif in notificaciones_fallidas:
            usuario = notif.usuario
            expediente = notif.acuerdo.expediente
            acuerdo = notif.acuerdo
            
            try:
                # Reutilizamos tu función de envío de WhatsApp existente
                exito = enviar_whatsapp_lote(usuario, expediente, [acuerdo])
                if notif.estatus == 'enviado':
                    exitosos += 1
                else:
                    fallidos += 1
            except Exception:
                notif.estatus = 'fallido'
                notif.save()
                fallidos += 1

        return Response({
            "message": f"Proceso de reintento finalizado. Exitosos: {exitosos}, Siguen fallando: {fallidos}"
        }, status=status.HTTP_200_OK)

    @action(detail=True, methods=['post'], url_path='reintentar')
    def reintentar_individual(self, request, pk=None):
        if not request.user.is_staff:
            return Response({"error": "No autorizado."}, status=status.HTTP_403_FORBIDDEN)
        
        notif = self.get_object()
        if notif.estatus != 'fallido':
            return Response({"message": "La notificación no está en estatus fallido."}, status=status.HTTP_400_BAD_REQUEST)
        
        # Reenviamos usando la función de lote (aunque sea 1 solo acuerdo) para mantener el formato limpio
        exito = enviar_whatsapp_lote(notif.usuario, notif.acuerdo.expediente, [notif.acuerdo])
        notif.estatus = 'enviado' if exito else 'fallido'
        notif.save()
        
        return Response({
            "message": "Reintento individual exitoso." if exito else "Volvió a fallar el envío."
        }, status=status.HTTP_200_OK if exito else status.HTTP_400_BAD_REQUEST)

    @action(detail=False, methods=['post'], url_path='reintentar-por-usuario')
    def reintentar_por_usuario(self, request):
        if not request.user.is_staff:
            return Response({"error": "No autorizado."}, status=status.HTTP_403_FORBIDDEN)
            
        usuario_id = request.data.get('usuario_id')
        expediente_id = request.data.get('expediente_id')
        
        # Filtramos las fallidas de ESTE usuario en ESTE expediente
        fallidas = Notificacion.objects.filter(
            usuario_id=usuario_id, 
            acuerdo__expediente_id=expediente_id, 
            estatus='fallido'
        ).select_related('usuario', 'acuerdo__expediente')
        
        if not fallidas.exists():
            return Response({"message": "No hay fallidas para este usuario en este expediente."}, status=status.HTTP_200_OK)
            
        acuerdos = [n.acuerdo for n in fallidas]
        usuario = fallidas.first().usuario
        expediente = fallidas.first().acuerdo.expediente
        
        # Enviamos todas juntas en un solo bloque
        exito = enviar_whatsapp_lote(usuario, expediente, acuerdos)
        nuevo_estatus = 'enviado' if exito else 'fallido'
        fallidas.update(estatus=nuevo_estatus)
        
        return Response({
            "message": f"Reintento finalizado. Estatus: {nuevo_estatus}"
        }, status=status.HTTP_200_OK)


