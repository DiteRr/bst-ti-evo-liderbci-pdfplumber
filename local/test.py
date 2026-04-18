import json
import logging
import traceback
import time
import re
import os
import urllib.request
import pdfplumber
import boto3
from io import BytesIO

from textract_utils import mover_a_lotes
from extractors import detectar_tipo_tarjeta, extraer_datos, extraer_nombre_titular_pdfplumber
from logger_utils import log_event
from db_utils import insertar_eecc_nacional, insertar_eecc_internacional, obtener_conexion

logger = logging.getLogger()
logger.setLevel(logging.INFO)

def running_in_lambda():
    return "AWS_EXECUTION_ENV" in os.environ

def truncar_tablas(cursor):
    query = "TRUNCATE TABLE EECC_Nacional_T"
    cursor.execute(query)
    query = "TRUNCATE TABLE TOTAL_OPERACIONES_T"
    cursor.execute(query)
    query = "TRUNCATE TABLE EECC_Internacional_T"
    cursor.execute(query)
    query = "TRUNCATE TABLE Transacciones_T"
    cursor.execute(query)



def process_cards(tarjetas, key, bucket, codigo_producto):
    """
    Procesa las tarjetas agrupadas por pdfplumber y extrae datos nacionales e internacionales.
    Recibe un solo diccionario de tarjetas con 'texto' (string) y 'lineas' (list) de pdfplumber.
    """
    log_event("CARDS_PROCESS_START", {"file": key, "total_cards": len(tarjetas)})
    datos_nacionales, datos_internacionales = [], []
    errores_por_tarjeta = {} 

    for id_unico, info in tarjetas.items():

        nombre_extraido, tarjeta = id_unico.rsplit('_', 1)

        texto = info['texto']
        lineas = info.get('lineas', [])

        # Guardar lineas en un archivo .txt para debug
        os.makedirs("outputs", exist_ok=True)
        nombre_archivo = f"lineas_{id_unico}.txt"
        with open(nombre_archivo, "w", encoding="utf-8") as f:
            for idx, linea in enumerate(lineas, start=1):
                f.write(f"{linea}\n")
        print(f"Lineas guardadas en: {nombre_archivo}")

        log_event("CARD_PROCESS", {
            "file": key,
            "card": tarjeta,
            "is_national": info['es_nacional'],
            "is_international": info['es_internacional']
        })

        try:
            # === Tarjeta nacional ===
            if info['es_nacional']:
                datos, errores_locales = extraer_datos(
                    texto,
                    lineas,
                    "nacional",
                    s3_key=key,
                    codigo_producto=codigo_producto,
                    bucket=bucket,
                    key=key
                )
                datos['NumeroTarjeta'] = tarjeta
                datos_nacionales.append(datos)

                if errores_locales:
                    errores_por_tarjeta.setdefault(id_unico, []).extend(errores_locales)

                log_event("CARD_NATIONAL_OK", {"file": key, "card": tarjeta})

            # === Tarjeta internacional ===
            if info['es_internacional']:
                datos, errores_locales = extraer_datos(
                    texto,
                    lineas,
                    "internacional",
                    s3_key=key,
                    codigo_producto=codigo_producto,
                    bucket=bucket,
                    key=key
                )
                datos['NumeroTarjeta'] = tarjeta
                datos_internacionales.append(datos)

                if errores_locales:
                    errores_por_tarjeta.setdefault(id_unico, []).extend(errores_locales)

                log_event("CARD_INTL_OK", {"file": key, "card": tarjeta})

        except Exception as e:
            log_event("CARD_ERROR", {"file": key, "card": tarjeta, "error": str(e)})
            errores_por_tarjeta.setdefault(id_unico, []).append({
                "codigo": "CARD_ERROR",
                "mensaje": str(e)
            })
            continue

    log_event("CARDS_PROCESS_END", {
        "file": key,
        "national_count": len(datos_nacionales),
        "intl_count": len(datos_internacionales),
        "cards_with_errors": list(errores_por_tarjeta.keys())
    })

    return datos_nacionales, datos_internacionales, errores_por_tarjeta


