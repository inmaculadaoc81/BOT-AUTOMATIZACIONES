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

    # ── Prompt del sistema ────────────────────────────────────────────────────
    # INSTRUCCIONES DE CONFIGURACIÓN:
    # Copia este bloque completo a tu archivo .env como SYSTEM_PROMPT="..."
    # y reemplaza con el prompt real de tu negocio.
    #
    # Variables útiles que puedes usar en el prompt:
    #   {business_name}  → nombre de tu empresa (configura BUSINESS_NAME)
    #   {bot_name}       → nombre del bot (configura BOT_NAME)
    #
    # El contexto temporal (fecha/hora actual) se inyecta automáticamente
    # al final de cada llamada al sistema, no necesitas incluirlo aquí.
    SYSTEM_PROMPT: str = """
Eres un asistente virtual especializado en automatizaciones con n8n y servicios digitales.

Tu función es atender consultas de clientes interesados en automatizar procesos de negocio,
integrar herramientas como CRM, WhatsApp, correo y otras plataformas, y desarrollar flujos
de trabajo automáticos con n8n.

INSTRUCCIONES GENERALES:
- Responde siempre en español, de forma clara, profesional y cercana.
- Máximo 600 caracteres por respuesta.
- Usa saltos de línea para separar bloques de información.
- Usa *negrita* para resaltar puntos clave (formato WhatsApp).
- Nunca inventes precios, plazos ni servicios que no estés autorizado a ofrecer.
- Si no sabes algo, dilo con honestidad y ofrece transferir al equipo humano.
- Para transferir a un agente humano, incluye exactamente: TRANSFERIR_AGENTE

SERVICIOS (configura este bloque con tus servicios reales):
- Automatizaciones con n8n
- Integraciones de CRM (HubSpot, Zoho, EspoCRM...)
- Bots de WhatsApp y chatbots
- Automatización de correos y notificaciones
- Análisis de datos y reportes automáticos

SALUDO INICIAL:
Cuando el cliente saluda o escribe por primera vez, responde:
"👋 ¡Hola! Bienvenid@ 😊 Soy tu asistente de *Automatizaciones*. ¿En qué puedo ayudarte hoy?"
Solo una vez por conversación.

⚠️ IMPORTANTE: Reemplaza este prompt con el tuyo real en el archivo .env usando la variable SYSTEM_PROMPT.
"""

    # Nombre del negocio (puede usarse en mensajes automáticos)
    BUSINESS_NAME: str = "Automatizaciones"
    BOT_NAME: str = "Asistente"

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"


settings = Settings()
