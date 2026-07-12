"""Defense-in-depth response headers — CSP, referrer, sniff, and frame policy.

Every response the app serves (dashboard, ``/browse``, ``/share``, and the
health/ready probes) gets a fixed, restrictive header set even though the app
already sits behind auth and has no known injection path: a future escaping
miss in ``app/render.py`` would otherwise become full script execution on an
authenticated, privacy-sensitive page, and citation links to catalog hosts
leak a ``Referer`` unless we say not to.

The CSP's inline-script/style allowances are **hashes of the exact source**,
computed here at import time from the same string constants the renderers
serve — never hand-maintained. If an inline script or style body changes
without this module being re-imported (i.e. without the process restarting),
the hash simply won't match and the browser will block it; the drift test in
``tests/test_security_headers.py`` catches source edits that forget to keep
the served page consistent with what ships.
"""

from __future__ import annotations

import base64
import hashlib
from typing import Final

from app.render import _FILTER_JS, _STYLE
from app.share import _COPY_JS, _SHARE_STYLE


def _sha256_b64(text: str) -> str:
    """Base64 sha256 digest of ``text``, in the ``'sha256-...'`` CSP form."""
    digest = hashlib.sha256(text.encode("utf-8")).digest()
    return base64.b64encode(digest).decode("ascii")


def _inline_script_hash(script_tag: str) -> str:
    """Hash the inner text of an inline ``<script>...</script>`` constant.

    The CSP hash source is the element's *content*, not its markup, so the
    surrounding ``<script>``/``</script>`` tags are stripped first.
    """
    inner = script_tag.removeprefix("<script>").removesuffix("</script>")
    return _sha256_b64(inner)


def _inline_style_hash(style_body: str) -> str:
    """Hash an inline ``<style>`` element's body (already tag-free source)."""
    return _sha256_b64(style_body)


#: sha256 hashes of every inline script/style the app serves, derived from
#: source at import time — never hand-maintained.
FILTER_JS_HASH: Final = _inline_script_hash(_FILTER_JS)
COPY_JS_HASH: Final = _inline_script_hash(_COPY_JS)
STYLE_HASH: Final = _inline_style_hash(_STYLE)
SHARE_STYLE_HASH: Final = _inline_style_hash(_SHARE_STYLE)

#: The full Content-Security-Policy served on every response. ``default-src
#: 'none'`` denies everything by default; each directive below opens only the
#: narrow slice the app actually uses.
CONTENT_SECURITY_POLICY: Final = (
    "default-src 'none'; "
    f"script-src 'sha256-{FILTER_JS_HASH}' 'sha256-{COPY_JS_HASH}'; "
    f"style-src 'sha256-{STYLE_HASH}' 'sha256-{SHARE_STYLE_HASH}'; "
    "img-src 'self' data:; "
    "base-uri 'none'; "
    "form-action 'none'; "
    "frame-ancestors 'none'"
)

#: The complete, fixed security-header set applied to every response.
SECURITY_HEADERS: Final = {
    "Content-Security-Policy": CONTENT_SECURITY_POLICY,
    "Referrer-Policy": "no-referrer",
    "X-Content-Type-Options": "nosniff",
    "Cross-Origin-Opener-Policy": "same-origin",
    # Belt-and-suspenders alongside frame-ancestors 'none' for older browsers
    # that don't honor CSP frame-ancestors.
    "X-Frame-Options": "DENY",
}
