# =============================================================================
# PROCFILE
# =============================================================================
# Este archivo le dice a Railway CÓMO arrancar tu aplicación.
# 
# web: → tipo de proceso (web = servidor HTTP)
# uvicorn → el servidor que ejecuta FastAPI
# main:app → archivo main.py, variable app (la instancia de FastAPI)
# --host 0.0.0.0 → escucha en todas las interfaces (necesario en Railway)
# --port $PORT → usa el puerto que Railway asigna automáticamente

web: uvicorn main:app --host 0.0.0.0 --port $PORT
