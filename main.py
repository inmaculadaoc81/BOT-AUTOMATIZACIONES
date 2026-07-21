import logging
import json
from contextlib import asynccontextmanager
from datetime import datetime
from zoneinfo import ZoneInfo

from fastapi import FastAPI, Request, Response, HTTPException, Query
from fastapi.responses import JSONResponse
from slowapi import Limiter
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded

from config import settings
from database import Database
from openai_service import OpenAIService
from whatsapp_service import WhatsAppService
from chatwoot_service import ChatwootService

# ── Logging ────────────────────────────────────────────────────────────────────

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
logger = logging.getLogger(__name__)

# ── Rate limiter (por IP) ──────────────────────────────────────────────────────

limiter = Limiter(key_func=get_remote_address)

# ── Services ──────────────────────────────────────────────────────────────────

db = Database()
ai_svc = OpenAIService()
whatsapp_svc = WhatsAppService()
chatwoot_svc = ChatwootService()


# ── Startup / Shutdown ────────────────────────────────────────────────────────

@asynccontextmanager
async def lifespan(app: FastAPI):
    await db.init()
    logger.info("Database initialized")
    logger.info(f"Bot: {settings.BOT_NAME} | Business: {settings.BUSINESS_NAME}")
    logger.info(f"Verify token: {settings.VERIFY_TOKEN}")
    yield
    await db.close()
    logger.info("Database closed")


app = FastAPI(
    title=f"{settings.BUSINESS_NAME} Bot API",
    version="1.0.0",
    lifespan=lifespan,
)
app.state.limiter = limiter


@app.exception_handler(RateLimitExceeded)
async def rate_limit_handler(request: Request, exc: RateLimitExceeded):
    logger.warning(f"IP rate limit exceeded: {get_remote_address(request)}")
    return JSONResponse(
        status_code=429,
        content={"error": "Too many requests. Try again later."},
    )


# ── Business hours helpers ────────────────────────────────────────────────────

def _is_within_business_hours() -> bool:
    """Check if current time falls within the configured business hours."""
    try:
        tz = ZoneInfo(settings.BUSINESS_TIMEZONE)
        now = datetime.now(tz)

        weekdays = [int(d) for d in settings.BUSINESS_WEEKDAYS.split(",") if d.strip().isdigit()]
        if now.weekday() not in weekdays:
            return False

        start_h, start_m = map(int, settings.BUSINESS_HOURS_START.split(":"))
        end_h, end_m = map(int, settings.BUSINESS_HOURS_END.split(":"))
        mins = now.hour * 60 + now.minute
        return (start_h * 60 + start_m) <= mins < (end_h * 60 + end_m)
    except Exception:
        return True  # Fail open


def _build_handoff_message() -> str:
    return (
        "🔄 Te conecto con un asesor ahora mismo. "
        "En breve te atenderán. ¡Gracias por tu paciencia! 😊"
    )


def _build_outside_hours_message() -> str:
    return (
        f"🕐 En este momento estamos fuera de nuestro horario de atención "
        f"({settings.BUSINESS_HOURS_START}-{settings.BUSINESS_HOURS_END}, "
        f"lunes a viernes). Un asesor se pondrá en contacto contigo en el "
        f"siguiente día hábil.\n\nMientras tanto, sigo disponible para "
        f"responder tus dudas. 😊"
    )


# ── Handoff helper ────────────────────────────────────────────────────────────

async def _do_handoff(sender_key: str, conversation_id: int | None = None):
    """Set conversation to human mode and notify Chatwoot if conversation_id is known."""
    if conversation_id is None:
        conversation_id = await chatwoot_svc.find_conversation_by_phone(sender_key)

    if conversation_id:
        try:
            await chatwoot_svc.handoff_to_agent(conversation_id)
        except Exception as e:
            logger.error(f"handoff_to_agent failed: {e}", exc_info=True)

        try:
            assigned = await chatwoot_svc.assign_handoff_agent(conversation_id)
            if assigned:
                logger.info(f"Agent {assigned} assigned to conversation {conversation_id}")
        except Exception as e:
            logger.error(f"assign_handoff_agent failed: {e}", exc_info=True)

    await db.set_conversation_mode(sender_key, "human")
    logger.info(f"Handoff complete for {sender_key} (conv: {conversation_id})")


# ── Rate limit helper ─────────────────────────────────────────────────────────

async def _is_rate_limited(sender_key: str) -> bool:
    count = await db.count_recent_messages(sender_key, seconds=settings.RATE_LIMIT_WINDOW)
    return count >= settings.RATE_LIMIT_MESSAGES


