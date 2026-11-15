"""SNAPBACK as an MCP server, so other agents (Claude, ChatGPT and others) can use it.

    uv run python -m snapback.mcp_server                    stdio: Claude Desktop, Claude Code
    uv run python -m snapback.mcp_server --http [--port N]  streamable HTTP on 127.0.0.1:N/mcp,
                                                            behind a bearer token

A thin client over SNAPBACK's own HTTP API (`SNAPBACK_API_URL`, default http://localhost:8000).
Every rule, limit and verdict stays in the API: this file chooses nothing. The case and finder
tokens the API hands out are kept in this process and sent in headers only; no tool result
ever carries one. Every result says LIVE or FIXTURE. Errors come back as plain sentences.

The server holds one renter's tokens per process. Run the HTTP mode for yourself on your own
machine, never as a shared service.
"""

from __future__ import annotations

import argparse
import ipaddress
import logging
import secrets
import socket
import sys
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Annotated, Any
from urllib.parse import quote, urljoin, urlsplit

import httpx
from mcp.server.mcpserver import MCPServer
from mcp.server.mcpserver.exceptions import ToolError
from mcp.types import CallToolResult, TextContent
from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict

from snapback.card import strings

log = logging.getLogger(__name__)
logging.getLogger("httpx").setLevel(logging.WARNING)  # request lines are noise on stderr

MAX_PHOTOS = 10  # the API's own cap (SNAPBACK_MAX_PHOTOS)
MAX_PHOTO_BYTES = 10 * 1024 * 1024  # the API's own cap per photo (SNAPBACK_MAX_PHOTO_MB)
MAX_AD_CHARS = 20_000
MAX_BRIEF_CHARS = 500  # FinderMessageRequest.text
MAX_REDIRECTS = 3
PHOTO_TIMEOUT_S = 15.0
API_TIMEOUT_S = 120.0  # a check runs until it needs the renter, which can take a while
TOKEN_HELD = "held by this MCP server; never shown"
LOCALHOST = "127.0.0.1"  # HTTP mode binds here only: sponsor data is never served publicly

# The one next step for the renter, by where the case stands. Code-owned, like the card.
NEXT_BY_STATUS = {
    "running": "The check is still running. Ask for the verdict again in a few seconds.",
    "waiting_for_approval": (
        "Open the result page and decide whether to send the drafted photo challenge to the "
        "poster. Send no money meanwhile."
    ),
    "waiting_for_reply": (
        "Wait for the poster's reply photo. No reply means hold, not failure. "
        "Send no money meanwhile."
    ),
    "waiting_for_answer": "Answer the question on the result page so the check can go on.",
}
NEXT_BY_STATE = {
    "dont_pay": (
        "Do not send money. Contact the manager on record yourself and ask to view the home."
    ),
    "hold": "Hold off paying. View the home in person and sign a lease before any money moves.",
    "unverified": (
        "The photos could not be placed. Ask for an in-person viewing before paying anything."
    ),
    "verified": (
        "Book a viewing and sign a lease before you pay. Never pay by Zelle, wire or gift card."
    ),
}
PHOTO_WHERE = {
    "located_in_claimed": "placed in the home the ad claims",
    "located_elsewhere": "taken in a different property",
    "not_located": "could not be placed",
    "not_indexed": "no scan of the claimed home to place it in",
}


class McpSettings(BaseSettings):
    """Where the API and the web app are. Read from the environment or `.env`."""

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    snapback_api_url: str = "http://localhost:8000"
    snapback_public_base_url: str = "http://localhost:5173"
    snapback_mcp_token: SecretStr | None = None  # HTTP mode's bearer token; one per run if unset


def label(source: Any) -> str:
    """LIVE or FIXTURE, from the API's lower-case DataSource. Anything else reads FIXTURE."""
    return "LIVE" if str(source).lower() == "live" else "FIXTURE"


# Ranges `is_global` lets through on Python 3.12 that still reach a private or local address:
# NAT64 (64:ff9b::/96 and the local-use 64:ff9b:1::/48), 6to4 (2002::/16, which embeds any
# IPv4 address), the old IPv4-compatible block (::/96) and site-local (fec0::/10).
UNSAFE_V6 = tuple(
    ipaddress.ip_network(n)
    for n in ("64:ff9b::/96", "64:ff9b:1::/48", "2002::/16", "::/96", "fec0::/10")
)


