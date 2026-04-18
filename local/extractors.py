import re
from helpers import limpiar_valor, limpiar_valor_float, float_sin_punto
from logger_utils import log_event

def es_nombre_probable(linea):
    palabras = linea.split()

    # Corrección OCR final '0' → 'O'
    if palabras and palabras[-1] == "0":
        palabras[-1] = "O"
        linea = " ".join(palabras)

    # No debe contener números
    if re.search(r'\d', linea):
        return False

    palabras = linea.split()

    PROHIBIDAS = {
        "CARTA", "CORREOS", "CUPO", "TOTAL", "RESUMEN",
        "MONTO", "INFORMACIÓN", "PAGO", "CARGOS", "COM",
        "ADMINISTRACION", "MANTENCION", "IMPUESTOS"
    }

    CONECTORES = {"DE", "DEL", "LA", "LAS", "LOS", "Y"}

    # Palabras reales (sin conectores)
    palabras_validas = [p for p in palabras if p.upper() not in CONECTORES]

    # Debe tener entre 2 y 4 palabras reales
    if not (2 <= len(palabras_validas) <= 7):
        return False

    # No debe contener palabras prohibidas
    if any(p.upper() in PROHIBIDAS for p in palabras):
        return False

    # Evitar más de una palabra de una sola letra (excepto conectores)
    if sum(1 for p in palabras_validas if len(p) == 1) > 1:
        return False

    return True


def es_direccion(linea):
    patrones = [
        r'\d',
        r'\bSN\b',
        r'CALLE|AVDA|AVENIDA|PASAJE|PJE|PSJ|CAMINO|LOTE|KM|POBLACION|PBLACION',
        r'VOLCAN|CERRO|RUTA|PARCELA|FUNDO|SECTOR|VILLA|CONDOMINIO'
    ]
    return bool(re.search('|'.join(patrones), linea.upper()))

def normalizar_lineas(texto):
    """
    Convierte el texto en líneas y corrige errores típicos de OCR:
    - Reemplaza tokens aislados '0', '0.' o '0,' por 'O', 'O.' y 'O,' respectivamente.
    - Devuelve la lista de líneas normalizadas (sin líneas vacías).
    """
    lineas = [l.strip() for l in texto.splitlines() if l.strip()]
    nuevas = []
    for linea in lineas:
        tokens = linea.split()
        for i, t in enumerate(tokens):
            # casos exactos: '0', '0.' , '0,'
            if t == '0':
                tokens[i] = 'O'
            else:
                m = re.fullmatch(r'0([.,])', t)
                if m:
                    tokens[i] = 'O' + m.group(1)
        nuevas.append(' '.join(tokens))
    return nuevas

def normalizar_linea(linea):
    """
    Corrige errores típicos de OCR:
    - Reemplaza tokens aislados '0', '0.' o '0,' por 'O', 'O.' y 'O,' respectivamente.
    - Devuelve la línea normalizada.
    """
    tokens = linea.split()

    for i, t in enumerate(tokens):
        if t == '0':
            tokens[i] = 'O'
        else:
            m = re.fullmatch(r'0([.,])', t)
            if m:
                tokens[i] = 'O' + m.group(1)

    return ' '.join(tokens).upper()

def extraer_nombre_titular(texto):
    lineas = [l.strip() for l in texto.splitlines() if l.strip()]
    
    for i in range(len(lineas) - 1):
        linea = lineas[i]
        siguiente = lineas[i + 1]

        if es_nombre_probable(linea) and es_direccion(siguiente):
            return normalizar_linea(linea), siguiente
    
    return "", ""

def extraer_nombre_titular_pdfplumber(lineas):
    """
    Extrae nombre y dirección del titular desde líneas de pdfplumber.
    Filtra líneas CID, encabezados y caracteres especiales antes de buscar.
    """
    lineas_filtradas = []
    for linea in lineas:
        l = linea.strip()
        if not l:
            continue
        # Filtrar líneas CID (caracteres de fuente de pdfplumber)
        if re.search(r'\(cid:\d+\)', l):
            linea_sin_cid = re.sub(r'\(cid:\d+\)', '', l).strip()
            if len(linea_sin_cid) == 0:
                continue
        # Filtrar encabezados del documento
        if "ESTADO DE CUENTA" in l.upper():
            continue
        # Filtrar líneas de página
        if re.search(r'Página\s+\d+\s+de\s+\d+', l, re.IGNORECASE):
            continue
        # Filtrar líneas que comienzan con (cid: o tienen BOM characters
        if l.startswith('(cid:') or l == '\ufeff' or l.strip('\ufeff').strip() == '':
            continue
        # Filtrar "CARTA CORREOS"
        if l.upper().strip() == "CARTA CORREOS":
            continue
        # Filtrar líneas con solo caracteres BOM/especiales + texto parcial (como "(cid:8)﻿﻿... Fecha...")
        if re.match(r'^\(cid:\d+\)', l):
            continue
        lineas_filtradas.append(l)

    for i in range(len(lineas_filtradas) - 1):
        linea = lineas_filtradas[i]
        siguiente = lineas_filtradas[i + 1]

        if es_nombre_probable(linea) and es_direccion(siguiente):
            return normalizar_linea(linea), siguiente

    return "", ""


def extraer_direccion(texto):
    lineas = [l.strip() for l in texto.splitlines() if l.strip()]
    #lineas = normalizar_lineas(texto)
    for linea in lineas:
        # Línea que contenga letras y números
        if es_direccion(linea):
            return linea
    return ""

def extraer_datos_montos_nacionales(texto, datos):
    def buscar_valor(patron):
        match = re.search(patron, texto, re.IGNORECASE)
        if match:
            valor = match.group(1)
            valor = valor.replace('.', '').replace(',', '.').strip()
            try:
                return float(valor)
            except ValueError:
                return None
        return None

    datos["MontoTotalFacturado"] = limpiar_valor_float(buscar_valor(r"Monto\s+Total\s+Facturado\s*\$\s*(-?[\d\.,]+)"))
    datos["MontoMinimoAPagar"] = limpiar_valor_float(buscar_valor(r"Monto\s+M[ií]nimo\s+a\s+Pagar\*?\s*\$\s*(-?[\d\.,]+)"))
    datos["CostoMonetarioPrepago"] = limpiar_valor_float(buscar_valor(r"Costo\s+Monetario\s+Prepago\s*\$\s*(-?[\d\.,]+)"))

    return datos

def extraer_texto_liberacion(texto):
    #La liberación del monto mínimo a pagar
    match1 = re.search(
        r'\*\s*La liberación del monto mínimo a pagar[^\n]*',
        texto, re.IGNORECASE
    )
    if not match1:
        return None
    linea1 = match1.group(0).strip()

    match2 = re.search(
        r'La vigencia será desde \d{2}/\d{2}/\d{4} hasta \d{2}/\d{2}/\d{4}\.?',
        texto, re.IGNORECASE
    )
    if match2:
        linea2 = match2.group(0).strip()
        return f"{linea1} {linea2}"
    return linea1

def extraer_vencimientos(texto):
    vencimiento_actual = 0.0
    meses = [0.0, 0.0, 0.0, 0.0]

    # Buscar "Monto $ XXX.XXX" para el Vencimiento Actual
    monto_match = re.search(r'Monto\s*\$\s*(-?[\d\.]+)', texto)
    if monto_match:
        try:
            vencimiento_actual = float(monto_match.group(1).replace('.', '').replace(',', '.'))
        except:
            vencimiento_actual = 0.0

    # Buscar los valores de Mes1 a Mes4
    for i in range(1, 5):
        pattern = rf'Mes{i}\s*\$\s*([\d\.]+)'
        match = re.search(pattern, texto)
        if match:
            try:
                meses[i-1] = float(match.group(1).replace('.', '').replace(',', '.'))
            except:
                meses[i-1] = 0.0

    return {
        "VencimientoActual": vencimiento_actual,
        "Mes1": meses[0],
        "Mes2": meses[1],
        "Mes3": meses[2],
        "Mes4": meses[3]
    }

