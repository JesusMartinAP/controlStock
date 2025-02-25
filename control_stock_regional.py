import concurrent.futures
from datetime import datetime
import requests
from bs4 import BeautifulSoup
from openpyxl import Workbook
import flet as ft
import time
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
import os
import re

# Variables globales
proceso_en_ejecucion = False
estado_codigos = []
total_codigos = 0
codigos_procesados = 0
start_time = None

def requests_retry_session(retries=5, backoff_factor=2.0, status_forcelist=(500, 502, 503, 504)):
    session = requests.Session()
    retry = Retry(
        total=retries,
        read=retries,
        connect=retries,
        backoff_factor=backoff_factor,
        status_forcelist=status_forcelist,
    )
    adapter = HTTPAdapter(max_retries=retry, pool_connections=50, pool_maxsize=50)
    session.mount('http://', adapter)
    session.mount('https://', adapter)
    return session

def obtener_estado_precio_imagenes(codigo_padre, pais):
    if not codigo_padre:
        return "Código vacío", "N/A", 0, "N/A", "N/A", 0, "N/A", "N/A"

    session = requests_retry_session()

    if len(codigo_padre) == 8:
        codigo_padre = codigo_padre + "001"

    try:
        time.sleep(2.0)

        url_estado = f'https://www.marathon.store/{pais}/view/ProductVariantSelectorComponentController?componentUid=VariantSelector&currentProductCode={codigo_padre}'
        url_precio = f'https://www.marathon.store/{pais}/p/{codigo_padre}'

        # Estado del producto
        inicio_tiempo = time.time()
        response_estado = session.get(url_estado, timeout=20)
        
        if response_estado.status_code != 200:
            return f"Error HTTP {response_estado.status_code}", "N/A", 0, "N/A", "N/A", 0, "N/A", "N/A"

        soup_estado = BeautifulSoup(response_estado.content, 'html.parser')
        estado = "Agotado"
        
        if lis := soup_estado.find_all('li', attrs={'data-url': lambda x: x and str(codigo_padre) in x}):
            for li in lis:
                if li.get('data-has-stock') == "true" or li.get('data-selected') == "true":
                    estado = "Disponible"
                    break

        # Detalles del producto
        response_precio = session.get(url_precio, timeout=20)
        if response_precio.status_code != 200:
            return estado, "N/A", 0, "N/A", "N/A", 0, "N/A", "N/A"

        soup_precio = BeautifulSoup(response_precio.content, 'html.parser')
        
        # Extraer el precio actual. Se prioriza la versión de promoción si existe.
        precio_element = (soup_precio.select_one('div.price.price-promotion') or 
                          soup_precio.select_one('div.desktop-price') or 
                          soup_precio.select_one('div.price') or 
                          soup_precio.select_one('[itemprop="price"]'))
        precio = precio_element.text.strip() if precio_element else "N/A"
        
        # Extraer el precio original (full price) que generalmente está dentro de <del>
        precio_original_element = soup_precio.find('del')
        precio_original = precio_original_element.text.strip() if precio_original_element else "N/A"
        
        # Extraer el descuento; se busca el porcentaje en el texto
        descuento_element = soup_precio.find('p', class_='promotion')
        if descuento_element:
            match = re.search(r'(\d+%)', descuento_element.text)
            descuento = match.group(1) if match else descuento_element.text.replace("Descuento del", "").strip()
        else:
            descuento = "N/A"
        
        galeria_imagenes = soup_precio.find('div', class_='desktop-image-gallery')
        imagenes = [img['data-src'] for img in galeria_imagenes.find_all('img', attrs={'data-src': True})] if galeria_imagenes else []
        
        tiempo_total = time.time() - inicio_tiempo
        
        return (
            estado,
            precio,
            len(imagenes),
            ', '.join(imagenes),
            url_precio,
            tiempo_total,
            descuento,
            precio_original
        )

    except Exception as e:
        print(f"Error en {codigo_padre}: {str(e)}")
        return f"Error: {str(e)}", "N/A", 0, "N/A", "N/A", 0, "N/A", "N/A"

def actualizar_progreso(page):
    global codigos_procesados, total_codigos, start_time
    tiempo_transcurrido = datetime.now() - start_time
    horas, resto = divmod(tiempo_transcurrido.seconds, 3600)
    minutos, segundos = divmod(resto, 60)
    progreso = (codigos_procesados / total_codigos) * 100

    # Actualizar elementos de la interfaz
    page.progress_bar.value = progreso / 100
    page.contador.value = f"Procesados: {codigos_procesados}/{total_codigos}"
    page.tiempo.value = f"Tiempo: {horas:02d}:{minutos:02d}:{segundos:02d}"
    page.update()

