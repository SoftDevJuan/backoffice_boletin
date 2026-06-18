from django.http import JsonResponse
from asgiref.sync import sync_to_async
from playwright.async_api import async_playwright
from .models import Juzgado, Expediente, Acuerdo
from datetime import datetime
import re

# =======================================================
# FUNCIONES DE BASE DE DATOS (HELPER)
# =======================================================
@sync_to_async
def obtener_id_juzgado(id_juzgado, nombre_juzgado):
    if id_juzgado:
        juzgado = Juzgado.objects.filter(id_boletin=id_juzgado).first()
        return juzgado.id_boletin if juzgado else None
    if nombre_juzgado:
        juzgado = Juzgado.objects.filter(nombre__icontains=nombre_juzgado).first()
        return juzgado.id_boletin if juzgado else None
    return None

@sync_to_async
def filtrar_suscritos(id_boletin, lista_expedientes_encontrados):
    """Recibe la lista masiva y devuelve SOLO los expedientes que nos importan (los que tienen usuarios)"""
    return list(Expediente.objects.filter(
        juzgado__id_boletin=id_boletin,
        numero_expediente__in=lista_expedientes_encontrados,
        usuarios__isnull=False,
        usuarios__esta_activo=True
    ).values_list('numero_expediente', flat=True).distinct())

@sync_to_async
def consultar_y_actualizar_bd(id_boletin, numero_expediente, fecha_hoy, acuerdos_extraidos, raw_title):
    juzgado = Juzgado.objects.get(id_boletin=id_boletin)
    expediente_obj = Expediente.objects.filter(juzgado=juzgado, numero_expediente=numero_expediente).first()
    ultimo_acuerdo = Acuerdo.objects.filter(expediente=expediente_obj).order_by('-fecha_acuerdo', '-created_at').first() if expediente_obj else None

    if not acuerdos_extraidos:
        if ultimo_acuerdo:
            return {
                "hubo_cambio": False,
                "estado_actual": ultimo_acuerdo.texto,
                "fecha_ultimo_acuerdo": ultimo_acuerdo.fecha_acuerdo.strftime("%d-%m-%Y"),
                "mensaje": "El boletín no arrojó resultados hoy, mostrando último registro."
            }
        else:
            return {"error": "Sin resultados en el boletín y sin registros previos."}

    exp_match = re.search(r'(\d+[/|-]\d+)', raw_title)
    if exp_match:
        resto = raw_title.replace(exp_match.group(1), '').strip(' -')
        fragmentos = [f.strip() for f in resto.split('-') if f.strip()]
        tipo_juicio = fragmentos[0][:150] if len(fragmentos) > 0 else "Sin especificar"
        partes = fragmentos[1][:255] if len(fragmentos) > 1 else None
    else:
        tipo_juicio, partes = "Atípico / Especial", None

    if not expediente_obj:
        expediente_obj = Expediente.objects.create(
            juzgado=juzgado, numero_expediente=numero_expediente, tipo_juicio=tipo_juicio, partes=partes
        )

    estado_anterior = ultimo_acuerdo.texto if ultimo_acuerdo else "No hay registro previo."
    nuevos_textos = []
    fecha_mas_reciente_extraida = None

    for texto_fila in acuerdos_extraidos:
        match = re.match(r'^(\d{2}-\d{2}-\d{4})\s*(?:(\d{2}-\d{2}-\d{4})\s+)?(.+)', texto_fila)
        
        # CORRECCIÓN 1: Si no es una fecha válida (ej. encabezados o basura), lo saltamos.
        if not match:
            continue
            
        f_acuerdo_str, f_prom_str, texto_limpio = match.group(1), match.group(2), match.group(3).strip()
        try:
            fecha_acuerdo = datetime.strptime(f_acuerdo_str, "%d-%m-%Y").date()
        except ValueError:
            continue # Si la fecha está corrupta, ignorar fila
            
        fecha_promocion = None
        if f_prom_str:
            try:
                fecha_promocion = datetime.strptime(f_prom_str, "%d-%m-%Y").date()
            except ValueError:
                pass

        # Guardamos registro de la última fecha válida leída
        fecha_mas_reciente_extraida = fecha_acuerdo
        
        acuerdo_obj, created = Acuerdo.objects.get_or_create(
            expediente=expediente_obj, fecha_acuerdo=fecha_acuerdo, texto=texto_limpio, defaults={'fecha_promocion': fecha_promocion}
        )
        if created: nuevos_textos.append(texto_limpio)

    if nuevos_textos:
        # CORRECCIÓN 2: Le mandamos al LLM solo el ÚLTIMO texto nuevo (el más reciente del expediente)
        ultimo_texto_nuevo = nuevos_textos[-1]
        fecha_retorno = fecha_mas_reciente_extraida.strftime("%d-%m-%Y") if fecha_mas_reciente_extraida else fecha_hoy.strftime("%d-%m-%Y")
        
        return {
            "hubo_cambio": True, 
            "estado_anterior": estado_anterior, 
            "estado_nuevo": ultimo_texto_nuevo, 
            "fecha_ultimo_acuerdo": fecha_retorno, 
            "mensaje": f"{len(nuevos_textos)} actualizaciones nuevas."
        }
    else:
        fecha_str = ultimo_acuerdo.fecha_acuerdo.strftime("%d-%m-%Y") if ultimo_acuerdo else fecha_hoy.strftime("%d-%m-%Y")
        return {
            "hubo_cambio": False, 
            "estado_actual": ultimo_acuerdo.texto if ultimo_acuerdo else "Sin extracto.",
            "fecha_ultimo_acuerdo": fecha_str, 
            "mensaje": "Información idéntica a la BD. Sin cambios reales."
        }

