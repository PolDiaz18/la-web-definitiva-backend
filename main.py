"""
=============================================================================
LA WEB DEFINITIVA — BACKEND
=============================================================================
Este archivo es el CORAZÓN del sistema. Hace dos cosas a la vez:

1. SERVIDOR API (FastAPI) → La web HTML se conecta aquí para leer/escribir datos
2. BOT DE TELEGRAM → Corre 24/7, envía recordatorios, gestiona hábitos

Conceptos clave:
- FastAPI: Framework web moderno para Python. Crea APIs REST automáticamente.
- Webhook vs Polling: El bot usa WEBHOOK (Telegram envía mensajes al servidor)
  en vez de polling (el bot pregunta constantemente). Es más eficiente en servidor.
- SQLite: Base de datos ligera que vive en un solo archivo. Perfecta para esto.
- CORS: Permite que tu web (en Vercel) hable con esta API (en Railway).
- asyncio: Permite que el bot y la API funcionen al mismo tiempo sin bloquearse.
=============================================================================
"""

import os
import logging
from datetime import datetime, time
from zoneinfo import ZoneInfo
from contextlib import asynccontextmanager

# --- FastAPI: el framework web ---
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware

# --- Telegram Bot ---
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, Bot
from telegram.ext import (
    Application,
    CommandHandler,
    CallbackQueryHandler,
    ContextTypes,
)

# --- Nuestros módulos propios ---
from database import Database
from config import CONFIG

# =============================================================================
# CONFIGURACIÓN DE LOGGING
# =============================================================================
# Logging = sistema de registro. En vez de usar print(), usamos logging
# porque nos dice la hora, el nivel de importancia y el módulo que lo genera.
# Niveles: DEBUG < INFO < WARNING < ERROR < CRITICAL
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)

# Zona horaria de Madrid
MADRID = ZoneInfo("Europe/Madrid")

# =============================================================================
# BASE DE DATOS
# =============================================================================
# Creamos una instancia global de la base de datos.
# Todos los handlers (tanto del bot como de la API) usan esta misma instancia.
db = Database()


# =============================================================================
# ===================== HANDLERS DEL BOT DE TELEGRAM ==========================
# =============================================================================
# Un "handler" es una función que responde a algo que el usuario hace.
# Cada comando (/start, /manana, etc.) tiene su propio handler.

async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Handler para /start
    Se ejecuta cuando alguien escribe /start por primera vez o de nuevo.
    Registramos al usuario en la base de datos para poder enviarle recordatorios.
    """
    user = update.effective_user
    chat_id = update.effective_chat.id

    # Guardamos el chat_id del usuario para poder enviarle mensajes luego
    db.register_user(chat_id, user.first_name)

    await update.message.reply_text(
        f"¡Hola {user.first_name}! 👋\n\n"
        f"Soy tu asistente de productividad. Esto es lo que puedo hacer:\n\n"
        f"📋 /manana — Rutina de mañana\n"
        f"🌙 /noche — Rutina de noche\n"
        f"✅ /habitos — Marcar hábitos del día\n"
        f"📊 /resumen — Ver progreso de hoy\n\n"
        f"También te enviaré recordatorios automáticos. ¡Vamos a por ello! 🚀"
    )


async def cmd_manana(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handler para /manana — Muestra la rutina de mañana"""
    rutina = (
        "🌅 *RUTINA DE MAÑANA*\n\n"
        "1. 🚿 Ducha fría\n"
        "2. 👔 Vestirme\n"
        "3. 🛏️ Hacer la cama\n"
        "4. 🎒 Preparar mochila\n"
        "5. 📖 Leer\n"
        "6. 🍳 Desayunar\n"
        "7. 🚶 Irme\n\n"
        "¡Vamos a por el día! 💪"
    )
    await update.message.reply_text(rutina, parse_mode="Markdown")