def unsafe(ip: ipaddress.IPv4Address | ipaddress.IPv6Address) -> bool:
    """True for any address a photo fetch must never reach."""
    if ip.version == 6 and ip.ipv4_mapped is not None:
        ip = ip.ipv4_mapped
    if not ip.is_global or ip.is_multicast:
        return True
    return ip.version == 6 and any(ip in net for net in UNSAFE_V6)


def vetted_address(host: str, port: int) -> str | None:
    """Resolve `host` once and vet every address it gave. Returns one address to connect to,
    or None when it did not resolve or any answer is private, loopback, link-local or reserved.
    The fetch then connects to this address itself, so a second lookup (DNS rebinding) can
    never send it somewhere else."""
    try:
        infos = socket.getaddrinfo(host, port, type=socket.SOCK_STREAM)
    except (OSError, UnicodeError):
        return None
    addresses = [ipaddress.ip_address(info[4][0].split("%")[0]) for info in infos]
    if not addresses or any(unsafe(ip) for ip in addresses):
        return None
    return str(addresses[0])


@dataclass
class Vault:
    """The secrets the API handed this process. Read by code here; never returned by a tool."""

    case_tokens: dict[str, str] = field(default_factory=dict)  # case id -> write token
    read_tokens: dict[str, str] = field(default_factory=dict)  # case id -> read token
    finder_id: str | None = None
    finder_token: str | None = None
    finder_source: str = "FIXTURE"


class SnapbackError(ToolError):
    """A failure the agent should read out as is: one plain sentence. `status` is the API's
    HTTP status when the API refused."""

    def __init__(self, sentence: str, status: int | None = None) -> None:
        super().__init__(sentence)
        self.status = status


