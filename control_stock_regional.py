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

    # Modificación del código si tiene solo 8 dígitos
    if len(codigo_padre) == 8:
        codigo_padre = codigo_padre + "001"

    try:
        # Retraso más generoso para evitar bloqueos
        time.sleep(2.0)

        # Construir URLs con el código correcto del país (pe, bo, ec)
        url_estado = f'https://www.marathon.store/{pais}/view/ProductVariantSelectorComponentController?componentUid=VariantSelector&currentProductCode={codigo_padre}'
        url_precio = f'https://www.marathon.store/{pais}/p/{codigo_padre}'

        # Obtener estado del producto
        inicio_tiempo_estado = time.time()
        response_estado = session.get(url_estado, timeout=15)
        
        # Manejar errores HTTP
        if response_estado.status_code != 200:
            raise requests.exceptions.HTTPError(f"Error HTTP {response_estado.status_code}")
        
        soup_estado = BeautifulSoup(response_estado.content, 'html.parser')
        lis = soup_estado.find_all('li', attrs={'data-url': lambda x: x and str(codigo_padre) in x})
        
        estado = "Agotado"
        for li in lis:
            if li.get('data-has-stock') == "true" or li.get('data-selected') == "true":
                estado = "Disponible"
                break

        # Obtener precio y descuento
        inicio_tiempo_precio = time.time()
        response_precio = session.get(url_precio, timeout=15)
        
        if response_precio.status_code != 200:
            raise requests.exceptions.HTTPError(f"Error HTTP {response_precio.status_code}")

        soup_precio = BeautifulSoup(response_precio.content, 'html.parser')
        
        # Extraer precios
        precio_element = soup_precio.select_one('div.desktop-price, div.price, [itemprop="price"]')
        precio = ''.join(filter(lambda x: x.isdigit() or x in [',', '.'], precio_element.text.strip())) if precio_element else "N/A"
        
        # Extraer precio con descuento
        precio_descuento_element = soup_precio.find('del')
        precio_descuento = precio_descuento_element.text.strip() if precio_descuento_element else "N/A"
        
        # Extraer descuento
        descuento_element = soup_precio.find('p', class_='promotion')
        descuento = descuento_element.text.replace("Descuento del", "").strip() if descuento_element else "N/A"
        
        # Extraer imágenes
        galeria_imagenes = soup_precio.find('div', class_='desktop-image-gallery')
        imagenes = [img['data-src'] for img in galeria_imagenes.find_all('img', attrs={'data-src': True})] if galeria_imagenes else []
        
        return (
            estado,
            precio,
            len(imagenes),
            ', '.join(imagenes),
            url_precio,
            (time.time() - inicio_tiempo_estado) + (time.time() - inicio_tiempo_precio),
            descuento,
            precio_descuento
        )

    except Exception as e:
        print(f"Error procesando código {codigo_padre}: {str(e)}")
        return f"Error: {str(e)}", "N/A", 0, "N/A", "N/A", 0, "N/A", "N/A"

# ... (El resto del código de la interfaz y funciones se mantiene igual)

def main(page: ft.Page):
    page.title = "Control Stock Web"
    page.vertical_alignment = ft.MainAxisAlignment.CENTER
    page.horizontal_alignment = ft.CrossAxisAlignment.CENTER

    # Selector de países mejorado
    pais_selector = ft.Dropdown(
        label="País",
        options=[
            ft.dropdown.Option("Perú", "pe"),
            ft.dropdown.Option("Bolivia", "bo"),
            ft.dropdown.Option("Ecuador", "ec")
        ],
        value="pe",  # Valor por defecto
        width=200,
        autofocus=True
    )

    # ... (El resto del código de la interfaz se mantiene igual)

ft.app(target=main)