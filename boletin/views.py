import asyncio
import requests
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
    print(f"\n[DEBUG FILTRO] Entrando a filtrar_suscritos para juzgado: {id_boletin}")
    print(f"[DEBUG FILTRO] Cantidad de expedientes crudos extraídos hoy del boletín: {len(lista_expedientes_encontrados)}")
    if lista_expedientes_encontrados:
        print(f"[DEBUG FILTRO] Muestra de expedientes del boletín (primeros 5): {lista_expedientes_encontrados[:5]}")
    
    qs = Expediente.objects.filter(
        juzgado__id_boletin=id_boletin,
        numero_expediente__in=lista_expedientes_encontrados,
        usuarios__isnull=False,
        usuarios__esta_activo=True
    ).values_list('numero_expediente', flat=True).distinct()
    
    coincidencias = list(qs)
    print(f"[DEBUG FILTRO] Coincidencias reales encontradas con usuarios activos en la BD: {coincidencias}")
    return coincidencias

# NUEVO HELPER: Extrae los nombres y teléfonos de los interesados en un expediente
@sync_to_async
def obtener_telefonos_suscritos(id_boletin, numero_expediente):
    expediente = Expediente.objects.filter(juzgado__id_boletin=id_boletin, numero_expediente=numero_expediente).first()
    if expediente:
        # Usamos .values('nombre', 'telefono') para traernos ambos campos como diccionario
        usuarios = list(expediente.usuarios.filter(esta_activo=True, notificaciones_activas=True).values('nombre', 'telefono'))
        print(f"[DEBUG NOTIFICACIÓN] Usuarios activos suscritos a {numero_expediente}: {usuarios}")
        return usuarios
    print(f"[DEBUG NOTIFICACIÓN] No se encontró el expediente {numero_expediente} para extraer usuarios.")
    return []

@sync_to_async
def verificar_cache_o_registrar(id_boletin, numero_expediente, fecha_hoy):
    juzgado = Juzgado.objects.get(id_boletin=id_boletin)
    expediente_obj, created = Expediente.objects.get_or_create(juzgado=juzgado, numero_expediente=numero_expediente)
    if not created and expediente_obj.ultima_revision_scraper == fecha_hoy:
        return expediente_obj, False
    return expediente_obj, True

@sync_to_async
def obtener_historial_local(expediente_obj, pedir_todo):
    acuerdos_queryset = Acuerdo.objects.filter(expediente=expediente_obj).order_by('-fecha_acuerdo', '-created_at')
    if not acuerdos_queryset.exists():
        return {"error": "Sin registros locales guardados."}
    ultimo = acuerdos_queryset.first()
    if pedir_todo:
        historial = [{"fecha_acuerdo": a.fecha_acuerdo.strftime("%d-%m-%Y"), "texto": a.texto} for a in acuerdos_queryset]
        return {
            "hubo_cambio": False, "solicitud_historial_completo": True, "historial_acuerdos": historial,
            "fecha_ultimo_acuerdo": ultimo.fecha_acuerdo.strftime("%d-%m-%Y"), "mensaje": "Historial local."
        }
    else:
        return {
            "hubo_cambio": False, "estado_actual": ultimo.texto,
            "fecha_ultimo_acuerdo": ultimo.fecha_acuerdo.strftime("%d-%m-%Y"), "mensaje": "Caché local."
        }

