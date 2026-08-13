"""Serving the built web app from the API's own origin.

Used on hosts where one container serves both (Hugging Face Spaces). Same
origin means /api requests are same-origin: no CORS, and no bearer token
crossing an origin boundary.

The security-relevant part is the containment check. Everything under `/` that
is not a real file falls back to index.html so a client-side route survives a
refresh — and that fallback is exactly the shape of code that leaks files when
`..` is not handled, because the process can read its own source, and this one
holds patient images.
"""

from __future__ import annotations

import pytest

from app.main import resolve_web_asset


@pytest.fixture
def bundle(tmp_path):
    web = tmp_path / "dist"
    (web / "assets").mkdir(parents=True)
    (web / "index.html").write_text("<div id='root'></div>", encoding="utf-8")
    (web / "sw.js").write_text("// service worker", encoding="utf-8")
    (web / "assets" / "index-abc123.js").write_text("console.log(1)",
                                                    encoding="utf-8")
    # A file OUTSIDE the bundle, next to it, standing in for application
    # source or anything else on the container's filesystem.
    (tmp_path / "secret.env").write_text("JWT_SECRET=real-secret",
                                         encoding="utf-8")
    return web.resolve()


def test_real_assets_are_served(bundle):
    assert resolve_web_asset(bundle, "sw.js") == bundle / "sw.js"
    assert (resolve_web_asset(bundle, "assets/index-abc123.js")
            == bundle / "assets" / "index-abc123.js")


@pytest.mark.parametrize("path", ["", "cases", "cases/6f1a-uuid", "emergency",
                                  "cases/6f1a/follow-up"])
def test_client_side_routes_fall_back_to_index(bundle, path):
    """A refresh on /cases/<uuid> must return the app, not a 404."""
    assert resolve_web_asset(bundle, path) == bundle / "index.html"


@pytest.mark.parametrize("attack", [
    "../secret.env",
    "../../secret.env",
    "assets/../../secret.env",
    "./../../secret.env",
    "..%2fsecret.env",
    "....//secret.env",
    "/etc/passwd",
    "../../../../../../etc/passwd",
])
def test_paths_escaping_the_bundle_are_refused(bundle, attack):
    resolved = resolve_web_asset(bundle, attack)
    assert resolved == bundle / "index.html", (
        f"{attack!r} resolved to {resolved} — outside the web bundle"
    )
    assert "secret" not in resolved.name


def test_a_directory_is_not_served_as_a_file(bundle):
    assert resolve_web_asset(bundle, "assets") == bundle / "index.html"


def test_a_malformed_path_falls_back_rather_than_raising(bundle):
    assert resolve_web_asset(bundle, "x" * 5000) == bundle / "index.html"
    assert resolve_web_asset(bundle, "\x00bad") == bundle / "index.html"


def test_api_only_by_default():
    """docker compose puts nginx in front and the dev server proxies, so the
    default must stay API-only rather than quietly mounting a stale bundle."""
    from app.config import Settings

    assert Settings().serve_web_dir == ""
