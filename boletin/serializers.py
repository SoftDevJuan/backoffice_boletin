from rest_framework import serializers
from .models import *

class UsuarioSerializer(serializers.ModelSerializer):
    password = serializers.CharField(write_only=True, required=False, style={'input_type': 'password'})

    class Meta:
        model = Usuario
        fields = ['id', 'nombre', 'telefono', 'esta_activo', 'notificaciones_activas', 'is_staff', 'created_at', 'password']
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
    juzgado_materia = serializers.CharField(source='juzgado.get_materia_display', read_only=True)

    class Meta:
        model = Expediente
        fields = '__all__'
        read_only_fields = ['ultima_revision_scraper', 'created_at']


class AdjuntoSerializer(serializers.ModelSerializer):
    class Meta:
        model = Adjunto
        fields = '__all__'

class AcuerdoSerializer(serializers.ModelSerializer):
    adjuntos = AdjuntoSerializer(many=True, read_only=True) # Trae los archivos automáticamente

    class Meta:
        model = Acuerdo
        fields = '__all__'