class Snapback:
    """The calls behind each tool. `api` talks to SNAPBACK's API; `web` fetches the renter's
    own photo links; `resolve` turns a photo link's host into one vetted address to connect to
    (see `vetted_address`)."""

    def __init__(
        self,
        api: httpx.Client,
        web: httpx.Client,
        web_url: str,
        resolve: Callable[[str, int], str | None] = vetted_address,
    ) -> None:
        self.api = api
        self.web = web
        self.web_url = web_url.rstrip("/")
        self.resolve = resolve
        self.vault = Vault()

    # --- plumbing ---------------------------------------------------------------------------

    def call(
        self,
        method: str,
        path: str,
        *,
        token: str | None = None,
        header: str = "Authorization",
        **kwargs: Any,
    ) -> Any:
        headers = {}
        if token is not None:
            headers[header] = f"Bearer {token}" if header == "Authorization" else token
        try:
            reply = self.api.request(method, path, headers=headers, **kwargs)
        except httpx.TimeoutException:
            raise SnapbackError("SNAPBACK's API took too long to answer. Try again.") from None
        except httpx.HTTPError:
            raise SnapbackError(
                f"SNAPBACK's API is not reachable at {self.api.base_url}. Start it with `make api`."
            ) from None
        if reply.status_code >= 400:
            raise SnapbackError(self.plain(reply), reply.status_code)
        return reply.json()

    @staticmethod
    def plain(reply: httpx.Response) -> str:
        """The API's own sentence when it gave one, else a plain one for the status."""
        try:
            detail = reply.json().get("detail")
        except (ValueError, AttributeError):
            detail = None
        if isinstance(detail, str) and detail.strip() and detail != "Not Found":
            return detail.strip()
        return {
            401: "SNAPBACK refused: this needs a token this MCP server does not hold.",
            403: "SNAPBACK refused: the token held here is not for that.",
            404: "SNAPBACK has no record of that.",
            409: "SNAPBACK is busy with that right now. Try again in a moment.",
            413: "That is too large for SNAPBACK to take.",
            422: "SNAPBACK could not read that request. Check the values and try again.",
            429: "Too many requests to SNAPBACK. Wait a minute and try again.",
        }.get(reply.status_code, f"SNAPBACK's API failed (HTTP {reply.status_code}). Try again.")

    def fetch_photo(self, url: str, n: int) -> tuple[str, bytes, str]:
        """One photo from a link the renter gave: http(s) only, public hosts only, an image
        content type, at most MAX_PHOTO_BYTES, a few redirects at most (each one vetted)."""
        for _ in range(MAX_REDIRECTS + 1):
            parts = urlsplit(url)
            if parts.scheme not in ("http", "https") or not parts.hostname:
                raise SnapbackError(f"Photo {n} is not an http or https link.")
            try:
                port = parts.port or (443 if parts.scheme == "https" else 80)
            except ValueError:
                raise SnapbackError(f"Photo {n} is not an http or https link.") from None
            try:  # an international name goes out in its ASCII (punycode) form
                host = parts.hostname.encode("idna").decode("ascii")
            except UnicodeError:
                raise SnapbackError(f"Photo {n} is not an http or https link.") from None
            address = self.resolve(host, port)
            if address is None:
                raise SnapbackError(f"Photo {n} points at a private or unknown address.")
            # Connect to the address vetted above, never to a fresh lookup of the name. The
            # name still goes in the Host header and, over https, in SNI, so TLS checks the
            # certificate against the name the renter gave.
            literal = f"[{address}]" if ":" in address else address
            target = f"{parts.scheme}://{literal}:{port}{parts.path or '/'}"
            if parts.query:
                target += f"?{parts.query}"
            default = port == (443 if parts.scheme == "https" else 80)
            named = f"[{host}]" if ":" in host else host
            headers = {"Host": named if default else f"{named}:{port}"}
            extensions = {"sni_hostname": host} if parts.scheme == "https" else {}
            try:
                with self.web.stream(
                    "GET", target, headers=headers, extensions=extensions, timeout=PHOTO_TIMEOUT_S
                ) as reply:
                    if reply.is_redirect and "location" in reply.headers:
                        url = urljoin(url, reply.headers["location"])
                        continue
                    if reply.status_code != 200:
                        raise SnapbackError(
                            f"Photo {n} could not be downloaded (HTTP {reply.status_code})."
                        )
                    kind = reply.headers.get("content-type", "").split(";")[0].strip().lower()
                    if not kind.startswith("image/"):
                        raise SnapbackError(f"Photo {n} is not an image.")
                    stated = reply.headers.get("content-length", "")
                    if stated.isdigit() and int(stated) > MAX_PHOTO_BYTES:
                        raise SnapbackError(f"Photo {n} is over {MAX_PHOTO_BYTES // 2**20} MB.")
                    body = bytearray()
                    for chunk in reply.iter_bytes():
                        body += chunk
                        if len(body) > MAX_PHOTO_BYTES:
                            raise SnapbackError(f"Photo {n} is over {MAX_PHOTO_BYTES // 2**20} MB.")
                    ext = kind.split("/")[1].replace("jpeg", "jpg") or "jpg"
                    return f"photo-{n}.{ext}", bytes(body), kind
            except httpx.HTTPError:
                raise SnapbackError(f"Photo {n} could not be downloaded.") from None
        raise SnapbackError(f"Photo {n} redirects too many times.")

    def result_url(self, case_id: str) -> str:
        return f"{self.web_url}/case/{quote(case_id, safe='')}"

    def optional(self, path: str, cid: str) -> Any:
        """A read that may be missing (older API, no record, no token held here): the answer, or
        None. Never an error, so one absent extra cannot sink a tool."""
        token = self.vault.read_tokens.get(cid) or self.vault.case_tokens.get(cid)
        if token is None:
            return None
        try:
            return self.call("GET", f"/cases/{quote(cid, safe='')}/{path}", token=token)
        except SnapbackError:
            return None

    def proof_of(self, cid: str, card: dict[str, Any]) -> dict[str, Any]:
        """The card's own summary, checks_out and does_not, and the real-listing hand-off link,
        all as the API words them. Absent fields stay empty; nothing is made up here."""
        real = self.optional("real-listing", cid) or {}
        link = real.get("cta_url")
        return {
            "headline": card.get("headline"),
            "summary": card.get("summary", []),
            "checks_out": card.get("checks_out", []),
            "does_not": card.get("does_not", []),
            "real_listing": (
                {
                    "headline": real.get("headline"),
                    "provenance": real.get("provenance"),
                    "link_label": real.get("cta_label"),
                    "link": link,
                }
                if link
                else None
            ),
        }

    # --- tools --------------------------------------------------------------------------------

    def check_listing(
        self, ad_text: str, photo_urls: list[str], max_rent: int | None
    ) -> dict[str, Any]:
        ad_text = ad_text.strip()
        if not ad_text and not photo_urls:
            raise SnapbackError("Give the listing's text, its photo links, or both.")
        if len(ad_text) > MAX_AD_CHARS:
            raise SnapbackError(f"The ad text is over {MAX_AD_CHARS} characters. Shorten it.")
        if len(photo_urls) > MAX_PHOTOS:
            raise SnapbackError(f"SNAPBACK takes at most {MAX_PHOTOS} photos per check.")
        if max_rent is not None and not 0 <= max_rent <= 1_000_000:
            raise SnapbackError("max_rent must be a monthly amount between 0 and 1,000,000.")
        photos = [self.fetch_photo(url, n) for n, url in enumerate(photo_urls, start=1)]
        made = self.call(
            "POST",
            "/cases",
            data={"text": ad_text},
            files=[("photos", photo) for photo in photos] or None,
        )
        case_id = made["case_id"]
        if made.get("token"):
            self.vault.case_tokens[case_id] = made["token"]
        if made.get("read_token"):
            self.vault.read_tokens[case_id] = made["read_token"]
        budget = None
        if max_rent is not None:
            if case_id not in self.vault.case_tokens:
                budget = "The budget was not saved: this case takes no changes."
            else:
                self.call(
                    "POST",
                    f"/cases/{quote(case_id, safe='')}/preferences",
                    token=self.vault.case_tokens[case_id],
                    json={"max_rent": max_rent},
                )
                budget = f"Budget saved for this case: up to {max_rent} a month."
        state = made.get("state")
        status = made.get("status", "running")
        try:
            card = self.call("GET", f"/cases/{quote(case_id, safe='')}/card")
        except SnapbackError:
            card = None  # the card is not ready yet; snapback_get_verdict will have it
        proof = self.proof_of(case_id, card) if card else {}
        return {
            **proof,
            "case_id": case_id,
            "source": label(made.get("source")),
            "status": status,
            "verdict": strings.text(f"state.{state}") if state else None,
            "photos_read": made.get("photos", 0),
            "screenshots_read": made.get("screenshots", 0),
            "ad_had_text_aimed_at_ai": bool(made.get("injection_noticed")),
            "challenge_drafted": bool(made.get("challenge_text")),
            "budget": budget,
            "read_token": TOKEN_HELD if case_id in self.vault.read_tokens else None,
            "result_url": self.result_url(case_id),
            "next_action": NEXT_BY_STATUS.get(status) or NEXT_BY_STATE.get(state or "", ""),
        }

    def get_verdict(self, case_id: str) -> dict[str, Any]:
        cid = quote(case_id.strip(), safe="")
        if not cid:
            raise SnapbackError("Give the case id that snapback_check_listing returned.")
        card = self.call("GET", f"/cases/{cid}/card")
        progress = self.call("GET", f"/cases/{cid}")  # the id alone gives the summary
        card_source = label(card.get("source"))
        checks = []
        for row in card.get("rows", []):
            for line in row.get("lines", []):
                checks.append(
                    {
                        "row": row.get("kind", "").upper(),
                        "check": line.get("label", ""),
                        "status": strings.tone_word(line.get("tone", ""), row.get("kind", "")),
                        "says": line.get("text", ""),
                        "source": label(line["source"]) if line.get("source") else card_source,
                    }
                )
        state = card.get("state", "")
        status = progress.get("status", "done")
        return {
            **self.proof_of(cid, card),
            "case_id": card.get("case_id", case_id),
            "source": card_source,
            "verdict": card.get("headline") or strings.text(f"state.{state}"),
            "verdict_set_by": "code (snapback.verdict.decide), never a language model",
            "status": status,
            "checks": checks,
            "not_checked": card.get("not_checked", []),
            "rules": card.get("footer", []),
            "checked_at": card.get("checked_at"),
            "expires_at": card.get("expires_at"),
            "verify_url": card.get("verify_url"),
            "result_url": self.result_url(card.get("case_id", case_id)),
            "next_action": NEXT_BY_STATUS.get(status) or NEXT_BY_STATE.get(state, ""),
        }

    def find_places(self, brief: str) -> dict[str, Any]:
        brief = brief.strip()
        if not brief:
            raise SnapbackError("Say what the renter is looking for, e.g. '1 bed under 1500'.")
        if len(brief) > MAX_BRIEF_CHARS:
            raise SnapbackError(f"Keep the brief under {MAX_BRIEF_CHARS} characters.")
        started = self.vault.finder_id is None
        if started:
            try:
                made = self.call("POST", "/finder/sessions")
            except SnapbackError as failed:
                if failed.status in (404, 405):
                    raise SnapbackError(
                        "This SNAPBACK API has no Finder yet (it needs the M9 Finder routes)."
                    ) from None
                raise
            self.vault.finder_id, self.vault.finder_token = made["session_id"], made["token"]
            self.vault.finder_source = label(made.get("source"))
        sid = quote(self.vault.finder_id or "", safe="")
        reply = self.call(
            "POST",
            f"/finder/{sid}/message",
            token=self.vault.finder_token,
            header="X-Finder-Token",
            json={"text": brief},
        )
        proposals = [
            {
                "proposal_id": p["id"],
                "question": p.get("text", ""),
                "because": p.get("evidence", ""),
                "status": p.get("status", "proposed"),
            }
            for p in reply.get("proposals", [])
        ]
        picks = [
            {
                "rank": p.get("rank"),
                "place_id": p.get("pid"),
                "kind": p.get("kind"),
                "has_3d_scan": p.get("has_scan"),
                "line": p.get("line", ""),
                "why": p.get("why", ""),
                "rent_from": p.get("rent_from"),
                "walkup": p.get("walkup"),
                "parking": p.get("parking"),
                "walk_it_first_url": f"{self.web_url}/tour/{quote(str(p.get('pid')), safe='')}",
            }
            for p in reply.get("picks", [])
        ]
        return {
            "source": label(reply.get("source")),
            "session": "started" if started else "continued",
            "reply": reply.get("reply", ""),
            "proposals": proposals,
            "needs_renter_yes": any(p["status"] == "proposed" for p in proposals),
            "picks": picks,
            "finder_url": f"{self.web_url}/finder",
        }

    def accept_preference(self, proposal_id: str, yes: bool) -> dict[str, Any]:
        if not isinstance(yes, bool):  # the schema already says boolean; this is belt and braces
            raise SnapbackError("Say yes or no with true or false, after the renter has said it.")
        if self.vault.finder_id is None:
            raise SnapbackError("There is no Finder session yet. Call snapback_find_places first.")
        sid = quote(self.vault.finder_id, safe="")
        pid = quote(proposal_id.strip(), safe="")
        if not pid:
            raise SnapbackError("Give the proposal_id that snapback_find_places returned.")
        done = self.call(
            "POST",
            f"/finder/{sid}/proposals/{pid}",
            token=self.vault.finder_token,
            header="X-Finder-Token",
            json={"decision": "accept" if yes else "decline"},
        )
        status = done.get("status", "accepted" if yes else "declined")
        return {
            "source": self.vault.finder_source,
            "proposal_id": done.get("id", proposal_id),
            "status": status,
            "question": done.get("text", ""),
            "result": (
                "Saved. The Finder applies it from the next search."
                if status == "accepted"
                else "Not saved. The Finder will not apply it."
            ),
        }

    def draft_tour_request(self, case_id: str, place_id: str) -> dict[str, Any]:
        cid = case_id.strip()
        token = self.vault.case_tokens.get(cid)
        if token is None:
            raise SnapbackError(
                f"This MCP server did not start case {cid or '(none)'}, so it cannot draft for "
                "it. Start the check with snapback_check_listing first."
            )
        if not place_id.strip():
            raise SnapbackError("Give the place_id of a pick from snapback_find_places.")
        draft = self.call(
            "POST",
            f"/cases/{quote(cid, safe='')}/tour-draft",
            token=token,
            json={"property_id": place_id.strip()},
        )
        return {
            "source": label(draft.get("source")),
            "place_id": draft.get("property_id", place_id),
            "to": draft.get("addressee", ""),
            "draft": draft.get("text", ""),
            "status": "draft",
            "sent": False,
            "note": "Nothing was sent. The renter reads it and sends it themselves, if they want.",
        }

    def why(self, case_id: str) -> dict[str, Any]:
        cid = case_id.strip()
        if not cid:
            raise SnapbackError("Give the case id that snapback_check_listing returned.")
        card = self.call("GET", f"/cases/{quote(cid, safe='')}/card")
        timeline = self.optional("timeline", cid)  # None on an API without it (404)
        if isinstance(timeline, dict):
            timeline = timeline.get("steps") or timeline.get("events")
        steps = None
        if isinstance(timeline, list):
            steps = [
                item
                if isinstance(item, str)
                else next(
                    (str(item[k]) for k in ("text", "summary", "label", "title") if item.get(k)),
                    "",
                )
                for item in timeline
                if isinstance(item, str | dict)
            ]
        return {
            "case_id": card.get("case_id", cid),
            "source": label(card.get("source")),
            "verdict": card.get("headline") or strings.text(f"state.{card.get('state', '')}"),
            "verdict_set_by": "code (snapback.verdict.decide), never a language model",
            "reasons": card.get("summary", []),
            "does_not_check_out": card.get("does_not", []),
            "checks_out": card.get("checks_out", []),
            "steps": steps,
            "steps_note": None if steps is not None else "This API has no step list for a case.",
        }

    def what_to_do(self, case_id: str) -> dict[str, Any]:
        cid = case_id.strip()
        if not cid:
            raise SnapbackError("Give the case id that snapback_check_listing returned.")
        card = self.call("GET", f"/cases/{quote(cid, safe='')}/card")
        office = self.optional("office", cid)
        state = card.get("state", "")
        return {
            "case_id": card.get("case_id", cid),
            "source": label(card.get("source")),
            "verdict": card.get("headline") or strings.text(f"state.{state}"),
            "next_steps": card.get("footer", []),
            "next_action": NEXT_BY_STATE.get(state, ""),
            "not_checked": card.get("not_checked", []),
            "office_on_record": (office or {}).get("guidance"),
            "office_domain": (office or {}).get("domain"),
            "real_listing_link": (self.proof_of(cid, card)["real_listing"] or {}).get("link"),
        }

    def walk_summary(self, case_id: str) -> dict[str, Any]:
        cid = case_id.strip()
        token = self.vault.read_tokens.get(cid) or self.vault.case_tokens.get(cid)
        if token is None:
            raise SnapbackError(
                f"This MCP server did not start case {cid or '(none)'}, so it holds no token for "
                "its walk. Start the check with snapback_check_listing first."
            )
        walk = self.call("GET", f"/cases/{quote(cid, safe='')}/walk", token=token)
        plan = walk.get("plan", {})
        rooms, landed = [], {}
        for stop in plan.get("stops", []):
            if stop.get("kind") not in ("room", "stop"):
                continue
            aliases = [p.get("alias") or p.get("photo_id") for p in stop.get("photos", [])]
            for alias in aliases:
                landed[alias] = stop.get("title", "")
            rooms.append(
                {
                    "room": stop.get("title", ""),
                    "ad_photos_here": aliases,
                    "ad_view": stop.get("ad_view", "unknown"),
                    "check_in_person": stop.get("tip"),
                }
            )
        photos = []
        locate = walk.get("locate") or {}
        for n, photo in enumerate(locate.get("photos", []), start=1):
            alias = f"P{n}"
            photos.append(
                {
                    "photo": alias,
                    "where": PHOTO_WHERE.get(photo.get("status", ""), "not known"),
                    "room": landed.get(alias),
                }
            )
        coverage = plan.get("coverage") or {}
        pid = plan.get("property_id", "")
        return {
            "case_id": cid,
            "source": label(plan.get("source")),
            "has_3d_scan": bool(plan.get("has_scan")),
            "rooms_note": plan.get("rooms_note"),
            "mode_line": plan.get("mode_line"),
            "rooms": rooms,
            "ad_photos": photos,
            "coverage": coverage.get("line"),
            "walk_it_first_url": (
                f"{self.web_url}/tour/{quote(pid, safe='')}?case={quote(cid, safe='')}"
                if pid
                else None
            ),
        }