# ── Health check ──────────────────────────────────────────────────────────────

@app.get("/")
async def health():
    return {
        "status": "ok",
        "service": f"{settings.BUSINESS_NAME} Bot",
        "bot": settings.BOT_NAME,
    }


# ══════════════════════════════════════════════════════════════════════════════
# WhatsApp Cloud API webhook (Meta)
# ══════════════════════════════════════════════════════════════════════════════

@app.get("/webhook")
async def verify_webhook(
    hub_mode: str = Query(None, alias="hub.mode"),
    hub_verify_token: str = Query(None, alias="hub.verify_token"),
    hub_challenge: str = Query(None, alias="hub.challenge"),
):
    """Meta webhook verification (GET)."""
    if hub_mode == "subscribe" and hub_verify_token == settings.VERIFY_TOKEN:
        logger.info("WhatsApp webhook verified")
        return Response(content=hub_challenge, media_type="text/plain")
    logger.warning(f"Webhook verification failed — mode: {hub_mode}")
    raise HTTPException(status_code=403, detail="Verification failed")


@app.post("/webhook")
@limiter.limit(settings.IP_RATE_LIMIT)
async def receive_whatsapp_message(request: Request):
    """Receive incoming WhatsApp messages from Meta Cloud API."""
    body = await request.json()
    logger.debug(f"WhatsApp webhook: {json.dumps(body)[:500]}")

    try:
        entry = body.get("entry", [])
        if not entry:
            return {"status": "no entry"}

        changes = entry[0].get("changes", [])
        if not changes:
            return {"status": "no changes"}

        value = changes[0].get("value", {})
        messages = value.get("messages", [])

        if not messages:
            logger.debug("No messages in webhook (status update)")
            return {"status": "no messages"}

        message = messages[0]
        sender = message.get("from")
        msg_type = message.get("type")
        msg_id = message.get("id", "")

        # Mark as read immediately
        if msg_id:
            await whatsapp_svc.mark_as_read(msg_id)

        # Only handle text messages
        if msg_type != "text":
            logger.info(f"Non-text message type: {msg_type} from {sender}")
            await whatsapp_svc.send_message(
                to=sender,
                text="Por ahora solo proceso mensajes de texto. ¿Puedes describirme tu consulta con palabras?",
            )
            return {"status": "non-text ignored"}

        text = message["text"]["body"]
        logger.info(f"WhatsApp message from {sender}: {text[:100]}")

        # Per-phone rate limiting
        if await _is_rate_limited(sender):
            logger.warning(f"Rate limit exceeded for {sender}")
            await whatsapp_svc.send_message(
                to=sender,
                text="Estás enviando mensajes muy rápido. Por favor espera un momento. ⏳",
            )
            return {"status": "rate_limited"}

        # Human mode: save and skip
        mode = await db.get_conversation_mode(sender)
        if mode == "human":
            await db.save_message(sender, "user", text)
            logger.info(f"Saved message in human mode for {sender}")
            return {"status": "human mode"}

        # Get history
        history = await db.get_history(sender, limit=settings.HISTORY_LIMIT)

        # Save user message
        await db.save_message(sender, "user", text)

        # Check if user wants a human agent (quick AI check)
        needs_human = await ai_svc.detect_handoff_needed(text, history)
        if needs_human:
            if _is_within_business_hours():
                handoff_msg = _build_handoff_message()
                await db.save_message(sender, "assistant", handoff_msg)
                await whatsapp_svc.send_message(to=sender, text=handoff_msg)
                await _do_handoff(sender)
                return {"status": "handoff"}
            else:
                msg = _build_outside_hours_message()
                await db.save_message(sender, "assistant", msg)
                await whatsapp_svc.send_message(to=sender, text=msg)
                return {"status": "outside_hours"}

        # Generate AI response
        ai_response = await ai_svc.generate_response(
            user_message=text,
            history=history,
        )
        logger.info(f"AI response for {sender}: {ai_response[:100]}")

        # Detect in-response handoff request
        if "TRANSFERIR_AGENTE" in ai_response:
            clean = ai_response.replace("TRANSFERIR_AGENTE", "").strip()
            if _is_within_business_hours():
                handoff_msg = _build_handoff_message()
                full_msg = f"{clean}\n\n{handoff_msg}" if clean else handoff_msg
                await db.save_message(sender, "assistant", full_msg)
                await whatsapp_svc.send_message(to=sender, text=full_msg)
                await _do_handoff(sender)
            else:
                msg = _build_outside_hours_message()
                await db.save_message(sender, "assistant", msg)
                await whatsapp_svc.send_message(to=sender, text=msg)
            return {"status": "handoff"}

        # Send response
        await db.save_message(sender, "assistant", ai_response)
        await whatsapp_svc.send_message(to=sender, text=ai_response)
        return {"status": "ok"}

    except Exception as e:
        logger.error(f"Error processing WhatsApp message: {e}", exc_info=True)
        return {"status": "error"}


