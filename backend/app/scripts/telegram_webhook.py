from __future__ import annotations

import argparse
import asyncio
import json
import os
import secrets
import string
import sys
from pathlib import Path
from typing import Any

import httpx

TELEGRAM_API_BASE_URL = "https://api.telegram.org"
DEFAULT_ALLOWED_UPDATES = ["message"]
SECRET_ALPHABET = string.ascii_letters + string.digits + "_-"
PROJECT_BACKEND_DIR = Path(__file__).resolve().parents[2]
DEFAULT_ENV_FILE = PROJECT_BACKEND_DIR / ".env"


class CliError(RuntimeError):
    pass


def generate_secret(length: int = 48) -> str:
    if not 1 <= length <= 256:
        raise CliError("Secret length must be between 1 and 256 characters.")
    return "".join(secrets.choice(SECRET_ALPHABET) for _ in range(length))


def parse_env_file(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    if not path.exists():
        return values

    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        values[key.strip()] = value.strip().strip('"').strip("'")
    return values


def update_env_file(path: Path, updates: dict[str, str]) -> None:
    existing_lines = path.read_text(encoding="utf-8").splitlines() if path.exists() else []
    seen: set[str] = set()
    new_lines: list[str] = []

    for line in existing_lines:
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or "=" not in line:
            new_lines.append(line)
            continue
        key, _ = line.split("=", 1)
        normalized_key = key.strip()
        if normalized_key in updates:
            new_lines.append(f"{normalized_key}={updates[normalized_key]}")
            seen.add(normalized_key)
        else:
            new_lines.append(line)

    if new_lines and new_lines[-1].strip():
        new_lines.append("")

    for key, value in updates.items():
        if key not in seen:
            new_lines.append(f"{key}={value}")

    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(new_lines).rstrip() + "\n", encoding="utf-8")


def get_setting(name: str, env_file: Path) -> str | None:
    return os.environ.get(name) or parse_env_file(env_file).get(name)


def require_setting(name: str, env_file: Path) -> str:
    value = get_setting(name, env_file)
    if not value:
        raise CliError(f"{name} is not configured. Set it in {env_file} or environment.")
    return value


def bot_method_url(api_base_url: str, token: str, method: str) -> str:
    return f"{api_base_url.rstrip('/')}/bot{token}/{method}"


def print_json(payload: Any) -> None:
    print(json.dumps(payload, ensure_ascii=False, indent=2))


async def call_telegram_method(
    *,
    api_base_url: str,
    token: str,
    method: str,
    json_payload: dict[str, Any] | None = None,
) -> dict[str, Any]:
    try:
        async with httpx.AsyncClient(timeout=20.0) as client:
            response = await client.post(
                bot_method_url(api_base_url, token, method),
                json=json_payload or {},
            )
    except httpx.HTTPError as exc:
        raise CliError(f"Telegram API is unavailable: {exc}") from exc
    try:
        payload = response.json()
    except ValueError as exc:
        raise CliError(f"Telegram returned non-JSON response: HTTP {response.status_code}") from exc

    if response.is_error or not payload.get("ok"):
        description = payload.get("description") or response.text
        raise CliError(f"Telegram {method} failed: {description}")
    return payload


async def setup_webhook(args: argparse.Namespace) -> None:
    token = require_setting("TELEGRAM_BOT_TOKEN", args.env_file)
    secret = args.secret_token or require_setting("TELEGRAM_WEBHOOK_SECRET", args.env_file)
    allowed_updates = args.allowed_updates or DEFAULT_ALLOWED_UPDATES

    payload = {
        "url": args.url,
        "secret_token": secret,
        "drop_pending_updates": args.drop_pending_updates,
        "allowed_updates": allowed_updates,
    }
    result = await call_telegram_method(
        api_base_url=args.api_base_url,
        token=token,
        method="setWebhook",
        json_payload=payload,
    )
    print_json(result)


async def webhook_info(args: argparse.Namespace) -> None:
    token = require_setting("TELEGRAM_BOT_TOKEN", args.env_file)
    result = await call_telegram_method(
        api_base_url=args.api_base_url,
        token=token,
        method="getWebhookInfo",
    )
    print_json(result)


async def delete_webhook(args: argparse.Namespace) -> None:
    token = require_setting("TELEGRAM_BOT_TOKEN", args.env_file)
    result = await call_telegram_method(
        api_base_url=args.api_base_url,
        token=token,
        method="deleteWebhook",
        json_payload={"drop_pending_updates": args.drop_pending_updates},
    )
    print_json(result)


