"""
=============================================================================
LA WEB DEFINITIVA — BACKEND (Versión 1: Mínima útil)
=============================================================================
Solo lo esencial:
- Registro + Login de usuarios
- Configurar hábitos personalizados
- Configurar rutinas personalizadas  
- Configurar horarios de recordatorios
- Bot de Telegram con recordatorios automáticos
- Tracking de hábitos diarios

Lo demás (libros, viajes, ejercicio, diario) lo añadimos después.
=============================================================================
"""

import os
import logging
import secrets
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, Depends
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, EmailStr

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, Bot
from telegram.ext import (
    Application, CommandHandler, CallbackQueryHandler, ContextTypes,
)

from database import Database
from config import CONFIG

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)

db = Database()


# =============================================================================
# MODELOS (Pydantic)
# =============================================================================
# Pydantic valida los datos que llegan a la API automáticamente.
# Si alguien envía un email mal formado, Pydantic lo rechaza antes
# de que llegue a tu código. Menos errores, menos trabajo.

class RegistroRequest(BaseModel):
    email: str
    password: str

class LoginRequest(BaseModel):
    email: str
    password: str

class NombreRequest(BaseModel):
    nombre: str

class HabitosConfigRequest(BaseModel):
    habitos: list  # [{"nombre": "Leer", "emoji": "📖"}, ...]

class RutinaConfigRequest(BaseModel):
    tipo: str      # "manana" o "noche"
    pasos: list    # [{"paso": "Ducha fría", "emoji": "🚿"}, ...]

class RecordatoriosConfigRequest(BaseModel):
    recordatorios: list  # [{"tipo": "manana", "hora": "07:00"}, ...]


# =============================================================================
# SESIONES SIMPLES
# =============================================================================
# En vez de JWT (complejo), usamos tokens simples en memoria.
# Cuando un usuario hace login, le damos un token aleatorio.
# Cada vez que hace una petición, nos envía ese token y sabemos quién es.
#
# Limitación: si el servidor se reinicia, todos tienen que hacer login de nuevo.
# Para la V1 es suficiente.

sesiones = {}  # {token: user_id}

def get_user_id(token: str) -> int:
    """Valida un token y devuelve el user_id. Si no es válido, lanza error."""
    if token not in sesiones:
        raise HTTPException(status_code=401, detail="No autenticado. Haz login primero.")
    return sesiones[token]


# =============================================================================
# BOT DE TELEGRAM
# =============================================================================

async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    /start en Telegram.
    Si viene con un código (ej: /start link_ABC123), vincula la cuenta.
    Si no, da la bienvenida.
    """
    chat_id = update.effective_chat.id
    args = context.args  # Lo que viene después de /start

    if args and args[0].startswith("link_"):
        # El usuario viene desde la web con un código de vinculación
        codigo = args[0]
        # Buscamos el código en los pendientes
        if codigo in codigos_vinculacion:
            user_id = codigos_vinculacion.pop(codigo)
            db.vincular_telegram(user_id, chat_id)
            user = db.get_user(user_id)
            nombre = user["nombre"] or "amigo"
            await update.message.reply_text(
                f"✅ ¡Cuenta vinculada, {nombre}!\n\n"
                f"A partir de ahora recibirás tus recordatorios aquí.\n\n"
                f"Comandos disponibles:\n"
                f"📋 /habitos — Marcar hábitos de hoy\n"
                f"📊 /resumen — Ver progreso\n"
                f"🌅 /manana — Tu rutina de mañana\n"
                f"🌙 /noche — Tu rutina de noche"
            )
        else:
            await update.message.reply_text(
                "❌ Código no válido o expirado.\n"
                "Genera uno nuevo desde la web."
            )
    else:
        await update.message.reply_text(
            "👋 ¡Hola! Soy el bot de La Web Definitiva.\n\n"
            "Para empezar, regístrate en la web y conecta tu Telegram desde ahí.\n\n"
            "Si ya tienes cuenta, ve a Configuración → Conectar Telegram."
        )


async def cmd_habitos(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Muestra los hábitos personalizados del usuario con botones."""
    chat_id = update.effective_chat.id
    user = db.get_user_by_telegram(chat_id)

    if not user:
        await update.message.reply_text("⚠️ No tienes cuenta vinculada. Regístrate en la web primero.")
        return

    user_id = user["id"]
    hoy = datetime.now(ZoneInfo("Europe/Madrid")).strftime("%Y-%m-%d")
    habitos = db.get_habitos_hoy(user_id, hoy)

    if not habitos:
        await update.message.reply_text("No tienes hábitos configurados. Configúralos en la web.")
        return

    keyboard = []
    for h in habitos:
        icono = "✅" if h["completado"] else "❌"
        keyboard.append([
            InlineKeyboardButton(
                f"{icono} {h['emoji']} {h['nombre']}",
                callback_data=f"hab_{h['id']}_toggle"
            )
        ])

    await update.message.reply_text(
        "📋 *HÁBITOS DE HOY*\n\nPulsa para marcar/desmarcar:",
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode="Markdown",
    )


