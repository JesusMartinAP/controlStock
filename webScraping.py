import concurrent.futures
import tkinter as tk
from tkinter import messagebox, filedialog, ttk
from datetime import datetime
import requests
from bs4 import BeautifulSoup
from openpyxl import Workbook
import webbrowser
import threading

# Variables globales
proceso_en_ejecucion = False
estado_codigos = []
total_codigos = 0
codigos_procesados = 0

# Función para obtener datos del producto (estado, precios y descuentos)
def obtener_datos_producto(codigo_padre, pais):
    url = f"https://www.marathon.store/{pais}/p/{codigo_padre}"
    response = requests.get(url)
    
    if response.status_code != 200:
        return {"estado": "Error de conexión", "precio": None, "rebajado": None, "descuento": None}
    
    soup = BeautifulSoup(response.content, 'html.parser')

    # Extracción del estado (stock)
    estado = "Agotado" if "agotado" in response.text.lower() else "Disponible"

    # Extracción del precio original
    precio_original = soup.find("div", class_="price price-promotion")
    precio_original = precio_original.text.strip() if precio_original else None

    # Extracción del precio rebajado (si existe)
    precio_rebajado = soup.find("del")
    precio_rebajado = precio_rebajado.text.strip() if precio_rebajado else None

    # Extracción del porcentaje de descuento (si existe)
    descuento = soup.find("p", class_="promotion")
    descuento = descuento.text.strip() if descuento else None

    return {
        "estado": estado,
        "precio": precio_original,
        "rebajado": precio_rebajado,
        "descuento": descuento
    }

# Procesamiento de códigos concurrentemente
def procesar_codigos(codigos, pais):
    global proceso_en_ejecucion, estado_codigos, total_codigos, codigos_procesados
    total_codigos = len(codigos)
    start_time = datetime.now()
    
    with concurrent.futures.ThreadPoolExecutor() as executor:
        futures = {executor.submit(obtener_datos_producto, codigo, pais): codigo for codigo in codigos}
        for future in concurrent.futures.as_completed(futures):
            codigo = futures[future]
            try:
                datos = future.result()
                estado_codigos.append((codigo, datos))
            except Exception as exc:
                estado_codigos.append((codigo, {"estado": f"Error: {exc}"}))
            
            codigos_procesados += 1
            elapsed_time = datetime.now() - start_time
            tiempo_transcurrido = str(elapsed_time).split('.')[0]
            info_estado.set(f"Procesando código {codigos_procesados}/{total_codigos} - Tiempo: {tiempo_transcurrido}")
            barra_progreso['value'] = (codigos_procesados / total_codigos) * 100
            root.update_idletasks()
    
    if proceso_en_ejecucion:
        guardar_resultados(pais)

# Función para guardar resultados en Excel
def guardar_resultados(pais):
    global proceso_en_ejecucion
    wb = Workbook()
    ws = wb.active
    ws.title = "Control de Precios"
    
    # Encabezados de columnas
    ws.append(["CÓDIGO", "ESTADO", "PRECIO ORIGINAL", "PRECIO REBAJADO", "DESCUENTO"])
    
    # Llenado de datos
    for codigo, datos in estado_codigos:
        ws.append([
            codigo,
            datos.get("estado"),
            datos.get("precio"),
            datos.get("rebajado"),
            datos.get("descuento")
        ])
    
    # Guardar archivo
    fecha_actual = datetime.now().strftime("%Y-%m-%d")
    nombre_archivo = f"Precios_{pais.upper()}_{fecha_actual}.xlsx"
    wb.save(nombre_archivo)
    messagebox.showinfo("Proceso completado", f"Archivo guardado como '{nombre_archivo}'")
    webbrowser.open(nombre_archivo)

# Función para iniciar procesamiento
def iniciar_procesamiento():
    global proceso_en_ejecucion
    if not proceso_en_ejecucion:
        proceso_en_ejecucion = True
        pais = pais_seleccionado.get()
        codigos = entry_codigos.get("1.0", "end").split()
        threading.Thread(target=procesar_codigos, args=(codigos, pais)).start()

# Función para detener el proceso
def detener_proceso():
    global proceso_en_ejecucion
    proceso_en_ejecucion = False
    guardar_resultados(pais_seleccionado.get())
    messagebox.showinfo("Proceso detenido", "Se ha detenido el proceso.")
    root.quit()

# Interfaz gráfica
root = tk.Tk()
root.title("Verificador de Precios y Stock")

# Entrada de códigos
tk.Label(root, text="Ingrese los códigos separados por espacio:").pack()
entry_codigos = tk.Text(root, height=10, width=50)
entry_codigos.pack()

# Botones de selección de país
tk.Label(root, text="Seleccione un país:").pack()
paises = [("Perú", "pe"), ("Ecuador", "ec"), ("Bolivia", "bo"), ("Chile", "ch")]
pais_seleccionado = tk.StringVar()
for nombre_pais, codigo_pais in paises:
    tk.Radiobutton(root, text=nombre_pais, variable=pais_seleccionado, value=codigo_pais).pack()

# Botones de control
tk.Button(root, text="Iniciar Procesamiento", command=iniciar_procesamiento).pack()
tk.Button(root, text="Detener", command=detener_proceso).pack()

# Información de estado y progreso
info_estado = tk.StringVar()
tk.Label(root, textvariable=info_estado).pack()
barra_progreso = ttk.Progressbar(root, length=200, mode='determinate')
barra_progreso.pack()

# Ejecutar interfaz
root.mainloop()