# =======================================================
# NÚCLEO SCRAPER (El Francotirador reutilizable)
# =======================================================
async def extraer_expediente_profundo(page, id_boletin, numero_expediente):
    """Automatiza el clic y la extracción de la tabla para 1 solo expediente."""
    acuerdos_extraidos, raw_title = [], ""
    try:
        await page.goto("https://cjj.gob.mx/bulletin", timeout=60000)
        await page.wait_for_function("document.querySelectorAll('#judge-1 option').length > 1", timeout=15000)
        await page.select_option('#judge-1', str(id_boletin))
        await page.click('input#proceedings') # Botón "Por Expediente"
        await page.wait_for_selector('input[name="exp"]', state='visible')
        await page.fill('input[name="exp"]', numero_expediente)
        await page.click('button.search-button')

        await page.wait_for_selector('.search-list', timeout=10000)
        elemento_colapsado = await page.query_selector('.item-title.pointer')
        
        if elemento_colapsado:
            await elemento_colapsado.click()
            await page.wait_for_selector('.item-table', timeout=5000)
            raw_title = (await elemento_colapsado.inner_text()).strip()
            filas_acuerdos = await page.query_selector_all('.item-grid')
            if len(filas_acuerdos) > 1:
                for fila in filas_acuerdos[1:]:
                    acuerdos_extraidos.append(re.sub(r'\s+', ' ', (await fila.inner_text()).strip()))
        else:
            items = await page.query_selector_all('.search-item')
            if items:
                title_el, text_el = await items[0].query_selector('.item-title'), await items[0].query_selector('.item-text')
                if title_el and text_el:
                    raw_title = (await title_el.inner_text()).strip()
                    acuerdos_extraidos.append(re.sub(r'\s+', ' ', (await text_el.inner_text()).strip()))
    except Exception as e:
        print(f"[Aviso Scraper Profundo] Exp {numero_expediente}: {e}")
        
    return acuerdos_extraidos, raw_title