@sync_to_async
def procesar_acuerdos_scraper(expediente_obj, acuerdos_extraidos, fecha_hoy, raw_title, pedir_todo):
    expediente_obj.ultima_revision_scraper = fecha_hoy
    expediente_obj.save()

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
        return getattr(obtener_historial_local(expediente_obj, pedir_todo), '_coro', obtener_historial_local(expediente_obj, pedir_todo))

    nuevos_textos = []
    fecha_mas_reciente_extraida = None

    for texto_fila in acuerdos_extraidos:
        match = re.match(r'^(\d{2}-\d{2}-\d{4})\s*(?:(\d{2}-\d{2}-\d{4})\s+)?(.+)', texto_fila)
        if not match: continue
            
        f_acuerdo_str, f_prom_str, texto_limpio = match.group(1), match.group(2), match.group(3).strip()
        try:
            fecha_acuerdo = datetime.strptime(f_acuerdo_str, "%d-%m-%Y").date()
        except ValueError: continue
            
        fecha_promocion = None
        if f_prom_str:
            try: fecha_promocion = datetime.strptime(f_prom_str, "%d-%m-%Y").date()
            except ValueError: pass

        fecha_mas_reciente_extraida = fecha_acuerdo
        _, created = Acuerdo.objects.get_or_create(
            expediente=expediente_obj, fecha_acuerdo=fecha_acuerdo, texto=texto_limpio, defaults={'fecha_promocion': fecha_promocion}
        )
        if created: nuevos_textos.append(texto_limpio)

    if pedir_todo:
        acuerdos_queryset = Acuerdo.objects.filter(expediente=expediente_obj).order_by('-fecha_acuerdo', '-created_at')
        historial = [{"fecha_acuerdo": a.fecha_acuerdo.strftime("%d-%m-%Y"), "texto": a.texto} for a in acuerdos_queryset]
        return {
            "hubo_cambio": bool(nuevos_textos), "solicitud_historial_completo": True, "historial_acuerdos": historial,
            "fecha_ultimo_acuerdo": acuerdos_queryset.first().fecha_acuerdo.strftime("%d-%m-%Y") if acuerdos_queryset.exists() else fecha_hoy.strftime("%d-%m-%Y"),
            "mensaje": f"Se detectaron {len(nuevos_textos)} nuevas actualizaciones."
        }

    if nuevos_textos:
        fecha_retorno = fecha_mas_reciente_extraida.strftime("%d-%m-%Y") if fecha_mas_reciente_extraida else fecha_hoy.strftime("%d-%m-%Y")
        return {
            "hubo_cambio": True,
            "estado_anterior": Acuerdo.objects.filter(expediente=expediente_obj).order_by('-fecha_acuerdo', '-created_at')[1].texto if Acuerdo.objects.filter(expediente=expediente_obj).count() > 1 else "Sin registro previo.",
            "estado_nuevo": nuevos_textos[-1], "fecha_ultimo_acuerdo": fecha_retorno, "mensaje": f"{len(nuevos_textos)} nuevas."
        }
    else:
        ultimo_acuerdo = Acuerdo.objects.filter(expediente=expediente_obj).order_by('-fecha_acuerdo', '-created_at').first()
        fecha_str = ultimo_acuerdo.fecha_acuerdo.strftime("%d-%m-%Y") if ultimo_acuerdo else fecha_hoy.strftime("%d-%m-%Y")
        return {
            "hubo_cambio": False, "estado_actual": ultimo_acuerdo.texto if ultimo_acuerdo else "Sin extracto.",
            "fecha_ultimo_acuerdo": fecha_str, "mensaje": "Sin cambios reales."
        }

# =======================================================
# NÚCLEO SCRAPER
# =======================================================
async def extraer_expediente_profundo(page, id_boletin, numero_expediente):
    acuerdos_extraidos, raw_title = [], ""
    try:
        await page.goto("https://cjj.gob.mx/bulletin", timeout=60000)
        await page.wait_for_function("document.querySelectorAll('#judge-1 option').length > 1", timeout=15000)
        await page.select_option('#judge-1', str(id_boletin))
        await page.click('input#proceedings')
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
                for fila in filas_acuerdos[1:]: acuerdos_extraidos.append(re.sub(r'\s+', ' ', (await fila.inner_text()).strip()))
        else:
            items = await page.query_selector_all('.search-item')
            if items:
                title_el, text_el = await items[0].query_selector('.item-title'), await items[0].query_selector('.item-text')
                if title_el and text_el:
                    raw_title = (await title_el.inner_text()).strip()
                    acuerdos_extraidos.append(re.sub(r'\s+', ' ', (await text_el.inner_text()).strip()))
    except Exception as e: print(f"[Aviso Scraper Profundo] Exp {numero_expediente}: {e}")
    return acuerdos_extraidos, raw_title

