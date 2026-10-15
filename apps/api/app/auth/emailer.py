"""E-mail goes through an outbox (ADR-016). The only implementation writes files, for development.

Each message is a file with permission 0600 in a directory with permission 0700 outside the
repository. An invitation message contains the accept link (and so the token): that is why the
sender is development only and the API refuses to start in production without a real one. The
password-changed notice never contains a password.
"""

import json
import os
import urllib.error
import urllib.request
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Protocol

from app.core.config import ApiSettings


@dataclass(frozen=True)
class Message:
    to: str
    subject: str
    body: str
    kind: str
    # Resend only: sending the same key twice sends one e-mail (a retry never duplicates).
    idempotency_key: str | None = None


class EmailDeliveryError(OSError):
    """The e-mail was not sent. An OSError on purpose: every caller already treats a failing sender
    as "log and go on". The text never carries the key, the address or what the server said."""


class EmailSender(Protocol):
    def send(self, message: Message) -> None: ...


RESEND_URL = "https://api.resend.com/emails"
RESEND_TIMEOUT_SECONDS = 10


class ResendSender:
    """Sends through the HTTP API of Resend (the same carrier the Forklin Central uses)."""

    def __init__(self, api_key: str, mail_from: str) -> None:
        self._api_key = api_key
        self._mail_from = mail_from

    def send(self, message: Message) -> None:
        payload = {
            "from": self._mail_from,
            "to": [message.to],
            "subject": message.subject,
            "text": message.body,
        }
        headers = {
            "Authorization": f"Bearer {self._api_key}",
            "Content-Type": "application/json",
            "User-Agent": "apm-digital/1.0",
        }
        if message.idempotency_key:
            headers["Idempotency-Key"] = message.idempotency_key
        request = urllib.request.Request(  # noqa: S310  (a fixed https URL)
            RESEND_URL, data=json.dumps(payload).encode(), headers=headers, method="POST"
        )
        try:
            with urllib.request.urlopen(request, timeout=RESEND_TIMEOUT_SECONDS):  # noqa: S310
                return
        except urllib.error.HTTPError as error:
            raise EmailDeliveryError(f"the e-mail provider answered {error.code}") from None
        except (urllib.error.URLError, TimeoutError, OSError):
            raise EmailDeliveryError("the e-mail provider could not be reached") from None


class FileOutbox:
    def __init__(self, directory: str) -> None:
        self.directory = Path(directory)

    def send(self, message: Message) -> None:
        self.directory.mkdir(mode=0o700, parents=True, exist_ok=True)
        stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%S")
        path = self.directory / f"{stamp}-{message.kind}-{uuid.uuid4().hex[:8]}.txt"
        content = f"To: {message.to}\nSubject: {message.subject}\n\n{message.body}\n"
        descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
            handle.write(content)


def build_sender(settings: ApiSettings) -> EmailSender:
    if settings.email_sender == "resend" and settings.resend_api_key and settings.mail_from:
        return ResendSender(settings.resend_api_key.get_secret_value(), settings.mail_from)
    return FileOutbox(settings.outbox_dir)


def invitation_message(settings: ApiSettings, to: str, token: str, organization: str) -> Message:
    link = f"{settings.public_base_url.rstrip('/')}/accept-invitation?token={token}"
    return Message(
        to=to,
        kind="invitation",
        subject=f"Convite para {organization} no APM Digital",
        body=(
            f"Voce foi convidado(a) para {organization} no APM Digital.\n"
            f"Para aceitar e definir sua senha, abra o link (vale por 72 horas, uso unico):\n{link}"
        ),
    )


def password_reset_message(settings: ApiSettings, to: str, token: str, minutes: int) -> Message:
    link = f"{settings.public_base_url.rstrip('/')}/redefinir-senha?token={token}"
    return Message(
        to=to,
        kind="password-reset",
        subject="Redefinir a senha do APM Digital",
        body=(
            "Recebemos um pedido para redefinir a senha da sua conta no APM Digital.\n"
            f"Para escolher uma senha nova, abra o link (vale por {minutes} minutos, uso unico):\n"
            f"{link}\n\n"
            "Se nao foi voce, ignore este e-mail: nada sera alterado."
        ),
    )


def password_changed_message(to: str) -> Message:
    return Message(
        to=to,
        kind="password-changed",
        subject="Sua senha do APM Digital foi alterada",
        body=(
            "A senha da sua conta no APM Digital foi alterada e todas as sessoes foram "
            "encerradas.\n"
            "Se nao foi voce, contate a administracao da sua escola imediatamente."
        ),
    )
