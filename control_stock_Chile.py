import flet as ft
import requests
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
from openpyxl import Workbook
from bs4 import BeautifulSoup
import time
import threading

# Configuración
MAX_WORKERS = 20  # Número máximo de hilos
TIMEOUT = 10      # Tiempo de espera para solicitudes

headers = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
}

# Variables globales de control
processing_paused = False
processing_running = False

def completar_codigo(codigo):
    """Agrega '001' a códigos de 8 dígitos."""
    if len(codigo) == 8:
        return codigo + "001"
    return codigo

def obtener_datos_producto(codigo_padre):
    """Extrae los datos del producto a partir de su código."""
    codigo_padre = completar_codigo(codigo_padre)
    url = f'https://www.marathon.cl/{codigo_padre}.html'
    status_web = 'N/A'
    try:
        start_time = time.time()
        response = requests.get(url, headers=headers, timeout=TIMEOUT, allow_redirects=True)
        load_time = time.time() - start_time
        final_url = response.url
        soup = BeautifulSoup(response.text, 'html.parser')
        
        # Determinar el estado web
        if 'marathon.cl/' not in final_url:
            status_web = 'Redirección detectada'
        elif "Página no encontrada" in soup.text or "El producto que buscas no existe" in soup.text:
            status_web = 'No disponible'
        elif response.status_code == 404:
            status_web = 'Error 404'
        else:
            status_web = 'Disponible'
        if final_url == 'https://www.marathon.cl/':
            status_web = 'Redireccionado al inicio'
        
        # Extraer precios y demás datos
        precio_actual = soup.select_one('span.value[content]')
        if not precio_actual:
            precio_actual = soup.select_one('span.price-sales')
        if precio_actual:
            if 'content' in precio_actual.attrs:
                precio_actual = precio_actual['content']
            else:
                precio_actual = precio_actual.text.strip()
        else:
            precio_actual = 'N/A'
        
        precio_anterior = soup.select_one('span.value[content]:nth-of-type(2)')
        if precio_anterior:
            precio_anterior = precio_anterior.get('content', 'N/A')
        else:
            precio_anterior = 'N/A'
        
        descuento = soup.select_one('div.pd-item-promo')
        descuento = descuento.text.strip() if descuento else 'N/A'
        imagenes = len(soup.select('img.galley_img'))
        
        descripcion_element = soup.select_one('div.product-text[data-product-field="longDescription"]')
        if not descripcion_element:
            descripcion_element = soup.select_one('div.product-description')
        descripcion_texto = descripcion_element.get_text(strip=True) if descripcion_element else 'N/A'
        
        return (codigo_padre, precio_actual, precio_anterior, descuento, imagenes, descripcion_texto, round(load_time, 2), url, status_web)
    
    except requests.exceptions.RequestException as e:
        print(f"Error de red al procesar {codigo_padre}: {str(e)}")
        return (codigo_padre, 'Error de red', 'N/A', 'N/A', 'N/A', 'N/A', 'N/A', url, 'Error de red')
    except Exception as e:
        print(f"Error inesperado al procesar {codigo_padre}: {str(e)}")
        return (codigo_padre, 'Error inesperado', 'N/A', 'N/A', 'N/A', 'N/A', 'N/A', url, 'Error inesperado')

def guardar_resultados(resultados):
    """Guarda los resultados en un archivo Excel."""
    wb = Workbook()
    ws = wb.active
    ws.title = "Datos Productos"
    headers_excel = [
        "CODIGO", "PRECIO ACTUAL", "PRECIO ANTERIOR", "DESCUENTO",
        "Cant. Img", "DESCRIPCION COMERCIAL", "TIEMPO DE CARGA (s)", "URL", "STATUS WEB"
    ]
    for col, header in enumerate(headers_excel, start=1):
        ws.cell(row=1, column=col, value=header)
    for i, row in enumerate(resultados, start=2):
        for j, value in enumerate(row, start=1):
            ws.cell(row=i, column=j, value=value)
    fecha_actual = datetime.now().strftime("%Y-%m-%d")
    nombre_archivo = f"Datos_Productos_Web_{fecha_actual}.xlsx"
    wb.save(nombre_archivo)
    return nombre_archivo

