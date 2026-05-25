import logging
import httpx

from config import settings

logger = logging.getLogger(__name__)

GRAPH_URL = "https://graph.facebook.com"


class WhatsAppService:
    """Client for the WhatsApp Cloud API (Meta)."""

    def __init__(self):
        self.token = settings.WHATSAPP_TOKEN
        self.phone_number_id = settings.WHATSAPP_PHONE_NUMBER_ID
        self.api_version = settings.GRAPH_API_VERSION
        self.base_url = f"{GRAPH_URL}/{self.api_version}/{self.phone_number_id}"
        self.headers = {
            "Authorization": f"Bearer {self.token}",
            "Content-Type": "application/json",
        }

    async def send_message(self, to: str, text: str) -> dict:
        """Send a text message via WhatsApp Cloud API."""
        url = f"{self.base_url}/messages"
        payload = {
            "messaging_product": "whatsapp",
            "recipient_type": "individual",
            "to": to,
            "type": "text",
            "text": {"body": text},
        }

        try:
            async with httpx.AsyncClient(timeout=30) as client:
                response = await client.post(url, json=payload, headers=self.headers)
                response.raise_for_status()
                logger.info(f"WhatsApp message sent to {to}")
                return response.json()
        except httpx.HTTPStatusError as e:
            logger.error(
                f"WhatsApp API error: {e.response.status_code} - {e.response.text}"
            )
            raise
        except Exception as e:
            logger.error(f"Error sending WhatsApp message: {e}", exc_info=True)
            raise

    async def send_template(self, to: str, template_name: str, language: str = "es") -> dict:
        """Send a WhatsApp template message (for re-opening 24h windows)."""
        url = f"{self.base_url}/messages"
        payload = {
            "messaging_product": "whatsapp",
            "to": to,
            "type": "template",
            "template": {
                "name": template_name,
                "language": {"code": language},
            },
        }

        try:
            async with httpx.AsyncClient(timeout=30) as client:
                response = await client.post(url, json=payload, headers=self.headers)
                response.raise_for_status()
                logger.info(f"WhatsApp template '{template_name}' sent to {to}")
                return response.json()
        except httpx.HTTPStatusError as e:
            logger.error(
                f"WhatsApp template API error: {e.response.status_code} - {e.response.text}"
            )
            raise
        except Exception as e:
            logger.error(f"Error sending WhatsApp template: {e}", exc_info=True)
            raise

    async def mark_as_read(self, message_id: str) -> dict:
        """Mark an incoming message as read."""
        url = f"{self.base_url}/messages"
        payload = {
            "messaging_product": "whatsapp",
            "status": "read",
            "message_id": message_id,
        }

        try:
            async with httpx.AsyncClient(timeout=10) as client:
                response = await client.post(url, json=payload, headers=self.headers)
                response.raise_for_status()
                return response.json()
        except Exception as e:
            logger.warning(f"Could not mark message {message_id} as read: {e}")
            return {}
