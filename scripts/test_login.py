"""JWT login smoke test for NutriFAQ.

Usage:
  python scripts/test_login.py
  python scripts/test_login.py --email admin@imxtech.ca --password "..."
  python scripts/test_login.py --base-url http://127.0.0.1:8080 --check-admin
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode, urlsplit, urlunsplit
from urllib.request import Request, urlopen

from dotenv import load_dotenv


PROJECT_ROOT = Path(__file__).resolve().parent.parent


def _normalize_base_url(value: str) -> str:
    return value.strip().rstrip("/")


def _read_json_response(response) -> dict[str, Any]:
    body = response.read().decode("utf-8", errors="replace")
    if not body:
        return {}
    return json.loads(body)


def _json_from_http_error(exc: HTTPError) -> dict[str, Any]:
    body = exc.read().decode("utf-8", errors="replace")
    if not body:
        return {}
    try:
        return json.loads(body)
    except json.JSONDecodeError:
        return {"raw": body}


def _candidate_base_urls(base_url: str) -> list[str]:
    normalized = _normalize_base_url(base_url)
    parsed = urlsplit(normalized)
    path = parsed.path.rstrip("/")

    candidates: list[str] = [normalized]
    if path.endswith("/api"):
        without_api = urlunsplit((parsed.scheme, parsed.netloc, path[:-4], parsed.query, parsed.fragment)).rstrip("/")
        if without_api:
            candidates.append(without_api)
    else:
        with_api = urlunsplit((parsed.scheme, parsed.netloc, f"{path}/api", parsed.query, parsed.fragment)).rstrip("/")
        candidates.append(with_api)

    # Preserve order and uniqueness.
    return list(dict.fromkeys([item for item in candidates if item]))


def _post_login(base_url: str, email: str, password: str, timeout: float) -> tuple[str, str]:
    payload = urlencode({"username": email, "password": password}).encode("utf-8")
    attempted: list[str] = []
    for candidate_base in _candidate_base_urls(base_url):
        login_url = f"{candidate_base}/auth/jwt/login"
        attempted.append(login_url)
        req = Request(
            url=login_url,
            data=payload,
            method="POST",
            headers={"Content-Type": "application/x-www-form-urlencoded"},
        )
        try:
            with urlopen(req, timeout=timeout) as response:
                data = _read_json_response(response)
            token = str(data.get("access_token", "")).strip()
            if not token:
                raise RuntimeError("Login succeeded but access_token is missing in response.")
            return token, candidate_base
        except HTTPError as exc:
            if exc.code == 404:
                continue
            raise

    attempted_text = "\n  - ".join(attempted)
    raise RuntimeError(
        "Login route not found (HTTP 404) on all candidates:\n"
        f"  - {attempted_text}\n"
        "Set --base-url to your backend API host (not frontend host)."
    )


def _get_json(url: str, token: str, timeout: float) -> tuple[int, dict[str, Any]]:
    req = Request(
        url=url,
        method="GET",
        headers={"Authorization": f"Bearer {token}"},
    )
    with urlopen(req, timeout=timeout) as response:
        return int(getattr(response, "status", 200)), _read_json_response(response)


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Test local JWT login and auth-protected endpoints.")
    parser.add_argument("--base-url", default="", help="API base URL (default: BACKEND_URL env or http://127.0.0.1:8080)")
    parser.add_argument("--email", default="", help="Login email (default: AUTH_DEFAULT_ADMIN_EMAIL env)")
    parser.add_argument("--password", default="", help="Login password (default: AUTH_DEFAULT_ADMIN_PASSWORD env)")
    parser.add_argument("--timeout", type=float, default=15.0, help="HTTP timeout in seconds (default: 15)")
    parser.add_argument(
        "--check-admin",
        action="store_true",
        help="Also call /api/users to verify admin-level access.",
    )
    return parser


def main() -> int:
    load_dotenv(PROJECT_ROOT / ".env")
    args = _build_parser().parse_args()

    base_url = _normalize_base_url(args.base_url or os.getenv("BACKEND_URL", "http://127.0.0.1:8080"))
    email = (args.email or os.getenv("AUTH_DEFAULT_ADMIN_EMAIL", "")).strip()
    password = args.password or os.getenv("AUTH_DEFAULT_ADMIN_PASSWORD", "")

    if not email or not password:
        print("FAIL: Missing credentials. Provide --email/--password or set AUTH_DEFAULT_ADMIN_* in .env.")
        return 2

    print(f"Testing login against: {base_url}")
    print(f"Using account: {email}")

    try:
        token, selected_base = _post_login(base_url=base_url, email=email, password=password, timeout=args.timeout)
        print(f"PASS: /auth/jwt/login returned an access token (base={selected_base}).")
    except HTTPError as exc:
        payload = _json_from_http_error(exc)
        print(f"FAIL: Login HTTP {exc.code}. Response: {json.dumps(payload, ensure_ascii=False)}")
        return 1
    except URLError as exc:
        print(f"FAIL: Cannot reach API at {base_url}. Error: {exc}")
        return 1
    except Exception as exc:  # explicit top-level failure reporting
        print(f"FAIL: Unexpected login error: {exc}")
        return 1

    try:
        status, profile = _get_json(url=f"{selected_base}/api/users/me", token=token, timeout=args.timeout)
        role = str(profile.get("role", ""))
        print(f"PASS: /api/users/me -> HTTP {status}, role={role or 'unknown'}")
    except HTTPError as exc:
        payload = _json_from_http_error(exc)
        print(f"FAIL: /api/users/me HTTP {exc.code}. Response: {json.dumps(payload, ensure_ascii=False)}")
        return 1
    except Exception as exc:
        print(f"FAIL: Unexpected /api/users/me error: {exc}")
        return 1

    if args.check_admin:
        try:
            status, users_payload = _get_json(url=f"{selected_base}/api/users", token=token, timeout=args.timeout)
            users_count = len(users_payload) if isinstance(users_payload, list) else "unknown"
            print(f"PASS: /api/users -> HTTP {status}, entries={users_count}")
        except HTTPError as exc:
            payload = _json_from_http_error(exc)
            print(f"FAIL: /api/users HTTP {exc.code}. Response: {json.dumps(payload, ensure_ascii=False)}")
            return 1
        except Exception as exc:
            print(f"FAIL: Unexpected /api/users error: {exc}")
            return 1

    print("DONE: Login smoke test succeeded.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