async def send_test_message(args: argparse.Namespace) -> None:
    token = require_setting("TELEGRAM_BOT_TOKEN", args.env_file)
    result = await call_telegram_method(
        api_base_url=args.api_base_url,
        token=token,
        method="sendMessage",
        json_payload={
            "chat_id": args.chat_id,
            "text": args.text,
            "parse_mode": "HTML",
        },
    )
    print_json(result)


def init_env(args: argparse.Namespace) -> None:
    secret = args.webhook_secret or generate_secret()
    updates = {
        "TELEGRAM_BOT_TOKEN": args.bot_token,
        "TELEGRAM_WEBHOOK_SECRET": secret,
        "TELEGRAM_BOT_USERNAME": args.bot_username.lstrip("@"),
    }
    update_env_file(args.env_file, updates)
    print(f"Updated {args.env_file}")
    message = (
        "TELEGRAM_WEBHOOK_SECRET generated."
        if not args.webhook_secret
        else "Webhook secret set."
    )
    print(message)


def print_generated_secret(args: argparse.Namespace) -> None:
    print(generate_secret(args.length))


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python -m app.scripts.telegram_webhook",
        description="Configure and inspect Telegram webhook for notification delivery.",
    )
    parser.add_argument(
        "--env-file",
        type=Path,
        default=DEFAULT_ENV_FILE,
        help=f"Path to backend .env file. Default: {DEFAULT_ENV_FILE}",
    )
    parser.add_argument(
        "--api-base-url",
        default=TELEGRAM_API_BASE_URL,
        help=f"Telegram Bot API base URL. Default: {TELEGRAM_API_BASE_URL}",
    )
    parser.add_argument(
        "--no-fail",
        action="store_true",
        help="Print Telegram errors but exit with code 0. Useful for non-critical deploy hooks.",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    init_parser = subparsers.add_parser(
        "init-env",
        help="Create or update Telegram variables in .env.",
    )
    init_parser.add_argument("--bot-token", required=True, help="Token from BotFather.")
    init_parser.add_argument(
        "--bot-username",
        required=True,
        help="Bot username without @, for example TaskPlatformBot.",
    )
    init_parser.add_argument(
        "--webhook-secret",
        help="Optional explicit webhook secret. Generated automatically when omitted.",
    )
    init_parser.set_defaults(func=init_env)

    secret_parser = subparsers.add_parser("generate-secret", help="Print a webhook secret.")
    secret_parser.add_argument("--length", type=int, default=48)
    secret_parser.set_defaults(func=print_generated_secret)

    setup_parser = subparsers.add_parser("setup", help="Register Telegram webhook.")
    setup_parser.add_argument("--url", required=True, help="Public webhook URL.")
    setup_parser.add_argument(
        "--secret-token",
        help="Override TELEGRAM_WEBHOOK_SECRET for this call.",
    )
    setup_parser.add_argument(
        "--allowed-updates",
        action="append",
        choices=["message", "edited_message", "callback_query"],
        help="Allowed update type. Can be repeated. Default: message.",
    )
    setup_parser.add_argument(
        "--keep-pending-updates",
        action="store_false",
        dest="drop_pending_updates",
        help="Do not drop pending updates while setting webhook.",
    )
    setup_parser.set_defaults(func=setup_webhook, drop_pending_updates=True)

    info_parser = subparsers.add_parser("info", help="Show current webhook info.")
    info_parser.set_defaults(func=webhook_info)

    delete_parser = subparsers.add_parser("delete", help="Delete Telegram webhook.")
    delete_parser.add_argument(
        "--keep-pending-updates",
        action="store_false",
        dest="drop_pending_updates",
        help="Do not drop pending updates while deleting webhook.",
    )
    delete_parser.set_defaults(func=delete_webhook, drop_pending_updates=True)

    test_parser = subparsers.add_parser("send-test", help="Send a test Telegram message.")
    test_parser.add_argument("--chat-id", required=True)
    test_parser.add_argument(
        "--text",
        default="<b>Тестовое уведомление</b>\nTelegram подключен.",
    )
    test_parser.set_defaults(func=send_test_message)

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        result = args.func(args)
        if asyncio.iscoroutine(result):
            asyncio.run(result)
    except CliError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 0 if args.no_fail else 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
