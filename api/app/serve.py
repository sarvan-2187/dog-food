"""Production entry point: `python -m app.serve` (api/Dockerfile).

Uvicorn with its transport-level DoS limits, plus a guard its CLI cannot
express: a **header timeout**. Found in acceptance testing (live probe P7):

- a connection that opens and never sends a request was held open forever.
  Uvicorn's keep-alive timeout only starts after a first response, and every
  open socket counts towards --limit-concurrency, so ~200 idle sockets from one
  machine made the server answer 503 to everyone (slow-loris);
- a client trickling header lines after a response cancels the keep-alive
  timer with each byte and can hold a socket the same way.

HeaderTimeoutH11Protocol closes any connection that has not delivered a
complete request head within HEADER_TIMEOUT_SECONDS of opening, or of its
previous response finishing. It is h11-based on purpose: with uvicorn[standard]
installed, "auto" picks httptools, which ignores the header-size cap below.
A slow request *body* is bounded separately by protection.ProtectionMiddleware.
"""
from __future__ import annotations

import asyncio
import logging
import os

import uvicorn
from uvicorn.protocols.http.h11_impl import H11Protocol

log = logging.getLogger("hackflow.serve")

HEADER_TIMEOUT_SECONDS = float(os.getenv("HEADER_TIMEOUT_SECONDS", "10"))


class HeaderTimeoutH11Protocol(H11Protocol):
    _header_timer: "asyncio.TimerHandle | None" = None

    def _arm_header_timer(self) -> None:
        self._disarm_header_timer()
        self._header_timer = self.loop.call_later(HEADER_TIMEOUT_SECONDS, self._header_timed_out)

    def _disarm_header_timer(self) -> None:
        if self._header_timer is not None:
            self._header_timer.cancel()
            self._header_timer = None

    def _waiting_for_request(self) -> bool:
        return self.cycle is None or self.cycle.response_complete

    def _header_timed_out(self) -> None:
        self._header_timer = None
        if self._waiting_for_request() and not self.transport.is_closing():
            log.info("closing a connection that sent no complete request in %ss", HEADER_TIMEOUT_SECONDS)
            self.transport.close()

    def connection_made(self, transport) -> None:  # type: ignore[override]
        super().connection_made(transport)
        self._arm_header_timer()

    def handle_events(self) -> None:
        super().handle_events()
        if not self._waiting_for_request():
            self._disarm_header_timer()

    def on_response_complete(self) -> None:
        super().on_response_complete()
        if not self.transport.is_closing():
            self._arm_header_timer()

    def connection_lost(self, exc) -> None:
        self._disarm_header_timer()
        super().connection_lost(exc)


def config(**overrides) -> uvicorn.Config:
    options = dict(
        app="app.main:app",
        host=os.getenv("HOST", "0.0.0.0"),
        port=int(os.getenv("PORT", "8000")),
        http=HeaderTimeoutH11Protocol,
        # Refuse work past 200 concurrent connections, drop idle keep-alive
        # sockets after 5s, cap the accept backlog, cap a request head at 16 KB.
        limit_concurrency=200,
        timeout_keep_alive=5,
        backlog=512,
        h11_max_incomplete_event_size=16384,
        # X-Forwarded-For is handled by protection.TrustedProxyMiddleware,
        # which trusts only the proxy's own hop.
        proxy_headers=False,
    )
    options.update(overrides)
    return uvicorn.Config(**options)


if __name__ == "__main__":
    uvicorn.Server(config()).run()
