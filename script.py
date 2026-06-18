from playwright.sync_api import sync_playwright

def determinar_materia(nombre_juzgado):
    """Clasifica el juzgado leyendo su nombre."""
    nombre = nombre_juzgado.lower()
    if 'familiar' in nombre: return 'familiar'
    if 'civil' in nombre: return 'civil'
    if 'mercantil' in nombre: return 'mercantil'
    if 'laboral' in nombre: return 'laboral'
    if 'penal' in nombre: return 'penal'
    if 'control' in nombre or 'oralidad' in nombre: return 'control'
    return 'mixto'

def extraer_catalogo():
    with sync_playwright() as p:
        print(">>> Abriendo navegador...")
        browser = p.chromium.launch(headless=True)
        page = browser.new_context().new_page()
        
        print(">>> Accediendo al CJJ...")
        page.goto("https://cjj.gob.mx/bulletin")
        
        # ESPERA INTELIGENTE (Tomada de tu script funcional)
        print(">>> Esperando a que carguen los juzgados...")
        page.wait_for_function("document.querySelectorAll('#judge-1 option').length > 1", timeout=15000)
        
        opciones = page.locator('#judge-1 option').all()
        
        print(f">>> Se encontraron {len(opciones)} opciones. Procesando...\n")
        
        juzgados_generados = []
        
        for opt in opciones:
            valor_id = opt.get_attribute('value')
            nombre_texto = opt.inner_text().strip()
            
            # Filtramos opciones vacías
            if valor_id and valor_id != "":
                materia = determinar_materia(nombre_texto)
                juzgados_generados.append({
                    "id_boletin": f"'{valor_id}'",
                    "nombre": nombre_texto,
                    "materia": materia
                })
        
        browser.close()
        
        # ==========================================
        # IMPRIMIR CÓDIGO LISTO PARA COPIAR Y PEGAR
        # ==========================================
        print("Copia y pega este bloque en tu archivo 0002_seed_juzgados.py:\n")
        print("    juzgados_data = [")
        for j in juzgados_generados:
            print(f"        {j},")
        print("    ]")

if __name__ == "__main__":
    extraer_catalogo()