def extraer_periodo_anterior(texto, debug=False):
    texto_normalizado = texto.replace('\n', ' ')

    resultado = {
        "PeriodoDeFacturacionAnteriorDesde": None,
        "PeriodoDeFacturacionAnteriorHasta": None,
        # Nacionales
        "SaldoAdeudadoInicioPeriodoAnterior": None,
        "MontoFacturadoPeriodoAnterior": None,
        "MontoPagadoPeriodoAnterior": None,
        "SaldoAdeudadoFinalPeriodoAnterior": None,
        # Internacionales (US)
        "SaldoAnteriorFacturadoUS": None,
        "AbonoRealizadoUS": None,
        "TraspasoDeudaNacionalUS": None,
        "DeudaTotalFacturadaMesUS": None,
    }

    # === Nacional ===
    nacional = re.search(
        r'Per[ií]odo de Facturaci[oó]n Anterior\s*(\d{2}/\d{2}/\d{4})\s+(\d{2}/\d{2}/\d{4})',
        texto_normalizado, re.IGNORECASE)
    if nacional:
        resultado["PeriodoDeFacturacionAnteriorDesde"] = nacional.group(1)
        resultado["PeriodoDeFacturacionAnteriorHasta"] = nacional.group(2)
        if debug:
            print(f"[DEBUG Nacional] PeriodoDesde: {nacional.group(1)}, PeriodoHasta: {nacional.group(2)}")

    def extraer_valor_etiqueta(etiqueta, campo):
        patron = rf'{etiqueta}\s*\$?\s*(-?[\d\.,]+)'
        match = re.search(patron, texto, re.IGNORECASE)
        if match:
            valor = match.group(1).replace(' ', '').replace('.', '').replace(',', '')
            if debug:
                print(f"[DEBUG Nacional] {campo}: {valor}")
            return valor
        if debug:
            print(f"[DEBUG Nacional] No se encontró {campo}")
        return None

    resultado["SaldoAdeudadoInicioPeriodoAnterior"] = extraer_valor_etiqueta(
        'Saldo Adeudado Inicio Per[ií]odo Anterior', "SaldoAdeudadoInicioPeriodoAnterior")
    resultado["MontoFacturadoPeriodoAnterior"] = extraer_valor_etiqueta(
        'Monto Facturado Per[ií]odo Anterior', "MontoFacturadoPeriodoAnterior")
    resultado["MontoPagadoPeriodoAnterior"] = extraer_valor_etiqueta(
        'Monto Pagado Per[ií]odo Anterior', "MontoPagadoPeriodoAnterior")
    resultado["SaldoAdeudadoFinalPeriodoAnterior"] = extraer_valor_etiqueta(
        'Saldo Adeudado Final Per[ií]odo Anterior', "SaldoAdeudadoFinalPeriodoAnterior")

    # === Internacional ===
    intl_desde = re.search(r'Per[ií]odo facturado Desde\s*(\d{2}/\d{2}/\d{4})', texto, re.IGNORECASE)
    if intl_desde and resultado["PeriodoDeFacturacionAnteriorDesde"] is None:
        resultado["PeriodoDeFacturacionAnteriorDesde"] = intl_desde.group(1)
        if debug:
            print(f"[DEBUG Internacional] PeriodoDesde: {intl_desde.group(1)}")

    intl_hasta = re.search(r'Per[ií]odo facturado Hasta\s*(\d{2}/\d{2}/\d{4})', texto, re.IGNORECASE)
    if intl_hasta and resultado["PeriodoDeFacturacionAnteriorHasta"] is None:
        resultado["PeriodoDeFacturacionAnteriorHasta"] = intl_hasta.group(1)
        if debug:
            print(f"[DEBUG Internacional] PeriodoHasta: {intl_hasta.group(1)}")

    def extraer_valor_etiqueta_usd(etiqueta, campo):
        patron = rf'{etiqueta}[\s\S]*?(-?)\s*US\$?\s*([\d\.,]+)'
        match = re.search(patron, texto, re.IGNORECASE)
        if match:
            signo = match.group(1)
            valor = match.group(2).replace('.', '').replace(',', '.')
            if signo == '-':
                valor = f"-{valor}"
            if debug:
                print(f"[DEBUG Internacional] {campo}: {valor}")
            return valor
        if debug:
            print(f"[DEBUG Internacional] No se encontró {campo}")
        return None

    resultado["SaldoAnteriorFacturadoUS"] = extraer_valor_etiqueta_usd(
        'Saldo Anterior Facturado', "SaldoAnteriorFacturadoUS")
    resultado["AbonoRealizadoUS"] = extraer_valor_etiqueta_usd(
        'Traspaso Deuda Nacional', "AbonoRealizadoUS")
    resultado["TraspasoDeudaNacionalUS"] = extraer_valor_etiqueta_usd(
        'Abono Realizado', "TraspasoDeudaNacionalUS")
    resultado["DeudaTotalFacturadaMesUS"] = extraer_valor_etiqueta_usd(
        'Deuda Total Facturada del Mes', "DeudaTotalFacturadaMesUS")

    return resultado

def detectar_tipo_tarjeta(texto):
    texto_upper = texto.upper()

    if "ESTADO DE CUENTA INTERNACIONAL DE TARJETA DE CRÉDITO" in texto_upper:
        return False, True

    elif "ESTADO DE CUENTA TARJETA DE CRÉDITO" in texto_upper:
        return True, False

    return False, False

def extraer_cae_prepago(texto, debug=False):
    match = re.search(r'CAE PREPAGO[\s\S]*?(\d{1,3}[,\.]?\d*)\s*%', texto, re.IGNORECASE)
    if match:
        valor = match.group(1).replace(',', '.').replace('.', '')
        if debug:
            print(f"[DEBUG] CAE PREPAGO: {valor}")
        return valor
    else:
        if debug:
            print("[DEBUG] No se encontró CAE PREPAGO")
        return None

def extraer_campo(patron, texto):
    match = re.search(patron, texto, re.IGNORECASE)
    return match.group(1).strip() if match else ""

def extraer_cupos_completos(texto, tipo=None):
    resultados = {
        'cupo_total': None,
        'cupo_total_utilizado': None,
        'cupo_total_disponible': None,
        'cupo_avance_total': None,
        'cupo_avance_utilizado': None,
        'cupo_avance_disponible': None,
        'cupo_sa_total': None,
        'cupo_sa_utilizado': None,
        'cupo_sa_disponible': None,
    }

    lineas = texto.splitlines()

    def extraer_valores_con_filtro(lineas, start_idx, max_lineas=4, ignorar_palabras=None):
        if ignorar_palabras is None:
            ignorar_palabras = []
        valores = []
        for j in range(start_idx, min(start_idx + max_lineas, len(lineas))):
            linea_baja = lineas[j].lower()
            # Uso regex para ignorar variantes con espacio o guion bajo
            if any(re.search(p.replace(" ", r"[\s_]?"), linea_baja) for p in ignorar_palabras):
                continue
            encontrados = re.findall(r"\$\s*[\d\.]+", lineas[j])
            valores.extend(encontrados)
            if len(valores) >= 3:
                break
        valores_int = []
        for v in valores[:3]:
            num = v.replace('$', '').replace('.', '').strip()
            try:
                valores_int.append(float(num))
            except:
                valores_int.append(None)
        return valores_int

    if tipo == "internacional":
        for i, linea in enumerate(lineas):
            linea_lower = linea.lower()
            if all(x in linea_lower for x in ["cupo total", "compra", "avance"]):
                valores_encontrados = []
                for j in range(i, min(i + 5, len(lineas))):
                    valores = re.findall(r"-?\d{1,3}(?:\.\d{3})*,\d{2}", lineas[j])
                    if not valores:
                        valores = re.findall(r"US\$?\s?[\d.,]+", lineas[j])
                    for v in valores:
                        val_float = limpiar_valor(v)
                        if val_float is not None:
                            valores_encontrados.append(val_float)
                    if len(valores_encontrados) >= 3:
                        break
                if len(valores_encontrados) >= 3:
                    resultados['cupo_total'] = valores_encontrados[0]
                    resultados['cupo_total_utilizado'] = valores_encontrados[1]
                    resultados['cupo_total_disponible'] = valores_encontrados[2]
                break

    elif tipo == "nacional":
        for i, linea in enumerate(lineas):
            linea_lower = linea.lower().strip()

            # Extraer todos los valores $ de la misma línea
            valores_en_linea = re.findall(r"\$\s*[\d\.]+", linea)
            montos = []
            for v in valores_en_linea:
                num = v.replace('$', '').replace('.', '').strip()
                try:
                    montos.append(float(num))
                except:
                    pass

            # Saltar líneas sin valores monetarios (encabezados)
            if not montos:
                continue

            # CUPO TOTAL (sin avance, sin superavance) — siempre 3 valores
            if (
                "cupo total" in linea_lower
                and "avance" not in linea_lower
                and not re.search(r'super[\s_]?avance', linea_lower)
            ):
                print(f"[DEBUG] Línea cupo total: {linea.strip()} -> montos: {montos}")
                if len(montos) >= 3:
                    resultados['cupo_total'] = montos[0]
                    resultados['cupo_total_utilizado'] = montos[1]
                    resultados['cupo_total_disponible'] = montos[2]

            # CUPO SUPERAVANCE (evaluar antes que avance) — variable: 1, 2 o 3 valores
            elif re.search(r'cupo\s+total\s+super\s?avance', linea_lower):
                print(f"[DEBUG] Línea cupo SA/superavance: {linea.strip()} -> montos: {montos}")
                if len(montos) == 1:
                    resultados['cupo_sa_total'] = montos[0]
                elif len(montos) == 2:
                    resultados['cupo_sa_total'] = montos[0]
                    resultados['cupo_sa_utilizado'] = montos[1]
                elif len(montos) >= 3:
                    resultados['cupo_sa_total'] = montos[0]
                    resultados['cupo_sa_utilizado'] = montos[1]
                    resultados['cupo_sa_disponible'] = montos[2]

            # CUPO AVANCE EN EFECTIVO (sin superavance) — solo 1 valor (disponible)
            elif "cupo total avance" in linea_lower and not re.search(r'super[\s_]?avance', linea_lower):
                print(f"[DEBUG] Línea cupo avance: {linea.strip()} -> montos: {montos}")
                if montos:
                    resultados['cupo_avance_disponible'] = montos[0]

    return resultados

def extraer_cobranza_interes(texto: str):
    gastos = 0
    interes = 0

    match_gastos = re.search(r"Gastos de Cobranza\s*\$?\s*([\d\.]+)", texto, re.IGNORECASE)
    if match_gastos:
        try:
            gastos = float(match_gastos.group(1).replace(".", "").replace(",", "."))
        except:
            gastos = 0

    match_interes = re.search(r"Inter[eé]s Moratorio\s*\$?\s*([\d\.]+)", texto, re.IGNORECASE)
    if match_interes:
        try:
            interes = float(match_interes.group(1).replace(".", "").replace(",", "."))
        except:
            interes = 0

    return gastos, interes

