import concurrent.futures
import time
import re
from datetime import datetime
import os
import flet as ft
from openpyxl import Workbook
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC

# Variables globales
proceso_en_ejecucion = False
estado_codigos = []
total_codigos = 0
codigos_procesados = 0
start_time = None

def obtener_estado_precio_imagenes_selenium(codigo_padre, pais):
    if not codigo_padre:
        return "Código vacío", "N/A", 0, "N/A", "N/A", 0, "N/A", "N/A"

    if len(codigo_padre) == 8:
        codigo_padre = codigo_padre + "001"

    # Configuración de Selenium (Chrome en modo headless)
    chrome_options = Options()
    chrome_options.add_argument("--headless")
    chrome_options.add_argument("--no-sandbox")
    chrome_options.add_argument("--disable-dev-shm-usage")
    driver = webdriver.Chrome(options=chrome_options)

    try:
        # Medir tiempo de procesamiento para este producto
        start_producto = time.time()

        # --- Extracción del estado del producto ---
        url_estado = f'https://www.marathon.store/{pais}/view/ProductVariantSelectorComponentController?componentUid=VariantSelector&currentProductCode={codigo_padre}'
        driver.get(url_estado)
        try:
            WebDriverWait(driver, 15).until(
                EC.presence_of_all_elements_located((By.CSS_SELECTOR, "li[data-url]"))
            )
        except Exception as e:
            print(f"Timeout en cargar estado para {codigo_padre}: {e}")

        lis = driver.find_elements(By.CSS_SELECTOR, "li[data-url]")
        estado = "Agotado"
        for li in lis:
            data_url = li.get_attribute("data-url")
            if codigo_padre in data_url:
                if li.get_attribute("data-has-stock") == "true" or li.get_attribute("data-selected") == "true":
                    estado = "Disponible"
                    break

        # --- Extracción de detalles del producto ---
        url_precio = f'https://www.marathon.store/{pais}/p/{codigo_padre}'
        driver.get(url_precio)

        # Precio actual usando XPath especificado
        precio = "N/A"
        try:
            price_element = WebDriverWait(driver, 15).until(
                EC.visibility_of_element_located((By.XPATH, "/html/body/main/div[4]/div[1]/div[1]/div[1]/div[3]/div[2]/div[2]"))
            )
            precio = price_element.text.strip()
        except Exception as e:
            print(f"No se encontró el precio para {codigo_padre} con el XPath especificado: {e}")

        # Precio original (full price) usando XPath especificado
        precio_original = "N/A"
        try:
            precio_original_element = WebDriverWait(driver, 10).until(
                EC.visibility_of_element_located((By.XPATH, "/html/body/main/div[4]/div[1]/div[1]/div[1]/div[3]/div[2]/div[1]/del"))
            )
            precio_original = precio_original_element.text.strip()
        except Exception as e:
            print(f"No se encontró precio original para {codigo_padre} con el XPath especificado: {e}")

        # Descuento extraído usando XPath especificado
        descuento = "N/A"
        try:
            descuento_element = WebDriverWait(driver, 10).until(
                EC.visibility_of_element_located((By.XPATH, "/html/body/main/div[4]/div[1]/div[1]/div[1]/div[3]/div[1]/p"))
            )
            texto_descuento = descuento_element.text.strip()
            match = re.search(r'(\d+%)', texto_descuento)
            descuento = match.group(1) if match else texto_descuento.replace("Descuento del", "").strip()
        except Exception as e:
            print(f"No se encontró descuento para {codigo_padre} con el XPath especificado: {e}")

        # Imágenes: se extraen las URLs desde el atributo data-src de las imágenes de la galería
        try:
            galeria_imagenes = WebDriverWait(driver, 10).until(
                EC.presence_of_element_located((By.CSS_SELECTOR, "div.desktop-image-gallery"))
            )
            imagenes_elements = galeria_imagenes.find_elements(By.TAG_NAME, "img")
            imagenes = [img.get_attribute("data-src") for img in imagenes_elements if img.get_attribute("data-src")]
        except Exception as e:
            print(f"No se encontró galería de imágenes para {codigo_padre}: {e}")
            imagenes = []

        end_producto = time.time()
        tiempo_total = round(end_producto - start_producto, 2)

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
        print(f"Error en {codigo_padre}: {e}")
        return (f"Error: {e}", "N/A", 0, "N/A", "N/A", 0, "N/A", "N/A")
    finally:
        driver.quit()

