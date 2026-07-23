from django.db import models
from django.contrib.auth.models import AbstractBaseUser, BaseUserManager, PermissionsMixin



class UsuarioManager(BaseUserManager):
    def create_user(self, telefono, nombre, password=None, **extra_fields):
        if not telefono:
            raise ValueError('El número de teléfono es obligatorio')
        user = self.model(telefono=telefono, nombre=nombre, **extra_fields)
        user.set_password(password) # Esto encripta la contraseña de forma segura
        user.save(using=self._db)
        return user

    def create_superuser(self, telefono, nombre, password=None, **extra_fields):
        extra_fields.setdefault('is_staff', True)
        extra_fields.setdefault('is_superuser', True)
        return self.create_user(telefono, nombre, password, **extra_fields)

# CORRECCIÓN AQUÍ: Cambiamos models.Model por AbstractBaseUser y PermissionsMixin
class Usuario(AbstractBaseUser, PermissionsMixin):
    nombre = models.CharField(max_length=150, verbose_name="Nombre Completo")
    telefono = models.CharField(
        max_length=20, 
        unique=True, 
        verbose_name="Teléfono (WhatsApp)",
        help_text="Incluir código de país sin signo + (Ej: 52133XXXXXXXX)"
    )
    esta_activo = models.BooleanField(default=True, verbose_name="Usuario Activo")
    notificaciones_activas = models.BooleanField(default=True, verbose_name="Notificaciones Habilitadas")
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="Fecha de Registro")

    # 2. Requeridos por Django para funcionar como usuario del sistema
    is_staff = models.BooleanField(default=False, verbose_name="Es Staff (Admin)")
    is_active = models.BooleanField(default=True, verbose_name="Activo en Sistema")
    
    # 3. Asignamos el Manager y configuramos el inicio de sesión
    objects = UsuarioManager()

    USERNAME_FIELD = 'telefono'  # Con esto indicamos que se inicia sesión con el teléfono
    REQUIRED_FIELDS = ['nombre']

    class Meta:
        verbose_name = "Usuario"
        verbose_name_plural = "Usuarios"

    def __str__(self):
        return f"{self.nombre} ({self.telefono})"



class Juzgado(models.Model):
    MATERIA_CHOICES = [
        ('familiar', 'Familiar'),
        ('civil', 'Civil'),
        ('mercantil', 'Mercantil'),
        ('laboral', 'Laboral'),
        ('penal', 'Penal'),
        ('control', 'Control y Oralidad'),
        ('mixto', 'Mixto'),
    ]
    
    # Este ID debe coincidir exactamente con el valor numérico del atributo 'value' en el HTML del Boletín
    id_boletin = models.CharField(max_length=20, unique=True, verbose_name="ID en el Boletín")
    nombre = models.CharField(max_length=200, verbose_name="Nombre del Juzgado")
    materia = models.CharField(max_length=50, choices=MATERIA_CHOICES, verbose_name="Materia / Contexto")
    partido_judicial = models.CharField(
        max_length=100, 
        default="Primer Partido Judicial", 
        verbose_name="Partido Judicial",
        help_text="Jurisdicción territorial del juzgado (Ej: Primer Partido Judicial para la Zona Metropolitana)"
    )
    esta_activo = models.BooleanField(default=True, verbose_name="Vigente en el Boletín")

    class Meta:
        verbose_name = "Juzgado"
        verbose_name_plural = "Juzgados"
        ordering = ['materia', 'id_boletin']

    def __str__(self):
        return f"{self.nombre} ({self.get_materia_display()})"


