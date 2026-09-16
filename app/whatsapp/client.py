"""Client per WhatsApp Business Platform (Cloud API).

Usa esclusivamente l'API ufficiale Meta (Cloud API), come richiesto dalla
specifica, evitando automazioni fragili basate su WhatsApp Web.

Note sui requisiti WhatsApp:
- Messaggi di testo liberi ("session messages") sono consentiti solo entro
  la finestra di 24h da un messaggio dell'utente al numero del bot.
- Per notifiche proattive fuori da questa finestra e' necessario un
  Message Template approvato da Meta (HSM). Questo client supporta
  entrambe le modalita' (vedi `send_text` e `send_template`); la scelta
  di quale usare in produzione va fatta in base alla configurazione
  effettiva del numero WhatsApp Business e ai template approvati.
"""
from __future__ import annotations

import logging
import time
from dataclasses import dataclass

import requests

logger = logging.getLogger(__name__)

GRAPH_API_BASE = "https://graph.facebook.com"
MAX_RETRIES = 3
RETRY_BACKOFF_SECONDS = 2.0


class WhatsAppSendError(Exception):
    """Invio fallito verso un destinatario dopo tutti i retry."""


@dataclass
class SendResult:
    recipient: str
    success: bool
    error: str | None = None
    dry_run: bool = False


class WhatsAppClient:
    def __init__(
        self,
        access_token: str,
        phone_number_id: str,
        api_version: str = "v21.0",
        dry_run: bool = False,
        timeout: int = 15,
    ):
        if not dry_run and (not access_token or not phone_number_id):
            raise ValueError(
                "WHATSAPP_ACCESS_TOKEN e WHATSAPP_PHONE_NUMBER_ID sono "
                "obbligatori quando DRY_RUN non e' attivo."
            )
        self._access_token = access_token
        self._phone_number_id = phone_number_id
        self._api_version = api_version
        self.dry_run = dry_run
        self._timeout = timeout
        self._session = requests.Session()

    @property
    def _url(self) -> str:
        return f"{GRAPH_API_BASE}/{self._api_version}/{self._phone_number_id}/messages"

    def send_text_to_all(self, recipients: list[str], message: str) -> list[SendResult]:
        """Invia `message` a tutti i destinatari configurati.

        Non solleva eccezioni per singoli fallimenti: ritorna un risultato
        per destinatario. Chi chiama decide come trattare fallimenti
        parziali (vedi monitoring/checker.py: l'intera notifica e'
        considerata fallita se anche un solo invio fallisce, per evitare
        di marcare "notificato" quando qualcuno non ha ricevuto nulla e
        rischiare di scordarsene poi. Vedi README per il compromesso).
        """
        results = []
        for recipient in recipients:
            results.append(self._send_text_one(recipient, message))
        return results

    def _send_text_one(self, recipient: str, message: str) -> SendResult:
        if self.dry_run:
            logger.info(
                "[DRY_RUN] Messaggio WhatsApp che verrebbe inviato a %s:\n%s",
                recipient,
                message,
            )
            return SendResult(recipient=recipient, success=True, dry_run=True)

        payload = {
            "messaging_product": "whatsapp",
            "to": recipient,
            "type": "text",
            "text": {"body": message, "preview_url": False},
        }
        return self._post_with_retry(recipient, payload)

    def send_template_to_all(
        self,
        recipients: list[str],
        template_name: str,
        language_code: str,
        components: list[dict] | None = None,
    ) -> list[SendResult]:
        """Invia un Message Template approvato (necessario per notifiche
        proattive fuori dalla finestra di 24h di conversazione)."""
        results = []
        for recipient in recipients:
            if self.dry_run:
                logger.info(
                    "[DRY_RUN] Template WhatsApp '%s' che verrebbe inviato a %s "
                    "(components=%s)",
                    template_name,
                    recipient,
                    components,
                )
                results.append(SendResult(recipient=recipient, success=True, dry_run=True))
                continue

            payload = {
                "messaging_product": "whatsapp",
                "to": recipient,
                "type": "template",
                "template": {
                    "name": template_name,
                    "language": {"code": language_code},
                },
            }
            if components:
                payload["template"]["components"] = components
            results.append(self._post_with_retry(recipient, payload))
        return results

    def _post_with_retry(self, recipient: str, payload: dict) -> SendResult:
        last_error: str | None = None
        for attempt in range(1, MAX_RETRIES + 1):
            try:
                response = self._session.post(
                    self._url,
                    headers={"Authorization": f"Bearer {self._access_token}"},
                    json=payload,
                    timeout=self._timeout,
                )
            except requests.Timeout:
                last_error = "timeout"
                logger.warning(
                    "Timeout invio WhatsApp a %s (tentativo %d/%d)",
                    recipient,
                    attempt,
                    MAX_RETRIES,
                )
            except requests.RequestException as exc:
                last_error = "network_error"
                logger.warning(
                    "Errore di rete invio WhatsApp a %s (tentativo %d/%d): %s",
                    recipient,
                    attempt,
                    MAX_RETRIES,
                    exc.__class__.__name__,
                )
            else:
                if response.status_code == 200:
                    logger.info("Messaggio WhatsApp inviato a %s", recipient)
                    return SendResult(recipient=recipient, success=True)

                error_body = self._safe_error_body(response)
                last_error = f"http_{response.status_code}:{error_body}"

                if response.status_code in (429, 500, 502, 503, 504):
                    logger.warning(
                        "Errore temporaneo (%s) invio WhatsApp a %s "
                        "(tentativo %d/%d)",
                        response.status_code,
                        recipient,
                        attempt,
                        MAX_RETRIES,
                    )
                else:
                    # Errore non recuperabile (es. 401/400): non ha senso
                    # ritentare con lo stesso payload.
                    logger.error(
                        "Errore non recuperabile invio WhatsApp a %s: HTTP %s",
                        recipient,
                        response.status_code,
                    )
                    return SendResult(recipient=recipient, success=False, error=last_error)

            if attempt < MAX_RETRIES:
                time.sleep(RETRY_BACKOFF_SECONDS * attempt)

        return SendResult(recipient=recipient, success=False, error=last_error)

    @staticmethod
    def _safe_error_body(response: requests.Response) -> str:
        try:
            data = response.json()
            error = data.get("error", {})
            # Non logghiamo mai il token; qui logghiamo solo il messaggio
            # d'errore restituito da Meta.
            return str(error.get("message", "unknown_error"))
        except ValueError:
            return "unparsable_error_body"
