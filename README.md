# 🚀 La Web Definitiva — Backend

Backend del sistema de productividad personal. Incluye:

- **Bot de Telegram** con rutinas, hábitos y recordatorios automáticos
- **API REST** para conectar la web (dashboard)
- **Base de datos SQLite** para persistir todo

## 📁 Estructura del proyecto

```
├── main.py          # Aplicación principal (FastAPI + Bot)
├── database.py      # Operaciones de base de datos (SQLite)
├── config.py        # Configuración (variables de entorno)
├── requirements.txt # Dependencias de Python
├── Procfile         # Instrucciones de arranque para Railway
├── runtime.txt      # Versión de Python
└── .gitignore       # Archivos ignorados por Git
```

## 🏠 Ejecutar en local

```bash
# 1. Instalar dependencias
pip install -r requirements.txt

# 2. Configurar el token del bot
export TELEGRAM_TOKEN="tu-token-aquí"

# 3. Arrancar el servidor
uvicorn main:app --reload --port 8000
```

## 🚂 Desplegar en Railway

1. Sube este código a un repositorio de GitHub
2. Ve a [railway.app](https://railway.app) y crea un nuevo proyecto
3. Conecta tu repositorio de GitHub
4. Añade la variable de entorno: `TELEGRAM_TOKEN=tu-token`
5. Railway despliega automáticamente

## 📡 Endpoints de la API

| Método | Ruta | Descripción |
|--------|------|-------------|
| GET | `/` | Health check |
| GET | `/api/stats` | Estadísticas del dashboard |
| GET | `/api/habitos/{fecha}` | Hábitos de un día |
| POST | `/api/habitos/{fecha}/{habito}` | Toggle un hábito |
| GET | `/api/habitos/semana/{fecha}` | Hábitos de la semana |
| GET | `/api/ejercicios` | Listar ejercicios |
| POST | `/api/ejercicios` | Crear ejercicio |
| DELETE | `/api/ejercicios/{id}` | Borrar ejercicio |
| GET | `/api/libros` | Listar libros |
| POST | `/api/libros` | Crear libro |
| PUT | `/api/libros/{id}` | Actualizar libro |
| DELETE | `/api/libros/{id}` | Borrar libro |
| GET | `/api/viajes` | Listar viajes |
| POST | `/api/viajes` | Crear viaje |
| DELETE | `/api/viajes/{id}` | Borrar viaje |

## 🤖 Comandos del Bot

| Comando | Descripción |
|---------|-------------|
| `/start` | Registrarse y ver ayuda |
| `/manana` | Rutina de mañana |
| `/noche` | Rutina de noche |
| `/habitos` | Marcar hábitos con botones |
| `/resumen` | Resumen del día |

## ⏰ Recordatorios automáticos

- **7:00** — Rutina de mañana
- **14:00** — ¿Cómo llevas los hábitos?
- **22:00** — Rutina de noche
- **22:30** — Resumen del día