class Expediente(models.Model):
    juzgado = models.ForeignKey('Juzgado', on_delete=models.PROTECT, related_name='expedientes')
    numero_expediente = models.CharField(max_length=50, verbose_name="Número de Expediente")
    tipo_juicio = models.CharField(max_length=150, blank=True, null=True, verbose_name="Tipo de Juicio")
    
    # NUEVO: Al hacer scraping general, a veces sale quién demanda a quién. 
    # Guardar esto te servirá para que el LLM busque por nombres si el usuario no se sabe su expediente.
    partes = models.CharField(max_length=255, blank=True, null=True, verbose_name="Partes (Actor vs Demandado)") 
    ultima_revision_scraper = models.DateField(null=True, blank=True, verbose_name="Última Consulta al Boletín")

    usuarios = models.ManyToManyField('Usuario', through='Suscripcion', related_name='expedientes_suscritos')
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Expediente"
        verbose_name_plural = "Expedientes"
        unique_together = ('juzgado', 'numero_expediente')
        
        # CRÍTICO: Indexar esta columna hará que la búsqueda de tu agente sea instantánea
        indexes = [
            models.Index(fields=['numero_expediente']),
        ]

    def __str__(self):
        return f"{self.juzgado.nombre} | Exp: {self.numero_expediente}"

class Acuerdo(models.Model):
    expediente = models.ForeignKey('Expediente', on_delete=models.CASCADE, related_name='acuerdos')
    
    # Renombramos para mayor precisión
    fecha_acuerdo = models.DateField(db_index=True, verbose_name="Fecha de Acuerdo")
    
    # Nuevo campo: Permite nulos porque no todos los acuerdos tienen fecha de promoción
    fecha_promocion = models.DateField(null=True, blank=True, verbose_name="Fecha de Promoción")
    
    texto = models.TextField(verbose_name="Texto del Acuerdo")
    
    procesado_para_notificacion = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Acuerdo"
        verbose_name_plural = "Acuerdos"
        
        # CRÍTICO: Actualizado con el nuevo nombre del campo
        unique_together = ('expediente', 'fecha_acuerdo', 'texto')
        ordering = ['-fecha_acuerdo', '-created_at']

    def __str__(self):
        return f"Acuerdo del {self.fecha_acuerdo} - Exp: {self.expediente.numero_expediente}"


class Suscripcion(models.Model):
    usuario = models.ForeignKey(Usuario, on_delete=models.CASCADE)
    expediente = models.ForeignKey(Expediente, on_delete=models.CASCADE)
    suscrito_el = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Suscripción"
        verbose_name_plural = "Suscripciones"
        unique_together = ('usuario', 'expediente')

    def __str__(self):
        return f"{self.usuario.nombre} -> {self.expediente.numero_expediente}"


class Notificacion(models.Model):
    ESTATUS_CHOICES = [
        ('pendiente', 'Pendiente'),
        ('enviado', 'Enviado'),
        ('fallido', 'Fallido'),
        ('leido', 'Leído'),
    ]
    usuario = models.ForeignKey(Usuario, on_delete=models.SET_NULL, null=True, related_name='notificaciones')
    acuerdo = models.ForeignKey('Acuerdo', on_delete=models.SET_NULL, null=True, related_name='notificaciones')
    estatus = models.CharField(max_length=20, choices=ESTATUS_CHOICES, default='pendiente')
    mensaje_enviado = models.TextField(blank=True, null=True, verbose_name="Contenido del Mensaje")
    fecha_intento = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Bitácora de Notificación"
        verbose_name_plural = "Bitácoras de Notificaciones"

    def __str__(self):
        return f"Notificación {self.estatus} para {self.usuario.nombre if self.usuario else 'Borrado'}"



class Adjunto(models.Model):
    expediente = models.ForeignKey(Expediente, on_delete=models.CASCADE, related_name='adjuntos')
    acuerdo = models.ForeignKey('Acuerdo', on_delete=models.CASCADE, null=True, blank=True, related_name='adjuntos')
    archivo = models.FileField(upload_to='adjuntos/%Y/%m/', verbose_name="Archivo Adjunto")
    nombre_archivo = models.CharField(max_length=255, blank=True, verbose_name="Nombre Original")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Adjunto"
        verbose_name_plural = "Adjuntos"

    def __str__(self):
        return self.nombre_archivo or "Archivo Adjunto"