def extraer_codigo_barra_sectorizacion(texto):
    match = re.search(r"\b\d{13}\b", texto)
    if match:
        return match.group(0)
    return None

def extraer_sector_cuartel(texto):
    pos = texto.upper().find("I. INFORMACIÓN GENERAL")
    if pos == -1:
        pos = texto.upper().find("INFORMACION GENERAL")
    texto_header = texto[:pos] if pos > 0 else texto

    match = re.search(r'(?:^|\n)\s*(\d{1,3}/\d{1,3})', texto_header)
    if match:
        return match.group(1)
    return None

def extraer_codigo_postal(texto):
    lineas = [l.strip() for l in texto.splitlines() if l.strip()]
    despues_tarjeta = False
    for linea in lineas:
        if "Número tarjeta" in linea or re.search(r'X{4,}\d{4}', linea):
            despues_tarjeta = True
            continue
        if despues_tarjeta:
            # Buscar patrón de dígitos separados por espacios (7-9 dígitos)
            # Caso 1: línea propia "1 7 1 0 2 0 9"
            # Caso 2: combinado "1 7 1 0 2 0 9 (cid:8)... Fecha Estado de Cuenta..."
            match = re.search(r'(?:\d\s){6,8}\d', linea)
            if match:
                return match.group(0).replace(' ', '')
            if "Fecha Estado" in linea or "INFORMACIÓN GENERAL" in linea.upper():
                break
    return None

def normalizar(texto):
    return re.sub(r'\s+', ' ', texto.strip().lower())

def linea_valida_geografica(linea):

    PALABRAS_PROHIBIDAS = [
        "número tarjeta", "fecha estado", "estado de cuenta",
        "rut", "folio", "cliente", "sucursal",
        "información general", "informacion general",
        "cupo total", "cupo utilizado", "cupo disponible", "cae prepago",
        "cae"
    ]

    KEYWORDS_DIRECCION = [
        "edificio", "depto", "dpto", "departamento",
        "oficina", "block", "bloque", "piso",
        "torre", "calle", "avda", "avenida",
        "pasaje", "condominio", "parcela",
        "consultorio", "consulta", "sector", "manzana"
    ]

    if not isinstance(linea, str):
        return False

    l = normalizar(linea)

    if len(l) < 3:
        return False

    if any(p in l for p in PALABRAS_PROHIBIDAS):
        return False

    if re.search(r'\d', l):
        return False

    if re.search(r'[%/#@&\*\+\(\)\$\\]', l):
        return False

    # Patrón de caracteres espaciados (ej: "4 8 0 1 5 5 5")
    palabras = l.split()
    if len(palabras) >= 3 and all(len(p) <= 1 for p in palabras):
        return False

    if any(kw in palabras for kw in KEYWORDS_DIRECCION):
        return False

    return True

def extraer_prefijo_geografico(linea):
    """Extrae un nombre geográfico del inicio de una línea mixta.
    Ej: 'VINA DEL MAR Número tarjeta XXXX0778' → 'VINA DEL MAR'
    """
    PALABRAS_CORTE = ["número tarjeta", "numero tarjeta", "fecha estado", "página"]
    l_lower = linea.lower()
    for palabra in PALABRAS_CORTE:
        pos = l_lower.find(palabra)
        if pos > 0:
            candidato = linea[:pos].strip()
            if candidato and linea_valida_geografica(candidato):
                return candidato
    return None

def _es_continuacion_direccion(linea_direccion, linea_siguiente):
    PREFIJOS_DIRECCION = {
        "SANTA", "SAN", "SANTO", "SANTOS",
        "LA", "LAS", "LOS", "EL",
        "PUERTO", "BAHIA", "RIO",
        "DEL", "DE",
        "NUEVA", "NUEVO",
        "GRAN", "MONTE", "CERRO", "PUNTA"
    }
    palabras_dir = linea_direccion.strip().split()
    if not palabras_dir:
        return False
    ultima = palabras_dir[-1].upper()
    sig = linea_siguiente.strip()
    if ultima in PREFIJOS_DIRECCION and re.match(r'^[A-Za-zÁÉÍÓÚÑáéíóúñ]+$', sig):
        return True
    return False

def extraer_comuna_region(lineas, idx_direccion, ventana=6):
    start = idx_direccion + 1
    if start < len(lineas) and _es_continuacion_direccion(lineas[idx_direccion], lineas[start]):
        start += 1

    valores_geo = []
    for i in range(start, len(lineas)):
        linea = lineas[i]

        if "información general" in linea.lower() or "informacion general" in linea.lower():
            break

        valor_geo = None
        if linea_valida_geografica(linea):
            valor_geo = linea
        else:
            valor_geo = extraer_prefijo_geografico(linea)

        if valor_geo:
            valores_geo.append(valor_geo)

    if len(valores_geo) == 0:
        return "", ""
    elif len(valores_geo) == 1:
        return valores_geo[0], ""
    elif len(valores_geo) == 2:
        return valores_geo[0], valores_geo[1]
    else:
        return valores_geo[0], valores_geo[-1]

def procesar_texto_transacciones(lineas_texto, row_index):
    resultados = []
    i = 0

    def limpiar_monto(monto):
        return monto.replace('.', '').replace(',', '')
    
    while i < len(lineas_texto):
        linea = lineas_texto[i].strip()
        #print(f"[DEBUG] BEFORE")
        # 1. CASO: Transacción Normal (Empieza con un número de 15 dígitos)
        if re.match(r'^\d{15}$', linea):
            try:
                registro = {
                    "EECC_Internacional_ROW_INDEX": row_index,
                    "NumeroReferenciaInternacional": linea,
                    "FechaOperacion": lineas_texto[i+1].strip(),
                    "DescripcionOperacionOCobro": lineas_texto[i+2].strip(),
                    "Ciudad": lineas_texto[i+3].strip(),
                    "Pais": lineas_texto[i+4].strip(),
                    "MontoMoneda": limpiar_monto(lineas_texto[i+5].strip()),
                    "MontoUSD": limpiar_monto(lineas_texto[i+6].strip())
                }
                resultados.append(registro)
                i += 7 # Saltamos los elementos procesados
                continue
            except IndexError:
                break

        # 2. CASO: Otros Cargos, Comisiones e Impuestos
        elif "otros cargos" in linea.lower():
            try:
                ref_especial = "OtrosCargos,ComisionesImpuesto;"
                
                # Saltamos la fecha (linea i+1) porque el usuario requiere NULL
                # El texto de la descripción viene en i+2 (ej: "TRASPASO DEUDA INTERNACIONAL")
                desc_texto = lineas_texto[i+2].strip()

                # Sin cargos, comisiones o impuestos asociados
                if "copia cliente" == desc_texto.lower():
                    descripcion_final = f"la Cuenta"
                    registro = {
                        "EECC_Internacional_ROW_INDEX": row_index,
                        "NumeroReferenciaInternacional": ref_especial,
                        "FechaOperacion": None, # NULL según requerimiento
                        "DescripcionOperacionOCobro": descripcion_final,
                        "Ciudad": None,
                        "Pais": None,
                        "MontoMoneda": None,
                        "MontoUSD": None
                    }
                    resultados.append(registro)
                else:
                    descripcion_final = f"la Cuenta {desc_texto} ~"
                    
                    # El monto final viene en i+3 (ej: "-7,18")
                    monto_usd = limpiar_monto(lineas_texto[i+3].strip())
                    #monto_usd = monto_raw.replace(",", "").replace("-", "")

                    registro = {
                        "EECC_Internacional_ROW_INDEX": row_index,
                        "NumeroReferenciaInternacional": ref_especial,
                        "FechaOperacion": None, # NULL según requerimiento
                        "DescripcionOperacionOCobro": descripcion_final,
                        "Ciudad": None,
                        "Pais": None,
                        "MontoMoneda": None,
                        "MontoUSD": monto_usd
                    }
                    resultados.append(registro)
                    i += 4
                    continue
            except IndexError:
                break
        
        i += 1
        
    return resultados

def transformar_s3_key(s3_key: str) -> str:
    partes = s3_key.split("/")
    
    if len(partes) < 4:
        return s3_key
    
    serie = partes[1]
    carpeta = partes[2]
    filename = partes[3]

    if serie.endswith("_VS"):
        tipo = "VISA"
    elif serie.endswith("_MC"):
        tipo = "MASTERCARD"
    else:
        tipo = "PRESTO"

    return f"I:\\ABBYY\\LIDER_BCI\\INGRESO\\{tipo}\\{carpeta}\\{filename}"

def transformar_s3_key_prod(s3_key: str) -> str:
    partes = s3_key.split("/")
    # walmart/MUESTRAS_PDF/MASTECARD/SERIE_DDMMYYYY_MC/Impresion/005174750.pdf
    # walmart/MUESTRAS_PDF/MASTECARD/SERIE_DDMMYYYY_MC/Publicacion/005174750.pdf
    # walmart/MUESTRAS_PDF/MASTECARD/SERIE_DDMMYYYY_MC/Tasas/005174750.pdf
    # walmart/MUESTRAS_PDF/VISA/SERIE_DDMMYYYY_VS/Impresion/005174750.pdf
    # walmart/MUESTRAS_PDF/VISA/SERIE_DDMMYYYY_VS/Publicacion/005174750.pdf
    # walmart/MUESTRAS_PDF/VISA/SERIE_DDMMYYYY_VS/Tasas/005174750.pdf
    # walmart/MUESTRAS_PDF/PRESTO/SERIE_DDMMYYYY/Impresion/005174750.pdf
    # walmart/MUESTRAS_PDF/PRESTO/SERIE_DDMMYYYY/Publicacion/005174750.pdf
    # walmart/MUESTRAS_PDF/PRESTO/SERIE_DDMMYYYY/Tasas/005174750.pdf
    if len(partes) < 6:
        return s3_key

    # partes[0] = "walmart"
    # partes[1] = "MUESTRAS_PDF"
    # partes[2] = "MASTERCARD" | "VISA" | "PRESTO"
    # partes[3] = "SERIE_DDMMYYYY_MC" | "SERIE_DDMMYYYY_VS" | "SERIE_DDMMYYYY"
    # partes[4] = "Impresion" | "Publicacion" | "Tasas"
    # partes[5] = "005174750.pdf"

    serie = partes[3]
    carpeta = partes[4]
    filename = partes[5]

    if serie.endswith("_VS"):
        tipo = "VISA"
    elif serie.endswith("_MC"):
        tipo = "MASTERCARD"
    else:
        tipo = "PRESTO"

    return f"I:\\ABBYY\\LIDER_BCI\\INGRESO\\{tipo}\\{carpeta}\\{filename}"

