import logging
import httpx

from config import settings

logger = logging.getLogger(__name__)


class ChatwootService:
    """Service for interacting with Chatwoot API as an Agent Bot."""

    def __init__(self):
        base = settings.CHATWOOT_URL.rstrip("/")
        self.account_id = settings.CHATWOOT_ACCOUNT_ID
        self.api_base = f"{base}/api/v1/accounts/{self.account_id}"
        self.bot_headers = {
            "api_access_token": settings.CHATWOOT_BOT_TOKEN,
            "Content-Type": "application/json",
        }
        self.admin_headers = {
            "api_access_token": settings.CHATWOOT_ADMIN_TOKEN,
            "Content-Type": "application/json",
        }
        self._handoff_agent_ids: list[int] = [
            int(x.strip())
            for x in settings.CHATWOOT_HANDOFF_AGENT_IDS.split(",")
            if x.strip().isdigit()
        ]
        self._last_assigned_index = -1

    # ── Mensajes ───────────────────────────────────────────────────────────────

    async def send_message(self, conversation_id: int, text: str) -> dict:
        """Send a text message to a Chatwoot conversation."""
        url = f"{self.api_base}/conversations/{conversation_id}/messages"
        payload = {"content": text, "message_type": "outgoing"}

        try:
            async with httpx.AsyncClient(timeout=30) as client:
                response = await client.post(url, json=payload, headers=self.bot_headers)
                response.raise_for_status()
                logger.info(f"Message sent to conversation {conversation_id}")
                return response.json()
        except httpx.HTTPStatusError as e:
            logger.error(
                f"Chatwoot API error: {e.response.status_code} - {e.response.text}"
            )
            raise
        except Exception as e:
            logger.error(f"Error sending Chatwoot message: {e}", exc_info=True)
            raise

    # ── Contactos ─────────────────────────────────────────────────────────────

    async def get_contact_phone(self, contact_id: int) -> str | None:
        """Get a contact's phone number from Chatwoot Contacts API."""
        url = f"{self.api_base}/contacts/{contact_id}"
        try:
            async with httpx.AsyncClient(timeout=15) as client:
                response = await client.get(url, headers=self.bot_headers)
                response.raise_for_status()
                data = response.json()
                phone = data.get("phone_number") or data.get("payload", {}).get("phone_number")
                if phone:
                    logger.info(f"Phone {phone} retrieved for contact {contact_id}")
                return phone
        except Exception as e:
            logger.error(f"Error fetching contact {contact_id}: {e}", exc_info=True)
            return None

    async def find_conversation_by_phone(self, phone: str) -> int | None:
        """Search for the most recent Chatwoot conversation by phone number."""
        search_url = f"{self.api_base}/contacts/search"
        try:
            async with httpx.AsyncClient(timeout=15) as client:
                resp = await client.get(
                    search_url, params={"q": phone}, headers=self.bot_headers
                )
                resp.raise_for_status()
                contacts = resp.json().get("payload", [])
                if not contacts:
                    return None

                contact_id = contacts[0]["id"]
                conv_url = f"{self.api_base}/contacts/{contact_id}/conversations"
                resp2 = await client.get(conv_url, headers=self.bot_headers)
                resp2.raise_for_status()
                conversations = resp2.json().get("payload", [])
                if not conversations:
                    return None

                conv_id = conversations[0]["id"]
                logger.info(f"Found conversation {conv_id} for phone {phone}")
                return conv_id
        except Exception as e:
            logger.error(f"Error searching conversation for {phone}: {e}", exc_info=True)
            return None

    # ── Handoff a agente humano ────────────────────────────────────────────────

    async def handoff_to_agent(self, conversation_id: int) -> dict:
        """Toggle conversation status to 'open' so a human agent takes over."""
        url = f"{self.api_base}/conversations/{conversation_id}/toggle_status"
        try:
            async with httpx.AsyncClient(timeout=15) as client:
                response = await client.post(
                    url, json={"status": "open"}, headers=self.bot_headers
                )
                response.raise_for_status()
                logger.info(f"Conversation {conversation_id} set to open for handoff")
                return response.json()
        except Exception as e:
            logger.error(f"Error toggling conversation status: {e}", exc_info=True)
            raise

    async def get_agent_availability(self) -> dict[int, str]:
        """Get availability status of configured handoff agents."""
        url = f"{self.api_base}/agents"
        try:
            async with httpx.AsyncClient(timeout=15) as client:
                response = await client.get(url, headers=self.admin_headers)
                response.raise_for_status()
                agents = response.json()
                return {
                    a["id"]: a.get("availability_status", "offline")
                    for a in agents
                    if a["id"] in self._handoff_agent_ids
                }
        except Exception as e:
            logger.error(f"Error fetching agent availability: {e}", exc_info=True)
            return {}

    async def assign_handoff_agent(self, conversation_id: int) -> int | None:
        """Assign the next available handoff agent (round-robin, prefers online)."""
        if not self._handoff_agent_ids:
            return None

        availability = await self.get_agent_availability()
        agent_ids = self._handoff_agent_ids
        n = len(agent_ids)
        start = (self._last_assigned_index + 1) % n

        # Prefer available agents first
        for i in range(n):
            idx = (start + i) % n
            agent_id = agent_ids[idx]
            if availability.get(agent_id) == "available":
                if await self._assign_agent(conversation_id, agent_id):
                    self._last_assigned_index = idx
                    return agent_id

        # Fallback: round-robin regardless of status
        for i in range(n):
            idx = (start + i) % n
            agent_id = agent_ids[idx]
            if await self._assign_agent(conversation_id, agent_id):
                self._last_assigned_index = idx
                return agent_id

        return None

    async def _assign_agent(self, conversation_id: int, agent_id: int) -> bool:
        url = f"{self.api_base}/conversations/{conversation_id}/assignments"
        try:
            async with httpx.AsyncClient(timeout=15) as client:
                response = await client.post(
                    url,
                    json={"assignee_id": agent_id},
                    headers=self.admin_headers,
                )
                response.raise_for_status()
                logger.info(f"Agent {agent_id} assigned to conversation {conversation_id}")
                return True
        except Exception as e:
            logger.error(
                f"Error assigning agent {agent_id} to conversation {conversation_id}: {e}",
                exc_info=True,
            )
            return False

    # ── Etiquetas ─────────────────────────────────────────────────────────────

    async def add_label(self, conversation_id: int, label: str) -> bool:
        """Add a label to a conversation (useful for tracking/segmentation)."""
        url = f"{self.api_base}/conversations/{conversation_id}/labels"
        try:
            async with httpx.AsyncClient(timeout=15) as client:
                response = await client.post(
                    url, json={"labels": [label]}, headers=self.bot_headers
                )
                response.raise_for_status()
                logger.info(f"Label '{label}' added to conversation {conversation_id}")
                return True
        except Exception as e:
            logger.error(f"Error adding label to conversation {conversation_id}: {e}", exc_info=True)
            return False

    # ── Notas privadas ────────────────────────────────────────────────────────

    async def send_private_note(self, conversation_id: int, text: str) -> dict:
        """Send a private note (only visible to agents, not to the customer)."""
        url = f"{self.api_base}/conversations/{conversation_id}/messages"
        payload = {
            "content": text,
            "message_type": "outgoing",
            "private": True,
        }
        try:
            async with httpx.AsyncClient(timeout=30) as client:
                response = await client.post(url, json=payload, headers=self.bot_headers)
                response.raise_for_status()
                logger.info(f"Private note sent to conversation {conversation_id}")
                return response.json()
        except Exception as e:
            logger.error(f"Error sending private note: {e}", exc_info=True)
            raise
