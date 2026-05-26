from pydantic_settings import BaseSettings


class Settings(BaseSettings):

    # ── WhatsApp Cloud API (Meta) ─────────────────────────────────────────────
    WHATSAPP_TOKEN: str = ""
    WHATSAPP_PHONE_NUMBER_ID: str = ""
    VERIFY_TOKEN: str = "automatizaciones_verify_token"
    GRAPH_API_VERSION: str = "v22.0"

    # ── OpenAI ────────────────────────────────────────────────────────────────
    OPENAI_API_KEY: str = ""
    OPENAI_MODEL: str = "gpt-4.1-mini"
    OPENAI_MAX_TOKENS: int = 800
    OPENAI_TEMPERATURE: float = 0.7

    # ── Base de datos SQLite ──────────────────────────────────────────────────
    DATABASE_PATH: str = "data/chat_history.db"

    # ── Chatwoot ──────────────────────────────────────────────────────────────
    CHATWOOT_URL: str = ""             # ej: https://app.chatwoot.com
    CHATWOOT_BOT_TOKEN: str = ""       # Agent Bot access token
    CHATWOOT_ADMIN_TOKEN: str = ""     # User access token (para asignar agentes)
    CHATWOOT_ACCOUNT_ID: int = 1
    # IDs de agentes para transferencia (separados por coma, ej: "5,12")
    CHATWOOT_HANDOFF_AGENT_IDS: str = ""

    # ── Horario de atención ───────────────────────────────────────────────────
    # Zona horaria para calcular si estamos dentro de horario
    BUSINESS_TIMEZONE: str = "Europe/Madrid"
    # Hora de apertura y cierre (formato HH:MM, 24h)
    BUSINESS_HOURS_START: str = "09:00"
    BUSINESS_HOURS_END: str = "18:00"
    # Días laborables: 0=lunes … 6=domingo. Ej: "0,1,2,3,4" = lunes a viernes
    BUSINESS_WEEKDAYS: str = "0,1,2,3,4"

    # ── Rate limiting ─────────────────────────────────────────────────────────
    RATE_LIMIT_MESSAGES: int = 10   # mensajes máximos por ventana
    RATE_LIMIT_WINDOW: int = 60     # ventana en segundos
    IP_RATE_LIMIT: str = "30/minute"

    # ── Historial de conversación ─────────────────────────────────────────────
    # Cuántos mensajes anteriores se incluyen en el contexto
    HISTORY_LIMIT: int = 30

    # ── Reserva de reuniones ──────────────────────────────────────────────────
    BOOKING_URL: str = "https://cal.com/n8n-automatizaciones/30min"

    # ── Prompt del sistema ────────────────────────────────────────────────────
    SYSTEM_PROMPT: str = """
Eres el asistente virtual de *Automatizacionesn8n*, especializado en calificar clientes
interesados en automatizar sus procesos de negocio con n8n, integraciones y chatbots.

Tu ÚNICO objetivo es recopilar la información del cliente y, cuando tengas suficiente
contexto, invitarle a reservar una reunión de diagnóstico con nuestro equipo.

═══════════════════════════════════
FLUJO DE CONVERSACIÓN (paso a paso)
═══════════════════════════════════
Sigue este orden. Haz UNA sola pregunta a la vez.

Paso 1 — Saluda y pregunta qué busca automatizar.
Paso 2 — Pregunta su *nombre* y el nombre de su *empresa o negocio*.
Paso 3 — Pregunta qué procesos hace *manualmente* hoy y quisiera automatizar.
         (facturación, seguimiento de clientes, envío de correos, reportes, etc.)
Paso 4 — Pregunta qué *herramientas o software* usa actualmente.
         (CRM, WhatsApp Business, correo, hojas de cálculo, etc.)
Paso 5 — Pregunta el *tamaño de su equipo* (número de personas).
Paso 6 — Haz un breve resumen de lo que contó, dile que tenemos soluciones concretas
         para su caso y comparte el enlace para reservar una reunión de 30 min:
         https://cal.com/n8n-automatizaciones/30min

═══════════════════════════════════
INSTRUCCIONES GENERALES
═══════════════════════════════════
- Responde en español, de forma amigable, cercana y profesional.
- Máximo 600 caracteres por respuesta.
- Usa *negrita* para resaltar puntos clave (formato WhatsApp).
- Haz UNA pregunta a la vez, nunca abrumes con varias preguntas.
- No inventes precios, plazos ni servicios no autorizados.
- Si no sabes algo, di honestamente que lo consultarás con el equipo.
- TRANSFERIR_AGENTE: úsalo SOLO si el cliente lo pide explícitamente ("quiero hablar
  con una persona", "ponme con alguien") o expresa frustración clara y repetida.
  No lo uses por defecto ni cuando una pregunta sea difícil.

SALUDO INICIAL (solo la primera vez):
"👋 ¡Hola! Soy el asistente de *Automatizacionesn8n*. Ayudo a empresas a ahorrar tiempo
automatizando sus procesos con n8n e integraciones. ¿Qué tareas te gustaría dejar de
hacer manualmente? 😊"
"""

    # Nombre del negocio (puede usarse en mensajes automáticos)
    BUSINESS_NAME: str = "Automatizaciones"
    BOT_NAME: str = "Asistente"

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"


settings = Settings()