def es_monto(texto):
    return bool(re.match(r'^-?\d{1,3}(\.\d{3})*(,\d+)?$', texto))

def es_fecha(texto):
    return bool(re.match(r'^\d{2}/\d{2}/\d{4}$', texto))

def es_encabezado_numerado(texto):
    """
    Verifica el patrón: Inicio + Dígitos + Punto + Espacio + Palabra.
    Ejemplos: '1. Total', '2. Productos', '10. Cargos'
    """
    # ^\d+   -> Empieza con uno o más números
    # \.     -> Seguido de un punto literal
    # \s+    -> Uno o más espacios
    # \w+    -> Al menos una letra o palabra
    return bool(re.match(r'^\d+\.\s+\w+', texto.strip()))

def es_encabezado(lineas, i):
    if i + 2 >= len(lineas):
        return False

    linea_actual = lineas[i].strip()
    linea_mas_2 = lineas[i + 2].strip()

    return (
        linea_actual != "" and
        not es_monto(linea_actual) and
        not es_fecha(linea_actual) and
        es_fecha(linea_mas_2)
    )

def isCuota(texto):
    """
    Valida si el texto tiene formato de cuota (ej: 01/12, 1/6, 12/24).
    """
    if not texto:
        return False
    # Busca 1 o 2 dígitos, una barra, y otros 1 o 2 dígitos
    return bool(re.match(r'^\d{1,2}/\d{1,2}$', texto.strip()))

def layout_sin_columnas(lineas, idx):
    """
    Detecta si después del primer monto viene:
    - una fecha
    - un lugar (texto)
    - otro monto TOTAL
    """

    is_monto = False
    is_cuota = False
    for offset in range(0, 6):
        if idx + offset >= len(lineas):
            break

        val = lineas[idx + offset].strip()
        print(f"  -> [VALOR]: '{val}'")

        if es_fecha(val):
            return True
        
        if isCuota(val):
            is_cuota = True
        
        if es_monto(val):
            is_monto = True
            # Caso: $ valor $ valor (total tabla)

    print(f"  -> [IS_MONTO]: '{is_monto}'")
    print(f"  -> [IS_CUOTA]: '{is_cuota}'")        
    return is_monto and not is_cuota

# Limpieza de símbolos de moneda
def clean_money(val): 
    return val.replace('$', '').replace('.', '').replace(',', '').strip()
    
MONTO_REGEX = re.compile(r'^-?\d{1,3}(\.\d{3})*(,\d+)?$')

def get_monto(lineas, start):
    for j in range(start, min(start + 4, len(lineas))):
        texto = lineas[j].strip()

        if texto == "$":
            continue

        if MONTO_REGEX.match(texto):
            return clean_money(texto)

    return None

def get_n_montos(lineas, start, n, offset=5):
    montos = []
    j = start

    while j < len(lineas) and len(montos) < n and (j - start) < offset:
        texto = lineas[j].strip()

        if texto != "$" and MONTO_REGEX.match(texto):
            montos.append(clean_money(texto))

        j += 1

    return montos, j

def get_descripcion(lineas, start, max_offset=4):
    partes = []
    j = start

    while j < len(lineas) and (j - start) < max_offset:
        texto = lineas[j].strip()
        print(f"[FILA TEXTO] Contenido: '{texto}'")
        # Cortamos si aparece monto o $
        if texto == "$" or es_monto(texto):
            print(f"[FILA BREAK]: '{texto}'")
            break

        partes.append(texto)
        j += 1

    descripcion = " ".join(partes)
    return descripcion, j

def avanzar_si_es_cuota(lineas, idx):
    if idx < len(lineas) and isCuota(lineas[idx].strip()):
        return lineas[idx].strip(), idx + 1
    return None, idx

def procesar_texto_operaciones_nacionales(lineas, row_index):
    resultados = []
    i = 0
    en_seccion_operaciones = False

    print(f"\n=== INICIANDO DEBUG DE EXTRACCIÓN NACIONAL (Row Index: {row_index}) ===")

    while i < len(lineas):
        linea = lineas[i].strip()
        
        # Print de trazabilidad básica
        print(f"[FILA {i:03}] Contenido: '{linea}'")

        # 0. DETECTOR DE SALTO DE PÁGINA (Encabezado del documento)
        if "ESTADO DE CUENTA TARJETA DE CRÉDITO" in linea.upper():
            if en_seccion_operaciones:
                print(f"  >>> [EVENTO] Salto de página detectado. Desactivando sección en línea {i}")
                en_seccion_operaciones = False
            i += 1
            continue
        # 1. GESTIÓN DE ENTRADA Y REGISTRO DE ENCABEZADOS
        if es_encabezado_numerado(linea):
            # Si es el "1. Total operaciones", activamos la sección
            if "1. total operaciones" in linea.lower():
                print(f"  >>> [EVENTO] Activando Sección Nacional en línea {i}")
                en_seccion_operaciones = True

            # Si la sección está activa, registramos el encabezado como una fila
            if en_seccion_operaciones:
                print(f"  -> [REGISTRO] Guardando encabezado: '{linea}'")
                resultados.append({
                    "EECC_Nacional_ROW_INDEX": row_index,
                    "LugarOperacion": None,
                    "FechaOperacion": None,
                    "DescripOperacion": linea,
                    "MontoOperacion": None,
                    "MontoTotal": None,
                    "NroCuota": None,
                    "ValorCuotaMensual": None
                })
                i += 1
                continue

        # 2. GESTIÓN DE SALIDA
        if "iii. información de pago" in linea.lower():
            print(f"  >>> [EVENTO] Fin de sección detectado.")
            break

        # --- Ignorar todo fuera de la sección ---
        if not en_seccion_operaciones:
            print(f"  ... [SKIP] Fuera de sección")
            i += 1
            continue

        if not linea: # Ignorar líneas vacías
            i += 1
            continue
        
        # --- CASO 1: Encabezados de Sección ---
        if es_encabezado(lineas, i):
            print(f"  -> [MATCH CASO 1] Encabezado: '{linea}'")
            resultados.append({
                "EECC_Nacional_ROW_INDEX": row_index,
                "LugarOperacion": None, "FechaOperacion": None,
                "DescripOperacion": linea,
                "MontoOperacion": None, "MontoTotal": None, "NroCuota": None, "ValorCuotaMensual": None
            })
            i += 1
            continue

        # --- CASO 2: Operación que empieza por FECHA (Seguros / Cargos / Pagos) ---
        if es_fecha(linea):
            fecha = linea
            print(f"  -> [DEBUG] index after: {i+1}")
            descripcion, next_idx = get_descripcion(lineas, i+1)
            print(f"  -> [DEBUG] index before: {next_idx}")
            print(f"  -> [MATCH CASO 2] Detectada Fecha inicial: {fecha} | Desc: {descripcion}")
            print(f"  -> [DEBUG] index before: {lineas[next_idx]}")
            print(f"  -> [DEBUG] index before: {lineas[next_idx + 1]}")
            # Sub-caso especial: faltan columnas
            if layout_sin_columnas(lineas, next_idx):

                # Obtener ValorCuotaMensual (1 monto, con o sin $)
                montos, next_idx = get_n_montos(lineas, next_idx, 1, offset=2)

                valor = montos[0] if montos else None

                registro = {
                    "EECC_Nacional_ROW_INDEX": row_index,
                    "LugarOperacion": None,
                    "FechaOperacion": fecha,
                    "DescripOperacion": descripcion,
                    "MontoOperacion": None,
                    "MontoTotal": None,
                    "NroCuota": None,
                    "ValorCuotaMensual": valor
                }
                resultados.append(registro)

                # Detectar total de tabla (otro monto inmediato)
                montos_total, next_idx_total = get_n_montos(lineas, next_idx, 1, offset=2)

                if montos_total:
                    resultados.append({
                        "EECC_Nacional_ROW_INDEX": row_index,
                        "LugarOperacion": None,
                        "FechaOperacion": None,
                        "DescripOperacion": None,
                        "MontoOperacion": None,
                        "MontoTotal": None,
                        "NroCuota": None,
                        "ValorCuotaMensual": montos_total[0]
                    })
                    i = next_idx_total
                else:
                    i = next_idx

                continue

            # Caso normal (Viene todo)
            print(f"[CASO NORMAL] Extrayendo bloque completo por fecha")
            montos, next_idx = get_n_montos(lineas, next_idx, 2)
            registro = {
                "EECC_Nacional_ROW_INDEX": row_index,
                "LugarOperacion": None,
                "FechaOperacion": fecha,
                "DescripOperacion": descripcion,
                "MontoOperacion": montos[0] if len(montos) > 0 else None,
                "MontoTotal": montos[1] if len(montos) > 1 else None,
                "NroCuota": lineas[next_idx].strip() if next_idx < len(lineas) else None,
            }

            valorCuotaMensual, next_idx = get_n_montos(lineas, next_idx+1, 1, 2)
            registro["ValorCuotaMensual"] = valorCuotaMensual[0] if len(valorCuotaMensual) > 0 else None

            resultados.append(registro)

            cursor = next_idx + 1

            # Detectar total de tabla (otro monto inmediato)
            print(f"[DEBUG] Cursor después de registro: {lineas[cursor]}")
            montos, next_idx = get_n_montos(lineas, cursor, 1, offset=2)
            if len(montos) > 0:
                print(f"[INFO] Detectado subtotal: {montos[0]}")
                resultados.append({
                    "EECC_Nacional_ROW_INDEX": row_index,
                    "LugarOperacion": None, "FechaOperacion": None, "DescripOperacion": None,
                    "MontoOperacion": None, "MontoTotal": None, "NroCuota": None, "ValorCuotaMensual": montos[0]
                })
                i = next_idx
            else: 
                i = cursor
            continue

        # --- CASO 3: Operación que empieza por LUGAR (Avances / Créditos) ---
        if i + 1 < len(lineas) and es_fecha(lineas[i+1].strip()):
            lugar = linea
            fecha = lineas[i+1].strip()
            descripcion, next_idx = get_descripcion(lineas, i+2)

            print(f"  -> [MATCH CASO 3] Detectado Lugar inicial: {lugar} | Fecha: {fecha}")

            # Sub-caso especial: faltan columnas
            if layout_sin_columnas(lineas, next_idx):

                # Obtener ValorCuotaMensual (1 monto, con o sin $)
                montos, next_idx = get_n_montos(lineas, next_idx, 1, offset=2)
                valor = montos[0] if montos else None

                registro = {
                    "EECC_Nacional_ROW_INDEX": row_index,
                    "LugarOperacion": lugar,
                    "FechaOperacion": fecha,
                    "DescripOperacion": descripcion,
                    "MontoOperacion": None,
                    "MontoTotal": None,
                    "NroCuota": None,
                    "ValorCuotaMensual": valor
                }
                resultados.append(registro)

                # Detectar total de tabla (otro monto inmediato)
                montos_total, next_idx_total = get_n_montos(lineas, next_idx, 1, offset=2)

                if montos_total:
                    resultados.append({
                        "EECC_Nacional_ROW_INDEX": row_index,
                        "LugarOperacion": None,
                        "FechaOperacion": None,
                        "DescripOperacion": None,
                        "MontoOperacion": None,
                        "MontoTotal": None,
                        "NroCuota": None,
                        "ValorCuotaMensual": montos_total[0]
                    })
                    i = next_idx_total
                else:
                    i = next_idx

                continue

            # Caso normal (vienen todas las columnas)
            print(f"     [CASO NORMAL] Extrayendo bloque completo por lugar")

            # MontoOperacion + MontoTotal
            montos, next_idx = get_n_montos(lineas, next_idx, 2)

            registro = {
                "EECC_Nacional_ROW_INDEX": row_index,
                "LugarOperacion": lugar,
                "FechaOperacion": fecha,
                "DescripOperacion": descripcion,
                "MontoOperacion": montos[0] if len(montos) > 0 else None,
                "MontoTotal": montos[1] if len(montos) > 1 else None,
                "NroCuota": lineas[next_idx].strip() if next_idx < len(lineas) else None,
            }

            valorCuotaMensual, next_idx = get_n_montos(lineas, next_idx+1, 1, 2)
            registro["ValorCuotaMensual"] = valorCuotaMensual[0] if len(valorCuotaMensual) > 0 else None

            resultados.append(registro)

            cursor = next_idx + 1
            print(f"[DEBUG] Cursor después de registro: {lineas[cursor]}")
            # Subtotal / total de fila
            montos, next_idx = get_n_montos(lineas, cursor, 1, offset=2)
            if montos:
                print(f"[INFO] Detectado subtotal: {montos[0]}")
                resultados.append({
                    "EECC_Nacional_ROW_INDEX": row_index,
                    "LugarOperacion": None,
                    "FechaOperacion": None,
                    "DescripOperacion": None,
                    "MontoOperacion": None,
                    "MontoTotal": None,
                    "NroCuota": None,
                    "ValorCuotaMensual": montos[0]
                })
                i = next_idx
            else:
                i = cursor

            continue
        
        # Si no se cumple ningún caso se avanza
        i += 1

    print(f"=== DEBUG FINALIZADO. Registros extraídos: {len(resultados)} ===\n")
    return resultados