# =======================================================
# HELPER DE BASE DE DATOS ADICIONAL PARA ENRUTAMIENTO MASIVO
# =======================================================
@sync_to_async
def consultar_y_actualizar_bd(id_boletin, numero_expediente, fecha_hoy, acuerdos_extraidos, raw_title):
    print(f"[DEBUG BD] Procesando actualización masiva para Exp: {numero_expediente}")
    juzgado = Juzgado.objects.get(id_boletin=id_boletin)
    expediente_obj = Expediente.objects.filter(juzgado=juzgado, numero_expediente=numero_expediente).first()
    ultimo_acuerdo = Acuerdo.objects.filter(expediente=expediente_obj).order_by('-fecha_acuerdo', '-created_at').first() if expediente_obj else None

    if not acuerdos_extraidos:
        print(f"[DEBUG BD] El scraper profundo devolvió una lista vacía para {numero_expediente}")
        if ultimo_acuerdo:
            return {"hubo_cambio": False, "estado_actual": ultimo_acuerdo.texto, "fecha_ultimo_acuerdo": ultimo_acuerdo.fecha_acuerdo.strftime("%d-%m-%Y")}
        return {"error": "Sin resultados"}

    nuevos_textos = []
    fecha_mas_reciente_extraida = None

    for texto_fila in acuerdos_extraidos:
        match = re.match(r'^(\d{2}-\d{2}-\d{4})\s*(?:(\d{2}-\d{2}-\d{4})\s+)?(.+)', texto_fila)
        if not match: continue
            
        f_acuerdo_str, f_prom_str, texto_limpio = match.group(1), match.group(2), match.group(3).strip()
        try:
            fecha_acuerdo = datetime.strptime(f_acuerdo_str, "%d-%m-%Y").date()
        except ValueError: continue
            
        fecha_promocion = None
        if f_prom_str:
            try: fecha_promocion = datetime.strptime(f_prom_str, "%d-%m-%Y").date()
            except ValueError: pass

        fecha_mas_reciente_extraida = fecha_acuerdo
        _, created = Acuerdo.objects.get_or_create(
            expediente=expediente_obj, fecha_acuerdo=fecha_acuerdo, texto=texto_limpio, defaults={'fecha_promocion': fecha_promocion}
        )
        if created: 
            nuevos_textos.append(texto_limpio)

    print(f"[DEBUG BD] Exp {numero_expediente} -> Total filas procesadas: {len(acuerdos_extraidos)} | Insertadas como nuevas: {len(nuevos_textos)}")

    if nuevos_textos:
        fecha_retorno = fecha_mas_reciente_extraida.strftime("%d-%m-%Y") if fecha_mas_reciente_extraida else fecha_hoy.strftime("%d-%m-%Y")
        return {"hubo_cambio": True, "estado_nuevo": nuevos_textos[-1], "fecha_ultimo_acuerdo": fecha_retorno}
    else:
        fecha_str = ultimo_acuerdo.fecha_acuerdo.strftime("%d-%m-%Y") if ultimo_acuerdo else fecha_hoy.strftime("%d-%m-%Y")
        return {"hubo_cambio": False, "estado_actual": ultimo_acuerdo.texto if ultimo_acuerdo else "Sin extracto.", "fecha_ultimo_acuerdo": fecha_str}

# =======================================================
# ENDPOINT 1: Consulta Individual
# =======================================================
async def consultar_expediente(request):
    numero_expediente = request.GET.get('expediente')
    id_juzgado_param = request.GET.get('id_juzgado')
    pedir_todo = request.GET.get('todo', 'false').lower() == 'true'

    if not numero_expediente or not id_juzgado_param: return JsonResponse({"error": "Faltan parámetros."}, status=400)

    id_boletin = await obtener_id_juzgado(id_juzgado_param, None)
    if not id_boletin: return JsonResponse({"error": "Juzgado no válido."}, status=404)

    fecha_hoy = datetime.now().date()
    expediente_obj, requiere_scraping = await verificar_cache_o_registrar(id_boletin, numero_expediente, fecha_hoy)
    
    if not requiere_scraping:
        respuesta = await obtener_historial_local(expediente_obj, pedir_todo)
        return JsonResponse(respuesta, status=404 if "error" in respuesta else 200)

    acuerdos_extraidos, raw_title = [], ""
    try:
        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True)
            page = await browser.new_page()
            acuerdos_extraidos, raw_title = await extraer_expediente_profundo(page, id_boletin, numero_expediente)
            await browser.close()
    except Exception as e: print(f"[ERROR] {e}")

    respuesta_final = await procesar_acuerdos_scraper(expediente_obj, acuerdos_extraidos, fecha_hoy, raw_title, pedir_todo)
    return JsonResponse(respuesta_final, status=404 if "error" in respuesta_final else 200)

