import re
import datetime

def limpiar_valor(valor):
    valor = valor.replace('US$', '').replace('$', '').replace('.', '').replace(',', '.').strip()
    try:
        return float(valor)
    except:
        return None
    
def limpiar_valor_float(v):
    if isinstance(v, float) and v.is_integer():
        return int(v)
    return v

def float_sin_punto(v):
    if v is None:
        return None
    if isinstance(v, float):
        return f"{v:.2f}".replace('.', '')
    return str(v).replace('.', '')

def extraer_campo(patron, texto):
    match = re.search(patron, texto, re.IGNORECASE)
    return match.group(1).strip() if match else ""

def parsear_fecha(fecha_str):
    if not fecha_str:
        return None
    try:
        return datetime.datetime.strptime(fecha_str, "%d/%m/%Y").strftime("%Y-%m-%d")
    except Exception:
        return fecha_str

def fecha_actual_str():
    return datetime.datetime.now().strftime("%Y-%m-%d")