def extraer_registro_tabla(linea):
    """
    Extrae los campos de una línea de registro de tabla según los diferentes casos.
    Retorna un diccionario con los campos extraídos.
    """
    resultado = {
        "LugarOperacion": None,
        "FechaOperacion": None,
        "DescripOperacion": None,
        "MontoOperacion": None,
        "MontoTotal": None,
        "NroCuota": None,
        "ValorCuotaMensual": None
    }
    
    # Caso 5: Solo ValorCuotaMensual (línea que empieza con $ y puede ser negativo)
    if re.match(r'^\$\s*-?[\d.,]+\s*$', linea.strip()):
        monto = re.search(r'\$\s*(-?[\d.,]+)', linea)
        if monto:
            resultado["ValorCuotaMensual"] = monto.group(1).replace('.', '').replace(',', '.')
        print(f"  -> [CASO 5] Solo ValorCuotaMensual: {resultado['ValorCuotaMensual']}")
        return resultado
    
    # Buscar fecha (patrón dd/mm/yyyy)
    fecha_match = re.search(r'\b(\d{2}/\d{2}/\d{4})\b', linea)
    
    # Caso 6: Solo DescripOperacion (no hay fecha ni montos)
    if not fecha_match and '$' not in linea:
        resultado["DescripOperacion"] = linea.strip()
        print(f"  -> [CASO 6] Solo DescripOperacion: '{resultado['DescripOperacion']}'")
        return resultado
    
    # Si hay fecha, procesamos los demás campos
    if fecha_match:
        resultado["FechaOperacion"] = fecha_match.group(1)
        pos_fecha = fecha_match.start()
        
        # LugarOperacion: todo lo que está a la izquierda de la fecha
        lugar = linea[:pos_fecha].strip()
        if lugar:
            resultado["LugarOperacion"] = lugar
        
        # Resto de la línea después de la fecha
        resto_linea = linea[fecha_match.end():].strip()
        
        # Buscar todos los montos (patrón $ seguido de número, puede ser negativo)
        montos = re.finditer(r'\$\s*(-?[\d.,]+)', resto_linea)
        lista_montos = [(m.group(1).replace('.', '').replace(',', '.'), m.start()) for m in montos]
        
        # Buscar NroCuota (patrón nn/nn o número suelto de 1-2 dígitos al final sin $)
        cuota_match = re.search(r'\b(\d{2}/\d{2})\b', resto_linea)
        print(f"  -> [DEBUG] Cuota match: {cuota_match}")    
        if not cuota_match:
            cuota_match = re.search(r'(?<!\$)\s+(\d{1,2})\s*$', resto_linea)
            if cuota_match:
                print(f"  -> [CASO 7] NroCuota suelto: {cuota_match.group(1)}")
        
        # Determinar DescripOperacion: desde el inicio hasta el primer $
        if lista_montos:
            pos_primer_monto = lista_montos[0][1]
            descripcion = resto_linea[:pos_primer_monto].strip()
            resultado["DescripOperacion"] = descripcion
            
            # Asignar montos según la cantidad encontrada
            if len(lista_montos) == 1:
                # Solo un monto (ValorCuotaMensual) o montoOperacion y nroCuota
                if cuota_match:
                    resultado["MontoOperacion"] = lista_montos[0][0]
                    resultado["NroCuota"] = cuota_match.group(1)
                else:
                    resultado["ValorCuotaMensual"] = lista_montos[0][0]
                    print(f"  -> [CASO 3/4] Un monto: ValorCuotaMensual = {resultado['ValorCuotaMensual']}")
            elif len(lista_montos) == 2:
                # Dos montos sin NroCuota: MontoOperacion y MontoTotal
                # O con NroCuota: MontoTotal y ValorCuotaMensual
                if cuota_match:
                    resultado["MontoTotal"] = lista_montos[0][0]
                    resultado["ValorCuotaMensual"] = lista_montos[1][0]
                    resultado["NroCuota"] = cuota_match.group(1)
                else:
                    resultado["MontoOperacion"] = lista_montos[0][0]
                    resultado["MontoTotal"] = lista_montos[1][0]
            elif len(lista_montos) >= 3:
                # Caso 1 o 2: Todos los montos
                resultado["MontoOperacion"] = lista_montos[0][0]
                resultado["MontoTotal"] = lista_montos[1][0]
                resultado["ValorCuotaMensual"] = lista_montos[2][0]
                if cuota_match:
                    resultado["NroCuota"] = cuota_match.group(1)
                print(f"  -> [CASO 1/2] Completo")
        else:
            # No hay montos, solo descripción
            resultado["DescripOperacion"] = resto_linea
    
    return resultado

