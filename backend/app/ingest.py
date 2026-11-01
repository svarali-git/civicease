"""Document ingestion: PDF bytes, public URLs and pasted text become plain text.

Everything happens in memory. Nothing is written to disk.
"""
import asyncio
import html
import io
import ipaddress
import re
import socket
from urllib.parse import urljoin, urlparse

import httpx
from pypdf import PdfReader
from pypdf.errors import PyPdfError

from . import config

MAX_PAGES = 120
MIN_TEXT_CHARS = 80


class IngestError(Exception):
    """A problem the user can understand and fix (shown as a friendly warning)."""

    def __init__(self, message: str, code: str = "unreadable_document"):
        super().__init__(message)
        self.message = message
        self.code = code


def pdf_to_text(data: bytes) -> str:
    try:
        reader = PdfReader(io.BytesIO(data))
        if reader.is_encrypted:
            raise IngestError("This PDF is password protected. Please upload an unlocked copy.")
        pages = reader.pages[:MAX_PAGES]
        text = "\n".join((page.extract_text() or "") for page in pages)
    except IngestError:
        raise
    except (PyPdfError, ValueError, KeyError, OSError, TypeError, AttributeError):
        raise IngestError(
            "We could not read this PDF. Please try a cleaner copy, paste the text instead, "
            "or search by typing your question."
        )
    return _require_text(text)


def _require_text(text: str) -> str:
    text = text.replace("\x00", "").strip()
    if len(text) < MIN_TEXT_CHARS:
        raise IngestError(
            "This document has very little readable text. It may be a scanned image. "
            "Please upload a text-based PDF or paste the text instead."
        )
    return text


def html_to_text(raw: str) -> str:
    raw = re.sub(r"(?is)<(script|style|noscript).*?>.*?</\1>", " ", raw)
    raw = re.sub(r"(?i)</(p|div|li|tr|h[1-6]|ul|ol|table)>|<br\s*/?>", "\n", raw)
    raw = re.sub(r"(?s)<[^>]+>", " ", raw)
    raw = html.unescape(raw)
    raw = re.sub(r"[ \t\r\f\v]+", " ", raw)
    raw = re.sub(r"\n\s*\n+", "\n", raw)
    return raw.strip()


def text_input(text: str) -> str:
    return _require_text(text)


def _host_is_public(host: str) -> bool:
    try:
        infos = socket.getaddrinfo(host, None)
    except socket.gaierror:
        raise IngestError("We could not find that website. Please check the link.", "bad_url")
    for info in infos:
        ip = ipaddress.ip_address(info[4][0])
        if (
            ip.is_private
            or ip.is_loopback
            or ip.is_link_local
            or ip.is_reserved
            or ip.is_multicast
            or ip.is_unspecified
        ):
            return False
    return True


async def _validate_url(url: str) -> None:
    parsed = urlparse(url)
    if parsed.scheme not in ("http", "https") or not parsed.hostname:
        raise IngestError("Please enter a full link starting with http:// or https://", "bad_url")
    host = parsed.hostname.lower()
    suffixes = config.allowed_url_suffixes()
    if suffixes and not any(host == s.lstrip(".") or host.endswith(s) for s in suffixes):
        raise IngestError(
            "This server only accepts links from approved government websites.", "url_not_allowed"
        )
    if not await asyncio.to_thread(_host_is_public, host):
        raise IngestError("That link points to a private address and cannot be opened.", "url_blocked")


async def fetch_url(url: str) -> str:
    """Download a public PDF or web page (size, time and redirect limits, private IPs blocked)."""
    limit = config.max_upload_bytes()
    headers = {"User-Agent": "CivicEase/1.0 (+informational civic tool)"}
    current = url.strip()
    try:
        async with httpx.AsyncClient(timeout=15, follow_redirects=False, headers=headers) as client:
            for _ in range(4):
                await _validate_url(current)
                async with client.stream("GET", current) as resp:
                    if resp.is_redirect:
                        location = resp.headers.get("location")
                        if not location:
                            raise IngestError("The link redirected nowhere.", "bad_url")
                        current = urljoin(current, location)
                        continue
                    if resp.status_code >= 400:
                        raise IngestError(
                            f"The website replied with an error ({resp.status_code}). "
                            "Please download the document and upload it instead.",
                            "fetch_failed",
                        )
                    body = bytearray()
                    async for chunk in resp.aiter_bytes():
                        body.extend(chunk)
                        if len(body) > limit:
                            raise IngestError("That document is too large.", "too_large")
                    break
            else:
                raise IngestError("Too many redirects.", "bad_url")
    except httpx.HTTPError:
        raise IngestError(
            "We could not download that link. Please upload the PDF or paste the text instead.",
            "fetch_failed",
        )
    data = bytes(body)
    if data[:5] == b"%PDF-":
        return await asyncio.to_thread(pdf_to_text, data)
    return _require_text(html_to_text(data.decode("utf-8", errors="ignore")))
