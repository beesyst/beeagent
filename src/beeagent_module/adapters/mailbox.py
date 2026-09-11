from __future__ import annotations

import imaplib
from contextlib import suppress
from typing import Protocol, runtime_checkable


class MailboxAuthError(RuntimeError):
    pass


class MailboxUnavailableError(RuntimeError):
    pass


def _read_uidvalidity(client: imaplib.IMAP4) -> int:
    response_name, data = client.response("UIDVALIDITY")
    if str(response_name).upper() != "UIDVALIDITY" or not data or not data[0]:
        raise MailboxUnavailableError("mailbox UIDVALIDITY unavailable")
    try:
        uidvalidity = int(data[0])
    except (TypeError, ValueError) as exc:
        raise MailboxUnavailableError("mailbox UIDVALIDITY invalid") from exc
    if uidvalidity <= 0:
        raise MailboxUnavailableError("mailbox UIDVALIDITY invalid")
    return uidvalidity


@runtime_checkable
class MailboxReadonlyClient(Protocol):
    def fetch_latest(self, folder: str, items_max: int) -> list[bytes]: ...


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
            message_ids = [item.decode("ascii") for item in raw_ids.split() if item]
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
            self._logout(client)

    def check_access(self, folder: str, *, timeout_seconds: float = 10.0) -> None:
        if (
            not isinstance(timeout_seconds, (int, float))
            or not 0 < timeout_seconds <= 30
        ):
            raise ValueError("mailbox access timeout is invalid")
        try:
            client = self._login_and_select(
                folder, timeout_seconds=float(timeout_seconds)
            )
        except MailboxAuthError:
            raise
        except (imaplib.IMAP4.error, OSError) as exc:
            raise MailboxUnavailableError("mailbox access check failed") from exc
        self._logout(client)

    def uid_state(self, folder: str) -> tuple[int, list[int]]:
        client = self._login_and_select(folder)
        try:
            uidvalidity = _read_uidvalidity(client)
            status, data = client.uid("SEARCH", "ALL")
            if status != "OK":
                raise MailboxUnavailableError("mailbox UID search failed")
            raw_uids = data[0] if data else b""
            if not isinstance(raw_uids, bytes):
                raise MailboxUnavailableError("mailbox UID search returned invalid UID")
            try:
                uids = sorted(int(item) for item in raw_uids.split() if item)
            except ValueError as exc:
                raise MailboxUnavailableError(
                    "mailbox UID search returned invalid UID"
                ) from exc
            if any(uid <= 0 for uid in uids):
                raise MailboxUnavailableError("mailbox UID search returned invalid UID")
            return uidvalidity, uids
        finally:
            self._logout(client)

    def fetch_uids(
        self,
        folder: str,
        uids: list[int],
        *,
        expected_uidvalidity: int,
    ) -> list[bytes]:
        client = self._login_and_select(folder)
        try:
            if _read_uidvalidity(client) != expected_uidvalidity:
                raise MailboxUnavailableError("mailbox UIDVALIDITY changed during poll")
            messages: list[bytes] = []
            for uid in uids:
                status, fetch_data = client.uid("FETCH", str(uid), "(BODY.PEEK[])")
                if status != "OK":
                    raise MailboxUnavailableError("mailbox UID fetch failed")
                raw_message = _extract_rfc822(fetch_data)
                if raw_message is None:
                    raise MailboxUnavailableError(
                        "mailbox UID fetch returned no payload"
                    )
                messages.append(raw_message)
            return messages
        finally:
            self._logout(client)

    def _login_and_select(
        self, folder: str, *, timeout_seconds: float | None = None
    ) -> imaplib.IMAP4:
        client = self._connect(timeout_seconds=timeout_seconds)
        try:
            client.login(self._username, self._password)
        except imaplib.IMAP4.error as exc:
            self._logout(client)
            raise MailboxAuthError("mailbox authentication failed") from exc
        try:
            status, _data = client.select(folder, readonly=True)
        except (imaplib.IMAP4.error, OSError) as exc:
            self._logout(client)
            raise MailboxUnavailableError("mailbox folder select failed") from exc
        if status != "OK":
            self._logout(client)
            raise MailboxUnavailableError(f"mailbox folder select failed: {folder}")
        return client

    @staticmethod
    def _logout(client: imaplib.IMAP4) -> None:
        with suppress(imaplib.IMAP4.error, OSError):
            client.logout()

    def _connect(self, *, timeout_seconds: float | None = None) -> imaplib.IMAP4:
        client_cls = imaplib.IMAP4_SSL if self._use_ssl else imaplib.IMAP4

        try:
            if timeout_seconds is None:
                return client_cls(self._host, self._port)
            return client_cls(self._host, self._port, timeout=timeout_seconds)
        except OSError as exc:
            raise MailboxUnavailableError(
                f"mailbox connection failed: host={self._host} port={self._port}"
            ) from exc


def _extract_rfc822(fetch_data: object) -> bytes | None:
    if not isinstance(fetch_data, list):
        return None

    for item in fetch_data:
        if isinstance(item, tuple) and len(item) >= 2 and isinstance(item[1], bytes):
            return item[1]

    return None
