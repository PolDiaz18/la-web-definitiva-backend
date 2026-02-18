"""
=============================================================================
DATABASE — BASE DE DATOS (SQLite)
=============================================================================
Este módulo maneja toda la persistencia de datos usando SQLite.

¿Qué es SQLite?
- Es una base de datos que vive en UN SOLO ARCHIVO (.db)
- No necesita instalar nada extra (viene con Python)
- Perfecta para apps personales
- Los datos sobreviven reinicios del servidor

¿Qué es SQL?
- SQL (Structured Query Language) es el lenguaje para hablar con bases de datos
- CREATE TABLE → Crear una tabla (como una hoja de Excel)
- INSERT → Añadir una fila
- SELECT → Leer datos
- UPDATE → Modificar datos
- DELETE → Borrar datos

Estructura de las tablas:
- users: Usuarios registrados en el bot (chat_id, nombre)
- habitos: Estado de cada hábito por día y usuario
- ejercicios: Planes de ejercicio
- libros: Biblioteca personal con progreso
- viajes: Planificación de viajes
=============================================================================
"""

import sqlite3
import json
import os
import logging
from datetime import datetime

logger = logging.getLogger(__name__)

# Ruta del archivo de base de datos
# En Railway, usamos /data/ si existe (volumen persistente), si no, el directorio actual
DB_PATH = os.environ.get("DB_PATH", "webdefinitiva.db")