def group_pages_by_card_pdfplumber(pdf_source, key='test', is_s3=False, bucket_name=None):
    """
    Agrupa las páginas de un PDF por Nombre + Tarjeta usando pdfplumber.
    """
    print("GROUP_START", {"file": key, "source": "pdfplumber", "is_s3": is_s3})
    tarjetas = {}
    total_pages = 0

    try:
        # Obtener el PDF según la fuente
        if is_s3:
            if not bucket_name:
                raise ValueError("bucket_name es requerido cuando is_s3=True")
            
            s3_client = boto3.client('s3')
            pdf_bytes = BytesIO()
            s3_client.download_fileobj(bucket_name, pdf_source, pdf_bytes)
            pdf_bytes.seek(0)
            pdf_file = pdf_bytes
        else:
            pdf_file = pdf_source
        
        with pdfplumber.open(pdf_file) as pdf:
            total_pages = len(pdf.pages)
            
            for num_pagina, page in enumerate(pdf.pages, start=1):
                texto_pagina = page.extract_text()
                
                if not texto_pagina:
                    print("NO_TEXT_EXTRACTED", {"page": num_pagina, "file": key})
                    continue

                lineas = texto_pagina.split('\n')
                
                # 1. Buscar número de tarjeta
                m = re.search(r"Número tarjeta\s+X+(\d{4})", texto_pagina, re.IGNORECASE) or \
                    re.search(r"X{4,}(\d{4})", texto_pagina)

                if not m:
                    print("NO_CARD_NUMBER", {"page": num_pagina, "file": key})
                    continue

                nro_tarjeta = m.group(1)

                # 2. Extraer nombre usando pdfplumber
                nombre_titular, _ = extraer_nombre_titular_pdfplumber(lineas)
                nombre_key = nombre_titular.strip().upper() if nombre_titular else "DESCONOCIDO"

                # 3. Crear Llave Única (Nombre + Tarjeta)
                id_unico = f"{nombre_key}_{nro_tarjeta}"
                
                es_nacional, es_internacional = detectar_tipo_tarjeta(texto_pagina)
                
                # Inicializar estructura con id_unico
                if id_unico not in tarjetas:
                    tarjetas[id_unico] = {
                        'texto': '',
                        'lineas': [],
                        'es_nacional': False,
                        'es_internacional': False,
                        'paginas': [],
                        'nombre': nombre_titular,
                        'ultimos_4': nro_tarjeta
                    }
                
                # Acumular datos
                tarjetas[id_unico]['texto'] += texto_pagina + "\n"
                tarjetas[id_unico]['lineas'].extend(lineas)
                tarjetas[id_unico]['es_nacional'] |= es_nacional
                tarjetas[id_unico]['es_internacional'] |= es_internacional
                tarjetas[id_unico]['paginas'].append(num_pagina)

                print("PAGE_CARD_INFO", {
                    "page": num_pagina,
                    "id": id_unico,
                    "is_national": es_nacional,
                    "file": key
                })

    except Exception as e:
        print("ERROR_PROCESSING_PDF", {"file": key, "error": str(e)})
        raise
    finally:
        if is_s3 and 'pdf_bytes' in locals():
            pdf_bytes.close()

    print("GROUP_END", {
        "file": key,
        "total_pages": total_pages,
        "unique_entities": len(tarjetas)
    })
    
    return tarjetas


def insert_results(datos_nacionales, datos_internacionales, bucket, key):
    log_event("DB_INSERT_START", {"file": key})

    # === Inserta nacionales ===
    if datos_nacionales:
        try:
            insertar_eecc_nacional(datos_nacionales)
            log_event("DB_INSERT_NATIONAL_OK", {
                "file": key,
                "rows": len(datos_nacionales)
            })
        except Exception as e:
            log_event("DB_INSERT_NATIONAL_ERROR", {
                "file": key,
                "error": str(e)
            })
            raise

    else:
        log_event("DB_INSERT_NATIONAL_EMPTY", {"file": key})

    # === Inserta internacionales ===
    if datos_internacionales:
        try:
            insertar_eecc_internacional(datos_internacionales)
            log_event("DB_INSERT_INTL_OK", {
                "file": key,
                "rows": len(datos_internacionales)
            })
        except Exception as e:
            log_event("DB_INSERT_INTL_ERROR", {
                "file": key,
                "error": str(e)
            })
            raise

    else:
        log_event("DB_INSERT_INTL_EMPTY", {"file": key})

    log_event("DB_INSERT_END", {"file": key})