INSTRUCTIONS = (
    "SNAPBACK checks a rental listing against the building's 3D scan and property record "
    "before a renter pays. Code sets every verdict; never restate one more strongly than the "
    "tool says, and never call a person a scammer. Every result says LIVE (real records) or "
    "FIXTURE (synthetic demo data): pass that on. Only call snapback_accept_preference after "
    "the renter has said yes or no in their own words."
)


def plainly(step: Callable[..., dict[str, Any]], *args: Any) -> Any:
    """Run one tool's step. A failure comes back as the plain sentence alone, marked as an
    error, without the SDK's "Error executing tool" prefix or any trace."""
    try:
        return step(*args)
    except SnapbackError as failed:
        sentence = str(failed)
    except Exception:
        log.exception("SNAPBACK MCP tool failed")  # the detail stays in this server's log
        sentence = "SNAPBACK's MCP server hit an error it did not expect. Try again."
    return CallToolResult(content=[TextContent(type="text", text=sentence)], is_error=True)


class PlainArgumentErrors:
    """Middleware: a call whose arguments fail the tool's schema gets one plain sentence naming
    the arguments, in place of the SDK's validation dump."""

    async def __call__(self, ctx: Any, call_next: Any) -> Any:
        result = await call_next(ctx)  # the wire form: a dict with camelCase keys
        if ctx.method != "tools/call" or not isinstance(result, dict) or not result.get("isError"):
            return result
        said = " ".join(str(block.get("text", "")) for block in result.get("content") or [])
        if "validation error" in said:
            name = (ctx.params or {}).get("name", "this tool")
            given = (ctx.params or {}).get("arguments") or {}
            wrong = [arg for arg in given if f"\n{arg}\n" in f"\n{said}\n"]
            missing = "Field required" in said
            sentence = (
                f"{name} needs {', '.join(wrong) or 'its arguments'} in the right type"
                f"{' (and every required argument)' if missing else ''}. "
                "See the tool's input schema."
            )
            if name == "snapback_accept_preference":
                sentence = (
                    "snapback_accept_preference needs a proposal_id and yes as a real true or "
                    "false, sent only after the renter has answered."
                )
            return {**result, "content": [{"type": "text", "text": sentence}]}
        return result