def es_linea_cid(linea):
    """
    Detecta si una línea contiene caracteres CID (coordenadas de pdfplumber).
    Ejemplos: (cid:108), (cid:108)(cid:108)(cid:108), etc.
    
    Args:
        linea: String de la línea a verificar
    
    Returns:
        Boolean indicando si es una línea CID
    """
    # Patrón: (cid:número) puede aparecer una o más veces
    patron_cid = r'\(cid:\d+\)'
    
    # Verificar si la línea contiene el patrón CID
    if re.search(patron_cid, linea):
        # Verificar que la línea SOLO contenga patrones CID y espacios
        # (para evitar falsos positivos si aparece en medio de texto válido)
        linea_limpia = re.sub(patron_cid, '', linea).strip()
        
        # Si después de remover los CID solo quedan espacios o está vacía, es una línea CID
        if len(linea_limpia) == 0:
            return True
    
    return False

def procesar_texto_operaciones_nacionales_pdf(lineas, row_index):
    resultados = []
    i = 1
    en_seccion_operaciones = False

    print(f"\n=== INICIANDO DEBUG DE EXTRACCIÓN NACIONAL (Row Index: {row_index}) ===")

    while i < len(lineas):
        linea = lineas[i].strip()
        
        # Print de trazabilidad básica
        print(f"[FILA {i:03}] Contenido: '{linea}'")

        # 0A. DETECTOR DE CARACTERES CID (Fin de página)
        if es_linea_cid(linea):
            if en_seccion_operaciones:
                print(f"  >>> [EVENTO] Caracteres CID detectados. Desactivando sección en línea {i}")
                en_seccion_operaciones = False
            i += 1
            continue

        # 0B. DETECTOR DE SALTO DE PÁGINA (Encabezado del documento)
        if "ESTADO DE CUENTA TARJETA DE CRÉDITO" in linea.upper():
            if en_seccion_operaciones:
                print(f"  >>> [EVENTO] Salto de página detectado. Desactivando sección en línea {i}")
                en_seccion_operaciones = False
            i += 1
            break
            #continue

        # 1. GESTIÓN DE ENTRADA Y REGISTRO DE ENCABEZADOS
        if es_encabezado_numerado(linea):
            # Si es el "1. Total operaciones", activamos la sección
            if "1. total operaciones" in linea.lower():
                print(f"  >>> [EVENTO] Activando Sección Nacional en línea {i}")
                en_seccion_operaciones = True

            # Si la sección está activa, registramos el encabezado como una fila
            if en_seccion_operaciones:
                print(f"  -> [REGISTRO] Guardando encabezado: '{linea}'")
                resultados.append({
                    "EECC_Nacional_ROW_INDEX": row_index,
                    "LugarOperacion": None,
                    "FechaOperacion": None,
                    "DescripOperacion": linea,
                    "MontoOperacion": None,
                    "MontoTotal": None,
                    "NroCuota": None,
                    "ValorCuotaMensual": None
                })
                i += 1
                continue

        # 2. GESTIÓN DE SALIDA
        if "iii. información de pago" in linea.lower():
            print(f"  >>> [EVENTO] Fin de sección detectado.")
            break

        # --- Ignorar todo fuera de la sección ---
        if not en_seccion_operaciones:
            print(f"  ... [SKIP] Fuera de sección")
            i += 1
            continue

        if not linea or linea.strip().lower() == "brelleno" or linea.strip() == ".": # Ignorar líneas vacías
            i += 1
            continue
             
        # --- Registros de tabla ---
        print(f"  -> [PROCESANDO] Registro de tabla")
        datos_extraidos = extraer_registro_tabla(linea)
        
        # Agregar el registro con el row_index
        registro_completo = {"EECC_Nacional_ROW_INDEX": row_index}
        registro_completo.update(datos_extraidos)
        resultados.append(registro_completo)

        i += 1

    print(f"=== DEBUG FINALIZADO. Registros extraídos: {len(resultados)} ===\n")
    return resultados

def procesar_texto_transacciones_internacional_pdf(lineas, row_index):
    """
    Procesa la sección de transacciones internacionales del estado de cuenta.
    
    Args:
        lineas: Lista de líneas de texto extraídas del PDF
        row_index: Índice de la fila para tracking
    
    Returns:
        Lista de diccionarios con los registros extraídos
    """
    resultados = []
    i = 0
    en_seccion_transacciones = False
    
    print(f"\n=== INICIANDO DEBUG DE EXTRACCIÓN INTERNACIONAL (Row Index: {row_index}) ===")

    def limpiar_monto(monto):
        """Elimina separadores de miles y mantiene decimales"""
        return monto.replace('.', '').replace(',', '')
    
    def extraer_transaccion_completa(linea):
        """
        Extrae todos los campos de una línea de transacción completa.
        Formato: NumRef Fecha Descripcion Ciudad Pais MontoMoneda MontoUSD
        """
        resultado = {
            "NumeroReferenciaInternacional": None,
            "FechaOperacion": None,
            "DescripcionOperacionOCobro": None,
            "Ciudad": None,
            "Pais": None,
            "MontoMoneda": None,
            "MontoUSD": None
        }
        
        # 1. Extraer NumeroReferencia (primeros 15 dígitos)
        num_ref_match = re.match(r'^(\d{15})\s+', linea)
        if not num_ref_match:
            return None
        
        resultado["NumeroReferenciaInternacional"] = num_ref_match.group(1)
        resto = linea[num_ref_match.end():].strip()
        
        # 2. Extraer Fecha (dd/mm/yyyy)
        fecha_match = re.match(r'^(\d{2}/\d{2}/\d{4})\s+', resto)
        if not fecha_match:
            return None
        
        resultado["FechaOperacion"] = fecha_match.group(1)
        resto = resto[fecha_match.end():].strip()
        
        # 3. Extraer los dos montos (al final de la línea)
        # Patrón: números con puntos de miles y comas decimales, pueden ser negativos
        montos = re.findall(r'-?[\d.]+,\d{2}', resto)
        
        if len(montos) < 2:
            return None
        
        # Los dos últimos montos son MontoMoneda y MontoUSD
        resultado["MontoUSD"] = limpiar_monto(montos[-1])
        resultado["MontoMoneda"] = limpiar_monto(montos[-2])
        
        # 4. Eliminar los montos del resto para procesar el medio
        # Encontrar posición del penúltimo monto
        pos_monto = resto.rfind(montos[-2])
        texto_medio = resto[:pos_monto].strip()
        
        # 5. Extraer País y Ciudad desde el final hacia atrás
        # El país es típicamente 2-3 letras mayúsculas al final (US, GB, CHL, etc.)
        # Buscar el último token que sea solo letras mayúsculas
        tokens = texto_medio.split()
        
        # Buscar el país (últimas 2-3 letras mayúsculas)
        pais_index = None
        for idx in range(len(tokens) - 1, -1, -1):
            token = tokens[idx]
            # Verificar si es un código de país (2-3 letras mayúsculas)
            if re.match(r'^[A-Z]{2,3}$', token):
                resultado["Pais"] = token
                pais_index = idx
                break
        
        if pais_index is not None:
            tokens_antes_pais = tokens[:pais_index]

            comma_idx = None
            for ci in range(len(tokens_antes_pais) - 1, -1, -1):
                if ',' in tokens_antes_pais[ci]:
                    comma_idx = ci
                    break

            if comma_idx is not None:
                comma_token = tokens_antes_pais[comma_idx]
                after_comma = comma_token.split(',')[-1].strip()
                after_comma_tokens = ([after_comma] if after_comma else []) + tokens_antes_pais[comma_idx + 1:]

                is_city_pattern = (
                    len(after_comma_tokens) >= 2
                    and len(after_comma_tokens) % 2 == 0
                    and all(re.match(r'^[A-Za-z]+$', t) for t in after_comma_tokens)
                )

                if is_city_pattern:
                    mid = len(after_comma_tokens) // 2
                    ciudad_words = after_comma_tokens[mid:]
                    desc_city_words = after_comma_tokens[:mid]

                    before_comma_part = ','.join(comma_token.split(',')[:-1])
                    desc_suffix = f"{before_comma_part},{' '.join(desc_city_words)}"
                    desc_parts = list(tokens_antes_pais[:comma_idx]) + [desc_suffix]
                    resultado["DescripcionOperacionOCobro"] = ' '.join(desc_parts)
                    resultado["Ciudad"] = ' '.join(ciudad_words)
                else:
                    if tokens_antes_pais:
                        resultado["Ciudad"] = tokens_antes_pais[-1]
                        resultado["DescripcionOperacionOCobro"] = ' '.join(tokens_antes_pais[:-1])
                    else:
                        resultado["DescripcionOperacionOCobro"] = texto_medio
            else:
                if tokens_antes_pais:
                    resultado["Ciudad"] = tokens_antes_pais[-1]
                    resultado["DescripcionOperacionOCobro"] = ' '.join(tokens_antes_pais[:-1])
                else:
                    resultado["DescripcionOperacionOCobro"] = texto_medio
        else:
            resultado["DescripcionOperacionOCobro"] = texto_medio
        
        return resultado

    while i < len(lineas):
        linea = lineas[i].strip()
        
        print(f"[FILA {i:03}] Contenido: '{linea}'")

        # 1. ACTIVAR SECCIÓN: Buscar inicio de transacciones
        if "número referencia" in linea.lower() or \
           "numero referencia" in linea.lower():
            print(f"  >>> [EVENTO] Activando Sección Internacional en línea {i}")
            en_seccion_transacciones = True
            i += 1
            continue
        
        # 2. DESACTIVAR SECCIÓN: Detectar fin
        if "copia emisor" in linea.lower() or "copia cliente" in linea.lower():
            print(f"  >>> [EVENTO] Fin de sección detectado en línea {i}")
            break
        
        # Ignorar líneas fuera de la sección
        if not en_seccion_transacciones:
            print(f"  ... [SKIP] Fuera de sección")
            i += 1
            continue
        
        if not linea or linea.strip().lower() == "brelleno" or linea.strip() == ".":
            i += 1
            continue
        
        # 3. CASO 1: Transacción completa en una línea
        if re.match(r'^\d{15}\s+', linea):
            print(f"  -> [CASO 1] Transacción completa detectada")
            datos = extraer_transaccion_completa(linea)
            
            if datos:
                registro = {"EECC_Internacional_ROW_INDEX": row_index}
                registro.update(datos)
                resultados.append(registro)
                print(f"      Extraído: Ref={datos['NumeroReferenciaInternacional']}, "
                      f"Fecha={datos['FechaOperacion']}, USD={datos['MontoUSD']}")
            i += 1
            continue
        
        # 4. CASO 2: Otros Cargos, Comisiones e Impuesto
        if "otros cargos" in linea.lower() and "comisiones" in linea.lower():
            print(f"  -> [CASO 2] Otros Cargos detectado")
           
            linea_siguiente = lineas[i + 1].strip()
            
            # Verificar si la siguiente línea tiene fecha
            fecha_match = re.match(r'^(\d{2}/\d{2}/\d{4})\s+', linea_siguiente)
            
            if fecha_match:
                # Extraer descripción y monto
                resto = linea_siguiente[fecha_match.end():].strip()
                
                # Buscar monto (último número en la línea)
                monto_match = re.search(r'(-?[\d.]+,\d{2})\s*$', resto)
                
                if monto_match:
                    monto_usd = limpiar_monto(monto_match.group(1))
                    # La descripción es todo lo anterior al monto
                    descripcion = resto[:monto_match.start()].strip()
                    
                    registro_detalle = {
                        "EECC_Internacional_ROW_INDEX": row_index,
                        "NumeroReferenciaInternacional": "OtrosCargos,ComisionesImpuesto",
                        "FechaOperacion": None,
                        "DescripcionOperacionOCobro": f"la Cuenta {descripcion}",
                        "Ciudad": None,
                        "Pais": None,
                        "MontoMoneda": None,
                        "MontoUSD": monto_usd
                    }
                    resultados.append(registro_detalle)
                    # Saltar linea procesada    
                    i += 2
                    print(f"Extraído Cargo: {descripcion}, USD={monto_usd}")
            else:
                registro = {
                        "EECC_Internacional_ROW_INDEX": row_index,
                        "NumeroReferenciaInternacional": "OtrosCargos,ComisionesImpuesto",
                        "FechaOperacion": None,
                        "DescripcionOperacionOCobro": f"la Cuenta",
                        "Ciudad": None,
                        "Pais": None,
                        "MontoMoneda": None,
                        "MontoUSD": None
                    }
                resultados.append(registro)
                print(f"      Extraído Cargos sin datos adicionales, solo descripción genérica.")

                # Saltar linea procesada    
                i += 1
            continue
  
        i += 1
    
    print(f"=== DEBUG FINALIZADO. Registros extraídos: {len(resultados)} ===\n")
    return resultados



