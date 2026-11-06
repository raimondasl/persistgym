"""Which organization the API key belongs to, against those R10's and R8's rate-limit errors name
(CLI `org-check`; PREREG §17.11, amendment R11; $0).

The rate-limit errors in the committed run records name an organization. R8's (2026-10-18) and
R10's (2026-11-01) name different ones, and R9's records hold no such error, so they name
none. R11's control is meant to run with a key in the organization that R10's error names, so
this command asks before and after the run:

1. it sends one short request to Anthropic's free token-counting endpoint, `POST
   /v1/messages/count_tokens` (https://platform.claude.com/docs/en/build-with-claude/token-counting),
   never to the model;
2. it reads the response's `anthropic-organization-id` header, "the ID of the organization that
   the API key or access token used in the request belongs to"
   (https://platform.claude.com/docs/en/api/overview, checked 2026-11-02), and compares its
   SHA-256 with `R10_ORG_SHA256` and `R8_ORG_SHA256`;
3. it reports the digest and the two comparisons. The ID itself is neither printed nor written.
   An API error can name the organization in its text, so only its type and status are reported.

This says which organization the key belongs to at the moment of the check. It does not record
which organization a run's own calls were served under, or anything about a workspace.

It takes no paid-run lock and needs no approval. It refuses (`credential_refusal`) unless
`ANTHROPIC_API_KEY` is set and no other credential, base URL or custom header is, and a built
client that holds a custom header (`client_header_refusal`). The SDK's debug log would print the
response's headers, so the command raises that logger's level before its call. The CLI writes
results/haiku_control_org/<time>/org_check.json (or --out), and exits 3 when the organization is
not the one R10's error names, so that a shell can stop on it.
"""

from __future__ import annotations

import hashlib
import logging
from collections.abc import Callable
from typing import Any

import anthropic

from common import runmeta
from harnesses import registered
from harnesses.anthropic_transport import client_header_refusal, credential_refusal

ORG_HEADER = "anthropic-organization-id"
R10_ORG_SHA256 = "74e53caccde4d5b5841efd69e7dd73d71b05ac4f4dd35f14616353674999b82d"
"""The digest of the organization that R10's rate-limit error names
(results/persistgym_haiku_provenance/20261101T184553Z-W-np-0-claude-haiku-5-5/episodes.jsonl)."""
R8_ORG_SHA256 = "78aa98ff2dfb8653aa303606d3b0bb65ea698c9b7c7fad600f006db5a94b4f29"
"""The digest of the organization that R8's rate-limit errors name
(results/persistgym_haiku/20261018T144829Z-W-0-claude-haiku-5-5/episodes.jsonl)."""
ENDPOINT = "POST /v1/messages/count_tokens"


class Refused(ValueError):
    """The check cannot be made."""


def org_digest(org: str) -> str:
    return hashlib.sha256(org.encode("utf-8")).hexdigest()


def _default_client() -> Any:
    return anthropic.Anthropic(max_retries=2, timeout=60.0)


def org_check(client_factory: Callable[[], Any] | None = None) -> dict:
    """The report (module docstring). Raises `Refused` on the credentials, a custom header, an
    API error, or a response without the header."""
    why = credential_refusal()
    if why:
        raise Refused(why)
    client = (client_factory or _default_client)()
    why = client_header_refusal(client)
    if why:
        raise Refused(why)
    logging.getLogger("anthropic").setLevel(logging.WARNING)  # its debug log prints the headers
    try:
        response = client.messages.with_raw_response.count_tokens(
            model=registered.HAIKU_MODEL, messages=[{"role": "user", "content": "hi"}])
    except anthropic.APIError as e:
        raise Refused(f"the endpoint answered {type(e).__name__}, status "
                      f"{getattr(e, 'status_code', None)}") from None
    org = response.headers.get(ORG_HEADER)
    if not org:
        raise Refused(f"the response has no {ORG_HEADER} header, so the organization is unknown")
    digest = org_digest(org)
    git = runmeta.git_state()
    return {"checked_utc": runmeta.utc_now(), "endpoint": ENDPOINT,
            "model": registered.HAIKU_MODEL, "prereg": registered.R11_REF,
            "org_sha256": digest, "same_org_as_r10_error": digest == R10_ORG_SHA256,
            "same_org_as_r8_error": digest == R8_ORG_SHA256,
            "git_commit": git["git_commit"], "git_dirty": git["git_dirty"]}