# =======================================================
# ENDPOINT 1: Consulta Individual (Para el Agente WhatsApp)
# =======================================================
async def consultar_expediente(request):
    numero_expediente = request.GET.get('expediente')
    id_juzgado_param = request.GET.get('id_juzgado')
    
    # NUEVO PARÁMETRO: Determina si el cliente requiere toda la lista de acuerdos
    pedir_todo = request.GET.get('todo', 'false').lower() == 'true'

    if not numero_expediente or not id_juzgado_param:
        return JsonResponse({"error": "Faltan parámetros."}, status=400)

    id_boletin = await obtener_id_juzgado(id_juzgado_param, None)
    if not id_boletin: 
        return JsonResponse({"error": "Juzgado no válido."}, status=404)

    fecha_hoy = datetime.now().date()
    
    # 1. CONTROL DE CACHÉ INTERNO DIARIO
    expediente_obj, requiere_scraping = await verificar_cache_o_registrar(id_boletin, numero_expediente, fecha_hoy)
    
    if not requiere_scraping:
        # Si ya se revisó hoy el portal del juzgado, respondemos directo de la BD
        respuesta = await obtener_historial_local(expediente_obj, pedir_todo)
        return JsonResponse(respuesta, status=404 if "error" in respuesta else 200)

    # 2. SI NO SE HA REVISADO HOY, LANZAMOS EL SCRAPER DE PLAYWRIGHT
    acuerdos_extraidos = []
    raw_title = ""
    try:
        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True)
            page = await browser.new_page()
            acuerdos_extraidos, raw_title = await extraer_expediente_profundo(page, id_boletin, numero_expediente)
            await browser.close()
    except Exception as e:
        print(f"[ERROR Crítico Scraper Individual] {e}")

    # 3. PROCESAMOS Y GUARDAMOS EN LA BD
    respuesta_final = await procesar_acuerdos_scraper(expediente_obj, acuerdos_extraidos, fecha_hoy, raw_title, pedir_todo)
    return JsonResponse(respuesta_final, status=404 if "error" in respuesta_final else 200)

# =======================================================
# ENDPOINT 2: Scraper Masivo (El Radar Manual)
# =======================================================
async def scraper_masivo(request):
    """Endpoint manual: Busca por fecha, cruza con DB y hace scraping profundo a coincidencias."""
    id_juzgado_param = request.GET.get('id_juzgado')
    fecha_param = request.GET.get('fecha') # Formato esperado YYYY-MM-DD
    
    if not id_juzgado_param or not fecha_param:
        return JsonResponse({"error": "Parámetros 'id_juzgado' y 'fecha' son obligatorios."}, status=400)

    id_boletin = await obtener_id_juzgado(id_juzgado_param, None)
    if not id_boletin: return JsonResponse({"error": "Juzgado no válido."}, status=404)

    lista_general = []
    try:
        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True)
            page = await browser.new_page()
            
            # FASE 1: BÚSQUEDA MASIVA (El Radar)
            await page.goto("https://cjj.gob.mx/bulletin", timeout=60000)
            await page.wait_for_function("document.querySelectorAll('#judge-1 option').length > 1", timeout=15000)
            await page.select_option('#judge-1', str(id_boletin))
            
            # Clic en radio "Por Fecha"
            await page.click('input#date') 
            await page.wait_for_selector('input[name="date"]', state='visible')
            
            # Playwright requiere formato YYYY-MM-DD para inputs tipo fecha
            await page.fill('input[name="date"]', fecha_param) 
            await page.click('button.search-button')

            # Esperar a que cargue la lista (puede demorar si hay muchos)
            await page.wait_for_selector('.search-list', timeout=15000)
            
            # Extraer todos los títulos de la lista
            titulos_html = await page.query_selector_all('.item-title')
            for t in titulos_html:
                texto = await t.inner_text()
                match = re.search(r'(\d+[/|-]\d+)', texto)
                if match:
                    lista_general.append(match.group(1))

            # FASE 2: FILTRO DE COINCIDENCIAS
            # Le preguntamos a la DB cuáles de estos expedientes tienen un usuario real
            expedientes_suscritos = await filtrar_suscritos(id_boletin, lista_general)
            
            # FASE 3: EL FRANCOTIRADOR (Solo a los que importan)
            resultados_actualizados = []
            fecha_hoy = datetime.now().date()
            
            for exp_num in expedientes_suscritos:
                # Reutilizamos la misma ventana del navegador para hacerlo rápido
                acuerdos, raw_title = await extraer_expediente_profundo(page, id_boletin, exp_num)
                res_bd = await consultar_y_actualizar_bd(id_boletin, exp_num, fecha_hoy, acuerdos, raw_title)
                
                # Si de verdad hubo un cambio, lo guardamos para el reporte
                if res_bd.get("hubo_cambio"):
                    resultados_actualizados.append({"expediente": exp_num, "actualizacion": res_bd})

            await browser.close()
            
        return JsonResponse({
            "fecha_buscada": fecha_param,
            "total_publicados": len(lista_general),
            "coincidencias_nuestras": len(expedientes_suscritos),
            "actualizados_hoy": len(resultados_actualizados),
            "detalles": resultados_actualizados
        })

    except Exception as e:
        return JsonResponse({"error": str(e)}, status=500)
    

    ython
