import logging
import re
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from openai import AsyncOpenAI

from config import settings

logger = logging.getLogger(__name__)


def _build_temporal_context() -> str:
    """Build a temporal context block injected at the end of every system prompt."""
    tz = ZoneInfo(settings.BUSINESS_TIMEZONE)
    now = datetime.now(tz)

    days_es = ["lunes", "martes", "miércoles", "jueves", "viernes", "sábado", "domingo"]
    months_es = [
        "enero", "febrero", "marzo", "abril", "mayo", "junio",
        "julio", "agosto", "septiembre", "octubre", "noviembre", "diciembre",
    ]

    weekday_name = days_es[now.weekday()]
    month_name = months_es[now.month - 1]
    fecha = f"{weekday_name} {now.day} de {month_name} de {now.year}"
    hora = now.strftime("%H:%M")

    # Business hours check
    try:
        start_h, start_m = map(int, settings.BUSINESS_HOURS_START.split(":"))
        end_h, end_m = map(int, settings.BUSINESS_HOURS_END.split(":"))
        weekdays = [int(d) for d in settings.BUSINESS_WEEKDAYS.split(",") if d.strip().isdigit()]
    except Exception:
        start_h, start_m = 9, 0
        end_h, end_m = 18, 0
        weekdays = [0, 1, 2, 3, 4]

    mins = now.hour * 60 + now.minute
    is_open = (
        now.weekday() in weekdays
        and (start_h * 60 + start_m) <= mins < (end_h * 60 + end_m)
    )
    estado = "ABIERTO" if is_open else "CERRADO"
    horario = f"{settings.BUSINESS_HOURS_START}-{settings.BUSINESS_HOURS_END}"

    # Next opening moment
    if now.weekday() in weekdays and mins < (start_h * 60 + start_m):
        proximo = f"hoy a las {settings.BUSINESS_HOURS_START}"
    else:
        candidate = now + timedelta(days=1)
        for _ in range(14):
            if candidate.weekday() in weekdays:
                break
            candidate += timedelta(days=1)
        diff = (candidate.date() - now.date()).days
        day_name = days_es[candidate.weekday()]
        day_num = candidate.day
        mon_name = months_es[candidate.month - 1]
        if diff == 1:
            proximo = f"mañana {day_name} {day_num} de {mon_name} a las {settings.BUSINESS_HOURS_START}"
        else:
            proximo = f"el {day_name} {day_num} de {mon_name} a las {settings.BUSINESS_HOURS_START}"

    return (
        f"\n\n[CONTEXTO TEMPORAL]\n"
        f"Fecha actual: {fecha}\n"
        f"Hora actual: {hora}\n"
        f"Zona horaria: {settings.BUSINESS_TIMEZONE}\n"
        f"Estado: {estado} (horario de atención: L-V {horario})\n"
        f"Próxima apertura: {proximo}\n"
        f"IMPORTANTE: Usa ÚNICAMENTE estos datos para determinar el día y hora actual."
    )


# Generic closing filler phrases to strip from responses
_FILLER_PATTERNS = [
    r"si necesitas.*",
    r"no dudes en.*",
    r"estoy aquí para.*",
    r"¿necesitas algo.*",
    r"¿algo más.*",
    r"si tienes alguna.*",
    r"cualquier cosa.*avis.*",
    r"quedo a tu disposición.*",
    r"quedo atento.*",
    r"con gusto te ayudo.*",
]
_FILLER_RE = re.compile(
    r"[\.\!\s]*\s*(" + "|".join(_FILLER_PATTERNS) + r")\s*$",
    re.IGNORECASE,
)


def _strip_filler(text: str) -> str:
    cleaned = _FILLER_RE.sub("", text).rstrip()
    if cleaned and cleaned[-1] not in ".!?":
        cleaned += "."
    return cleaned


class OpenAIService:
    """Service for generating AI responses using OpenAI."""

    def __init__(self):
        self.client = AsyncOpenAI(api_key=settings.OPENAI_API_KEY)
        self.model = settings.OPENAI_MODEL

    async def generate_response(
        self,
        user_message: str,
        history: list[dict] | None = None,
        extra_context: str | None = None,
    ) -> str:
        """
        Generate an AI response.

        Args:
            user_message: The customer's message.
            history: Previous messages in chronological order.
            extra_context: Optional context block injected into the system prompt
                           (e.g. CRM data, lookup results, available slots).

        Returns:
            AI-generated response text.
        """
        try:
            # Build system content: static prompt first (OpenAI cache-friendly),
            # then variable context, then temporal block (changes every minute).
            system_content = settings.SYSTEM_PROMPT.strip()
            if extra_context:
                system_content += f"\n\n{extra_context}"
            system_content += _build_temporal_context()

            messages = [{"role": "system", "content": system_content}]

            if history:
                for msg in history:
                    messages.append({"role": msg["role"], "content": msg["content"]})

            messages.append({"role": "user", "content": user_message})

            response = await self.client.chat.completions.create(
                model=self.model,
                messages=messages,
                max_tokens=settings.OPENAI_MAX_TOKENS,
                temperature=settings.OPENAI_TEMPERATURE,
            )

            reply = response.choices[0].message.content.strip()
            reply = _strip_filler(reply)
            logger.info(f"OpenAI response ({self.model}): {reply[:120]}...")
            return reply

        except Exception as e:
            logger.error(f"OpenAI API error: {e}", exc_info=True)
            return (
                "Disculpa, estoy teniendo un problema técnico en este momento. "
                "Por favor intenta de nuevo en unos minutos o escribe para hablar con un asesor."
            )

    async def detect_handoff_needed(self, user_message: str, history: list[dict]) -> bool:
        """
        Quick, cheap check: does the user want to speak with a human agent?
        Uses a mini-model call to keep costs low.
        """
        try:
            context_msgs = history[-6:] if history else []
            messages = [
                {
                    "role": "system",
                    "content": (
                        "Responde SOLO con 'SI' o 'NO'.\n"
                        "¿El usuario está pidiendo EXPLÍCITAMENTE hablar con una persona humana, "
                        "un agente o un asesor real?\n"
                        "Solo responde SI si usa frases muy claras como: 'quiero hablar con una persona', "
                        "'ponme con alguien', 'quiero un agente humano', 'hablar con un asesor', "
                        "'no quiero hablar con un bot'.\n"
                        "Para cualquier otra cosa — preguntas, respuestas cortas, mensajes vagos, "
                        "frustración leve — responde NO.\n"
                        "En caso de duda, responde NO."
                    ),
                }
            ]
            for msg in context_msgs:
                messages.append({"role": msg["role"], "content": msg["content"]})
            messages.append({"role": "user", "content": user_message})

            response = await self.client.chat.completions.create(
                model="gpt-4.1-mini",
                messages=messages,
                max_tokens=5,
                temperature=0,
            )
            answer = response.choices[0].message.content.strip().upper()
            return answer.startswith("SI") or answer == "SÍ"
        except Exception as e:
            logger.error(f"Error in handoff detection: {e}", exc_info=True)
            return False
