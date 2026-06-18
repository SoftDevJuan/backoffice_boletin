from django.contrib import admin
from django.apps import apps
from django.db.models import CharField, TextField

# Obtenemos todos los modelos de la app 'boletin'
app_models = apps.get_app_config('boletin').get_models()

for model in app_models:
    # Usamos _meta.fields en lugar de get_fields() para ignorar relaciones inversas y M2M
    display_fields = [
        field.name for field in model._meta.fields
        if field.get_internal_type() != 'TextField'
    ]
    
    # Filtramos campos para search_fields: Solo buscamos en campos de texto corto
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