def build_server(app: Snapback) -> MCPServer:
    """The MCP server with SNAPBACK's eight tools bound to `app`."""
    mcp = MCPServer(
        name="snapback",
        title="SNAPBACK",
        description="Check a rental listing before you pay, and find places with a 3D scan.",
        instructions=INSTRUCTIONS,
        website_url="https://github.com/DevSingh05/snapback",
        middleware=[PlainArgumentErrors()],
    )

    @mcp.tool(name="snapback_check_listing")
    def check_listing(
        ad_text: str,
        photo_urls: list[str] = [],  # noqa: B006 (the schema default; never mutated)
        max_rent: int | None = None,
    ) -> dict[str, Any]:
        """Start a SNAPBACK check of a rental listing, before the renter pays anything.

        Args:
            ad_text: The listing's text or the poster's messages, as the renter has them.
            photo_urls: Links to the ad's photos that the renter gave you (http or https,
                at most 10, 10 MB each). Never invent or search for photos.
            max_rent: The renter's monthly budget, if they said one. Saved for this case.

        Returns the case_id, LIVE or FIXTURE, the status, the verdict once known and a link to
        the result page. The case's tokens stay inside this MCP server and are never shown.
        Also returns, when the card is ready, its summary, what checks out, what does not, and the
        link to the real listing on the building's own site. Quote the verdict as given and never
        call a person a scammer.
        Next: snapback_get_verdict, snapback_why, snapback_what_to_do or snapback_walk_summary
        with the case_id.
        """
        return plainly(app.check_listing, ad_text, list(photo_urls), max_rent)

    @mcp.tool(name="snapback_get_verdict")
    def get_verdict(case_id: str) -> dict[str, Any]:
        """The result card for a case: the verdict, each check line with its status, LIVE or
        FIXTURE per line, what SNAPBACK does not check, and the one next action.

        The verdict is chosen by code (snapback.verdict.decide) from the evidence, never by a
        language model. Repeat it as given: do not soften or strengthen it, and never call the
        poster a scammer. If status is not "done", the card is what is known so far.
        """
        return plainly(app.get_verdict, case_id)

    @mcp.tool(name="snapback_why")
    def why(case_id: str) -> dict[str, Any]:
        """Why SNAPBACK reached its verdict for a case: the reasons in the API's own words, the
        lines that check out, the lines that do not, and the steps the check took when the API
        lists them. Quote the verdict as given, do not soften or strengthen it, and never call a
        person a scammer: SNAPBACK says what does not match, not who someone is."""
        return plainly(app.why, case_id)

    @mcp.tool(name="snapback_what_to_do")
    def what_to_do(case_id: str) -> dict[str, Any]:
        """What the renter should do next for a case: the next steps as the API words them, what
        SNAPBACK did not check, the leasing office on record (to call on a number the renter
        finds themselves) and the link to the real listing when there is one. Quote the verdict
        as given and never call a person a scammer."""
        return plainly(app.what_to_do, case_id)

    @mcp.tool(name="snapback_find_places")
    def find_places(brief: str) -> dict[str, Any]:
        """Ask SNAPBACK's Finder for places, in plain words (e.g. "1 bed under 1500, no
        walk-ups"). The first call starts a Finder session; later calls continue it.

        Returns the Finder's reply, its picks (each with a Walk it first link) and any
        proposals: things the Finder offers to remember. A proposal changes nothing until the
        renter says yes. Ask the renter the proposal's question and wait for their answer.
        """
        return plainly(app.find_places, brief)

    @mcp.tool(name="snapback_accept_preference")
    def accept_preference(
        proposal_id: str, yes: Annotated[bool, Field(strict=True)]
    ) -> dict[str, Any]:
        """Send the renter's own yes or no on a Finder proposal.

        Only call this after the renter has explicitly answered the proposal's question in
        their own words. Never decide for them, never guess, and never call it on silence.
        yes=true saves the preference; yes=false declines it. `yes` must be a real boolean.
        """
        return plainly(app.accept_preference, proposal_id, yes)

    @mcp.tool(name="snapback_walk_summary")
    def walk_summary(case_id: str) -> dict[str, Any]:
        """The case's walk through the home's 3D scan: the rooms, which ad photo landed in
        which room, the coverage line, and a link to Walk it first in the browser.

        Only works for a case this MCP server started with snapback_check_listing (it holds the read
        token). LIVE or FIXTURE is on the result.
        """
        return plainly(app.walk_summary, case_id)

    @mcp.tool(name="snapback_draft_tour_request")
    def draft_tour_request(case_id: str, place_id: str) -> dict[str, Any]:
        """Draft a tour request to the leasing office on record for a place, for the renter to
        read. Draft only: nothing is ever sent from here, and SNAPBACK has no send route.

        Args:
            case_id: A case this MCP server started with snapback_check_listing.
            place_id: The place_id of a pick from snapback_find_places.

        Show the draft to the renter; they decide whether to send it themselves.
        """
        return plainly(app.draft_tour_request, case_id, place_id)

    return mcp