def procesar_codigos(page, codigos, pais):
    global proceso_en_ejecucion, estado_codigos, total_codigos, codigos_procesados, start_time
    total_codigos = len(codigos)
    codigos_procesados = 0
    start_time = datetime.now()
    estado_codigos = []

    with concurrent.futures.ThreadPoolExecutor(max_workers=3) as executor:
        futures = {executor.submit(obtener_estado_precio_imagenes, codigo, pais): codigo for codigo in codigos}
        
        for future in concurrent.futures.as_completed(futures):
            codigo = futures[future]
            try:
                resultado = future.result()
                estado_codigos.append((codigo, *resultado))
            except Exception as exc:
                estado_codigos.append((codigo, f"Error: {exc}", "N/A", 0, "N/A", "N/A", 0, "N/A", "N/A"))
            
            codigos_procesados += 1
            actualizar_progreso(page)

    guardar_resultados(page, pais)
    proceso_en_ejecucion = False

def guardar_resultados(page, pais):
    wb = Workbook()
    ws = wb.active
    ws.title = "Resultados"
    headers = ["Código", "Estado", "Precio", "Imágenes", "Enlaces Imágenes", "URL", "Tiempo", "Descuento", "Precio Original"]
    ws.append(headers)
    
    for fila in estado_codigos:
        ws.append(fila)
    
    nombre_archivo = f"Resultados_{pais}_{datetime.now().strftime('%Y%m%d_%H%M')}.xlsx"
    wb.save(nombre_archivo)
    
    page.add(ft.Text(f"Archivo guardado: {nombre_archivo}"))
    page.add(ft.ElevatedButton(
        text="Abrir Excel",
        on_click=lambda _: os.system(f'start excel "{os.path.abspath(nombre_archivo)}"')
    ))

def main(page: ft.Page):
    page.title = "Scraper Marathon"
    page.theme_mode = ft.ThemeMode.LIGHT
    page.window_width = 800
    page.window_height = 600
    
    # Componentes de UI
    codigos_control = ft.TextField(
        multiline=True, 
        min_lines=10,
        hint_text="Ingrese códigos separados por espacio o nueva línea",
        width=700
    )
    
    # Invertimos el orden: el primer parámetro es el valor (usado en la URL) y el segundo la etiqueta visible.
    pais_selector = ft.Dropdown(
        options=[
            ft.dropdown.Option("pe", "Perú"),
            ft.dropdown.Option("bo", "Bolivia"),
            ft.dropdown.Option("ec", "Ecuador")
        ],
        value=None,  # sin valor predeterminado para forzar la selección
        label="País",
        width=200
    )
    
    # Elementos de progreso (ahora son atributos de page)
    page.progress_bar = ft.ProgressBar(width=700, visible=False)
    page.contador = ft.Text()
    page.tiempo = ft.Text()
    
    # Botones
    btn_iniciar = ft.ElevatedButton("Iniciar scraping", scale=1.2)
    btn_detener = ft.OutlinedButton("Detener proceso")
    
    # Layout
    page.add(
        ft.Column([
            ft.Row([pais_selector], alignment=ft.MainAxisAlignment.CENTER),
            ft.Row([codigos_control], alignment=ft.MainAxisAlignment.CENTER),
            ft.Row([btn_iniciar, btn_detener], alignment=ft.MainAxisAlignment.CENTER),
            page.progress_bar,
            page.contador,
            page.tiempo
        ])
    )
    
    # Eventos
    def iniciar_scraping(e):
        global proceso_en_ejecucion
        if not pais_selector.value:
            page.add(ft.Text("Por favor, seleccione un país.", color=ft.colors.RED))
            return
        if not proceso_en_ejecucion:
            proceso_en_ejecucion = True
            page.progress_bar.visible = True  # Hacer visible la barra
            codigos = codigos_control.value.strip().split()
            procesar_codigos(page, codigos, pais_selector.value)
    
    def detener_scraping(e):
        global proceso_en_ejecucion
        proceso_en_ejecucion = False
        page.add(ft.Text("Proceso detenido por el usuario", color=ft.colors.RED))
    
    btn_iniciar.on_click = iniciar_scraping
    btn_detener.on_click = detener_scraping

ft.app(target=main)
