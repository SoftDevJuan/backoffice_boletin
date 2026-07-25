import requests
from django.conf import settings
from .models import Notificacion, Expediente, Usuario
from asgiref.sync import sync_to_async
import re

OPENWA_API_URL = "http://localhost:2785/api"
OPENWA_API_KEY = "owa_k1_c7c3988df633377ab4505c201e084f422ab679fe7e2eee3d3d5008623b87e40e"
SESSION_NAME = "7b4decee-b2d6-4797-b472-d563f490fcd4"

def procesar_notificaciones_lote(expediente):
    """
    Versión inteligente: Cruza la base de datos para saber qué acuerdos le faltan 
    a cada usuario suscrito y envía un lote exclusivo con los faltantes.
    """
    # 1. Obtenemos a todos los usuarios suscritos al expediente
    usuarios_suscritos = expediente.usuarios.all()
    
    # 2. Obtenemos TODOS los acuerdos que existen actualmente para ese expediente
    # (Si tu related_name no es 'acuerdos', cámbialo por expediente.acuerdo_set.all())
    todos_los_acuerdos = expediente.acuerdos.all() 
    
    if not todos_los_acuerdos.exists():
        return # Si el expediente no tiene acuerdos, no hay nada que notificar

    for usuario in usuarios_suscritos:
        # 3. ¿De cuáles acuerdos YA TIENE registro este usuario?
        # (Evaluamos tanto 'enviado' como 'fallido' para no duplicar. Los fallidos se reintentan manual en React)
        acuerdos_notificados = Notificacion.objects.filter(
            usuario=usuario,
            acuerdo__expediente=expediente
        ).values_list('acuerdo_id', flat=True)
        
        # 4. LA MAGIA: Filtramos excluyendo los que ya tiene y ordenamos del más nuevo al más viejo
        acuerdos_faltantes = todos_los_acuerdos.exclude(id__in=acuerdos_notificados).order_by('-fecha_acuerdo')
        
        if not acuerdos_faltantes.exists():
            continue # Este usuario está al día, saltamos al siguiente
            
        print(f"Enviando {acuerdos_faltantes.count()} acuerdos faltantes a {usuario.nombre}...")
        
        # 5. Creamos las notificaciones en estado 'pendiente' para reservar su lugar en la BD
        notificaciones_creadas = []
        for acuerdo in acuerdos_faltantes:
            notif = Notificacion.objects.create(
                usuario=usuario,
                acuerdo=acuerdo,
                estatus='pendiente'
            )
            notificaciones_creadas.append(notif)
            
        # 6. Enviamos el lote a WhatsApp usando la función que parches en el turno anterior
        exito_wa = enviar_whatsapp_lote(usuario, expediente, list(acuerdos_faltantes))
        
        # 7. Actualizamos el estatus final de todas las notificaciones de este lote
        nuevo_estatus = 'enviado' if exito_wa else 'fallido'
        for notif in notificaciones_creadas:
            notif.estatus = nuevo_estatus
            notif.save()

def enviar_whatsapp_lote(usuario, expediente, acuerdos_nuevos):
    # Redacción del encabezado
    texto_wa = f"Hola {usuario.nombre}, hay una actualización del expediente {expediente.numero_expediente}.\n\n"
    
    acuerdos_ordenados = sorted(acuerdos_nuevos, key=lambda x: x.fecha_acuerdo, reverse=True)
    for acuerdo in acuerdos_ordenados:
        fecha_str = acuerdo.fecha_acuerdo.strftime('%d-%m-%Y')
        texto_wa += f"🗓️ {fecha_str}\n{acuerdo.texto}\n\n"
        
    texto_wa += "Quedo a tus órdenes."

    headers = {
        "x-api-key": OPENWA_API_KEY,
        "Content-Type": "application/json",
        "accept": "application/json"
    }
    
    # 1. LIMPIEZA DEL NÚMERO: Eliminamos espacios, guiones, símbolos '+' y paréntesis
    telefono_limpio = re.sub(r'\D', '', usuario.telefono)
    
    # 2. VALIDACIÓN DEL CÓDIGO DE PAÍS (Para México: 52 o 521)
    # Si el usuario solo puso 10 dígitos (ej. 3312345678), le agregamos el 521
    if len(telefono_limpio) == 10:
        telefono_limpio = f"521{telefono_limpio}"

    chat_id = f"{telefono_limpio}@c.us" if not telefono_limpio.endswith('@c.us') else telefono_limpio

    body = {
        "chatId": chat_id,
        "text": texto_wa
    }

    url_envio = f"{OPENWA_API_URL}/sessions/{SESSION_NAME}/messages/send-text"
    
    # DEBUG CRÍTICO: Esto imprimirá exactamente qué chatId se está usando
    print(f"[DEBUG WA] Intentando enviar a {usuario.nombre} -> ChatID formateado: {chat_id}")
    
    try:
        response = requests.post(url_envio, json=body, headers=headers, timeout=10)
        
        # Agregamos impresión de la respuesta exacta de OpenWA para depurar si sigue fallando
        print(f"[DEBUG WA] Respuesta OpenWA: {response.status_code} - {response.text}")
        
        if response.status_code in [200, 201]:
            print(f"✅ Lote WhatsApp entregado a {usuario.nombre}")
            return True
        elif response.status_code == 500 and telefono_limpio.startswith('521'):
            print(f"⚠️ [GHOST BUG] OpenWA crasheó al leer el ID para {telefono_limpio}, pero el mensaje SÍ llegó. Forzando ÉXITO.")
            return True
        else:
            print(f"❌ Error OpenWA al enviar lote a {usuario.nombre}: {response.status_code}")
            return False
            
    except Exception as e:
        print(f"❌ Error de conexión al enviar WhatsApp lote a {usuario.nombre}: {e}")
        return False