class Database:
    """
    Clase que encapsula todas las operaciones de base de datos.
    
    ¿Por qué una clase y no funciones sueltas?
    - Agrupa toda la lógica de datos en un solo lugar
    - Facilita cambiar de SQLite a PostgreSQL en el futuro
    - Cada método es una operación atómica (se completa o no se hace)
    """

    def __init__(self):
        """El constructor solo guarda la ruta. La conexión se crea en init()."""
        self.db_path = DB_PATH

    def _get_conn(self):
        """
        Crea una nueva conexión a la base de datos.
        
        row_factory = sqlite3.Row → Permite acceder a columnas por nombre
        en vez de por índice. Ejemplo: row["nombre"] en vez de row[0]
        """
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def init(self):
        """
        Inicializa la base de datos creando las tablas si no existen.
        
        IF NOT EXISTS → Solo crea la tabla si no existe ya.
        Esto es importante porque se ejecuta cada vez que arranca el servidor.
        """
        conn = self._get_conn()
        cursor = conn.cursor()

        # --- Tabla de usuarios ---
        # Guarda a cada persona que ha hecho /start en el bot
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS users (
                chat_id INTEGER PRIMARY KEY,
                nombre TEXT,
                fecha_registro TEXT
            )
        """)

        # --- Tabla de hábitos ---
        # Una fila por cada hábito por cada día por cada usuario
        # Ejemplo: chat_id=123, fecha="2026-02-18", habito="leer", completado=1
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS habitos (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                chat_id INTEGER,
                fecha TEXT,
                habito TEXT,
                completado INTEGER DEFAULT 0,
                UNIQUE(chat_id, fecha, habito)
            )
        """)

        # --- Tabla de ejercicios ---
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS ejercicios (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                nombre TEXT NOT NULL,
                tipo TEXT,
                series INTEGER,
                repeticiones INTEGER,
                peso REAL,
                notas TEXT,
                fecha_creacion TEXT
            )
        """)

        # --- Tabla de libros ---
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS libros (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                titulo TEXT NOT NULL,
                autor TEXT,
                estado TEXT DEFAULT 'pendiente',
                progreso INTEGER DEFAULT 0,
                paginas_total INTEGER,
                notas TEXT,
                fecha_inicio TEXT,
                fecha_fin TEXT,
                fecha_creacion TEXT
            )
        """)

        # --- Tabla de viajes ---
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS viajes (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                destino TEXT NOT NULL,
                fecha_inicio TEXT,
                fecha_fin TEXT,
                presupuesto REAL,
                gastado REAL DEFAULT 0,
                notas TEXT,
                estado TEXT DEFAULT 'planificando',
                fecha_creacion TEXT
            )
        """)

        conn.commit()
        conn.close()
        logger.info(f"✅ Base de datos inicializada en {self.db_path}")

    # =================================================================
    # USUARIOS
    # =================================================================

    def register_user(self, chat_id: int, nombre: str):
        """
        Registra un nuevo usuario o actualiza su nombre.
        
        INSERT OR REPLACE: Si el chat_id ya existe, actualiza la fila.
        Si no existe, la crea. Así evitamos errores de duplicados.
        """
        conn = self._get_conn()
        conn.execute(
            "INSERT OR REPLACE INTO users (chat_id, nombre, fecha_registro) VALUES (?, ?, ?)",
            (chat_id, nombre, datetime.now().isoformat()),
        )
        conn.commit()
        conn.close()

    def get_all_users(self) -> list:
        """Devuelve todos los usuarios registrados."""
        conn = self._get_conn()
        rows = conn.execute("SELECT * FROM users").fetchall()
        conn.close()
        return [dict(row) for row in rows]

    # =================================================================
    # HÁBITOS
    # =================================================================

    def get_habitos_hoy(self, chat_id: int, fecha: str) -> dict:
        """
        Obtiene el estado de todos los hábitos para un usuario y fecha.
        
        Devuelve un diccionario como:
        {"leer": True, "meditar": False, "ducha": True, ...}
        
        Si un hábito no tiene registro para hoy, se asume False (no completado).
        """
        conn = self._get_conn()
        rows = conn.execute(
            "SELECT habito, completado FROM habitos WHERE chat_id = ? AND fecha = ?",
            (chat_id, fecha),
        ).fetchall()
        conn.close()

        # Empezamos con todos en False
        habitos_default = {
            "leer": False,
            "meditar": False,
            "ducha": False,
            "ejercicio": False,
            "proyecto": False,
        }

        # Actualizamos con los que tienen registro en la base de datos
        for row in rows:
            habitos_default[row["habito"]] = bool(row["completado"])

        return habitos_default

    def toggle_habito(self, chat_id: int, fecha: str, habito: str):
        """
        Cambia el estado de un hábito (toggle = invertir).
        Si estaba completado → lo marca como no completado, y viceversa.
        
        INSERT OR REPLACE: Crea o actualiza el registro.
        """
        conn = self._get_conn()

        # Primero, obtenemos el estado actual
        row = conn.execute(
            "SELECT completado FROM habitos WHERE chat_id = ? AND fecha = ? AND habito = ?",
            (chat_id, fecha, habito),
        ).fetchone()

        if row:
            # Existe → invertimos el valor (1→0, 0→1)
            nuevo_estado = 0 if row["completado"] else 1
            conn.execute(
                "UPDATE habitos SET completado = ? WHERE chat_id = ? AND fecha = ? AND habito = ?",
                (nuevo_estado, chat_id, fecha, habito),
            )
        else:
            # No existe → lo creamos como completado (1)
            conn.execute(
                "INSERT INTO habitos (chat_id, fecha, habito, completado) VALUES (?, ?, ?, 1)",
                (chat_id, fecha, habito),
            )

        conn.commit()
        conn.close()

    # =================================================================
    # EJERCICIOS
    # =================================================================

    def get_ejercicios(self) -> list:
        """Devuelve todos los ejercicios."""
        conn = self._get_conn()
        rows = conn.execute("SELECT * FROM ejercicios ORDER BY id DESC").fetchall()
        conn.close()
        return [dict(row) for row in rows]

    def crear_ejercicio(self, data: dict) -> int:
        """Crea un nuevo ejercicio y devuelve su ID."""
        conn = self._get_conn()
        cursor = conn.execute(
            """INSERT INTO ejercicios (nombre, tipo, series, repeticiones, peso, notas, fecha_creacion)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (
                data.get("nombre"),
                data.get("tipo"),
                data.get("series"),
                data.get("repeticiones"),
                data.get("peso"),
                data.get("notas"),
                datetime.now().isoformat(),
            ),
        )
        conn.commit()
        ejercicio_id = cursor.lastrowid
        conn.close()
        return ejercicio_id

    def borrar_ejercicio(self, ejercicio_id: int):
        """Borra un ejercicio por su ID."""
        conn = self._get_conn()
        conn.execute("DELETE FROM ejercicios WHERE id = ?", (ejercicio_id,))
        conn.commit()
        conn.close()

    # =================================================================
    # LIBROS
    # =================================================================

    def get_libros(self) -> list:
        """Devuelve todos los libros."""
        conn = self._get_conn()
        rows = conn.execute("SELECT * FROM libros ORDER BY id DESC").fetchall()
        conn.close()
        return [dict(row) for row in rows]

    def crear_libro(self, data: dict) -> int:
        """Crea un nuevo libro y devuelve su ID."""
        conn = self._get_conn()
        cursor = conn.execute(
            """INSERT INTO libros (titulo, autor, estado, progreso, paginas_total, notas, fecha_inicio, fecha_creacion)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                data.get("titulo"),
                data.get("autor"),
                data.get("estado", "pendiente"),
                data.get("progreso", 0),
                data.get("paginas_total"),
                data.get("notas"),
                data.get("fecha_inicio"),
                datetime.now().isoformat(),
            ),
        )
        conn.commit()
        libro_id = cursor.lastrowid
        conn.close()
        return libro_id

    def actualizar_libro(self, libro_id: int, data: dict):
        """
        Actualiza los campos de un libro.
        Solo actualiza los campos que vienen en 'data'.
        """
        conn = self._get_conn()
        campos_permitidos = ["titulo", "autor", "estado", "progreso", "paginas_total", "notas", "fecha_inicio", "fecha_fin"]

        updates = []
        values = []
        for campo in campos_permitidos:
            if campo in data:
                updates.append(f"{campo} = ?")
                values.append(data[campo])

        if updates:
            values.append(libro_id)
            query = f"UPDATE libros SET {', '.join(updates)} WHERE id = ?"
            conn.execute(query, values)
            conn.commit()

        conn.close()

    def borrar_libro(self, libro_id: int):
        """Borra un libro por su ID."""
        conn = self._get_conn()
        conn.execute("DELETE FROM libros WHERE id = ?", (libro_id,))
        conn.commit()
        conn.close()

    # =================================================================
    # VIAJES
    # =================================================================

    def get_viajes(self) -> list:
        """Devuelve todos los viajes."""
        conn = self._get_conn()
        rows = conn.execute("SELECT * FROM viajes ORDER BY id DESC").fetchall()
        conn.close()
        return [dict(row) for row in rows]

    def crear_viaje(self, data: dict) -> int:
        """Crea un nuevo viaje y devuelve su ID."""
        conn = self._get_conn()
        cursor = conn.execute(
            """INSERT INTO viajes (destino, fecha_inicio, fecha_fin, presupuesto, gastado, notas, estado, fecha_creacion)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                data.get("destino"),
                data.get("fecha_inicio"),
                data.get("fecha_fin"),
                data.get("presupuesto"),
                data.get("gastado", 0),
                data.get("notas"),
                data.get("estado", "planificando"),
                datetime.now().isoformat(),
            ),
        )
        conn.commit()
        viaje_id = cursor.lastrowid
        conn.close()
        return viaje_id

    def borrar_viaje(self, viaje_id: int):
        """Borra un viaje por su ID."""
        conn = self._get_conn()
        conn.execute("DELETE FROM viajes WHERE id = ?", (viaje_id,))
        conn.commit()
        conn.close()