# ══════════════════════════════════════════════════════════════════════════════
# Chatwoot Agent Bot webhook
# ══════════════════════════════════════════════════════════════════════════════

@app.post("/chatwoot/webhook")
@limiter.limit(settings.IP_RATE_LIMIT)
async def chatwoot_webhook(request: Request):
    """
    Receive events from Chatwoot Agent Bot.
    This URL is registered in Chatwoot → Settings → Agent Bots → Webhook URL.
    """
    body = await request.json()
    logger.debug(f"Chatwoot webhook: {json.dumps(body)[:500]}")

    try:
        event = body.get("event")
        message_type = body.get("message_type")

        # ── Conversación resuelta → restaurar modo bot ─────────────────────
        if event == "conversation_status_changed":
            status = body.get("status")
            if status == "resolved":
                conv_id = body.get("id") or body.get("conversation", {}).get("id")
                if conv_id:
                    sender_key = f"chatwoot_{conv_id}"
                    await db.set_conversation_mode(sender_key, "bot")
                    logger.info(f"Conversation {conv_id} resolved → bot mode restored")

                    # Also restore by phone/source_id
                    source_id = body.get("contact_inbox", {}).get("source_id")
                    if source_id:
                        await db.set_conversation_mode(source_id, "bot")

                return {"status": "bot_restored"}
            return {"status": "ignored"}

        # ── Agente asignado/desasignado → cambiar modo ─────────────────────
        if event == "conversation_updated":
            changed_list = body.get("changed_attributes", [])
            changed: dict = {}
            for item in changed_list:
                changed.update(item)

            if "assignee_id" in changed:
                assignee = changed["assignee_id"]
                current = assignee.get("current_value")
                previous = assignee.get("previous_value")
                conv_id = body.get("id")

                if conv_id:
                    sender_key = f"chatwoot_{conv_id}"
                    source_id = body.get("contact_inbox", {}).get("source_id")

                    if current and not previous:
                        # Agent assigned → human mode
                        await db.set_conversation_mode(sender_key, "human")
                        if source_id:
                            await db.set_conversation_mode(source_id, "human")
                        logger.info(f"Agent {current} assigned → human mode (conv {conv_id})")
                        return {"status": "agent_assigned"}

                    elif not current and previous:
                        # Agent unassigned → bot mode
                        await db.set_conversation_mode(sender_key, "bot")
                        if source_id:
                            await db.set_conversation_mode(source_id, "bot")
                        logger.info(f"Agent unassigned → bot mode (conv {conv_id})")
                        return {"status": "agent_unassigned"}

            return {"status": "ignored"}

        # ── Mensaje saliente del agente → activar modo humano ─────────────
        if event == "message_created" and message_type == "outgoing":
            sender_info = body.get("sender", {})
            if sender_info.get("type") == "agent_bot":
                logger.debug("Ignoring bot's own outgoing message")
                return {"status": "bot_echo_ignored"}

            conversation = body.get("conversation", {})
            conv_id = conversation.get("id")
            if conv_id:
                sender_key = f"chatwoot_{conv_id}"
                await db.set_conversation_mode(sender_key, "human")
                source_id = conversation.get("contact_inbox", {}).get("source_id")
                if source_id:
                    await db.set_conversation_mode(source_id, "human")
                logger.info(f"Agent message → human mode (conv {conv_id})")
            return {"status": "agent_mode"}

        # ── Solo procesar mensajes entrantes del cliente ───────────────────
        if event != "message_created" or message_type != "incoming":
            logger.debug(f"Ignoring event: {event}, type: {message_type}")
            return {"status": "ignored"}

        # ── Extraer datos del payload ──────────────────────────────────────
        content = body.get("content", "")
        conversation = body.get("conversation", {})
        conversation_id = conversation.get("id")
        sender = body.get("sender", {})
        contact_id = sender.get("id")

        if not conversation_id:
            logger.warning("Missing conversation_id in Chatwoot webhook")
            return {"status": "missing data"}

        # Attachments o contenido vacío
        attachments = body.get("attachments", [])
        if attachments or not content:
            file_type = attachments[0].get("file_type", "archivo") if attachments else "vacío"
            logger.info(f"Attachment/empty content ({file_type}) in conversation {conversation_id}")
            await chatwoot_svc.send_message(
                conversation_id,
                "Por ahora solo proceso mensajes de texto. ¿Puedes describirme tu consulta con palabras? 😊",
            )
            return {"status": "non-text ignored"}

        # Solo texto
        content_type = body.get("content_type", "text")
        if content_type != "text":
            logger.info(f"Non-text content_type: {content_type}")
            await chatwoot_svc.send_message(
                conversation_id,
                "Por ahora solo proceso mensajes de texto. ¿Puedes describirme tu consulta con palabras? 😊",
            )
            return {"status": "non-text ignored"}

        # Obtener teléfono del cliente
        phone: str | None = None
        contact_inbox = conversation.get("contact_inbox", {})
        source_id = contact_inbox.get("source_id")
        if source_id:
            phone = source_id
        elif contact_id:
            phone = await chatwoot_svc.get_contact_phone(contact_id)

        sender_key = f"chatwoot_{conversation_id}"
        logger.info(f"Chatwoot message in conv {conversation_id}: {content[:100]}")

        # Rate limiting
        if await _is_rate_limited(sender_key):
            logger.warning(f"Rate limit exceeded for conversation {conversation_id}")
            await chatwoot_svc.send_message(
                conversation_id,
                "Estás enviando mensajes muy rápido. Por favor espera un momento. ⏳",
            )
            return {"status": "rate_limited"}

        # Human mode: save and skip
        mode = await db.get_conversation_mode(sender_key)
        if mode == "human":
            await db.save_message(sender_key, "user", content)
            logger.info(f"Saved message in human mode (conv {conversation_id})")
            return {"status": "human mode"}

        # History
        history = await db.get_history(sender_key, limit=settings.HISTORY_LIMIT)

        # Save user message
        await db.save_message(sender_key, "user", content)

        # Handoff detection
        needs_human = await ai_svc.detect_handoff_needed(content, history)
        if needs_human:
            if _is_within_business_hours():
                handoff_msg = _build_handoff_message()
                await db.save_message(sender_key, "assistant", handoff_msg)
                await chatwoot_svc.send_message(conversation_id, handoff_msg)
                await _do_handoff(sender_key, conversation_id=conversation_id)
                return {"status": "handoff"}
            else:
                msg = _build_outside_hours_message()
                await db.save_message(sender_key, "assistant", msg)
                await chatwoot_svc.send_message(conversation_id, msg)
                return {"status": "outside_hours"}

        # Generate AI response
        ai_response = await ai_svc.generate_response(
            user_message=content,
            history=history,
        )
        logger.info(f"AI response for conv {conversation_id}: {ai_response[:100]}")

        # Detect in-response handoff request
        if "TRANSFERIR_AGENTE" in ai_response:
            clean = ai_response.replace("TRANSFERIR_AGENTE", "").strip()
            if _is_within_business_hours():
                handoff_msg = _build_handoff_message()
                full_msg = f"{clean}\n\n{handoff_msg}" if clean else handoff_msg
                await db.save_message(sender_key, "assistant", full_msg)
                await chatwoot_svc.send_message(conversation_id, full_msg)
                await _do_handoff(sender_key, conversation_id=conversation_id)
            else:
                msg = _build_outside_hours_message()
                await db.save_message(sender_key, "assistant", msg)
                await chatwoot_svc.send_message(conversation_id, msg)
            return {"status": "handoff"}

        # Send response
        await db.save_message(sender_key, "assistant", ai_response)
        await chatwoot_svc.send_message(conversation_id, ai_response)
        return {"status": "ok"}

    except Exception as e:
        logger.error(f"Error processing Chatwoot webhook: {e}", exc_info=True)
        return {"status": "error"}


# ══════════════════════════════════════════════════════════════════════════════
# Admin endpoints (opcional, proteger con autenticación en producción)
# ══════════════════════════════════════════════════════════════════════════════

@app.get("/admin/conversations")
async def list_conversations():
    """List all conversations and their current mode."""
    conversations = await db.get_all_conversations()
    return {"total": len(conversations), "conversations": conversations}


@app.post("/admin/conversations/{sender_key}/mode")
async def set_mode(sender_key: str, request: Request):
    """Manually set a conversation mode (bot/human). Useful for debugging."""
    body = await request.json()
    mode = body.get("mode")
    if mode not in ("bot", "human"):
        raise HTTPException(status_code=400, detail="mode must be 'bot' or 'human'")
    await db.set_conversation_mode(sender_key, mode)
    return {"sender_key": sender_key, "mode": mode, "status": "updated"}