# =======================================================
# ENDPOINT 2: Scraper Masivo 
# =======================================================
async def scraper_masivo(request):
    id_juzgado_param = request.GET.get('id_juzgado')
    fecha_param = request.GET.get('fecha')
    
    print(f"\n=======================================================")
    print(f"[DEBUG RADAR] INICIANDO SCRAPER MASIVO EN DJANGO")
    print(f"[DEBUG RADAR] Parámetros recibidos -> Juzgado: {id_juzgado_param} | Fecha: {fecha_param}")
    print(f"=======================================================")

    if not id_juzgado_param or not fecha_param: return JsonResponse({"error": "Faltan parámetros."}, status=400)
    id_boletin = await obtener_id_juzgado(id_juzgado_param, None)
    if not id_boletin: return JsonResponse({"error": "Juzgado no válido."}, status=404)

    lista_general = []
    try:
        async with async_playwright() as p: 
            # headless=True por headless=False temporalmente para ver el navegador en tiempo real.
            browser = await p.chromium.launch(headless=True)
            page = await browser.new_page()
            
            print(f"[DEBUG RADAR] Abriendo navegador y conectando al portal...")
            
            # BLOQUE PROTEGIDO: Carga inicial del sitio con diagnóstico visual
            try:
                await page.goto("https://cjj.gob.mx/bulletin", timeout=60000)
                await page.wait_for_selector('#judge-1', timeout=15000)
                # Extendemos el tiempo de espera a 25 segundos para servidores lentos
                await page.wait_for_function("document.querySelectorAll('#judge-1 option').length > 1", timeout=25000)
            except Exception as timeout_err:
                # Evidencia crucial: Guarda una imagen de lo que el bot está viendo realmente
                await page.screenshot(path="error_radar_timeout.png")
                print(f"[❌ DEBUG RADAR] El portal falló al cargar el catálogo de juzgados.")
                print(f"[❌ DEBUG RADAR] Captura de pantalla de diagnóstico guardada en: error_radar_timeout.png")
                await browser.close()
                return JsonResponse({
                    "error": "El portal del Poder Judicial no respondió a tiempo o bloqueó la conexión automática.",
                    "diagnostico": "Revisa el archivo error_radar_timeout.png en la raíz del proyecto para verificar si hay un bloqueo o caída."
                }, status=503)

            # Continuación normal si la página carga correctamente
            await page.select_option('#judge-1', str(id_boletin))
            await page.click('input#date') 
            await page.wait_for_selector('input[name="date"]', state='visible')
            await page.fill('input[name="date"]', fecha_param) 
            await page.click('button.search-button')

            print(f"[DEBUG RADAR] Esperando renderización de resultados masivos...")
            await page.wait_for_selector('.search-list', timeout=15000)
            titulos_html = await page.query_selector_all('.item-title')
            
            for t in titulos_html:
                texto = await t.inner_text()
                match = re.search(r'(\d+[/|-]\d+)', texto)
                if match: lista_general.append(match.group(1))

            print(f"[DEBUG RADAR] Extracción masiva terminada. Total expedientes en HTML: {len(lista_general)}")

            expedientes_suscritos = await filtrar_suscritos(id_boletin, lista_general)
            resultados_actualizados = []
            fecha_hoy = datetime.now().date()
            
            for exp_num in expedientes_suscritos:
                print(f"[DEBUG RADAR] -> Disparando Francotirador Profundo para coincidencia: {exp_num}")
                acuerdos, raw_title = await extraer_expediente_profundo(page, id_boletin, exp_num)
                res_bd = await consultar_y_actualizar_bd(id_boletin, exp_num, fecha_hoy, acuerdos, raw_title)
                
                print(f"[DEBUG RADAR] Resultado BD para {exp_num}: hubo_cambio = {res_bd.get('hubo_cambio')}")

                if res_bd.get("hubo_cambio"):
                    resultados_actualizados.append({"expediente": exp_num, "actualizacion": res_bd})
                    usuarios = await obtener_telefonos_suscritos(id_boletin, exp_num)
                    
                    for usuario in usuarios:
                        payload = {
                            "nombre": usuario["nombre"], 
                            "telefono": usuario["telefono"],
                            "expediente": exp_num,
                            "juzgado": id_juzgado_param,
                            "fecha": res_bd["fecha_ultimo_acuerdo"],
                            "nuevo_acuerdo": res_bd["estado_nuevo"]
                        }
                        
                        print(f"[DEBUG HTTP] Enviando payload a FastAPI para {usuario['nombre']} ({usuario['telefono']})")
                        try:
                            response_fastapi = await asyncio.to_thread(
                                requests.post, 
                                "http://127.0.0.1:8000/api/notificar-actualizacion", 
                                json=payload, 
                                timeout=5
                            )
                        except Exception as e:
                            print(f"[❌ DEBUG HTTP ERROR] Falló la conexión con FastAPI para exp {exp_num}: {e}")
                else:
                    print(f"[DEBUG RADAR] Se omitió el envío HTTP para {exp_num} porque no se insertaron filas nuevas (duplicado local).")

            await browser.close()
            
        print(f"\n=======================================================")
        print(f"[DEBUG RADAR] PROCESO TERMINADO EXITOSAMENTE")
        print(f"=======================================================\n")
        
        return JsonResponse({
            "fecha_buscada": fecha_param, "total_publicados": len(lista_general),
            "coincidencias_nuestras": len(expedientes_suscritos), "actualizados_hoy": len(resultados_actualizados),
            "detalles": resultados_actualizados
        })

    except Exception as e: 
        print(f"[❌ DEBUG RADAR CRÍTICO] Excepción general en scraper_masivo: {e}")
        return JsonResponse({"error": str(e)}, status=500)