def extraer_datos(texto, texto_pdfplumber, tipo=None, s3_key=None, codigo_producto=None, bucket=None, key=None):
    log_event("EXTRACT_START", {"file": key, "tipo": tipo})
    lote = None
    datos = {}
    errores = []  # lista de errores no fatales
    
    # === Extracción de cupos ===
    try:
        cupos = extraer_cupos_completos(texto, tipo)
        log_event("EXTRACT_CUPOS_OK", {"file": key, "tipo": tipo})
    except Exception as e:
        log_event("EXTRACT_CUPOS_ERROR", {"file": key, "error": str(e)})
        errores.append({
            "codigo": "EXTRACT_CUPOS_ERROR",
            "mensaje": str(e)
        })
        cupos = {}

    # === Extracción de vencimientos ===
    try:
        vencimientos = extraer_vencimientos(texto)
        log_event("EXTRACT_VENCIMIENTOS_OK", {"file": key})
    except Exception as e:
        log_event("EXTRACT_VENCIMIENTOS_ERROR", {"file": key, "error": str(e)})
        errores.append({
            "codigo": "EXTRACT_VENCIMIENTOS_ERROR",
            "mensaje": str(e)
        })
        vencimientos = {}

    # === Extracción de periodo anterior ===
    try:
        periodo_anterior = extraer_periodo_anterior(texto, debug=False)
        log_event("EXTRACT_PERIODO_OK", {"file": key})
    except Exception as e:
        log_event("EXTRACT_PERIODO_ERROR", {"file": key, "error": str(e)})
        errores.append({
            "codigo": "EXTRACT_PERIODO_ERROR",
            "mensaje": str(e)
        })
        periodo_anterior = {}

    # === Extracción de nombre y dirección ===
    try:
        lineas_pdf = texto_pdfplumber if isinstance(texto_pdfplumber, list) else texto_pdfplumber.split('\n')
        nombre, direccion = extraer_nombre_titular_pdfplumber(lineas_pdf)
        log_event("EXTRACT_TITULAR_OK", {"file": key, "nombre": nombre})
    except Exception as e:
        log_event("EXTRACT_TITULAR_ERROR", {"file": key, "error": str(e)})
        errores.append({
            "codigo": "EXTRACT_TITULAR_ERROR",
            "mensaje": str(e)
        })
        nombre, direccion = "", ""

    # === Extracción de cobranza e interés ===
    try:
        gastos_cobranza, interes_moratorio = extraer_cobranza_interes(texto)
        log_event("EXTRACT_COBRANZA_OK", {"file": key})
    except Exception as e:
        log_event("EXTRACT_COBRANZA_ERROR", {"file": key, "error": str(e)})
        errores.append({
            "codigo": "EXTRACT_COBRANZA_ERROR",
            "mensaje": str(e)
        })
        gastos_cobranza, interes_moratorio = None, None

    # === Procesamiento de comuna / región ===
    lineas = [l.strip() for l in texto.splitlines() if l.strip()]
    comuna = region = ""

    if direccion in lineas:
        idx = lineas.index(direccion)
        if idx + 1 < len(lineas) and _es_continuacion_direccion(lineas[idx], lineas[idx + 1]):
            direccion = direccion + " " + lineas[idx + 1].strip()
        comuna, region = extraer_comuna_region(lineas, idx)

    # Validar Comuna: si contiene palabras de encabezados no es comuna
    PALABRAS_INVALIDAS_COMUNA = ["información general", "informacion general"]
    if comuna and any(p in comuna.lower() for p in PALABRAS_INVALIDAS_COMUNA):
        comuna = ""

    # Validar Region: si contiene palabras de la tabla de cupos no es region
    PALABRAS_INVALIDAS_REGION = ["cupo", "total", "utilizado", "disponible"]
    if region and any(p in region.lower() for p in PALABRAS_INVALIDAS_REGION):
        region = ""

    refundido = "No"
    tasa1 = tasa2 = tasa3 = ""
    cae1 = cae2 = cae3 = ""
    cae_prepago = None

    # === Datos para estados nacionales ===
    if tipo == "nacional":
        log_event("EXTRACT_TIPO_NACIONAL", {"file": key})
        try:
            for i, linea in enumerate(lineas):
                if "Refundido Cuotas Avance" in linea:
                    refundido = "Sí"
                elif "Tasa Interés Vigente" in linea or re.search(r'T\s*a\s*s\s*a.*V\s*i\s*g\s*e\s*n\s*t\s*e', linea, re.IGNORECASE):
                    encontrados = re.findall(r"(\d{1,3},\d{2}|\d+)\s*%", linea)
                    if len(encontrados) >= 3:
                        tasa_vals = []
                        for t in encontrados[:3]:
                            v = t.replace(',', '')
                            tasa_vals.append('0' if v == '0' or v == '00' or v == '000' else v)
                        tasa1, tasa2, tasa3 = tasa_vals
                elif "CAE" in linea or re.search(r'C\s+A\s+E', linea):
                    texto_busqueda = ' '.join(lineas[i:i+5])
                    encontrados = re.findall(r"(\d{1,3},\d{2}|\d{1,3})\s*%", texto_busqueda)
                    if len(encontrados) >= 3:
                        cae_vals = []
                        for c in encontrados[:3]:
                            v = c.replace(',', '').replace('.', '')
                            cae_vals.append('0' if v == '0' or v == '00' or v == '000' else v)
                        cae1, cae2, cae3 = cae_vals

            cae_prepago = extraer_cae_prepago(texto)
            match_pago = re.search(r'Pagar Hasta\s+(\d{2}/\d{2}/\d{4})', texto)
            fecha_pago_hasta = match_pago.group(1) if match_pago else ''
            fecha_desde = fecha_hasta = ''
            match_periodo = re.search(
                r'Per[ií]odo Facturado\s+(\d{2}/\d{2}/\d{4})\s+(\d{2}/\d{2}/\d{4})', texto, re.IGNORECASE
            )
            if match_periodo:
                fecha_desde = match_periodo.group(1)                
                fecha_hasta = match_periodo.group(2)            
                proximo_periodo_desde = proximo_periodo_hasta = ''
            match_proximo = re.search(
                r'Pr[oó]ximo Per[ií]odo de Facturaci[oó]n\s+(\d{2}/\d{2}/\d{4})\s+(\d{2}/\d{2}/\d{4})',
                texto, re.IGNORECASE
            )
            if match_proximo:
                proximo_periodo_desde = match_proximo.group(1)                
                proximo_periodo_hasta = match_proximo.group(2)
            datos = {
                "Nombre": nombre,
                "Direccion": direccion,
                "Comuna": comuna,
                "Region": region,
                "NumeroTarjeta": extraer_campo(r"Número tarjeta\s+X+(\d{4})", texto)
                                  or extraer_campo(r"X{4,}(\d{4})", texto),
                "FechaEstadoCuenta": extraer_campo(
                    r"Fecha Estado de Cuenta\s+(\d{2}/\d{2}/\d{4})", texto
                ),
                "CupoTotal": limpiar_valor_float(cupos.get('cupo_total')),
                "CupoUtilizado": limpiar_valor_float(cupos.get('cupo_total_utilizado')),
                "CupoDisponible": limpiar_valor_float(cupos.get('cupo_total_disponible')),
                "CupoAvanceTotal": limpiar_valor_float(cupos.get('cupo_avance_total')),
                "CupoAvanceUtilizado": limpiar_valor_float(cupos.get('cupo_avance_utilizado')),
                "CupoAvanceDisponible": limpiar_valor_float(cupos.get('cupo_avance_disponible')),
                "CupoSATotal": limpiar_valor_float(cupos.get('cupo_sa_total')),
                "CupoSAUtilizado": limpiar_valor_float(cupos.get('cupo_sa_utilizado')),
                "CupoSADisponible": limpiar_valor_float(cupos.get('cupo_sa_disponible')),
                "PeriodoFacturadoDesde": fecha_desde,
                "PeriodoFacturadoHasta": fecha_hasta,
                "ProximoPeriodoFacturadoDesde": proximo_periodo_desde,
                "ProximoPeriodoFacturadoHasta": proximo_periodo_hasta,
                "FechaPagoHasta": fecha_pago_hasta,
                "RefundidoCuotasAvance": refundido,
                "TasaInteres1": tasa1,
                "TasaInteres2": tasa2,
                "TasaInteres3": tasa3,
                "CAE1": cae1,
                "CAE2": cae2,
                "CAE3": cae3,
                "CAE_PREPAGO": cae_prepago,
                "VencimientoActual": limpiar_valor_float(vencimientos.get("VencimientoActual")),
                "Mes1": limpiar_valor_float(vencimientos.get("Mes1")),
                "Mes2": limpiar_valor_float(vencimientos.get("Mes2")),
                "Mes3": limpiar_valor_float(vencimientos.get("Mes3")),
                "Mes4": limpiar_valor_float(vencimientos.get("Mes4")),
                "PeriodoDeFacturacionAnteriorDesde": periodo_anterior.get("PeriodoDeFacturacionAnteriorDesde"),
                "PeriodoDeFacturacionAnteriorHasta": periodo_anterior.get("PeriodoDeFacturacionAnteriorHasta"),
                "SaldoAdeudadoInicioPeriodoAnterior": periodo_anterior.get("SaldoAdeudadoInicioPeriodoAnterior"),
                "MontoFacturadoPeriodoAnterior": periodo_anterior.get("MontoFacturadoPeriodoAnterior"),
                "MontoPagadoPeriodoAnterior": periodo_anterior.get("MontoPagadoPeriodoAnterior"),
                "SaldoAdeudadoFinalPeriodoAnterior": periodo_anterior.get("SaldoAdeudadoFinalPeriodoAnterior"),
                "GastosCobranza": limpiar_valor_float(gastos_cobranza),
                "InteresMoratorio": limpiar_valor_float(interes_moratorio),
                #"Operaciones": procesar_texto_operaciones_nacionales(lineas, 0)
                "Operaciones": procesar_texto_operaciones_nacionales_pdf(texto_pdfplumber, 0)
            }
            datos = extraer_datos_montos_nacionales(texto, datos)
            datos["TextoLiberacion"] = extraer_texto_liberacion(texto)
            log_event("EXTRACT_NACIONAL_OK", {"file": key, "nombre": nombre})
        except Exception as e:
            log_event("EXTRACT_NACIONAL_ERROR", {"file": key, "error": str(e)})
            errores.append({
                "codigo": "EXTRACT_NACIONAL_ERROR",
                "mensaje": str(e)
            })
            datos = {}

    # === Datos para estados internacionales ===
    elif tipo == "internacional":
        log_event("EXTRACT_TIPO_INTERNACIONAL", {"file": key})
        try:
            match_pago = re.search(r'Pagar Hasta\s+(\d{2}/\d{2}/\d{4})', texto)
            fecha_pago_hasta = match_pago.group(1) if match_pago else ''
            match_desde = re.search(
                r'Per[ií]odo facturado Desde\s+(\d{2}/\d{2}/\d{4})',
                texto, re.IGNORECASE
            )
            match_hasta = re.search(
                r'Per[ií]odo facturado Hasta\s+(\d{2}/\d{2}/\d{4})',
                texto, re.IGNORECASE
            )
            fecha_desde = match_desde.group(1) if match_desde else ''
            fecha_hasta = match_hasta.group(1) if match_hasta else ''

            def extraer_valor_us(etiqueta):
                patron = rf'{etiqueta}[\s\S]*?US\$?\s*([\d\.,]+)'
                m = re.search(patron, texto, re.IGNORECASE)
                if m:
                    valor = m.group(1).replace('.', '').replace(',', '')
                    return valor if valor else None
                return None

            numero_cuenta = None
            for i, linea in enumerate(lineas):
                if re.search(r"N[uú]mero de cuenta", linea, re.IGNORECASE):
                    for j in range(i + 1, min(i + 5, len(lineas))):
                        match_cuenta = re.search(r'\b\d{7,10}\b', lineas[j])
                        if match_cuenta:
                            numero_cuenta = match_cuenta.group(0)
                            break
                    break

            saldo_anterior = extraer_valor_us('Saldo Anterior Facturado')
            abono_realizado = extraer_valor_us('Abono Realizado')
            traspaso_deuda = extraer_valor_us('Traspaso Deuda Nacional')
            deuda_total_mes = extraer_valor_us('Deuda Total Facturada del Mes')

            datos = {
                "Nombre": nombre,
                "Direccion": direccion,
                "Comuna": comuna,
                "Region": region,
                "NumeroTarjeta": extraer_campo(r"Número tarjeta\s+X+(\d{4})", texto)
                                  or extraer_campo(r"X{4,}(\d{4})", texto),
                "NumeroDeCuenta": numero_cuenta,
                "FechaEstadoCuenta": extraer_campo(
                    r"Fecha Estado de Cuenta\s+(\d{2}/\d{2}/\d{4})", texto
                ),
                "CupoTotalUSD": float_sin_punto(cupos.get('cupo_total')),
                "CupoUtilizadoUSD": float_sin_punto(cupos.get('cupo_total_utilizado')),
                "CupoDisponibleUSD": float_sin_punto(cupos.get('cupo_total_disponible')),
                "PeriodoFacturadoDesde": fecha_desde,
                "PeriodoFacturadoHasta": fecha_hasta,
                "FechaPagoHasta": fecha_pago_hasta,
                "PeriodoDeFacturacionAnteriorDesde": periodo_anterior.get("PeriodoDeFacturacionAnteriorDesde"),
                "PeriodoDeFacturacionAnteriorHasta": periodo_anterior.get("PeriodoDeFacturacionAnteriorHasta"),
                "SaldoAnteriorFacturadoUS": saldo_anterior,
                "AbonoRealizadoUS": abono_realizado,
                "TraspasoDeudaNacionalUS": traspaso_deuda,
                "DeudaTotalFacturadaMesUS": deuda_total_mes,
                "Transacciones": procesar_texto_transacciones_internacional_pdf(texto_pdfplumber, 0)
            }
            log_event("EXTRACT_INTERNACIONAL_OK", {"file": key, "nombre": nombre})
        except Exception as e:
            log_event("EXTRACT_INTERNACIONAL_ERROR", {"file": key, "error": str(e)})
            errores.append({
                "codigo": "EXTRACT_INTERNACIONAL_ERROR",
                "mensaje": str(e)
            })
            datos = {}

    # === Datos comunes ===
    # Codigo_producto siempre 0
    datos["Codigo_producto"] = 0
    # Lógica anterior comentada:
    # if codigo_producto is not None:
    #     try:
    #         datos["Codigo_producto"] = int(codigo_producto)
    #     except Exception:
    #         datos["Codigo_producto"] = 0
    # else:
    #     datos["Codigo_producto"] = 0

    if s3_key:
        datos["NOMBRE_ARCHIVO"] = transformar_s3_key(s3_key)
    if lote:
        datos["Lote"] = lote

    try:
        codigo_barra = extraer_codigo_barra_sectorizacion(texto)
        datos["CodigoBarraSectorizacion"] = codigo_barra
        datos["Sector_Cuartel"] = extraer_sector_cuartel(texto)
        log_event("EXTRACT_BARCODE_OK", {"file": key})
    except Exception as e:
        log_event("EXTRACT_BARCODE_ERROR", {"file": key, "error": str(e)})
        errores.append({
            "codigo": "EXTRACT_BARCODE_ERROR",
            "mensaje": str(e)
        })

    try:
        datos["CodigoPostal"] = extraer_codigo_postal(texto)
    except Exception as e:
        log_event("EXTRACT_CODIGOPOSTAL_ERROR", {"file": key, "error": str(e)})
        errores.append({
            "codigo": "EXTRACT_CODIGOPOSTAL_ERROR",
            "mensaje": str(e)
        })

    log_event("EXTRACT_END", {
        "file": key,
        "tipo": tipo,
        "status": "OK",
        "errores_count": len(errores)
    })

    return datos, errores