async def cmd_noche(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handler para /noche — Muestra la rutina de noche"""
    rutina = (
        "🌙 *RUTINA DE NOCHE*\n\n"
        "1. 📵 Apagar pantallas\n"
        "2. 📝 Hacer diario\n"
        "3. 📖 Leer\n"
        "4. 🧘 Meditar\n\n"
        "Descansa bien, mañana será un gran día 🌟"
    )
    await update.message.reply_text(rutina, parse_mode="Markdown")


async def cmd_habitos(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Handler para /habitos — Muestra los 5 hábitos con botones ✅/❌
    
    InlineKeyboard: Son botones que aparecen debajo del mensaje.
    Cada botón tiene un "callback_data" que es un texto oculto que
    se envía al bot cuando el usuario pulsa el botón.
    
    Formato del callback_data: "habito_NOMBRE_ACCION"
    Ejemplo: "habito_leer_toggle" → El usuario quiere cambiar el estado de "leer"
    """
    chat_id = update.effective_chat.id
    hoy = datetime.now(MADRID).strftime("%Y-%m-%d")

    # Lista de hábitos con sus emojis
    habitos = [
        ("📖 Leer", "leer"),
        ("🧘 Meditar", "meditar"),
        ("🚿 Ducha fría", "ducha"),
        ("🏋️ Ejercicio", "ejercicio"),
        ("🚀 Avanzar en proyecto", "proyecto"),
    ]

    # Obtenemos el estado actual de los hábitos del usuario para hoy
    estados = db.get_habitos_hoy(chat_id, hoy)

    # Construimos los botones inline
    keyboard = []
    for nombre_display, nombre_id in habitos:
        completado = estados.get(nombre_id, False)
        icono = "✅" if completado else "❌"
        keyboard.append([
            InlineKeyboardButton(
                f"{icono} {nombre_display}",
                callback_data=f"habito_{nombre_id}_toggle"
            )
        ])

    reply_markup = InlineKeyboardMarkup(keyboard)

    await update.message.reply_text(
        "📋 *HÁBITOS DE HOY*\n\nPulsa para marcar/desmarcar:",
        reply_markup=reply_markup,
        parse_mode="Markdown",
    )


async def callback_habito(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Handler para cuando el usuario pulsa un botón inline.
    
    CallbackQuery: Cuando pulsas un botón inline, Telegram no envía un mensaje
    normal, envía un "callback query". Es un evento especial que hay que manejar
    de forma diferente.
    
    query.answer(): OBLIGATORIO. Le dice a Telegram "he recibido el click".
    Si no lo llamas, el usuario ve un relojito de carga infinito.
    """
    query = update.callback_query
    await query.answer()  # Siempre primero

    # Extraemos qué hábito se pulsó
    # callback_data viene como "habito_leer_toggle"
    parts = query.data.split("_")
    nombre_id = parts[1]  # "leer", "meditar", etc.

    chat_id = update.effective_chat.id
    hoy = datetime.now(MADRID).strftime("%Y-%m-%d")

    # Cambiamos el estado en la base de datos (toggle = invertir)
    db.toggle_habito(chat_id, hoy, nombre_id)

    # Reconstruimos los botones con el nuevo estado
    habitos = [
        ("📖 Leer", "leer"),
        ("🧘 Meditar", "meditar"),
        ("🚿 Ducha fría", "ducha"),
        ("🏋️ Ejercicio", "ejercicio"),
        ("🚀 Avanzar en proyecto", "proyecto"),
    ]

    estados = db.get_habitos_hoy(chat_id, hoy)

    keyboard = []
    for nombre_display, nombre_id_loop in habitos:
        completado = estados.get(nombre_id_loop, False)
        icono = "✅" if completado else "❌"
        keyboard.append([
            InlineKeyboardButton(
                f"{icono} {nombre_display}",
                callback_data=f"habito_{nombre_id_loop}_toggle"
            )
        ])

    reply_markup = InlineKeyboardMarkup(keyboard)

    # edit_message_text: Actualiza el mensaje existente en vez de enviar uno nuevo
    # Esto mantiene el chat limpio
    await query.edit_message_text(
        "📋 *HÁBITOS DE HOY*\n\nPulsa para marcar/desmarcar:",
        reply_markup=reply_markup,
        parse_mode="Markdown",
    )


async def cmd_resumen(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handler para /resumen — Muestra el progreso de hoy"""
    chat_id = update.effective_chat.id
    hoy = datetime.now(MADRID).strftime("%Y-%m-%d")

    estados = db.get_habitos_hoy(chat_id, hoy)

    nombres = {
        "leer": "📖 Leer",
        "meditar": "🧘 Meditar",
        "ducha": "🚿 Ducha fría",
        "ejercicio": "🏋️ Ejercicio",
        "proyecto": "🚀 Avanzar en proyecto",
    }

    total = len(nombres)
    completados = sum(1 for v in estados.values() if v)

    lineas = []
    for nombre_id, nombre_display in nombres.items():
        estado = estados.get(nombre_id, False)
        icono = "✅" if estado else "❌"
        lineas.append(f"{icono} {nombre_display}")

    # Barra de progreso visual
    porcentaje = int((completados / total) * 100) if total > 0 else 0
    barra_llena = "█" * (porcentaje // 10)
    barra_vacia = "░" * (10 - porcentaje // 10)

    texto = (
        f"📊 *RESUMEN DE HOY* ({hoy})\n\n"
        + "\n".join(lineas)
        + f"\n\n{barra_llena}{barra_vacia} {porcentaje}%"
        + f"\n\n{completados}/{total} hábitos completados"
    )

    if completados == total:
        texto += "\n\n🎉 ¡TODOS COMPLETADOS! ¡Día perfecto!"
    elif completados >= 3:
        texto += "\n\n💪 ¡Buen trabajo! Sigue así."
    elif completados > 0:
        texto += "\n\n🔥 Has empezado, ¡no pares!"
    else:
        texto += "\n\n⏳ Todavía estás a tiempo, ¡vamos!"

    await update.message.reply_text(texto, parse_mode="Markdown")


# =============================================================================
# ===================== RECORDATORIOS AUTOMÁTICOS =============================
# =============================================================================
# Estas funciones se ejecutan automáticamente a horas programadas.
# Usan el objeto Bot directamente para enviar mensajes sin que el usuario
# haya escrito nada.

async def enviar_recordatorio(bot: Bot, tipo: str):
    """
    Envía un recordatorio a todos los usuarios registrados.
    
    Args:
        bot: La instancia del bot de Telegram
        tipo: "manana", "habitos_mediodia", "noche", "resumen_noche"
    """
    usuarios = db.get_all_users()

    mensajes = {
        "manana": (
            "🌅 *¡Buenos días!*\n\n"
            "Tu rutina de mañana te espera:\n"
            "1. 🚿 Ducha fría\n"
            "2. 👔 Vestirme\n"
            "3. 🛏️ Hacer la cama\n"
            "4. 🎒 Preparar mochila\n"
            "5. 📖 Leer\n"
            "6. 🍳 Desayunar\n"
            "7. 🚶 Irme\n\n"
            "¡Vamos a por el día! 💪\n\n"
            "Escribe /habitos para empezar a marcar."
        ),
        "habitos_mediodia": (
            "☀️ *¡Mediodía!*\n\n"
            "¿Cómo llevas los hábitos de hoy?\n"
            "Escribe /habitos para actualizar tu progreso.\n"
            "Escribe /resumen para ver cómo vas."
        ),
        "noche": (
            "🌙 *Hora de la rutina de noche*\n\n"
            "1. 📵 Apagar pantallas\n"
            "2. 📝 Hacer diario\n"
            "3. 📖 Leer\n"
            "4. 🧘 Meditar\n\n"
            "Descansa bien 🌟"
        ),
        "resumen_noche": None,  # Se genera dinámicamente
    }

    for user in usuarios:
        chat_id = user["chat_id"]
        try:
            if tipo == "resumen_noche":
                # Generamos el resumen personalizado para cada usuario
                hoy = datetime.now(MADRID).strftime("%Y-%m-%d")
                estados = db.get_habitos_hoy(chat_id, hoy)
                nombres = {
                    "leer": "📖 Leer", "meditar": "🧘 Meditar",
                    "ducha": "🚿 Ducha fría", "ejercicio": "🏋️ Ejercicio",
                    "proyecto": "🚀 Avanzar en proyecto",
                }
                completados = sum(1 for v in estados.values() if v)
                total = len(nombres)
                lineas = []
                for nid, ndisp in nombres.items():
                    icono = "✅" if estados.get(nid, False) else "❌"
                    lineas.append(f"{icono} {ndisp}")

                texto = (
                    f"📊 *RESUMEN DEL DÍA*\n\n"
                    + "\n".join(lineas)
                    + f"\n\n{completados}/{total} completados"
                    + "\n\n¡Buenas noches! 😴"
                )
                await bot.send_message(chat_id=chat_id, text=texto, parse_mode="Markdown")
            else:
                texto = mensajes[tipo]
                await bot.send_message(chat_id=chat_id, text=texto, parse_mode="Markdown")

            logger.info(f"Recordatorio '{tipo}' enviado a {chat_id}")
        except Exception as e:
            logger.error(f"Error enviando recordatorio a {chat_id}: {e}")


# =============================================================================
# ===================== SCHEDULER (PLANIFICADOR) ==============================
# =============================================================================
# APScheduler: Librería que ejecuta funciones a horas programadas.
# Es como un "despertador" para el código.

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger

scheduler = AsyncIOScheduler(timezone=MADRID)
telegram_app = None  # Se inicializa en el lifespan


def configurar_recordatorios():
    """
    Configura los 4 recordatorios diarios.
    CronTrigger funciona como crontab en Linux:
    - hour=7, minute=0 → Se ejecuta a las 7:00 AM
    """
    bot = telegram_app.bot

    # 7:00 AM — Rutina de mañana
    scheduler.add_job(
        enviar_recordatorio,
        CronTrigger(hour=7, minute=0, timezone=MADRID),
        args=[bot, "manana"],
        id="recordatorio_manana",
        replace_existing=True,
    )

    # 2:00 PM — Recordatorio de hábitos
    scheduler.add_job(
        enviar_recordatorio,
        CronTrigger(hour=14, minute=0, timezone=MADRID),
        args=[bot, "habitos_mediodia"],
        id="recordatorio_mediodia",
        replace_existing=True,
    )

    # 10:00 PM — Rutina de noche
    scheduler.add_job(
        enviar_recordatorio,
        CronTrigger(hour=22, minute=0, timezone=MADRID),
        args=[bot, "noche"],
        id="recordatorio_noche",
        replace_existing=True,
    )

    # 10:30 PM — Resumen del día
    scheduler.add_job(
        enviar_recordatorio,
        CronTrigger(hour=22, minute=30, timezone=MADRID),
        args=[bot, "resumen_noche"],
        id="recordatorio_resumen",
        replace_existing=True,
    )

    logger.info("✅ Recordatorios configurados: 7:00, 14:00, 22:00, 22:30")


# =============================================================================
# ===================== FASTAPI — LIFESPAN ====================================
# =============================================================================
# Lifespan: Controla qué pasa cuando el servidor arranca y cuando se apaga.
# - Al arrancar: inicializamos el bot y el scheduler
# - Al apagar: los detenemos limpiamente

@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Ciclo de vida de la aplicación.
    Todo lo que va antes del 'yield' se ejecuta al ARRANCAR.
    Todo lo que va después del 'yield' se ejecuta al APAGAR.
    """
    global telegram_app

    logger.info("🚀 Arrancando La Web Definitiva Backend...")

    # --- Inicializar base de datos ---
    db.init()
    logger.info("✅ Base de datos inicializada")

    # --- Inicializar bot de Telegram ---
    telegram_app = (
        Application.builder()
        .token(CONFIG["TELEGRAM_TOKEN"])
        .build()
    )

    # Registrar handlers del bot
    telegram_app.add_handler(CommandHandler("start", cmd_start))
    telegram_app.add_handler(CommandHandler("manana", cmd_manana))
    telegram_app.add_handler(CommandHandler("noche", cmd_noche))
    telegram_app.add_handler(CommandHandler("habitos", cmd_habitos))
    telegram_app.add_handler(CommandHandler("resumen", cmd_resumen))
    telegram_app.add_handler(CallbackQueryHandler(callback_habito, pattern="^habito_"))

    # Inicializar y arrancar el bot en modo polling
    await telegram_app.initialize()
    await telegram_app.updater.start_polling(drop_pending_updates=True)
    await telegram_app.start()
    logger.info("✅ Bot de Telegram arrancado (polling)")

    # --- Configurar y arrancar recordatorios ---
    configurar_recordatorios()
    scheduler.start()
    logger.info("✅ Scheduler arrancado")

    logger.info("🎉 Todo listo. Servidor operativo.")

    yield  # --- La aplicación está corriendo ---

    # --- APAGADO LIMPIO ---
    logger.info("🛑 Apagando...")
    scheduler.shutdown()
    await telegram_app.updater.stop()
    await telegram_app.stop()
    await telegram_app.shutdown()
    logger.info("👋 Apagado completo.")


# =============================================================================
# ===================== FASTAPI — APLICACIÓN ==================================
# =============================================================================

app = FastAPI(
    title="La Web Definitiva — API",
    description="Backend para el sistema de productividad personal de Carlos",
    version="1.0.0",
    lifespan=lifespan,
)

# --- CORS ---
# CORS (Cross-Origin Resource Sharing): Permite que tu web en Vercel
# (dominio X) haga peticiones a esta API (dominio Y).
# Sin esto, el navegador bloquea las peticiones por seguridad.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # En producción, pon aquí tu dominio de Vercel
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# =============================================================================
# ===================== ENDPOINTS DE LA API ===================================
# =============================================================================
# Endpoint = una URL que hace algo. Es como una "puerta" a una función.
# GET = leer datos, POST = crear/modificar datos, DELETE = borrar datos.

# --- Health Check ---
@app.get("/")
async def root():
    """Endpoint raíz. Útil para verificar que el servidor está vivo."""
    return {
        "status": "ok",
        "app": "La Web Definitiva",
        "version": "1.0.0",
    }


@app.get("/health")
async def health():
    """Health check para Railway y monitorización."""
    return {"status": "healthy", "timestamp": datetime.now(MADRID).isoformat()}


# --- HÁBITOS ---
@app.get("/api/habitos/{fecha}")
async def get_habitos(fecha: str):
    """
    Obtiene los hábitos de todos los usuarios para una fecha.
    La web llama aquí para mostrar el estado de los hábitos.
    
    Ejemplo: GET /api/habitos/2026-02-18
    """
    try:
        # Obtenemos los hábitos del primer usuario registrado (es app personal)
        usuarios = db.get_all_users()
        if not usuarios:
            return {"fecha": fecha, "habitos": {}, "mensaje": "No hay usuarios registrados"}

        chat_id = usuarios[0]["chat_id"]
        estados = db.get_habitos_hoy(chat_id, fecha)
        completados = sum(1 for v in estados.values() if v)

        return {
            "fecha": fecha,
            "habitos": estados,
            "completados": completados,
            "total": 5,
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/habitos/{fecha}/{habito}")
async def toggle_habito_api(fecha: str, habito: str):
    """
    Cambia el estado de un hábito desde la web.
    
    Ejemplo: POST /api/habitos/2026-02-18/leer
    """
    habitos_validos = ["leer", "meditar", "ducha", "ejercicio", "proyecto"]
    if habito not in habitos_validos:
        raise HTTPException(status_code=400, detail=f"Hábito no válido. Válidos: {habitos_validos}")

    usuarios = db.get_all_users()
    if not usuarios:
        raise HTTPException(status_code=404, detail="No hay usuarios registrados")

    chat_id = usuarios[0]["chat_id"]
    db.toggle_habito(chat_id, fecha, habito)
    estados = db.get_habitos_hoy(chat_id, fecha)

    return {"fecha": fecha, "habito": habito, "habitos": estados}


@app.get("/api/habitos/semana/{fecha}")
async def get_habitos_semana(fecha: str):
    """
    Obtiene los hábitos de los últimos 7 días desde la fecha dada.
    Útil para el dashboard semanal de la web.
    
    Ejemplo: GET /api/habitos/semana/2026-02-18
    """
    from datetime import timedelta

    usuarios = db.get_all_users()
    if not usuarios:
        return {"semana": [], "mensaje": "No hay usuarios registrados"}

    chat_id = usuarios[0]["chat_id"]

    try:
        fecha_base = datetime.strptime(fecha, "%Y-%m-%d")
    except ValueError:
        raise HTTPException(status_code=400, detail="Formato de fecha inválido. Usa YYYY-MM-DD")

    semana = []
    for i in range(6, -1, -1):
        dia = (fecha_base - timedelta(days=i)).strftime("%Y-%m-%d")
        estados = db.get_habitos_hoy(chat_id, dia)
        completados = sum(1 for v in estados.values() if v)
        semana.append({
            "fecha": dia,
            "habitos": estados,
            "completados": completados,
            "total": 5,
        })

    return {"semana": semana}


# --- EJERCICIOS ---
@app.get("/api/ejercicios")
async def get_ejercicios():
    """Obtiene todos los ejercicios guardados."""
    return {"ejercicios": db.get_ejercicios()}


@app.post("/api/ejercicios")
async def crear_ejercicio(data: dict):
    """
    Crea un nuevo ejercicio.
    
    Body: {"nombre": "Flexiones", "tipo": "Fuerza", "series": 3, "repeticiones": 15}
    """
    required = ["nombre", "tipo"]
    for field in required:
        if field not in data:
            raise HTTPException(status_code=400, detail=f"Campo requerido: {field}")

    ejercicio_id = db.crear_ejercicio(data)
    return {"id": ejercicio_id, "mensaje": "Ejercicio creado"}


@app.delete("/api/ejercicios/{ejercicio_id}")
async def borrar_ejercicio(ejercicio_id: int):
    """Borra un ejercicio por su ID."""
    db.borrar_ejercicio(ejercicio_id)
    return {"mensaje": "Ejercicio borrado"}


# --- LIBROS ---
@app.get("/api/libros")
async def get_libros():
    """Obtiene todos los libros."""
    return {"libros": db.get_libros()}


@app.post("/api/libros")
async def crear_libro(data: dict):
    """
    Crea un nuevo libro.
    
    Body: {"titulo": "Atomic Habits", "autor": "James Clear", "estado": "leyendo", "progreso": 45}
    """
    if "titulo" not in data:
        raise HTTPException(status_code=400, detail="Campo requerido: titulo")

    libro_id = db.crear_libro(data)
    return {"id": libro_id, "mensaje": "Libro creado"}


@app.put("/api/libros/{libro_id}")
async def actualizar_libro(libro_id: int, data: dict):
    """Actualiza un libro (progreso, estado, etc.)"""
    db.actualizar_libro(libro_id, data)
    return {"mensaje": "Libro actualizado"}


@app.delete("/api/libros/{libro_id}")
async def borrar_libro(libro_id: int):
    """Borra un libro por su ID."""
    db.borrar_libro(libro_id)
    return {"mensaje": "Libro borrado"}


# --- VIAJES ---
@app.get("/api/viajes")
async def get_viajes():
    """Obtiene todos los viajes."""
    return {"viajes": db.get_viajes()}


@app.post("/api/viajes")
async def crear_viaje(data: dict):
    """
    Crea un nuevo viaje.
    
    Body: {"destino": "Japón", "fecha_inicio": "2026-06-01", "presupuesto": 2000}
    """
    if "destino" not in data:
        raise HTTPException(status_code=400, detail="Campo requerido: destino")

    viaje_id = db.crear_viaje(data)
    return {"id": viaje_id, "mensaje": "Viaje creado"}


@app.delete("/api/viajes/{viaje_id}")
async def borrar_viaje(viaje_id: int):
    """Borra un viaje por su ID."""
    db.borrar_viaje(viaje_id)
    return {"mensaje": "Viaje borrado"}


# --- ESTADÍSTICAS GENERALES ---
@app.get("/api/stats")
async def get_stats():
    """
    Estadísticas generales para el dashboard de la web.
    Devuelve un resumen rápido de todo el sistema.
    """
    usuarios = db.get_all_users()
    hoy = datetime.now(MADRID).strftime("%Y-%m-%d")

    habitos_hoy = {}
    if usuarios:
        habitos_hoy = db.get_habitos_hoy(usuarios[0]["chat_id"], hoy)

    completados_hoy = sum(1 for v in habitos_hoy.values() if v)

    return {
        "fecha": hoy,
        "habitos_completados_hoy": completados_hoy,
        "habitos_total": 5,
        "libros_total": len(db.get_libros()),
        "libros_leyendo": len([l for l in db.get_libros() if l.get("estado") == "leyendo"]),
        "ejercicios_total": len(db.get_ejercicios()),
        "viajes_total": len(db.get_viajes()),
        "usuarios_registrados": len(usuarios),
    }
