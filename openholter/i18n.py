"""Server-side language: each request says its language (X-Lang header or ?lang=), and
messages shown to the user are picked with tr(fi, en). The default is Finnish."""
from __future__ import annotations

import contextvars
from typing import Any, Dict

LANG: contextvars.ContextVar = contextvars.ContextVar("openholter_lang", default="fi")
SUPPORTED = ("fi", "en")


def tr(fi: str, en: str) -> str:
    return en if LANG.get() == "en" else fi


def lang_of(scope: Dict[str, Any]) -> str:
    for k, v in scope.get("headers") or []:
        if k == b"x-lang":
            lang = v.decode("latin-1").strip().lower()
            if lang in SUPPORTED:
                return lang
    qs = (scope.get("query_string") or b"").decode("latin-1")
    for part in qs.split("&"):
        if part.startswith("lang=") and part[5:] in SUPPORTED:
            return part[5:]
    return "fi"


class LangMiddleware:
    """Pure ASGI, so the context variable reaches sync endpoints run in the thread pool too."""

    def __init__(self, app: Any) -> None:
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] in ("http", "websocket"):
            token = LANG.set(lang_of(scope))
            try:
                return await self.app(scope, receive, send)
            finally:
                LANG.reset(token)
        return await self.app(scope, receive, send)