@sync_to_async
def verificar_cache_o_registrar(id_boletin, numero_expediente, fecha_hoy):
    """
    Verifica si el expediente ya se revisó hoy en el portal.
    Devuelve el objeto expediente y un booleano (True si requiere scraping, False si usa caché).
    """
    juzgado = Juzgado.objects.get(id_boletin=id_boletin)
    expediente_obj, created = Expediente.objects.get_or_create(
        juzgado=juzgado,
        numero_expediente=numero_expediente
    )
    
    if not created and expediente_obj.ultima_revision_scraper == fecha_hoy:
        return expediente_obj, False  # No requiere scraping, ya se consultó hoy
        
    return expediente_obj, True  # Requiere consultar el portal público

@sync_to_async
def obtener_historial_local(expediente_obj, pedir_todo):
    """Construye la respuesta usando exclusivamente la base de datos local."""
    acuerdos_queryset = Acuerdo.objects.filter(expediente=expediente_obj).order_by('-fecha_acuerdo', '-created_at')
    
    if not acuerdos_queryset.exists():
        return {"error": "Sin registros locales guardados para este caso."}
        
    ultimo = acuerdos_queryset.first()
    
    if pedir_todo:
        # Serializamos todos los acuerdos históricos del expediente
        historial = [
            {
                "fecha_acuerdo": a.fecha_acuerdo.strftime("%d-%m-%Y"),
                "texto": a.texto
            } for a in acuerdos_queryset
        ]
        return {
            "hubo_cambio": False,
            "solicitud_historial_completo": True,
            "historial_acuerdos": historial,
            "fecha_ultimo_acuerdo": ultimo.fecha_acuerdo.strftime("%d-%m-%Y"),
            "mensaje": "Mostrando el historial completo desde el almacenamiento local sin lanzar el scraper."
        }
    else:
        return {
            "hubo_cambio": False,
            "estado_actual": ultimo.texto,
            "fecha_ultimo_acuerdo": ultimo.fecha_acuerdo.strftime("%d-%m-%Y"),
            "mensaje": "Información recuperada localmente (ya consultado el día de hoy)."
        }
    