class BearerGate:
    """HTTP mode only: refuse every request without `Authorization: Bearer <token>`."""

    def __init__(self, app: Any, token: str) -> None:
        self.app = app
        self.expected = f"Bearer {token}".encode()

    async def __call__(self, scope: Any, receive: Any, send: Any) -> None:
        if scope["type"] == "http":
            offered = dict(scope.get("headers") or []).get(b"authorization", b"")
            if not secrets.compare_digest(offered, self.expected):
                body = b"This MCP server needs its bearer token in the Authorization header."
                await send(
                    {
                        "type": "http.response.start",
                        "status": 401,
                        "headers": [(b"content-type", b"text/plain")],
                    }
                )
                await send({"type": "http.response.body", "body": body})
                return
        await self.app(scope, receive, send)


def make_app(settings: McpSettings | None = None) -> Snapback:
    settings = settings or McpSettings()
    api = httpx.Client(base_url=settings.snapback_api_url, timeout=API_TIMEOUT_S)
    return Snapback(api, photo_client(), settings.snapback_public_base_url)


def photo_client(verify: Any = True) -> httpx.Client:
    """The client for the renter's photo links. No connection is kept for reuse: httpcore pools
    by address and port, so a kept TLS session for one name would be reused for another name on
    the same address without checking that name's certificate."""
    return httpx.Client(
        follow_redirects=False,
        headers={"User-Agent": "snapback-mcp"},
        limits=httpx.Limits(max_keepalive_connections=0),
        verify=verify,
    )


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="SNAPBACK's MCP server (stdio by default).")
    parser.add_argument(
        "--http", action="store_true", help="serve streamable HTTP on 127.0.0.1, not stdio"
    )
    parser.add_argument("--port", type=int, default=8765, help="HTTP mode only")
    args = parser.parse_args(argv)
    settings = McpSettings()
    server = build_server(make_app(settings))
    if not args.http:
        server.run("stdio")
        return
    import uvicorn

    token = settings.snapback_mcp_token.get_secret_value() if settings.snapback_mcp_token else ""
    if not token:
        token = secrets.token_urlsafe(24)
        # Printed once, to this terminal only, so the person running it can paste it into
        # their client. Set SNAPBACK_MCP_TOKEN to choose it instead.
        print(f"SNAPBACK MCP bearer token for this run: {token}", file=sys.stderr)
    app = BearerGate(server.streamable_http_app(host=LOCALHOST), token)
    print(f"SNAPBACK MCP on http://{LOCALHOST}:{args.port}/mcp", file=sys.stderr)
    uvicorn.run(app, host=LOCALHOST, port=args.port, log_level="warning")


if __name__ == "__main__":
    main()