def actualizar_progreso(page):
    global codigos_procesados, total_codigos, start_time
    tiempo_transcurrido = datetime.now() - start_time
    horas, resto = divmod(tiempo_transcurrido.seconds, 3600)
    minutos, segundos = divmod(resto, 60)
    progreso = (codigos_procesados / total_codigos) * 100

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
        futures = {executor.submit(obtener_estado_precio_imagenes_selenium, codigo, pais): codigo for codigo in codigos}
        for future in concurrent.futures.as_completed(futures):
            if not proceso_en_ejecucion:
                for fut in futures:
                    if not fut.done():
                        fut.cancel()
                break
            codigo = futures[future]
            try:
                resultado = future.result()
                estado_codigos.append((codigo, *resultado))
            except Exception as exc:
                estado_codigos.append((codigo, f"Error: {exc}", "N/A", 0, "N/A", 0, "N/A", "N/A"))
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
    page.title = "Scraper Marathon con Selenium"
    page.theme_mode = ft.ThemeMode.LIGHT
    page.window_width = 800
    page.window_height = 600
    page.scroll = ft.ScrollMode.AUTO
    
    codigos_control = ft.TextField(
        multiline=True, 
        height=200,
        min_lines=10,
        max_lines=10,
        hint_text="Ingrese códigos separados por espacio o nueva línea (o cargue un archivo)",
        width=700
    )
    
    pais_selector = ft.Dropdown(
        options=[
            ft.dropdown.Option("pe", "Perú"),
            ft.dropdown.Option("bo", "Bolivia"),
            ft.dropdown.Option("ec", "Ecuador")
        ],
        value=None,
        label="País",
        width=200
    )
    
    page.progress_bar = ft.ProgressBar(width=700, visible=False)
    page.contador = ft.Text()
    page.tiempo = ft.Text()
    
    def on_file_picker_result(e: ft.FilePickerResultEvent):
        if e.files:
            try:
                file = e.files[0]
                with open(file.path, "r", encoding="utf-8") as f:
                    contenido = f.read()
                codigos_control.value = contenido
                page.update()
            except Exception as ex:
                page.add(ft.Text(f"Error leyendo el archivo: {ex}", color=ft.colors.RED))
                
    file_picker = ft.FilePicker(on_result=on_file_picker_result)
    page.overlay.append(file_picker)
    
    btn_cargar_archivo = ft.ElevatedButton("Cargar archivo", on_click=lambda e: file_picker.pick_files())
    
    btn_iniciar = ft.ElevatedButton("Iniciar scraping", scale=1.2)
    btn_detener = ft.OutlinedButton("Detener proceso")
    
    page.add(
        ft.Column([
            ft.Row([pais_selector], alignment=ft.MainAxisAlignment.CENTER),
            ft.Row([codigos_control, btn_cargar_archivo], alignment=ft.MainAxisAlignment.CENTER),
            ft.Row([btn_iniciar, btn_detener], alignment=ft.MainAxisAlignment.CENTER),
            page.progress_bar,
            page.contador,
            page.tiempo
        ])
    )
    
    def iniciar_scraping(e):
        global proceso_en_ejecucion
        if not pais_selector.value:
            page.add(ft.Text("Por favor, seleccione un país.", color=ft.colors.RED))
            return
        if not proceso_en_ejecucion:
            proceso_en_ejecucion = True
            page.progress_bar.visible = True
            codigos = codigos_control.value.strip().split()
            procesar_codigos(page, codigos, pais_selector.value)
    
    def detener_scraping(e):
        global proceso_en_ejecucion
        proceso_en_ejecucion = False
        page.add(ft.Text("Proceso detenido por el usuario", color=ft.colors.RED))
    
    btn_iniciar.on_click = iniciar_scraping
    btn_detener.on_click = detener_scraping

ft.app(target=main)
