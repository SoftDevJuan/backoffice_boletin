from rest_framework import serializers
from .models import *

class UsuarioSerializer(serializers.ModelSerializer):
    password = serializers.CharField(write_only=True, required=False, style={'input_type': 'password'})

    class Meta:
        model = Usuario
        fields = ['id', 'username', 'email', 'nombre', 'telefono', 'esta_activo', 'is_staff', 'created_at', 'password','foto',]
        read_only_fields = ['created_at']

    def create(self, validated_data):
        # 1. Extraemos la contraseña
        password = validated_data.pop('password', 'temporal123')
        
        # 2. Extraemos teléfono y nombre para evitar enviarlos duplicados
        telefono = validated_data.pop('telefono')
        nombre = validated_data.pop('nombre')
        
        # 3. Ahora **validated_data ya solo tiene los campos extra (esta_activo, etc.)
        user = Usuario.objects.create_user(
            telefono=telefono,
            nombre=nombre,
            password=password,
            **validated_data
        )
        return user

    def update(self, instance, validated_data):
        password = validated_data.pop('password', None)
        for attr, value in validated_data.items():
            setattr(instance, attr, value)
        if password:
            instance.set_password(password)
        instance.save()
        return instance


class JuzgadoSerializer(serializers.ModelSerializer):
    materia_display = serializers.CharField(source='get_materia_display', read_only=True)

    class Meta:
        model = Juzgado
        fields = '__all__'

class ExpedienteSerializer(serializers.ModelSerializer):
    juzgado_nombre = serializers.CharField(source='juzgado.nombre', read_only=True)
    juzgado_materia = serializers.CharField(source='juzgado.materia', read_only=True)
    estoy_suscrito = serializers.SerializerMethodField()

    class Meta:
        model = Expediente
        fields = [
            'id', 'numero_expediente', 'juzgado', 'juzgado_nombre', 
            'juzgado_materia', 'partes', 'tipo_juicio', 'creador', 
            'created_at', 'estoy_suscrito'
        ]
        # SOLUCIÓN CRÍTICA: Bloqueamos 'creador' para que DRF no lo ponga en null
        read_only_fields = ['creador', 'created_at'] 

    def get_estoy_suscrito(self, obj):
        user = self.context['request'].user
        if user.is_anonymous:
            return False
        return Suscripcion.objects.filter(usuario=user, expediente=obj, estatus='activa').exists()

class AdjuntoSerializer(serializers.ModelSerializer):
    class Meta:
        model = Adjunto
        fields = '__all__'

class AcuerdoSerializer(serializers.ModelSerializer):
    adjuntos = AdjuntoSerializer(many=True, read_only=True) # Trae los archivos automáticamente

    class Meta:
        model = Acuerdo
        fields = '__all__'

# Usamos estos Ligeros exclusivamente para no saturar el JSON de Notificaciones
class ExpedienteBasicoSerializer(serializers.ModelSerializer):
    class Meta:
        model = Expediente
        fields = ['id', 'numero_expediente']

class AcuerdoBasicoSerializer(serializers.ModelSerializer):
    expediente = ExpedienteBasicoSerializer(read_only=True)
    
    class Meta:
        model = Acuerdo
        # CORRECCIÓN CRÍTICA: 'texto' en lugar de 'sintesis'
        fields = ['id', 'texto', 'fecha_acuerdo', 'expediente']

class NotificacionSerializer(serializers.ModelSerializer):
    # Anidamos el acuerdo para que React pueda leer notif.acuerdo.expediente.numero_expediente
    acuerdo = AcuerdoBasicoSerializer(read_only=True)
    usuario_nombre = serializers.CharField(source='usuario.nombre', read_only=True)
    usuario_telefono = serializers.CharField(source='usuario.telefono', read_only=True)
    
    class Meta:
        model = Notificacion
        fields = [
            'id', 
            'usuario', 
            'acuerdo', 
            'estatus', 
            'fecha_intento',
            'usuario_nombre',   # <- Nuevo
            'usuario_telefono',
            # 'leida',   # Actívalo si ya agregaste el campo a tu modelo
        ]

class SuscripcionSerializer(serializers.ModelSerializer):
    # Campos extraídos para facilitar la vista en el Frontend
    expediente_numero = serializers.CharField(source='expediente.numero_expediente', read_only=True)
    usuario_nombre = serializers.CharField(source='usuario.nombre', read_only=True)

    class Meta:
        model = Suscripcion
        fields = ['id', 'usuario', 'usuario_nombre', 'expediente', 'expediente_numero', 'estatus', 'suscrito_el']
        # Protegemos estos campos para que el usuario no pueda "auto-aprobarse" mandando un estatus falso
        read_only_fields = ['usuario', 'estatus', 'suscrito_el']