@sync_to_async
def procesar_acuerdos_scraper(expediente_obj, acuerdos_extraidos, fecha_hoy, raw_title, pedir_todo):
    """Procesa los datos nuevos del scraper, actualiza la fecha de revisión y estructura la respuesta."""
    # Actualizar la fecha de control para evitar segundas consultas hoy
    expediente_obj.ultima_revision_scraper = fecha_hoy
    expediente_obj.save()

    # Si venía el título de la página, actualizamos metadatos generales si no existen
    if raw_title and (not expediente_obj.tipo_juicio or not expediente_obj.partes):
        exp_match = re.search(r'(\d+[/|-]\d+)', raw_title)
        if exp_match:
            resto = raw_title.replace(exp_match.group(1), '').strip(' -')
            fragmentos = [f.strip() for f in resto.split('-') if f.strip()]
            if len(fragmentos) > 0 and not expediente_obj.tipo_juicio:
                expediente_obj.tipo_juicio = fragmentos[0][:150]
            if len(fragmentos) > 1 and not expediente_obj.partes:
                expediente_obj.partes = fragmentos[1][:255]
            expediente_obj.save()

    if not acuerdos_extraidos:
        # Si el scraper falla o no hay datos en el portal, recurrimos a lo que tengamos guardado
        return getattr(obtener_historial_local(expediente_obj, pedir_todo), '_coro', obtener_historial_local(expediente_obj, pedir_todo))

    nuevos_textos = []
    fecha_mas_reciente_extraida = None

    for texto_fila in acuerdos_extraidos:
        match = re.match(r'^(\d{2}-\d{2}-\d{4})\s*(?:(\d{2}-\d{2}-\d{4})\s+)?(.+)', texto_fila)
        if not match:
            continue
            
        f_acuerdo_str, f_prom_str, texto_limpio = match.group(1), match.group(2), match.group(3).strip()
        try:
            fecha_acuerdo = datetime.strptime(f_acuerdo_str, "%d-%m-%Y").date()
        except ValueError:
            continue
            
        fecha_promocion = None
        if f_prom_str:
            try:
                fecha_promocion = datetime.strptime(f_prom_str, "%d-%m-%Y").date()
            except ValueError:
                pass

        fecha_mas_reciente_extraida = fecha_acuerdo
        
        _, created = Acuerdo.objects.get_or_create(
            expediente=expediente_obj,
            fecha_acuerdo=fecha_acuerdo,
            texto=texto_limpio,
            defaults={'fecha_promocion': fecha_promocion}
        )
        if created:
            nuevos_textos.append(texto_limpio)

    # Si se pide todo el historial, ignoramos si hubo cambios o no para la estructura de salida
    if pedir_todo:
        acuerdos_queryset = Acuerdo.objects.filter(expediente=expediente_obj).order_by('-fecha_acuerdo', '-created_at')
        historial = [{"fecha_acuerdo": a.fecha_acuerdo.strftime("%d-%m-%Y"), "texto": a.texto} for a in acuerdos_queryset]
        return {
            "hubo_cambio": bool(nuevos_textos),
            "solicitud_historial_completo": True,
            "historial_acuerdos": historial,
            "fecha_ultimo_acuerdo": acuerdos_queryset.first().fecha_acuerdo.strftime("%d-%m-%Y") if acuerdos_queryset.exists() else fecha_hoy.strftime("%d-%m-%Y"),
            "mensaje": f"Consulta al portal realizada. Se detectaron {len(nuevos_textos)} nuevas actualizaciones en el historial."
        }

    if nuevos_textos:
        fecha_retorno = fecha_mas_reciente_extraida.strftime("%d-%m-%Y") if fecha_mas_reciente_extraida else fecha_hoy.strftime("%d-%m-%Y")
        return {
            "hubo_cambio": True,
            "estado_anterior": Acuerdo.objects.filter(expediente=expediente_obj).order_by('-fecha_acuerdo', '-created_at')[1].texto if Acuerdo.objects.filter(expediente=expediente_obj).count() > 1 else "Sin registro previo.",
            "estado_nuevo": nuevos_textos[-1],
            "fecha_ultimo_acuerdo": fecha_retorno,
            "mensaje": f"Se detectaron {len(nuevos_textos)} actualizaciones nuevas."
        }
    else:
        ultimo_acuerdo = Acuerdo.objects.filter(expediente=expediente_obj).order_by('-fecha_acuerdo', '-created_at').first()
        fecha_str = ultimo_acuerdo.fecha_acuerdo.strftime("%d-%m-%Y") if ultimo_acuerdo else fecha_hoy.strftime("%d-%m-%Y")
        return {
            "hubo_cambio": False,
            "estado_actual": ultimo_acuerdo.texto if ultimo_acuerdo else "Sin extracto.",
            "fecha_ultimo_acuerdo": fecha_str,
            "mensaje": "Información idéntica a la BD. Sin cambios reales."
        }
    
