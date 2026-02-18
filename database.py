"""
=============================================================================
DATABASE — BASE DE DATOS (SQLite)
=============================================================================
Maneja toda la persistencia de datos.

TABLAS:
- users → Cuenta del usuario (email, contraseña, nombre)
- user_config → Configuración personal (zona horaria, idioma)
- habitos_config → Qué hábitos sigue cada usuario (personalizados)
- rutinas_config → Pasos de rutina mañana/noche (personalizados)
- recordatorios_config → A qué horas quiere los avisos
- habitos_diarios → Estado de cada hábito por día
- ejercicios → Planes de entrenamiento
- libros → Biblioteca personal
- viajes → Planificación de viajes
- objetivos → Metas personales
- diario → Entradas de diario

CONCEPTOS:
- Cada tabla tiene user_id → vincula los datos a UN usuario concreto
- Las contraseñas se guardan HASHEADAS (encriptadas), nunca en texto plano
- AUTOINCREMENT → el ID se genera solo, no lo pones tú
=============================================================================
"""

import sqlite3
import os
import logging
import hashlib
import secrets
from datetime import datetime

logger = logging.getLogger(__name__)

DB_PATH = os.environ.get("DB_PATH", "webdefinitiva.db")


class Database:

    def __init__(self):
        self.db_path = DB_PATH

    def _get_conn(self):
        """Crea conexión a SQLite. row_factory=Row para acceder por nombre de columna."""
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        return conn

    def init(self):
        """Crea todas las tablas si no existen."""
        conn = self._get_conn()
        c = conn.cursor()

        # --- USUARIOS ---
        c.execute("""
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                email TEXT UNIQUE NOT NULL,
                password_hash TEXT NOT NULL,
                salt TEXT NOT NULL,
                nombre TEXT,
                fecha_registro TEXT,
                onboarding_completado INTEGER DEFAULT 0,
                telegram_chat_id INTEGER
            )
        """)

        # --- CONFIGURACIÓN DEL USUARIO ---
        c.execute("""
            CREATE TABLE IF NOT EXISTS user_config (
                user_id INTEGER PRIMARY KEY,
                zona_horaria TEXT DEFAULT 'Europe/Madrid',
                idioma TEXT DEFAULT 'es',
                FOREIGN KEY (user_id) REFERENCES users(id)
            )
        """)

        # --- HÁBITOS CONFIGURADOS ---
        c.execute("""
            CREATE TABLE IF NOT EXISTS habitos_config (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                nombre TEXT NOT NULL,
                emoji TEXT DEFAULT '✅',
                orden INTEGER DEFAULT 0,
                activo INTEGER DEFAULT 1,
                FOREIGN KEY (user_id) REFERENCES users(id)
            )
        """)

        # --- RUTINAS CONFIGURADAS ---
        c.execute("""
            CREATE TABLE IF NOT EXISTS rutinas_config (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                tipo TEXT NOT NULL,
                paso TEXT NOT NULL,
                emoji TEXT DEFAULT '▪️',
                orden INTEGER DEFAULT 0,
                FOREIGN KEY (user_id) REFERENCES users(id)
            )
        """)

        # --- RECORDATORIOS CONFIGURADOS ---
        c.execute("""
            CREATE TABLE IF NOT EXISTS recordatorios_config (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                tipo TEXT NOT NULL,
                hora TEXT NOT NULL,
                activo INTEGER DEFAULT 1,
                FOREIGN KEY (user_id) REFERENCES users(id)
            )
        """)

        # --- HÁBITOS DIARIOS ---
        c.execute("""
            CREATE TABLE IF NOT EXISTS habitos_diarios (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                habito_config_id INTEGER NOT NULL,
                fecha TEXT NOT NULL,
                completado INTEGER DEFAULT 0,
                UNIQUE(user_id, habito_config_id, fecha),
                FOREIGN KEY (user_id) REFERENCES users(id),
                FOREIGN KEY (habito_config_id) REFERENCES habitos_config(id)
            )
        """)

        # --- EJERCICIOS ---
        c.execute("""
            CREATE TABLE IF NOT EXISTS ejercicios (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                nombre TEXT NOT NULL,
                tipo TEXT,
                series INTEGER,
                repeticiones INTEGER,
                peso REAL,
                notas TEXT,
                fecha_creacion TEXT,
                FOREIGN KEY (user_id) REFERENCES users(id)
            )
        """)

        # --- LIBROS ---
        c.execute("""
            CREATE TABLE IF NOT EXISTS libros (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                titulo TEXT NOT NULL,
                autor TEXT,
                estado TEXT DEFAULT 'pendiente',
                progreso INTEGER DEFAULT 0,
                paginas_total INTEGER,
                notas TEXT,
                fecha_inicio TEXT,
                fecha_fin TEXT,
                fecha_creacion TEXT,
                FOREIGN KEY (user_id) REFERENCES users(id)
            )
        """)

        # --- VIAJES ---
        c.execute("""
            CREATE TABLE IF NOT EXISTS viajes (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                destino TEXT NOT NULL,
                fecha_inicio TEXT,
                fecha_fin TEXT,
                presupuesto REAL,
                gastado REAL DEFAULT 0,
                notas TEXT,
                estado TEXT DEFAULT 'planificando',
                fecha_creacion TEXT,
                FOREIGN KEY (user_id) REFERENCES users(id)
            )
        """)

        # --- OBJETIVOS ---
        c.execute("""
            CREATE TABLE IF NOT EXISTS objetivos (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                titulo TEXT NOT NULL,
                descripcion TEXT,
                categoria TEXT,
                fecha_limite TEXT,
                progreso INTEGER DEFAULT 0,
                completado INTEGER DEFAULT 0,
                fecha_creacion TEXT,
                FOREIGN KEY (user_id) REFERENCES users(id)
            )
        """)

        # --- DIARIO ---
        c.execute("""
            CREATE TABLE IF NOT EXISTS diario (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                fecha TEXT NOT NULL,
                contenido TEXT,
                estado_animo TEXT,
                fecha_creacion TEXT,
                FOREIGN KEY (user_id) REFERENCES users(id)
            )
        """)

        conn.commit()
        conn.close()
        logger.info(f"✅ Base de datos inicializada en {self.db_path}")

    # =================================================================
    # AUTENTICACIÓN
    # =================================================================

    def _hash_password(self, password: str, salt: str) -> str:
        """Encripta la contraseña con salt para seguridad."""
        return hashlib.sha256((salt + password).encode()).hexdigest()

    def registrar_usuario(self, email: str, password: str, nombre: str = None) -> dict:
        """Registra un nuevo usuario. Devuelve {"ok": True/False, ...}"""
        conn = self._get_conn()
        try:
            salt = secrets.token_hex(16)
            password_hash = self._hash_password(password, salt)
            cursor = conn.execute(
                """INSERT INTO users (email, password_hash, salt, nombre, fecha_registro)
                   VALUES (?, ?, ?, ?, ?)""",
                (email.lower().strip(), password_hash, salt, nombre, datetime.now().isoformat()),
            )
            user_id = cursor.lastrowid
            conn.execute("INSERT INTO user_config (user_id) VALUES (?)", (user_id,))
            conn.commit()
            return {"ok": True, "user_id": user_id}
        except sqlite3.IntegrityError:
            return {"ok": False, "error": "Ya existe una cuenta con ese email"}
        finally:
            conn.close()

    def login_usuario(self, email: str, password: str) -> dict:
        """Verifica email + contraseña."""
        conn = self._get_conn()
        row = conn.execute("SELECT * FROM users WHERE email = ?", (email.lower().strip(),)).fetchone()
        conn.close()
        if not row:
            return {"ok": False, "error": "Email o contraseña incorrectos"}
        password_hash = self._hash_password(password, row["salt"])
        if password_hash != row["password_hash"]:
            return {"ok": False, "error": "Email o contraseña incorrectos"}
        return {
            "ok": True,
            "user": {
                "id": row["id"], "email": row["email"], "nombre": row["nombre"],
                "onboarding_completado": bool(row["onboarding_completado"]),
            },
        }

    # =================================================================
    # PERFIL Y CONFIGURACIÓN
    # =================================================================

    def get_user(self, user_id: int) -> dict:
        conn = self._get_conn()
        row = conn.execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()
        conn.close()
        if not row:
            return None
        return {
            "id": row["id"], "email": row["email"], "nombre": row["nombre"],
            "onboarding_completado": bool(row["onboarding_completado"]),
            "telegram_conectado": row["telegram_chat_id"] is not None,
        }

    def actualizar_nombre(self, user_id: int, nombre: str):
        conn = self._get_conn()
        conn.execute("UPDATE users SET nombre = ? WHERE id = ?", (nombre, user_id))
        conn.commit()
        conn.close()

    def marcar_onboarding_completado(self, user_id: int):
        conn = self._get_conn()
        conn.execute("UPDATE users SET onboarding_completado = 1 WHERE id = ?", (user_id,))
        conn.commit()
        conn.close()

    # =================================================================
    # HÁBITOS — CONFIGURACIÓN
    # =================================================================

    def guardar_habitos_config(self, user_id: int, habitos: list):
        conn = self._get_conn()
        conn.execute("DELETE FROM habitos_config WHERE user_id = ?", (user_id,))
        for i, h in enumerate(habitos):
            conn.execute(
                "INSERT INTO habitos_config (user_id, nombre, emoji, orden) VALUES (?, ?, ?, ?)",
                (user_id, h["nombre"], h.get("emoji", "✅"), i),
            )
        conn.commit()
        conn.close()

    def get_habitos_config(self, user_id: int) -> list:
        conn = self._get_conn()
        rows = conn.execute(
            "SELECT * FROM habitos_config WHERE user_id = ? AND activo = 1 ORDER BY orden", (user_id,)
        ).fetchall()
        conn.close()
        return [dict(r) for r in rows]

    # =================================================================
    # RUTINAS — CONFIGURACIÓN
    # =================================================================

    def guardar_rutina(self, user_id: int, tipo: str, pasos: list):
        conn = self._get_conn()
        conn.execute("DELETE FROM rutinas_config WHERE user_id = ? AND tipo = ?", (user_id, tipo))
        for i, p in enumerate(pasos):
            conn.execute(
                "INSERT INTO rutinas_config (user_id, tipo, paso, emoji, orden) VALUES (?, ?, ?, ?, ?)",
                (user_id, tipo, p["paso"], p.get("emoji", "▪️"), i),
            )
        conn.commit()
        conn.close()

    def get_rutina(self, user_id: int, tipo: str) -> list:
        conn = self._get_conn()
        rows = conn.execute(
            "SELECT * FROM rutinas_config WHERE user_id = ? AND tipo = ? ORDER BY orden", (user_id, tipo)
        ).fetchall()
        conn.close()
        return [dict(r) for r in rows]

    # =================================================================
    # RECORDATORIOS — CONFIGURACIÓN
    # =================================================================

    def guardar_recordatorios(self, user_id: int, recordatorios: list):
        conn = self._get_conn()
        conn.execute("DELETE FROM recordatorios_config WHERE user_id = ?", (user_id,))
        for r in recordatorios:
            conn.execute(
                "INSERT INTO recordatorios_config (user_id, tipo, hora) VALUES (?, ?, ?)",
                (user_id, r["tipo"], r["hora"]),
            )
        conn.commit()
        conn.close()

    def get_recordatorios(self, user_id: int) -> list:
        conn = self._get_conn()
        rows = conn.execute(
            "SELECT * FROM recordatorios_config WHERE user_id = ? AND activo = 1", (user_id,)
        ).fetchall()
        conn.close()
        return [dict(r) for r in rows]

    # =================================================================
    # HÁBITOS DIARIOS — TRACKING
    # =================================================================

    def get_habitos_hoy(self, user_id: int, fecha: str) -> list:
        conn = self._get_conn()
        rows = conn.execute("""
            SELECT hc.id, hc.nombre, hc.emoji, COALESCE(hd.completado, 0) as completado
            FROM habitos_config hc
            LEFT JOIN habitos_diarios hd ON hc.id = hd.habito_config_id AND hd.fecha = ? AND hd.user_id = ?
            WHERE hc.user_id = ? AND hc.activo = 1
            ORDER BY hc.orden
        """, (fecha, user_id, user_id)).fetchall()
        conn.close()
        return [{"id": r["id"], "nombre": r["nombre"], "emoji": r["emoji"], "completado": bool(r["completado"])} for r in rows]

    def toggle_habito(self, user_id: int, habito_config_id: int, fecha: str):
        conn = self._get_conn()
        row = conn.execute(
            "SELECT completado FROM habitos_diarios WHERE user_id = ? AND habito_config_id = ? AND fecha = ?",
            (user_id, habito_config_id, fecha),
        ).fetchone()
        if row:
            nuevo = 0 if row["completado"] else 1
            conn.execute(
                "UPDATE habitos_diarios SET completado = ? WHERE user_id = ? AND habito_config_id = ? AND fecha = ?",
                (nuevo, user_id, habito_config_id, fecha),
            )
        else:
            conn.execute(
                "INSERT INTO habitos_diarios (user_id, habito_config_id, fecha, completado) VALUES (?, ?, ?, 1)",
                (user_id, habito_config_id, fecha),
            )
        conn.commit()
        conn.close()

    # =================================================================
    # TELEGRAM
    # =================================================================

    def vincular_telegram(self, user_id: int, chat_id: int):
        conn = self._get_conn()
        conn.execute("UPDATE users SET telegram_chat_id = ? WHERE id = ?", (chat_id, user_id))
        conn.commit()
        conn.close()

    def get_user_by_telegram(self, chat_id: int) -> dict:
        conn = self._get_conn()
        row = conn.execute("SELECT * FROM users WHERE telegram_chat_id = ?", (chat_id,)).fetchone()
        conn.close()
        return dict(row) if row else None

    def get_all_users_with_telegram(self) -> list:
        conn = self._get_conn()
        rows = conn.execute("SELECT * FROM users WHERE telegram_chat_id IS NOT NULL").fetchall()
        conn.close()
        return [dict(r) for r in rows]

    # =================================================================
    # ITEMS GENÉRICOS (ejercicios, libros, viajes, objetivos, diario)
    # =================================================================

    def get_items(self, tabla: str, user_id: int) -> list:
        tablas_validas = ["ejercicios", "libros", "viajes", "objetivos", "diario"]
        if tabla not in tablas_validas:
            return []
        conn = self._get_conn()
        rows = conn.execute(f"SELECT * FROM {tabla} WHERE user_id = ? ORDER BY id DESC", (user_id,)).fetchall()
        conn.close()
        return [dict(r) for r in rows]

    def crear_item(self, tabla: str, user_id: int, data: dict) -> int:
        tablas_validas = ["ejercicios", "libros", "viajes", "objetivos", "diario"]
        if tabla not in tablas_validas:
            return None
        data["user_id"] = user_id
        data["fecha_creacion"] = datetime.now().isoformat()
        conn = self._get_conn()
        campos = ", ".join(data.keys())
        placeholders = ", ".join(["?"] * len(data))
        cursor = conn.execute(f"INSERT INTO {tabla} ({campos}) VALUES ({placeholders})", list(data.values()))
        conn.commit()
        item_id = cursor.lastrowid
        conn.close()
        return item_id

    def borrar_item(self, tabla: str, user_id: int, item_id: int):
        tablas_validas = ["ejercicios", "libros", "viajes", "objetivos", "diario"]
        if tabla not in tablas_validas:
            return
        conn = self._get_conn()
        conn.execute(f"DELETE FROM {tabla} WHERE id = ? AND user_id = ?", (item_id, user_id))
        conn.commit()
        conn.close()
