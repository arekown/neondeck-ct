"""Aktion „HTTP-Anfrage“ (Webhook): einzige Aktion mit Netzwerkzugriff.

Laeuft wie jede Aktion im Executor (nie im GUI-Thread). Erlaubt sind nur ``http``- und
``https``-Adressen; das Zeitlimit ist ``TIMEOUT_S``. Die Ergebnis-Meldung ist der
Antwortstatus (z. B. ``"200"``), auf einem Regler erscheint er als Leistenwert.
"""
from __future__ import annotations

import urllib.error
import urllib.parse
import urllib.request

from ..core.i18n import N_, tr
from .base import Param, Result, register

TIMEOUT_S = 5
METHODS = ["GET", "POST", "PUT", "DELETE"]
SCHEMES = ("http", "https")


def _allowed(url: str) -> bool:
    return urllib.parse.urlsplit(url).scheme.lower() in SCHEMES


class _HttpOnlyRedirects(urllib.request.HTTPRedirectHandler):
    """Weiterleitungen nur auf http/https (sonst endet die Anfrage mit dem 3xx-Status)."""

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        if not _allowed(newurl):
            return None
        return super().redirect_request(req, fp, code, msg, headers, newurl)


_OPENER = urllib.request.build_opener(_HttpOnlyRedirects)


def parse_headers(text: str) -> dict[str, str]:
    """``Name: Wert`` je Zeile; Zeilen ohne Doppelpunkt oder ohne Namen werden ignoriert."""
    headers = {}
    for line in (text or "").splitlines():
        name, sep, value = line.partition(":")
        if sep and name.strip():
            headers[name.strip()] = value.strip()
    return headers


@register("http", label=N_("HTTP-Anfrage"), category="apps", params=[
    Param("method", N_("Methode"), "choice", "GET", METHODS), Param("url", N_("Adresse"), "text"),
    Param("headers", N_("Kopfzeilen (Name: Wert je Zeile)"), "text", ""),
    Param("body", N_("Inhalt"), "text", "")])
def http(action, ctx, **_):
    url = (action.get("url") or "").strip()
    if not _allowed(url):
        return Result(False, tr("Nur http- und https-Adressen erlaubt: {url!r}", url=url))
    method = (action.get("method") or "GET").upper()
    if method not in METHODS:
        return Result(False, tr("Unbekannte HTTP-Methode: {method}", method=method))
    body = action.get("body") or ""
    data = body.encode("utf-8") if body or method in ("POST", "PUT") else None
    req = urllib.request.Request(url, data=data, method=method,
                                 headers=parse_headers(action.get("headers") or ""))
    try:
        with _OPENER.open(req, timeout=TIMEOUT_S) as resp:
            return Result(True, str(resp.status))
    except urllib.error.HTTPError as e:
        return Result(False, f"HTTP {e.code}")
    except TimeoutError:
        return Result(False, tr("Zeitüberschreitung nach {seconds} s", seconds=TIMEOUT_S))
    except urllib.error.URLError as e:
        if isinstance(e.reason, TimeoutError):
            return Result(False, tr("Zeitüberschreitung nach {seconds} s", seconds=TIMEOUT_S))
        return Result(False, tr("HTTP-Anfrage fehlgeschlagen: {reason}", reason=e.reason))
    except (OSError, ValueError) as e:
        return Result(False, tr("HTTP-Anfrage fehlgeschlagen: {reason}", reason=e))
