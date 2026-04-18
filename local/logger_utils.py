import logging
import json
import os
import sys

logger = logging.getLogger()
logger.setLevel(logging.INFO)

# === Detectar entorno ===
is_aws_lambda = "AWS_EXECUTION_ENV" in os.environ

# === Formato estándar ===
formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')

# === Handler consola (siempre activo) ===
stream_handler = logging.StreamHandler(sys.stdout)
stream_handler.setFormatter(formatter)
logger.addHandler(stream_handler)

# === Handler adicional para logs locales ===
if not is_aws_lambda:
    log_path = "outputs/debug.log"
    file_handler = logging.FileHandler(log_path, mode="a", encoding="utf-8")
    file_handler.setFormatter(formatter)
    logger.addHandler(file_handler)
    print(f"[LOGGER] Modo local detectado → los logs también se guardarán en {log_path}")
else:
    print("[LOGGER] Modo AWS Lambda detectado → los logs van solo a CloudWatch")

def log_event(event_type, details):
    """
    Registra eventos estructurados en JSON para CloudWatch o local file.
    """
    logger.info(json.dumps({"event": event_type, **details}))