from __future__ import annotations

import imaplib
from typing import Protocol, runtime_checkable


# Ошибка аутентификации mailbox source
class MailboxAuthError(RuntimeError):
    pass


# Ошибка недоступности mailbox source
class MailboxUnavailableError(RuntimeError):
    pass


# Read-only контракт mailbox client для fake/live реализаций
@runtime_checkable
class MailboxReadonlyClient(Protocol):
    def fetch_latest(self, folder: str, items_max: int) -> list[bytes]: ...


# Минимальный IMAP read-only client для smoke ingestion.
class ImapReadonlyMailboxClient:
    def __init__(
        self,
        host: str,
        port: int,
        use_ssl: bool,
        username: str,
        password: str,
    ) -> None:
        self._host = host
        self._port = port
        self._use_ssl = use_ssl
        self._username = username
        self._password = password

    def fetch_latest(self, folder: str, items_max: int) -> list[bytes]:
        client = self._connect()

        try:
            try:
                client.login(self._username, self._password)
            except imaplib.IMAP4.error as exc:
                raise MailboxAuthError("mailbox authentication failed") from exc

            status, _data = client.select(folder, readonly=True)
            if status != "OK":
                raise MailboxUnavailableError(f"mailbox folder select failed: {folder}")

            status, data = client.search(None, "ALL")
            if status != "OK":
                raise MailboxUnavailableError("mailbox search failed")

            raw_ids = data[0] if data else b""
            message_ids = [
                item.decode("ascii")
                for item in raw_ids.split()
                if item
            ]
            latest_ids = list(reversed(message_ids[-items_max:]))

            messages: list[bytes] = []
            for message_id in latest_ids:
                status, fetch_data = client.fetch(message_id, "(RFC822)")
                if status != "OK":
                    raise MailboxUnavailableError("mailbox fetch failed")

                raw_message = _extract_rfc822(fetch_data)
                if raw_message is None:
                    raise MailboxUnavailableError(
                        "mailbox fetch returned no RFC822 payload"
                    )

                messages.append(raw_message)

            return messages
        finally:
            try:
                client.logout()
            except Exception:
                pass

    def _connect(self):
        client_cls = imaplib.IMAP4_SSL if self._use_ssl else imaplib.IMAP4

        try:
            return client_cls(self._host, self._port)
        except OSError as exc:
            raise MailboxUnavailableError(
                f"mailbox connection failed: host={self._host} port={self._port}"
            ) from exc


# Извлечь RFC822 байты из fetch-ответа
def _extract_rfc822(fetch_data: object) -> bytes | None:
    if not isinstance(fetch_data, list):
        return None

    for item in fetch_data:
        if isinstance(item, tuple) and len(item) >= 2 and isinstance(item[1], bytes):
            return item[1]

    return None
