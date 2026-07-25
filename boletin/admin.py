from django.contrib import admin
from django.contrib.auth.admin import UserAdmin
from django.apps import apps
from django.db.models import CharField, TextField
from .models import Usuario

# Obtenemos todos los modelos de la app 'boletin'
app_models = apps.get_app_config('boletin').get_models()

for model in app_models:
    # EXCLUSIÓN CRÍTICA: Evitamos que el bucle tome al modelo Usuario
    if model == Usuario:
        continue

    # Usamos _meta.fields en lugar de get_fields() para ignorar relaciones inversas y M2M
    display_fields = [
        field.name for field in model._meta.fields
        if field.get_internal_type() != 'TextField'
    ]
    
    # Filtramos campos para search_fields: Solo buscamos en campos de texto corto y largo
    searchable_fields = [
        field.name for field in model._meta.fields
        if isinstance(field, (CharField, TextField))
    ]

    # Creamos una clase ModelAdmin dinámica
    class GenericAdmin(admin.ModelAdmin):
        list_display = display_fields
        search_fields = searchable_fields

    # Registramos el modelo
    try:
        admin.site.register(model, GenericAdmin)
    except admin.sites.AlreadyRegistered:
        pass

@admin.register(Usuario)
class CustomUserAdmin(UserAdmin):
    # Campos que se muestran en la lista del panel
    list_display = ('id', 'nombre', 'telefono', 'is_staff', 'esta_activo')
    ordering = ('id',)

    # Secciones para EDITAR un usuario existente (eliminando username y date_joined)
    fieldsets = (
        (None, {'fields': ('telefono', 'password')}),
        ('Información Personal', {'fields': ('nombre',)}),
        ('Permisos y Estados', {'fields': ('is_active', 'is_staff', 'is_superuser', 'groups', 'user_permissions')}),
    )

    # Secciones requeridas para CREAR un usuario desde el panel de admin
    add_fieldsets = (
        (None, {
            'classes': ('wide',),
            'fields': ('telefono', 'passworddata', 'nombre', 'is_staff', 'is_active') # Ajusta según los campos obligatorios al crear
        }),
    )

    search_fields = ('nombre', 'telefono')
    filter_horizontal = ('groups', 'user_permissions')