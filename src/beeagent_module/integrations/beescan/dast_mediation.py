import hashlib
import ipaddress
import re
import socket
import socketserver
import ssl
import threading
import time
from urllib.parse import urlsplit

import h11


class DastMediation:
    def __init__(
        self,
        *,
        origin,
        connected_ip,
        request_budget,
        seconds,
        response_bytes,
        socket_path,
        downstream_tls,
        authorize,
        resolve,
        upstream_tls,
        connect=None,
        observe=None,
        allowed_targets=(),
    ):
        parsed = urlsplit(origin)
        if (
            parsed.scheme != "https"
            or parsed.username
            or parsed.password
            or parsed.path
            or parsed.query
            or parsed.fragment
            or not parsed.hostname
            or origin != f"https://{parsed.netloc}"
            or type(request_budget) is not int
            or not 1 <= request_budget <= 100
            or type(seconds) is not int
            or not 1 <= seconds <= 60
            or type(response_bytes) is not int
            or not 1024 <= response_bytes <= 262144
            or upstream_tls.verify_mode != ssl.CERT_REQUIRED
            or not upstream_tls.check_hostname
            or observe is not None
            and not callable(observe)
            or type(allowed_targets) is not tuple
            or len(allowed_targets) > 10
            or any(
                type(target) is not str or not target.startswith("/")
                for target in allowed_targets
            )
        ):
            raise ValueError("invalid_dast_mediation")
        ipaddress.ip_address(connected_ip)
        self.origin = origin
        self.hostname = parsed.hostname
        self.port = parsed.port or 443
        self.authority = parsed.netloc.encode("ascii")
        host = f"[{self.hostname}]" if ":" in self.hostname else self.hostname
        self.connect_authority = f"{host}:{self.port}".encode("ascii")
        self.connected_ip = connected_ip
        self.budget = request_budget
        self.limit = response_bytes
        self.deadline = time.monotonic() + seconds
        self.authorize = authorize
        self.resolve = resolve
        self.upstream_tls = upstream_tls
        self.connect = connect
        self.observe = observe
        self.allowed_targets = allowed_targets
        self.seen_targets = set()
        self.downstream_tls = downstream_tls
        self.lock = threading.RLock()
        self.sockets = set()
        self.accepted = 0
        self.reserved = 0
        self.completed = 0
        self.denied = 0
        self.denial_reasons = {}
        self.failure_diagnostic = {"phase": "none", "exception_category": None}
        self.failed = False
        self.closed = False
        self.records = []
        self.socket_path = socket_path
        mediator = self

        class Handler(socketserver.BaseRequestHandler):
            def handle(self):
                mediator.handle(self.request)

        class Server(socketserver.ThreadingUnixStreamServer):
            daemon_threads = False

            def verify_request(self, request, client_address):
                with mediator.lock:
                    mediator.accepted += 1
                    return not mediator.closed and mediator.accepted <= 128

            def handle_error(self, request, client_address):
                mediator.failed = True

        self.server = Server(str(socket_path), Handler)
        socket_path.chmod(0o600)
        self.thread = threading.Thread(target=self.server.serve_forever)

    def start(self):
        self.authorize()
        self.thread.start()

    def remaining(self):
        seconds = self.deadline - time.monotonic()
        if self.closed or seconds <= 0:
            raise PermissionError("dast_deadline")
        return min(seconds, 10)

    def track(self, connection):
        with self.lock:
            if self.closed:
                connection.close()
                raise PermissionError("dast_closed")
            self.sockets.add(connection)
        return connection

    def event(self, protocol, connection, *, read_size=1):
        while True:
            event = protocol.next_event()
            if event is not h11.NEED_DATA:
                return event
            connection.settimeout(self.remaining())
            data = connection.recv(read_size)
            protocol.receive_data(data)

    def request(self, protocol, connection):
        event = self.event(protocol, connection)
        if isinstance(event, h11.ConnectionClosed):
            return None
        if not isinstance(event, h11.Request) or event.http_version != b"1.1":
            raise ValueError("dast_request_protocol")
        headers = list(event.headers)
        names = [name for name, _value in headers]
        if (
            len(names) > 32
            or len(names) != len(set(names))
            or any(
                name in names
                for name in (
                    b"transfer-encoding",
                    b"upgrade",
                    b"expect",
                    b"trailer",
                    b"proxy-authorization",
                    b"authorization",
                    b"cookie",
                )
            )
            or dict(headers).get(b"content-length", b"0") != b"0"
            or dict(headers).get(b"connection", b"keep-alive").lower()
            not in {b"close", b"keep-alive"}
        ):
            raise ValueError("dast_request_framing")
        if not isinstance(self.event(protocol, connection), h11.EndOfMessage):
            raise TypeError("dast_request_body")
        return event

    def forward(self, request):
        if (
            request.method != b"GET"
            or dict(request.headers).get(b"host") != self.authority
        ):
            raise PermissionError("dast_request_scope")
        target = request.target.decode("ascii")
        if target.startswith(self.origin + "/"):
            target = target[len(self.origin) :]
        parsed = urlsplit(target)
        if (
            not target.startswith("/")
            or target.startswith("//")
            or parsed.scheme
            or parsed.netloc
            or parsed.fragment
            or len(target) > 4096
            or re.search(r"[\x00-\x20\x7f\\]", target)
            or self.allowed_targets
            and target not in self.allowed_targets
        ):
            raise PermissionError("dast_request_scope")
        with self.lock:
            self.remaining()
            self.authorize()
            if self.connected_ip not in self.resolve(self.origin):
                raise PermissionError("dast_dns_changed")
            if self.reserved >= self.budget:
                raise PermissionError("dast_request_budget")
            if self.allowed_targets:
                if target in self.seen_targets:
                    raise PermissionError("dast_verification_repeated")
                self.seen_targets.add(target)
            self.reserved += 1
        family = socket.AF_INET6 if ":" in self.connected_ip else socket.AF_INET
        self.failure_diagnostic = {"phase": "connection_establishment", "exception_category": None}
        raw = self.track(
            self.connect()
            if self.connect is not None
            else socket.socket(family, socket.SOCK_STREAM)
        )
        stream = raw
        try:
            raw.settimeout(self.remaining())
            if self.connect is None:
                raw.connect((self.connected_ip, self.port))
            self.failure_diagnostic = {"phase": "tls_handshake", "exception_category": None}
            stream = self.track(
                self.upstream_tls.wrap_socket(raw, server_hostname=self.hostname)
            )
            protocol = h11.Connection(h11.CLIENT, max_incomplete_event_size=8192)
            self.authorize()
            self.remaining()
            self.failure_diagnostic = {"phase": "request_write", "exception_category": None}
            stream.sendall(
                protocol.send(
                    h11.Request(
                        method="GET",
                        target=target,
                        headers=[
                            (b"Host", self.authority),
                            (b"Connection", b"close"),
                            (b"Accept", b"*/*"),
                            (b"User-Agent", b"BeeAgent-DAST"),
                        ],
                    )
                )
                + protocol.send(h11.EndOfMessage())
            )
            self.failure_diagnostic = {"phase": "response_headers", "exception_category": None}
            response = self.event(protocol, stream, read_size=4096)
            if (
                not isinstance(response, h11.Response)
                or 300 <= response.status_code < 400
                or sum(len(name) + len(value) + 4 for name, value in response.headers)
                > 8192
            ):
                raise ValueError("dast_response_status")
            body = bytearray()
            self.failure_diagnostic = {"phase": "response_body", "exception_category": None}
            while True:
                event = self.event(protocol, stream, read_size=4096)
                if isinstance(event, h11.EndOfMessage):
                    break
                if (
                    not isinstance(event, h11.Data)
                    or len(body) + len(event.data) > self.limit
                ):
                    raise ValueError("dast_response_limit")
                body.extend(event.data)
            with self.lock:
                self.failure_diagnostic = {"phase": "none", "exception_category": None}
                if self.observe is not None:
                    self.observe(target, response.status_code, bytes(body))
                self.completed += 1
                self.records.append(
                    {
                        "request_sha256": hashlib.sha256(
                            target.encode("ascii")
                            if self.allowed_targets
                            else request.target
                        ).hexdigest(),
                        "response_sha256": hashlib.sha256(body).hexdigest(),
                        "status_code": response.status_code,
                    }
                )
            return (
                response.status_code,
                bytes(body),
                dict(response.headers).get(b"content-type"),
            )
        finally:
            stream.close()
            raw.close()
            with self.lock:
                self.sockets.discard(stream)
                self.sockets.discard(raw)

    def handle(self, connection):
        stream = self.track(connection)
        try:
            protocol = h11.Connection(h11.SERVER, max_incomplete_event_size=8192)
            request = self.request(protocol, stream)
            if request is None:
                return
            if (
                request.method != b"CONNECT"
                or request.target != self.connect_authority
                or dict(request.headers).get(b"host")
                not in {self.authority, self.connect_authority}
            ):
                raise PermissionError("dast_connect_scope")
            stream.sendall(protocol.send(h11.Response(status_code=200, headers=[])))
            stream.settimeout(self.remaining())
            stream = self.track(
                self.downstream_tls.wrap_socket(stream, server_side=True)
            )
            protocol = h11.Connection(h11.SERVER, max_incomplete_event_size=8192)
            while not self.closed:
                request = self.request(protocol, stream)
                if request is None:
                    break
                status, body, media = self.forward(request)
                headers = [(b"content-length", str(len(body)).encode())]
                if media is not None and len(media) <= 256:
                    headers.append((b"content-type", media))
                stream.sendall(
                    protocol.send(h11.Response(status_code=status, headers=headers))
                )
                if body:
                    stream.sendall(protocol.send(h11.Data(data=body)))
                stream.sendall(protocol.send(h11.EndOfMessage()))
                if protocol.our_state is h11.MUST_CLOSE:
                    break
                protocol.start_next_cycle()
        except BrokenPipeError, ConnectionResetError:
            pass
        except (OSError, ValueError, TypeError, h11.ProtocolError) as error:
            with self.lock:
                self.failure_diagnostic = {
                    "phase": self.failure_diagnostic["phase"],
                    "exception_category": type(error).__name__,
                }
                self.denied += 1
                reason = (
                    str(error)
                    if str(error).startswith("dast_")
                    else type(error).__name__
                )
                if len(reason) <= 64:
                    self.denial_reasons[reason] = self.denial_reasons.get(reason, 0) + 1
            try:
                stream.sendall(
                    b"HTTP/1.1 403 Refused\r\nContent-Length: 0\r\nConnection: close\r\n\r\n"
                )
            except OSError:
                pass
        finally:
            stream.close()
            connection.close()
            with self.lock:
                self.sockets.discard(stream)
                self.sockets.discard(connection)

    def close(self):
        with self.lock:
            if self.closed:
                return
            self.closed = True
            for connection in tuple(self.sockets):
                try:
                    connection.shutdown(socket.SHUT_RDWR)
                except OSError:
                    pass
                connection.close()
        if self.thread.ident is not None:
            self.server.shutdown()
            self.thread.join(timeout=2)
        self.server.server_close()
        self.socket_path.unlink(missing_ok=True)
        if self.thread.is_alive() or self.sockets:
            raise RuntimeError("dast_cleanup_unverified")
