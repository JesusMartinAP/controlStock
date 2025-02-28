import flet as ft
import requests
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
from openpyxl import Workbook
from bs4 import BeautifulSoup
import time
import threading
import os
import re

# =====================================
# Variables globales
processing_paused = False
processing_running = False
last_excel_file = None

# Para ir almacenando resultados
results_data = []
start_time = None
total_codes = 0
processed_codes = 0

# =====================================
# Función para extraer datos con requests y BeautifulSoup
def extraer_datos(codigo, pais):
    """
    Lógica de extracción de datos sin Selenium.
    Ajusta los selectores y URLs a la realidad de la página.
    """
    # Completamos el código si tiene 8 dígitos
    if len(codigo) == 8:
        codigo += "001"
    
    # Construimos la URL
    # Por ejemplo: https://www.marathon.store/pe/p/ + codigo
    base_url = f"https://www.marathon.store/{pais}/p/{codigo}"
    inicio_tiempo = time.time()

    try:
        response = requests.get(base_url, timeout=10, allow_redirects=True)
        tiempo_respuesta = round(time.time() - inicio_tiempo, 2)
        if response.status_code != 200:
            # Podríamos devolver un estado de error
            return (
                codigo,
                "ERROR WEB",      # Control Stock
                "N/A",            # Precio
                0,                # Cant. Img
                "N/A",            # Enlaces Imágenes
                base_url,         # URL
                tiempo_respuesta, # Tiempo
                "N/A",            # Descuento
                "N/A"             # Full Price
            )
        
        soup = BeautifulSoup(response.text, "html.parser")
        
        # 1. Determinar "Control Stock"
        #    Si hay algún indicio de "agotado" o "no disponible" en la página:
        #    Ajustar selectores o condiciones según la estructura real
        stock_status = "AGOTADO"
        # Ejemplo: si existe un texto "Disponible" en la página
        if "disponible" in soup.text.lower():
            stock_status = "DISPONIBLE"

        # 2. Precio actual
        #    Ajustar selectores a la realidad
        precio_elem = soup.select_one("div.price > span.current-price")
        precio = precio_elem.get_text(strip=True) if precio_elem else "N/A"

        # 3. Full Price (precio original tachado)
        full_price_elem = soup.select_one("div.price del.original-price")
        full_price = full_price_elem.get_text(strip=True) if full_price_elem else "N/A"

        # 4. Descuento (buscamos un % en la página)
        descuento_elem = soup.select_one("div.discount-label")
        descuento = "N/A"
        if descuento_elem:
            desc_text = descuento_elem.get_text(strip=True)
            match = re.search(r"(\d+%)", desc_text)
            if match:
                descuento = match.group(1)
            else:
                descuento = desc_text

        # 5. Cantidad de imágenes y enlaces
        imagenes = soup.select("div.desktop-image-gallery img")
        enlaces_img = []
        for img in imagenes:
            src = img.get("src") or img.get("data-src")
            if src:
                enlaces_img.append(src)
        cant_img = len(enlaces_img)
        enlaces_str = ", ".join(enlaces_img)

        return (
            codigo,
            stock_status,
            precio,
            cant_img,
            enlaces_str,
            base_url,
            tiempo_respuesta,
            descuento,
            full_price
        )
    except requests.exceptions.RequestException as e:
        return (
            codigo,
            "ERROR DE RED",
            "N/A",
            0,
            "N/A",
            base_url,
            0,
            "N/A",
            "N/A"
        )

# =====================================
# Procesamiento concurrente
def process_codes(codes, pais, progress_callback, status_callback, done_callback):
    global processing_paused, processing_running
    global results_data, total_codes, processed_codes, start_time

    processing_running = True
    processing_paused = False
    results_data = []
    total_codes = len(codes)
    processed_codes = 0
    start_time = datetime.now()

    # Ajusta el número de hilos
    max_workers = 5

    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = {executor.submit(extraer_datos, code, pais): code for code in codes}
        for future in as_completed(futures):
            # Si se pausó, salimos
            if processing_paused:
                status_callback("PROCESO PAUSADO. GUARDANDO RESULTADOS PARCIALES...")
                break

            result = future.result()
            results_data.append(result)
            processed_codes += 1

            # Llamamos a las funciones de callback para actualizar la UI
            progress_callback(processed_codes / total_codes)
            elapsed = datetime.now() - start_time
            h, r = divmod(elapsed.seconds, 3600)
            m, s = divmod(r, 60)
            status_callback(f"Procesando {processed_codes}/{total_codes} - Tiempo {h:02d}:{m:02d}:{s:02d}")

            time.sleep(0.2)  # Pequeña pausa para no saturar el sitio

    # Guardamos resultados (parciales o totales)
    file_name = guardar_resultados()
    if processing_paused:
        status_callback(f"RESULTADOS PARCIALES GUARDADOS: {file_name}")
    else:
        status_callback(f"PROCESAMIENTO COMPLETADO. ARCHIVO: {file_name}")

    processing_running = False
    done_callback()