async def callback_habito(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Cuando pulsan un botón de hábito."""
    query = update.callback_query
    await query.answer()

    chat_id = update.effective_chat.id
    user = db.get_user_by_telegram(chat_id)
    if not user:
        return

    user_id = user["id"]
    habito_id = int(query.data.split("_")[1])
    hoy = datetime.now(ZoneInfo("Europe/Madrid")).strftime("%Y-%m-%d")

    db.toggle_habito(user_id, habito_id, hoy)

    # Reconstruir botones
    habitos = db.get_habitos_hoy(user_id, hoy)
    keyboard = []
    for h in habitos:
        icono = "✅" if h["completado"] else "❌"
        keyboard.append([
            InlineKeyboardButton(
                f"{icono} {h['emoji']} {h['nombre']}",
                callback_data=f"hab_{h['id']}_toggle"
            )
        ])

    await query.edit_message_text(
        "📋 *HÁBITOS DE HOY*\n\nPulsa para marcar/desmarcar:",
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode="Markdown",
    )


async def cmd_resumen(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Resumen del día."""
    chat_id = update.effective_chat.id
    user = db.get_user_by_telegram(chat_id)
    if not user:
        await update.message.reply_text("⚠️ No tienes cuenta vinculada.")
        return

    user_id = user["id"]
    hoy = datetime.now(ZoneInfo("Europe/Madrid")).strftime("%Y-%m-%d")
    habitos = db.get_habitos_hoy(user_id, hoy)

    if not habitos:
        await update.message.reply_text("No tienes hábitos configurados.")
        return

    total = len(habitos)
    completados = sum(1 for h in habitos if h["completado"])

    lineas = [f"{'✅' if h['completado'] else '❌'} {h['emoji']} {h['nombre']}" for h in habitos]

    porcentaje = int((completados / total) * 100)
    barra = "█" * (porcentaje // 10) + "░" * (10 - porcentaje // 10)

    texto = (
        f"📊 *RESUMEN DE HOY* ({hoy})\n\n"
        + "\n".join(lineas)
        + f"\n\n{barra} {porcentaje}%"
        + f"\n{completados}/{total} completados"
    )

    await update.message.reply_text(texto, parse_mode="Markdown")


async def cmd_manana(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Muestra la rutina de mañana personalizada."""
    chat_id = update.effective_chat.id
    user = db.get_user_by_telegram(chat_id)
    if not user:
        await update.message.reply_text("⚠️ No tienes cuenta vinculada.")
        return

    pasos = db.get_rutina(user["id"], "manana")
    if not pasos:
        await update.message.reply_text("No tienes rutina de mañana configurada. Hazlo desde la web.")
        return

    lineas = [f"{i+1}. {p['emoji']} {p['paso']}" for i, p in enumerate(pasos)]
    texto = "🌅 *TU RUTINA DE MAÑANA*\n\n" + "\n".join(lineas) + "\n\n¡Vamos a por el día! 💪"
    await update.message.reply_text(texto, parse_mode="Markdown")


async def cmd_noche(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Muestra la rutina de noche personalizada."""
    chat_id = update.effective_chat.id
    user = db.get_user_by_telegram(chat_id)
    if not user:
        await update.message.reply_text("⚠️ No tienes cuenta vinculada.")
        return

    pasos = db.get_rutina(user["id"], "noche")
    if not pasos:
        await update.message.reply_text("No tienes rutina de noche configurada. Hazlo desde la web.")
        return

    lineas = [f"{i+1}. {p['emoji']} {p['paso']}" for i, p in enumerate(pasos)]
    texto = "🌙 *TU RUTINA DE NOCHE*\n\n" + "\n".join(lineas) + "\n\nDescansa bien 🌟"
    await update.message.reply_text(texto, parse_mode="Markdown")


# =============================================================================
# RECORDATORIOS AUTOMÁTICOS PERSONALIZADOS
# =============================================================================

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger

scheduler = AsyncIOScheduler()
telegram_app = None
codigos_vinculacion = {}  # {codigo: user_id} — para vincular Telegram


async def enviar_recordatorios_tipo(bot: Bot, tipo: str):
    """
    Busca todos los usuarios que tienen un recordatorio de este tipo
    configurado para AHORA y les envía el mensaje.
    """
    usuarios = db.get_all_users_with_telegram()
    ahora = datetime.now(ZoneInfo("Europe/Madrid"))
    hora_actual = ahora.strftime("%H:%M")

    for user in usuarios:
        user_id = user["id"]
        chat_id = user["telegram_chat_id"]
        recordatorios = db.get_recordatorios(user_id)

        for rec in recordatorios:
            if rec["tipo"] == tipo and rec["hora"] == hora_actual:
                try:
                    if tipo == "manana":
                        pasos = db.get_rutina(user_id, "manana")
                        if pasos:
                            lineas = [f"{i+1}. {p['emoji']} {p['paso']}" for i, p in enumerate(pasos)]
                            texto = "🌅 *¡Buenos días!*\n\n" + "\n".join(lineas) + "\n\n/habitos para empezar"
                        else:
                            texto = "🌅 *¡Buenos días!* Escribe /habitos para empezar el día."
                    elif tipo == "mediodia":
                        texto = "☀️ *¡Mediodía!* ¿Cómo llevas los hábitos?\n\nEscribe /resumen para ver tu progreso."
                    elif tipo == "noche":
                        pasos = db.get_rutina(user_id, "noche")
                        if pasos:
                            lineas = [f"{i+1}. {p['emoji']} {p['paso']}" for i, p in enumerate(pasos)]
                            texto = "🌙 *Rutina de noche*\n\n" + "\n".join(lineas)
                        else:
                            texto = "🌙 *Hora de descansar.* ¡Buenas noches!"
                    elif tipo == "resumen":
                        hoy = ahora.strftime("%Y-%m-%d")
                        habitos = db.get_habitos_hoy(user_id, hoy)
                        completados = sum(1 for h in habitos if h["completado"])
                        total = len(habitos)
                        lineas = [f"{'✅' if h['completado'] else '❌'} {h['emoji']} {h['nombre']}" for h in habitos]
                        texto = f"📊 *RESUMEN DEL DÍA*\n\n" + "\n".join(lineas) + f"\n\n{completados}/{total} completados\n\n😴 ¡Buenas noches!"
                    else:
                        continue

                    await bot.send_message(chat_id=chat_id, text=texto, parse_mode="Markdown")
                    logger.info(f"Recordatorio '{tipo}' enviado a user {user_id}")
                except Exception as e:
                    logger.error(f"Error enviando a user {user_id}: {e}")


def configurar_scheduler():
    """
    Ejecuta la comprobación de recordatorios cada minuto.
    Así detectamos la hora de cada usuario automáticamente.
    """
    bot = telegram_app.bot

    for tipo in ["manana", "mediodia", "noche", "resumen"]:
        scheduler.add_job(
            enviar_recordatorios_tipo,
            "interval",
            minutes=1,
            args=[bot, tipo],
            id=f"check_{tipo}",
            replace_existing=True,
        )

    logger.info("✅ Scheduler configurado (comprueba cada minuto)")


# =============================================================================
# FASTAPI — LIFESPAN
# =============================================================================

@asynccontextmanager
async def lifespan(app: FastAPI):
    global telegram_app

    logger.info("🚀 Arrancando...")
    db.init()

    if CONFIG["TELEGRAM_TOKEN"]:
        telegram_app = Application.builder().token(CONFIG["TELEGRAM_TOKEN"]).build()
        telegram_app.add_handler(CommandHandler("start", cmd_start))
        telegram_app.add_handler(CommandHandler("habitos", cmd_habitos))
        telegram_app.add_handler(CommandHandler("resumen", cmd_resumen))
        telegram_app.add_handler(CommandHandler("manana", cmd_manana))
        telegram_app.add_handler(CommandHandler("noche", cmd_noche))
        telegram_app.add_handler(CallbackQueryHandler(callback_habito, pattern="^hab_"))

        await telegram_app.initialize()
        await telegram_app.updater.start_polling(drop_pending_updates=True)
        await telegram_app.start()
        logger.info("✅ Bot de Telegram arrancado")

        configurar_scheduler()
        scheduler.start()
    else:
        logger.warning("⚠️ No hay TELEGRAM_TOKEN. Bot desactivado.")

    logger.info("🎉 Servidor listo")
    yield

    logger.info("🛑 Apagando...")
    if telegram_app:
        scheduler.shutdown()
        await telegram_app.updater.stop()
        await telegram_app.stop()
        await telegram_app.shutdown()


# =============================================================================
# FASTAPI — APP
# =============================================================================

app = FastAPI(title="La Web Definitiva", version="1.0.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# =============================================================================
# ENDPOINTS — AUTENTICACIÓN
# =============================================================================

@app.post("/api/registro")
async def registro(data: RegistroRequest):
    """Crea una cuenta nueva."""
    if len(data.password) < 6:
        raise HTTPException(status_code=400, detail="La contraseña debe tener al menos 6 caracteres")
    result = db.registrar_usuario(data.email, data.password)
    if not result["ok"]:
        raise HTTPException(status_code=400, detail=result["error"])

    # Auto-login después de registrarse
    token = secrets.token_hex(32)
    sesiones[token] = result["user_id"]
    return {"token": token, "user_id": result["user_id"]}


@app.post("/api/login")
async def login(data: LoginRequest):
    """Inicia sesión."""
    result = db.login_usuario(data.email, data.password)
    if not result["ok"]:
        raise HTTPException(status_code=401, detail=result["error"])

    token = secrets.token_hex(32)
    sesiones[token] = result["user"]["id"]
    return {"token": token, "user": result["user"]}


# =============================================================================
# ENDPOINTS — PERFIL
# =============================================================================

@app.get("/api/perfil")
async def get_perfil(token: str):
    """Obtiene el perfil del usuario autenticado."""
    user_id = get_user_id(token)
    user = db.get_user(user_id)
    if not user:
        raise HTTPException(status_code=404, detail="Usuario no encontrado")
    return user


@app.post("/api/perfil/nombre")
async def set_nombre(data: NombreRequest, token: str):
    """Actualiza el nombre."""
    user_id = get_user_id(token)
    db.actualizar_nombre(user_id, data.nombre)
    return {"ok": True}


# =============================================================================
# ENDPOINTS — CONFIGURACIÓN DE HÁBITOS
# =============================================================================

@app.get("/api/config/habitos")
async def get_config_habitos(token: str):
    """Devuelve los hábitos configurados del usuario."""
    user_id = get_user_id(token)
    return {"habitos": db.get_habitos_config(user_id)}


@app.post("/api/config/habitos")
async def set_config_habitos(data: HabitosConfigRequest, token: str):
    """Guarda los hábitos que el usuario quiere seguir."""
    user_id = get_user_id(token)
    db.guardar_habitos_config(user_id, data.habitos)
    return {"ok": True}


# =============================================================================
# ENDPOINTS — CONFIGURACIÓN DE RUTINAS
# =============================================================================

@app.get("/api/config/rutina/{tipo}")
async def get_config_rutina(tipo: str, token: str):
    """Devuelve la rutina de mañana o noche."""
    if tipo not in ["manana", "noche"]:
        raise HTTPException(status_code=400, detail="Tipo debe ser 'manana' o 'noche'")
    user_id = get_user_id(token)
    return {"pasos": db.get_rutina(user_id, tipo)}


@app.post("/api/config/rutina")
async def set_config_rutina(data: RutinaConfigRequest, token: str):
    """Guarda los pasos de una rutina."""
    if data.tipo not in ["manana", "noche"]:
        raise HTTPException(status_code=400, detail="Tipo debe ser 'manana' o 'noche'")
    user_id = get_user_id(token)
    db.guardar_rutina(user_id, data.tipo, data.pasos)
    return {"ok": True}


# =============================================================================
# ENDPOINTS — CONFIGURACIÓN DE RECORDATORIOS
# =============================================================================

@app.get("/api/config/recordatorios")
async def get_config_recordatorios(token: str):
    """Devuelve los recordatorios configurados."""
    user_id = get_user_id(token)
    return {"recordatorios": db.get_recordatorios(user_id)}


@app.post("/api/config/recordatorios")
async def set_config_recordatorios(data: RecordatoriosConfigRequest, token: str):
    """Guarda los horarios de recordatorios."""
    user_id = get_user_id(token)
    db.guardar_recordatorios(user_id, data.recordatorios)
    return {"ok": True}


# =============================================================================
# ENDPOINTS — HÁBITOS DIARIOS (TRACKING)
# =============================================================================

@app.get("/api/habitos/{fecha}")
async def get_habitos_dia(fecha: str, token: str):
    """Hábitos del usuario para un día concreto."""
    user_id = get_user_id(token)
    habitos = db.get_habitos_hoy(user_id, fecha)
    completados = sum(1 for h in habitos if h["completado"])
    return {"fecha": fecha, "habitos": habitos, "completados": completados, "total": len(habitos)}


@app.post("/api/habitos/{fecha}/{habito_id}")
async def toggle_habito_dia(fecha: str, habito_id: int, token: str):
    """Marca/desmarca un hábito."""
    user_id = get_user_id(token)
    db.toggle_habito(user_id, habito_id, fecha)
    return {"ok": True}


@app.get("/api/habitos/semana/{fecha}")
async def get_habitos_semana(fecha: str, token: str):
    """Hábitos de los últimos 7 días."""
    user_id = get_user_id(token)
    try:
        fecha_base = datetime.strptime(fecha, "%Y-%m-%d")
    except ValueError:
        raise HTTPException(status_code=400, detail="Formato: YYYY-MM-DD")

    semana = []
    for i in range(6, -1, -1):
        dia = (fecha_base - timedelta(days=i)).strftime("%Y-%m-%d")
        habitos = db.get_habitos_hoy(user_id, dia)
        completados = sum(1 for h in habitos if h["completado"])
        semana.append({"fecha": dia, "habitos": habitos, "completados": completados, "total": len(habitos)})
    return {"semana": semana}


# =============================================================================
# ENDPOINTS — VINCULAR TELEGRAM
# =============================================================================

@app.post("/api/telegram/generar-codigo")
async def generar_codigo_telegram(token: str):
    """
    Genera un código único para vincular Telegram.
    El usuario abre el bot con: t.me/TU_BOT?start=link_CODIGO
    """
    user_id = get_user_id(token)
    codigo = f"link_{secrets.token_hex(8)}"
    codigos_vinculacion[codigo] = user_id
    
    bot_username = ""
    if telegram_app:
        bot_info = await telegram_app.bot.get_me()
        bot_username = bot_info.username

    return {
        "codigo": codigo,
        "enlace": f"https://t.me/{bot_username}?start={codigo}" if bot_username else None,
        "instrucciones": "Abre este enlace en Telegram para vincular tu cuenta.",
    }


# =============================================================================
# ENDPOINTS — ONBOARDING
# =============================================================================

@app.post("/api/onboarding/completar")
async def completar_onboarding(token: str):
    """Marca que el usuario ha terminado el cuestionario."""
    user_id = get_user_id(token)
    db.marcar_onboarding_completado(user_id)
    return {"ok": True}


# =============================================================================
# HEALTH CHECK
# =============================================================================

@app.get("/")
async def root():
    return {"status": "ok", "app": "La Web Definitiva", "version": "1.0.0"}

@app.get("/health")
async def health():
    return {"status": "healthy"}