def test_internet():
    try:
        urllib.request.urlopen("https://www.google.com", timeout=5)
        print("Tiene salida a Internet")
    except Exception as e:
        print("NO tiene salida a Internet:", e)



bucket = "bst-ti-evo-liderbci"
carpeta_raiz = "C:\\Users\\Diterod\\Desktop\\pdfplumber_files"
codigo_producto = 0

resultados_totales = []
total_nacionales = 0
total_internacionales = 0
archivos_con_error = []

conn = obtener_conexion()
cursor = conn.cursor()
truncar_tablas(cursor)
conn.commit()
cursor.close()
conn.close()

# Recorrer: pdfplumber_files / subcarpeta / (Impresion|Publicacion|Tasas) / *.pdf
for subcarpeta in os.listdir(carpeta_raiz):
    ruta_subcarpeta = os.path.join(carpeta_raiz, subcarpeta)
    if not os.path.isdir(ruta_subcarpeta):
        continue

    for tipo_carpeta in os.listdir(ruta_subcarpeta):
        ruta_tipo = os.path.join(ruta_subcarpeta, tipo_carpeta)
        if not os.path.isdir(ruta_tipo):
            continue

        archivos_pdf = [f for f in os.listdir(ruta_tipo) if f.lower().endswith('.pdf')]
        print(f"\n{'='*60}")
        print(f"Carpeta: {subcarpeta}/{tipo_carpeta} -> {len(archivos_pdf)} archivos PDF")
        print(f"{'='*60}")

        for archivo in archivos_pdf: 
            ruta_archivo = os.path.join(ruta_tipo, archivo)
            key = ruta_archivo
            resultado = {"file": key, "status": "OK", "error": None}
            process_start = time.time()

            try:
                log_event("START_PROCESS", {"file": key, "bucket": bucket})

                tarjetas = group_pages_by_card_pdfplumber(key, key=key, is_s3=False, bucket_name=bucket)
                datos_nacionales, datos_internacionales, errores_por_tarjeta = process_cards(tarjetas, key, bucket, codigo_producto)

                insert_results(datos_nacionales, datos_internacionales, bucket, key)

                resultado["tarjetasDetectadas"] = list(tarjetas.keys())
                resultado["registrosNacionales"] = len(datos_nacionales)
                resultado["registrosInternacionales"] = len(datos_internacionales)
                resultado["erroresPorTarjeta"] = errores_por_tarjeta
                resultado["duration_sec"] = round(time.time() - process_start, 2)

                total_nacionales += len(datos_nacionales)
                total_internacionales += len(datos_internacionales)

                log_event("PROCESS_SUCCESS", resultado)
                print(f"  OK: {archivo} -> Nac: {len(datos_nacionales)}, Int: {len(datos_internacionales)}, Tiempo: {resultado['duration_sec']}s")

            except Exception as e:
                resultado["status"] = "ERROR"
                resultado["error"] = str(e)
                resultado["duration_sec"] = round(time.time() - process_start, 2)
                log_event("PROCESS_ERROR", {
                    "file": key,
                    "error": str(e),
                    "trace": traceback.format_exc(),
                    "duration_sec": resultado["duration_sec"]
                })
                resultado["tarjetasDetectadas"] = []
                resultado["registrosNacionales"] = 0
                resultado["registrosInternacionales"] = 0
                archivos_con_error.append({"archivo": key, "error": str(e)})
                print(f"  ERROR: {archivo} -> {str(e)[:100]}")

            resultados_totales.append(resultado)
            log_event("END_PROCESS", resultado)

            # === Resumen final ===
            print(f"\n{'='*60}")
            print(f"RESUMEN FINAL")
            print(f"{'='*60}")
            print(f"Archivos procesados: {len(resultados_totales)}")
            print(f"Registros nacionales totales: {total_nacionales}")
            print(f"Registros internacionales totales: {total_internacionales}")
            print(f"Archivos con error: {len(archivos_con_error)}")
            for err in archivos_con_error:
                print(f"  - {err['archivo']}: {err['error'][:100]}")