def process_codes(codes, progress_callback, status_callback):
    """Procesa la lista de códigos y actualiza el progreso y estado."""
    global processing_paused
    results = []
    total = len(codes)
    start_time = datetime.now()
    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
        futures = {executor.submit(obtener_datos_producto, code): code for code in codes}
        for i, future in enumerate(as_completed(futures), start=1):
            if processing_paused:
                status_callback("Proceso pausado.")
                break
            result = future.result()
            results.append(result)
            elapsed = datetime.now() - start_time
            elapsed_str = str(elapsed).split('.')[0]
            status_callback(f"Procesando código {i}/{total} - Tiempo transcurrido: {elapsed_str}")
            progress_callback(i / total)
            time.sleep(0.5)  # Pequeña espera entre solicitudes
    return results

def run_processing(codes, progress_callback, status_callback, done_callback):
    """Función que se ejecuta en segundo plano para procesar los códigos."""
    global processing_running, processing_paused
    processing_running = True
    processing_paused = False
    results = process_codes(codes, progress_callback, status_callback)
    if results:
        file_name = guardar_resultados(results)
        status_callback(f"Procesamiento completado. Archivo guardado: {file_name}")
    processing_running = False
    done_callback()

def main(page: ft.Page):
    page.title = "Scraper de Marathon.cl"
    page.vertical_alignment = ft.MainAxisAlignment.START

    # Elementos de la interfaz
    txt_codes = ft.TextField(
        label="Códigos (separados por espacio o salto de línea)",
        multiline=True,
        width=600,
        height=200
    )
    status_text = ft.Text(value="Estado: Esperando iniciar...")
    progress_bar = ft.ProgressBar(width=600, value=0)
    
    btn_load_file = ft.ElevatedButton("Cargar archivo txt")
    btn_start = ft.ElevatedButton("Iniciar Procesamiento")
    btn_pause = ft.ElevatedButton("Pausar Procesamiento")
    btn_pause.disabled = True  # Inhabilitado hasta que se inicie el proceso

    # Configuración del FilePicker para cargar el archivo
    file_picker = ft.FilePicker(on_result=lambda e: file_picker_result(e, txt_codes, page))
    page.overlay.append(file_picker)

    processing_thread = None

    # Funciones de actualización de UI (se llaman desde el thread)
    def update_progress(value):
        progress_bar.value = value
        page.update()
        
    def update_status(msg):
        status_text.value = msg
        page.update()
        
    def processing_done():
        btn_start.disabled = False
        btn_pause.disabled = True
        progress_bar.value = 0
        page.update()

    def on_start_click(e):
        nonlocal processing_thread
        if txt_codes.value.strip() == "":
            update_status("Por favor, ingresa o carga códigos.")
            return
        # Separa los códigos por espacios y saltos de línea
        codes = [code.strip() for code in txt_codes.value.replace("\n", " ").split() if code.strip()]
        btn_start.disabled = True
        btn_pause.disabled = False
        page.update()
        # Inicia el procesamiento en un thread en segundo plano
        processing_thread = threading.Thread(
            target=run_processing,
            args=(codes, update_progress, update_status, processing_done),
            daemon=True
        )
        processing_thread.start()

    def on_pause_click(e):
        global processing_paused
        processing_paused = True
        update_status("Pausando proceso, se guardarán los resultados parciales...")
        btn_pause.disabled = True
        page.update()

    btn_start.on_click = on_start_click
    btn_pause.on_click = on_pause_click
    btn_load_file.on_click = lambda e: file_picker.pick_files(allow_multiple=False)

    page.add(
        txt_codes,
        ft.Row([btn_load_file, btn_start, btn_pause]),
        progress_bar,
        status_text
    )

def file_picker_result(e, txt_codes, page):
    if e.files:
        file = e.files[0]
        try:
            # Se asume que el contenido viene en bytes y se decodifica a UTF-8
            content = file.content.decode("utf-8")
            txt_codes.value = content
            page.update()
        except Exception as ex:
            print("Error al leer el archivo:", ex)

ft.app(target=main)