# =====================================
# Guardar resultados en Excel
def guardar_resultados():
    global results_data, last_excel_file
    wb = Workbook()
    ws = wb.active
    ws.title = "RESULTADOS"

    headers = [
        "CÓDIGO", "CONTROL STOCK", "PRECIO", "CANT. IMG",
        "ENLACES IMÁGENES", "URL", "TIEMPO (s)", "DESCUENTO", "FULL PRICE"
    ]
    for col, header in enumerate(headers, start=1):
        ws.cell(row=1, column=col, value=header)

    for i, row in enumerate(results_data, start=2):
        for j, value in enumerate(row, start=1):
            ws.cell(row=i, column=j, value=value)

    fecha_hora = datetime.now().strftime("%Y%m%d_%H%M%S")
    nombre_archivo = f"RESULTADOS_{fecha_hora}.xlsx"
    wb.save(nombre_archivo)
    last_excel_file = nombre_archivo
    return nombre_archivo

# =====================================
# Interfaz Flet
def main(page: ft.Page):
    page.title = "Scraper Marathon Store (Requests + BS4)"
    page.bgcolor = ft.colors.WHITE
    page.vertical_alignment = ft.MainAxisAlignment.START
    page.scroll = ft.ScrollMode.AUTO

    # Variables locales para UI
    status_text = ft.Text(value="ESTADO: Esperando inicio...", color=ft.colors.BLACK)
    progress_bar = ft.ProgressBar(width=600, value=0)
    txt_codes = ft.TextField(
        label="Códigos (separados por espacio o salto de línea)",
        multiline=True,
        width=600,
        height=150,
        border_color=ft.colors.GREY,
        border_width=2
    )

    # Selector de país
    dd_pais = ft.Dropdown(
        label="País",
        options=[
            ft.dropdown.Option(key="pe", text="Perú"),
            ft.dropdown.Option(key="bo", text="Bolivia"),
            ft.dropdown.Option(key="ec", text="Ecuador")
        ],
        width=200
    )

    # FilePicker
    file_picker = ft.FilePicker(on_result=lambda e: on_file_picked(e, txt_codes, page))
    page.overlay.append(file_picker)

    # Botones
    btn_load_file = ft.ElevatedButton(
        text="Cargar archivo TXT",
        on_click=lambda _: file_picker.pick_files(allow_multiple=False),
        bgcolor=ft.colors.BLUE, color=ft.colors.WHITE
    )
    btn_start = ft.ElevatedButton(
        text="Iniciar",
        bgcolor=ft.colors.GREEN, color=ft.colors.WHITE
    )
    btn_pause = ft.ElevatedButton(
        text="Pausar",
        bgcolor=ft.colors.RED, color=ft.colors.WHITE
    )
    btn_open_excel = ft.ElevatedButton(
        text="Abrir Excel",
        bgcolor=ft.colors.BLUE, color=ft.colors.WHITE
    )

    btn_pause.disabled = True
    btn_open_excel.disabled = True

    # Callbacks
    def update_progress(value: float):
        progress_bar.value = value
        page.update()

    def update_status(msg: str):
        status_text.value = msg
        page.update()

    def processing_done():
        btn_start.disabled = False
        btn_pause.disabled = True
        progress_bar.value = 0
        page.update()

    def on_start_click(e):
        # Validar que se haya seleccionado un país
        if not dd_pais.value:
            update_status("Por favor, selecciona un país.")
            return
        # Validar que se hayan ingresado códigos
        codes_str = txt_codes.value.strip()
        if not codes_str:
            update_status("Por favor, ingresa o carga algunos códigos.")
            return

        codes = [c.strip() for c in codes_str.replace("\n", " ").split() if c.strip()]

        # Iniciar proceso en segundo plano
        btn_start.disabled = True
        btn_pause.disabled = False
        btn_open_excel.disabled = True
        update_status("Iniciando procesamiento...")
        page.update()

        threading.Thread(
            target=process_codes,
            args=(codes, dd_pais.value, update_progress, update_status, processing_done),
            daemon=True
        ).start()

    def on_pause_click(e):
        global processing_paused
        processing_paused = True
        update_status("Pausando el proceso...")
        btn_pause.disabled = True
        btn_open_excel.disabled = False  # Ya tenemos un Excel parcial
        page.update()

    def on_open_excel_click(e):
        global last_excel_file
        if last_excel_file and os.path.exists(last_excel_file):
            try:
                os.startfile(last_excel_file)
            except Exception as ex:
                update_status(f"Error al abrir el archivo: {ex}")
        else:
            update_status("No se ha generado ningún archivo Excel todavía.")

    btn_start.on_click = on_start_click
    btn_pause.on_click = on_pause_click
    btn_open_excel.on_click = on_open_excel_click

    # Disposición en la página
    page.add(
        ft.Column([
            ft.Row([dd_pais]),
            txt_codes,
            ft.Row([btn_load_file, btn_start, btn_pause, btn_open_excel]),
            progress_bar,
            status_text
        ], spacing=10)
    )

def on_file_picked(e: ft.FilePickerResultEvent, txt_codes: ft.TextField, page: ft.Page):
    if e.files:
        file = e.files[0]
        try:
            content = open(file.path, "r", encoding="utf-8").read()
            txt_codes.value = content
            page.update()
        except Exception as ex:
            page.add(ft.Text(f"Error al leer el archivo: {ex}", color=ft.colors.RED))
            page.update()

# Ejecutar la app
ft.app(target=main)
