from django.db import migrations

def cargar_juzgados_iniciales(apps, schema_editor):
    Juzgado = apps.get_model('boletin', 'Juzgado')
    
    juzgados_data = [
        {'id_boletin': 'C01', 'nombre': 'JUZGADO PRIMERO DE LO CIVIL', 'materia': 'civil'},
        {'id_boletin': 'C02', 'nombre': 'JUZGADO SEGUNDO DE LO CIVIL', 'materia': 'civil'},
        {'id_boletin': 'C03', 'nombre': 'JUZGADO TERCERO DE LO CIVIL', 'materia': 'civil'},
        {'id_boletin': 'C04', 'nombre': 'JUZGADO CUARTO DE LO CIVIL', 'materia': 'civil'},
        {'id_boletin': 'C05', 'nombre': 'JUZGADO QUINTO DE LO CIVIL', 'materia': 'civil'},
        {'id_boletin': 'C06', 'nombre': 'JUZGADO SEXTO DE LO CIVIL', 'materia': 'civil'},
        {'id_boletin': 'C07', 'nombre': 'JUZGADO SEPTIMO DE LO CIVIL', 'materia': 'civil'},
        {'id_boletin': 'C08', 'nombre': 'JUZGADO OCTAVO DE LO CIVIL', 'materia': 'civil'},
        {'id_boletin': 'C09', 'nombre': 'JUZGADO NOVENO DE LO CIVIL', 'materia': 'civil'},
        {'id_boletin': 'C10', 'nombre': 'JUZGADO DECIMO DE LO CIVIL', 'materia': 'civil'},
        {'id_boletin': 'C11', 'nombre': 'JUZGADO DECIMO PRIMERO DE LO CIVIL', 'materia': 'civil'},
        {'id_boletin': 'C12', 'nombre': 'JUZGADO DECIMO SEGUNDO DE LO CIVIL', 'materia': 'civil'},
        {'id_boletin': 'C13', 'nombre': 'JUZGADO DECIMO TERCERO DE LO CIVIL', 'materia': 'civil'},
        
        {'id_boletin': 'F01', 'nombre': 'JUZGADO PRIMERO DE LO FAMILIAR', 'materia': 'familiar'},
        {'id_boletin': 'F02', 'nombre': 'JUZGADO SEGUNDO DE LO FAMILIAR', 'materia': 'familiar'},
        {'id_boletin': 'F03', 'nombre': 'JUZGADO TERCERO DE LO FAMILIAR', 'materia': 'familiar'},
        {'id_boletin': 'F04', 'nombre': 'JUZGADO CUARTO DE LO FAMILIAR', 'materia': 'familiar'},
        {'id_boletin': 'F05', 'nombre': 'JUZGADO QUINTO DE LO FAMILIAR', 'materia': 'familiar'},
        {'id_boletin': 'F06', 'nombre': 'JUZGADO SEXTO DE LO FAMILIAR', 'materia': 'familiar'},
        {'id_boletin': 'F07', 'nombre': 'JUZGADO SEPTIMO DE LO FAMILIAR', 'materia': 'familiar'},
        {'id_boletin': 'F08', 'nombre': 'JUZGADO OCTAVO DE LO FAMILIAR', 'materia': 'familiar'},
        {'id_boletin': 'F09', 'nombre': 'JUZGADO NOVENO DE LO FAMILIAR', 'materia': 'familiar'},
        {'id_boletin': 'F10', 'nombre': 'JUZGADO DECIMO DE LO FAMILIAR', 'materia': 'familiar'},
        {'id_boletin': 'F12', 'nombre': 'JUZGADO DECIMO SEGUNDO DE LO FAMILIAR', 'materia': 'familiar'},
        {'id_boletin': 'F13', 'nombre': 'JUZGADO DECIMO TERCERO DE LO FAMILIAR', 'materia': 'familiar'},
        {'id_boletin': 'F14', 'nombre': 'JUZGADO DECIMO CUARTO DE LO FAMILIAR', 'materia': 'familiar'},
        {'id_boletin': 'F15', 'nombre': 'JUZGADO DECIMO QUINTO DE LO FAMILIAR', 'materia': 'familiar'},
        {'id_boletin': 'F16', 'nombre': 'JUZGADO DECIMO SEXTO DE LO FAMILIAR', 'materia': 'familiar'},
        {'id_boletin': 'F17', 'nombre': 'JUZGADO DECIMO SEPTIMO DE LO FAMILIAR', 'materia': 'familiar'},
        {'id_boletin': 'FNI', 'nombre': 'JUZGADO FAMILIAR ESPECIALIZADO EN NIÑAS, NIÑOS Y ADOLESCENTES', 'materia': 'familiar'},
        
        {'id_boletin': 'M01', 'nombre': 'JUZGADO PRIMERO DE LO MERCANTIL', 'materia': 'mercantil'},
        {'id_boletin': 'M02', 'nombre': 'JUZGADO SEGUNDO DE LO MERCANTIL', 'materia': 'mercantil'},
        {'id_boletin': 'M03', 'nombre': 'JUZGADO TERCERO DE LO MERCANTIL', 'materia': 'mercantil'},
        {'id_boletin': 'M04', 'nombre': 'JUZGADO CUARTO DE LO MERCANTIL', 'materia': 'mercantil'},
        {'id_boletin': 'M05', 'nombre': 'JUZGADO QUINTO DE LO MERCANTIL', 'materia': 'mercantil'},
        {'id_boletin': 'M06', 'nombre': 'JUZGADO SEXTO DE LO MERCANTIL', 'materia': 'mercantil'},
        {'id_boletin': 'M07', 'nombre': 'JUZGADO SEPTIMO DE LO MERCANTIL', 'materia': 'mercantil'},
        {'id_boletin': 'M08', 'nombre': 'JUZGADO OCTAVO DE LO MERCATIL', 'materia': 'mercantil'},
        {'id_boletin': 'M09', 'nombre': 'JUZGADO NOVENO DE LO MERCANTIL', 'materia': 'mercantil'},
        {'id_boletin': 'M10', 'nombre': 'JUZGADO DECIMO DE LO MERCANTIL', 'materia': 'mercantil'},
        {'id_boletin': 'OM01', 'nombre': 'JUZGADO DECIMO  PRIMERO MERCANTIL', 'materia': 'mercantil'},
        {'id_boletin': 'OM02', 'nombre': 'JUZGADO DECIMO  SEGUNDO MERCANTIL', 'materia': 'mercantil'},
        {'id_boletin': 'OM03', 'nombre': 'JUZGADO DECIMO  TERCERO MERCANTIL', 'materia': 'mercantil'},
        {'id_boletin': 'OM04', 'nombre': 'JUZGADO DECIMO  CUARTO MERCANTIL', 'materia': 'mercantil'},
        {'id_boletin': 'OM05', 'nombre': 'JUZGADO DECIMO QUINTO MERCANTIL', 'materia': 'mercantil'},
        {'id_boletin': 'OM06', 'nombre': 'JUZGADO DECIMO  SEXTO MERCANTIL', 'materia': 'mercantil'},
        {'id_boletin': 'OM07', 'nombre': 'JUZGADO DECIMO SEPTIMO MERCANTIL', 'materia': 'mercantil'},
        {'id_boletin': 'OM08', 'nombre': 'JUZGADO DECIMO  OCTAVO MERCANTIL', 'materia': 'mercantil'},
        {'id_boletin': 'OM09', 'nombre': 'JUZGADO DECIMO NOVENO MERCANTIL', 'materia': 'mercantil'},
        
        {'id_boletin': 'TQ4', 'nombre': 'JUZGADO FAMILIAR ESPECIALIZADO EN VIOLENCIA CONTRA LAS MUJERES  EN TLAQUEPAQUE', 'materia': 'familiar'},
        {'id_boletin': 'XF1', 'nombre': 'JUZGADO DECIMO PRIMERO ESPECIALIZADO DE LO FAMILIAR', 'materia': 'familiar'},
    ]
    
    for data in juzgados_data:
        Juzgado.objects.get_or_create(
            id_boletin=data["id_boletin"],
            defaults={
                "nombre": data["nombre"],
                "materia": data["materia"],
                "partido_judicial": "Primer Partido Judicial"
            }
        )

def revertir_juzgados_iniciales(apps, schema_editor):
    Juzgado = apps.get_model('boletin', 'Juzgado')
    Juzgado.objects.all().delete()

class Migration(migrations.Migration):

    dependencies = [
        ('boletin', '0001_initial'), 
    ]

    operations = [
        migrations.RunPython(cargar_juzgados_iniciales, revertir_juzgados_iniciales),
    ]