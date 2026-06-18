import os
from django.core.management.base import BaseCommand
from django.db import IntegrityError
from boletin.models import Juzgado, Expediente, Acuerdo
from playwright.sync_api import sync_playwright
from datetime import datetime
import re

class Command(BaseCommand):
    help = 'Extrae el boletín del CJJ de forma masiva para todos los juzgados activos.'

    def handle(self, *args, **kwargs):
        # Desactivamos el bloqueo asíncrono de Django para que el ORM 
        # pueda convivir con el bucle oculto de Playwright en este script
        os.environ["DJANGO_ALLOW_ASYNC_UNSAFE"] = "true"

        fecha_hoy = datetime.now().date()
        self.stdout.write(self.style.SUCCESS(f"Iniciando extracción masiva para la fecha: {fecha_hoy}"))

        # Obtenemos los juzgados que registramos en el seeder
        juzgados = Juzgado.objects.filter(esta_activo=True).order_by('id')
        total_juzgados = juzgados.count()

        if total_juzgados == 0:
            self.stdout.write(self.style.ERROR("No hay juzgados activos en la base de datos."))
            return

        stats = {'nuevos': 0, 'duplicados_omitidos': 0, 'errores': 0}

        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            context = browser.new_context()
            page = context.new_page()

            self.stdout.write("Accediendo a https://cjj.gob.mx/bulletin ...")
            page.goto("https://cjj.gob.mx/bulletin", timeout=60000)

            # Esperamos a que el formulario principal cargue
            page.wait_for_function("document.querySelectorAll('#judge-1 option').length > 1", timeout=15000)

            for index, juzgado in enumerate(juzgados, 1):
                self.stdout.write(f"\n[{index}/{total_juzgados}] Buscando en: {juzgado.nombre} (ID: {juzgado.id_boletin})")
                
                try:
                    page.select_option('#judge-1', str(juzgado.id_boletin))
                    page.click('button.search-button, button:has-text("Buscar")')

                    try:
                        page.wait_for_selector('.search-list', timeout=5000)
                        items = page.query_selector_all('.search-item')
                    except Exception:
                        self.stdout.write(self.style.WARNING("  -> Sin resultados hoy o tardó demasiado."))
                        continue

                    self.stdout.write(f"  -> Se encontraron {len(items)} acuerdos. Procesando...")

                    for item in items:
                        try:
                            # 1. PREVENCIÓN ERROR NONETYPE (Estructura HTML incompleta)
                            title_el = item.query_selector('.item-title')
                            text_el = item.query_selector('.item-text')
                            
                            if not title_el or not text_el:
                                stats['errores'] += 1
                                self.stdout.write(self.style.WARNING("  [!] Registro ignorado: Estructura HTML atípica o vacía."))
                                continue

                            raw_title = title_el.inner_text().strip()
                            raw_text = text_el.inner_text().strip()
                            acuerdo_limpio = re.sub(r'\s+', ' ', raw_text)

                            # 2. PREVENCIÓN ERROR VARCHAR(50) (Búsqueda inteligente)
                            # Buscamos el patrón clásico "numero/año" en cualquier parte del título
                            exp_match = re.search(r'(\d+[/|-]\d+)', raw_title)
                            
                            if exp_match:
                                num_expediente = exp_match.group(1)
                                # Lo que sobra lo usamos para deducir el tipo de juicio y partes
                                resto = raw_title.replace(num_expediente, '').strip(' -')
                                fragmentos = [f.strip() for f in resto.split('-') if f.strip()]
                                tipo_juicio = fragmentos[0][:150] if len(fragmentos) > 0 else "Sin especificar"
                                partes = fragmentos[1][:255] if len(fragmentos) > 1 else None
                            else:
                                # Si no hay patrón (ej. "EXHORTO"), truncamos agresivamente para salvar la BD
                                num_expediente = raw_title[:50].strip()
                                tipo_juicio = "Atípico / Especial"
                                partes = None

                            # 3. Guardado seguro en la Base de Datos
                            expediente_obj, exp_created = Expediente.objects.get_or_create(
                                juzgado=juzgado,
                                numero_expediente=num_expediente,
                                defaults={
                                    'tipo_juicio': tipo_juicio,
                                    'partes': partes
                                }
                            )

                            try:
                                Acuerdo.objects.create(
                                    expediente=expediente_obj,
                                    fecha_publicacion=fecha_hoy,
                                    texto=acuerdo_limpio
                                )
                                stats['nuevos'] += 1
                            except IntegrityError:
                                stats['duplicados_omitidos'] += 1
                                
                        except Exception as e:
                            stats['errores'] += 1
                            self.stdout.write(self.style.ERROR(f"  [!] Error al parsear item: {e}"))

                except Exception as e:
                    self.stdout.write(self.style.ERROR(f"  [!] Error general con el juzgado {juzgado.nombre}: {e}"))
                    page.goto("https://cjj.gob.mx/bulletin")
                    page.wait_for_function("document.querySelectorAll('#judge-1 option').length > 1")

            browser.close()

        self.stdout.write(self.style.SUCCESS("\n======================================="))
        self.stdout.write(self.style.SUCCESS("RESUMEN DE EXTRACCIÓN MASIVA"))
        self.stdout.write(f"Nuevos acuerdos guardados: {stats['nuevos']}")
        self.stdout.write(f"Duplicados omitidos:       {stats['duplicados_omitidos']}")
        self.stdout.write(f"Errores de lectura:        {stats['errores']}")
        self.stdout.write(self.style.SUCCESS("======================================="))