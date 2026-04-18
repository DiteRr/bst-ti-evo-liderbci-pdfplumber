import re
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

def limpiar_valor_float(v):
    if isinstance(v, float) and v.is_integer():
        return int(v)
    return v

texto = "Monto Total Facturado $ -113.666 Opción de Pago Total Facturado Cuota Flexible (1)"
raw = buscar_valor(r"Monto\s+Total\s+Facturado\s*\$\s*(-?[\d\.,]+)")
print(f"TEEEEEEEEEEEEEEEEEEEEEEEEEEEST")
print(f"raw: {repr(raw)}")
print(limpiar_valor_float(raw))