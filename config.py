"""
=============================================================================
CONFIG — CONFIGURACIÓN
=============================================================================
Carga la configuración desde VARIABLES DE ENTORNO.

¿Qué son variables de entorno?
- Son valores que se configuran FUERA del código
- El código lee: os.environ.get("NOMBRE_VARIABLE")
- Ventaja: puedes cambiar configuración sin tocar el código
- En Railway: se configuran en el dashboard (Settings → Variables)
- En local: se pueden poner en un archivo .env

¿Por qué no poner el token directamente en el código?
- SEGURIDAD: Si subes el código a GitHub, todo el mundo ve tu token
- Con variables de entorno, el token está en el servidor, no en el código
=============================================================================
"""

import os

CONFIG = {
    # Token del bot de Telegram
    # En Railway: configúralo como variable de entorno
    # En local: puedes ponerlo aquí temporalmente para probar
    "TELEGRAM_TOKEN": os.environ.get("TELEGRAM_TOKEN", ""),

    # Puerto del servidor (Railway lo asigna automáticamente)
    "PORT": int(os.environ.get("PORT", 8000)),

    # Ruta de la base de datos
    "DB_PATH": os.environ.get("DB_PATH", "webdefinitiva.db"),
}
