#!/usr/bin/env python3
"""Seuraa Prisma.fi Pokemon-sivua ja ilmoittaa Slackiin tai Telegramiin 30th Celebration -korteista."""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent
DATA_DIR = ROOT / "data"
STATE_PATH = DATA_DIR / "state.json"
LOG_PATH = DATA_DIR / "scraper.log"

BRAND_URL = "https://www.prisma.fi/tuotemerkit/pokemon"
SEARCH_URLS = (
    "https://www.prisma.fi/haku?search=30",
    "https://www.prisma.fi/haku?search=pokemon+30",
    "https://www.prisma.fi/haku?search=30th+celebration",
    "https://www.prisma.fi/haku?search=pokemon+30th+celebration",
    "https://www.prisma.fi/haku?search=pokemon+30th",
    "https://www.prisma.fi/haku?search=30-vuotisjuhla",
    "https://www.prisma.fi/haku?search=pokemon+30-vuotis",
    "https://www.prisma.fi/haku?search=pokemon+juhlavuosi",
)
PRODUCT_URL = "https://www.prisma.fi/tuote/{slug}"
MAX_PAGES = 8
REQUEST_PAUSE_SECONDS = 1.5

# Juhlavuosi tai pelkkä luku 30. "30 cm" ja vastaavat mitat poistetaan ennen täsmäystä.
MATCH_RE = re.compile(
    r"""
    30th |
    30-th |
    anniversary |
    celebration |
    juhlavuosi |
    30\s*-?\s*vuotis |
    30\s*v\.?\s*(?:juhla|anniversary|celebration) |
    (?<!\d)30(?!\d)
    """,
    re.IGNORECASE | re.VERBOSE,
)
MEASUREMENT_30_RE = re.compile(
    r"(?<!\d)30(?:[.,]\d+)?\s*(?:cm|mm|cl|ml|g|kg|kpl)\b",
    re.IGNORECASE,
)
# Sivun markkinointibanneri, ei myynnissä oleva tuote.
IGNORED_MARKETING_RE = re.compile(
    r"30-vuotisjuhlat ovat k[aä]ynniss|tästä juhlavuoden uutuuskortit",
    re.IGNORECASE,
)
POKEMON_RE = re.compile(r"pok[eé]mon|\btcg\b", re.IGNORECASE)
TCG_RE = re.compile(
    r"booster|elite trainer|\betb\b|collection|mini tin|\btin\b|blister|binder|upc",
    re.IGNORECASE,
)
NEXT_DATA_RE = re.compile(
    r'<script id="__NEXT_DATA__" type="application/json">(.*?)</script>',
    re.DOTALL,
)

USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/122.0.0.0 Safari/537.36 PokemonAvailabilityWatch/1.0"
)


def now_iso() -> str:
    return datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")


def log(message: str) -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    line = f"{now_iso()} {message}"
    print(line, flush=True)
    with LOG_PATH.open("a", encoding="utf-8") as handle:
        handle.write(line + "\n")


def load_env() -> None:
    env_path = ROOT / ".env"
    if not env_path.exists():
        return
    for raw in env_path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip("'").strip('"')
        os.environ.setdefault(key, value)


def fetch_html(url: str) -> str:
    request = urllib.request.Request(
        url,
        headers={
            "User-Agent": USER_AGENT,
            "Accept": "text/html,application/xhtml+xml",
            "Accept-Language": "fi-FI,fi;q=0.9,en;q=0.8",
        },
    )
    with urllib.request.urlopen(request, timeout=25) as response:
        return response.read().decode("utf-8", "replace")


def parse_next_data(html: str) -> dict[str, Any]:
    match = NEXT_DATA_RE.search(html)
    if not match:
        raise RuntimeError("Prisman sivulta ei löytynyt tuotetietoja (__NEXT_DATA__).")
    payload = json.loads(match.group(1))
    page_props = payload.get("props", {}).get("pageProps")
    if not isinstance(page_props, dict):
        raise RuntimeError("Prisman sivun tuotelista on odottamattomassa muodossa.")
    return page_props


def cents_to_euros(value: Any) -> str | None:
    if value is None:
        return None
    try:
        return f"{int(value) / 100:.2f} €"
    except (TypeError, ValueError):
        return None


def availability_from_ribbon(ribbon: dict[str, Any] | None) -> dict[str, bool]:
    ribbon = ribbon or {}
    return {
        "ecom": bool(ribbon.get("ecom")),
        "click_and_collect": bool(ribbon.get("clickAndCollect")),
        "store": bool(ribbon.get("brickAndMortar")),
    }


def is_available(availability: dict[str, bool]) -> bool:
    return any(availability.values())


def looks_like_pokemon_product(name: str, brand: str = "") -> bool:
    return bool(POKEMON_RE.search(name) or TCG_RE.search(name) or re.search(r"pokemon", brand, re.I))


def name_for_match(name: str) -> str:
    return MEASUREMENT_30_RE.sub(" ", name)


def is_ignored_marketing(name: str) -> bool:
    return bool(IGNORED_MARKETING_RE.search(name))


def is_anniversary_product(name: str, brand: str = "", require_pokemon: bool = False) -> bool:
    if is_ignored_marketing(name):
        return False
    if require_pokemon and not looks_like_pokemon_product(name, brand):
        return False
    return bool(MATCH_RE.search(name_for_match(name)))


def normalize_product(raw: dict[str, Any], ribbons: dict[str, Any], source: str) -> dict[str, Any]:
    sok_id = str(raw.get("sokId") or "")
    name = str(raw.get("productName") or "").strip()
    slug = str(raw.get("slug") or "").strip()
    brand = str(raw.get("brandName") or "").strip()
    availability = availability_from_ribbon(ribbons.get(sok_id))
    return {
        "id": sok_id,
        "name": name,
        "slug": slug,
        "brand": brand,
        "url": PRODUCT_URL.format(slug=slug) if slug else BRAND_URL,
        "price": cents_to_euros(raw.get("finalPrice") if raw.get("finalPrice") is not None else raw.get("price")),
        "image": raw.get("mainImage"),
        "source": source,
        "availability": availability,
        "available": is_available(availability),
    }


def products_from_page(page_props: dict[str, Any], source: str) -> list[dict[str, Any]]:
    ribbons = page_props.get("availabilityRibbons") or {}
    products = []
    for raw in page_props.get("products") or []:
        if not isinstance(raw, dict):
            continue
        products.append(normalize_product(raw, ribbons, source))
    return products


def fetch_brand_products() -> tuple[list[dict[str, Any]], int]:
    collected: dict[str, dict[str, Any]] = {}
    total = 0
    page = 1
    while page <= MAX_PAGES:
        url = BRAND_URL if page == 1 else f"{BRAND_URL}?page={page}"
        page_props = parse_next_data(fetch_html(url))
        total = int(page_props.get("productTotalCount") or 0)
        batch = products_from_page(page_props, "brand")
        if not batch:
            break
        for product in batch:
            if product["id"]:
                collected[product["id"]] = product
        if len(collected) >= total:
            break
        page += 1
        time.sleep(REQUEST_PAUSE_SECONDS)
    return list(collected.values()), total


def fetch_search_products() -> list[dict[str, Any]]:
    collected: dict[str, dict[str, Any]] = {}
    for url in SEARCH_URLS:
        page_props = parse_next_data(fetch_html(url))
        for product in products_from_page(page_props, "search"):
            if product["id"] and is_anniversary_product(
                product["name"], product.get("brand", ""), require_pokemon=True
            ):
                collected[product["id"]] = product
        time.sleep(REQUEST_PAUSE_SECONDS)
    return list(collected.values())


def collect_matches() -> dict[str, Any]:
    brand_products, total = fetch_brand_products()
    matches = {
        product["id"]: product
        for product in brand_products
        if is_anniversary_product(product["name"])
    }
    for product in fetch_search_products():
        matches.setdefault(product["id"], product)
    return {
        "checked_at": now_iso(),
        "brand_product_count": len(brand_products),
        "brand_total_count": total,
        "matches": list(matches.values()),
    }


def load_state() -> dict[str, Any]:
    if not STATE_PATH.exists():
        return {
            "products": {},
            "last_check": None,
            "consecutive_errors": 0,
            "error_alerted": False,
            "announced": False,
        }
    return json.loads(STATE_PATH.read_text(encoding="utf-8"))


def save_state(state: dict[str, Any]) -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    STATE_PATH.write_text(json.dumps(state, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def availability_label(availability: dict[str, bool]) -> str:
    parts = []
    if availability.get("ecom"):
        parts.append("verkko")
    if availability.get("click_and_collect"):
        parts.append("nouto")
    if availability.get("store"):
        parts.append("myymälä")
    return ", ".join(parts) if parts else "ei saatavilla"


def slack_webhook() -> str:
    return (os.environ.get("SLACK_WEBHOOK_URL") or "").strip()


def telegram_creds() -> tuple[str, str]:
    token = (os.environ.get("TELEGRAM_BOT_TOKEN") or "").strip()
    chat_id = (os.environ.get("TELEGRAM_CHAT_ID") or "").strip()
    return token, chat_id


def telegram_configured() -> bool:
    token, chat_id = telegram_creds()
    return bool(token and chat_id)


def has_notifier() -> bool:
    return bool(slack_webhook() or telegram_configured())


def html_escape(text: str) -> str:
    return text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def post_telegram(text: str) -> None:
    token, chat_id = telegram_creds()
    if not token or not chat_id:
        raise RuntimeError("TELEGRAM_BOT_TOKEN tai TELEGRAM_CHAT_ID puuttuu.")
    payload = urllib.parse.urlencode(
        {
            "chat_id": chat_id,
            "text": text[:4096],
            "parse_mode": "HTML",
            "disable_web_page_preview": "false",
        }
    ).encode("utf-8")
    request = urllib.request.Request(
        f"https://api.telegram.org/bot{token}/sendMessage",
        data=payload,
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=20) as response:
        body = response.read().decode("utf-8", "replace")
        if response.status >= 300:
            raise RuntimeError(f"Telegram vastasi {response.status}: {body}")


def post_slack(payload: dict[str, Any]) -> None:
    webhook = slack_webhook()
    if not webhook:
        raise RuntimeError("SLACK_WEBHOOK_URL puuttuu. Kopioi .env.example -> .env ja lisää webhook.")
    data = json.dumps(payload).encode("utf-8")
    request = urllib.request.Request(
        webhook,
        data=data,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=20) as response:
        body = response.read().decode("utf-8", "replace")
        if response.status >= 300:
            raise RuntimeError(f"Slack vastasi {response.status}: {body}")


def product_lines(product: dict[str, Any]) -> list[str]:
    price = product.get("price") or "hinta ei tiedossa"
    return [
        f"*<{product['url']}|{product['name']}>*",
        f"{price} · {availability_label(product['availability'])}",
    ]


def telegram_product_message(title: str, products: list[dict[str, Any]]) -> str:
    lines = [f"<b>{html_escape(title)}</b>", ""]
    for product in products:
        name = html_escape(product["name"])
        price = html_escape(product.get("price") or "hinta ei tiedossa")
        avail = html_escape(availability_label(product["availability"]))
        lines.append(f'<a href="{product["url"]}">{name}</a>')
        lines.append(f"{price} · {avail}")
        lines.append("")
    lines.append(f'<a href="{BRAND_URL}">Avaa Pokemon-sivu</a>')
    return "\n".join(lines).strip()


def send_to_channels(*, slack_payload: dict[str, Any] | None = None, telegram_text: str | None = None) -> None:
    errors: list[str] = []
    sent = False
    if slack_webhook() and slack_payload is not None:
        try:
            post_slack(slack_payload)
            sent = True
        except Exception as error:  # noqa: BLE001
            errors.append(f"Slack: {error}")
    if telegram_configured() and telegram_text is not None:
        try:
            post_telegram(telegram_text)
            sent = True
        except Exception as error:  # noqa: BLE001
            errors.append(f"Telegram: {error}")
    if errors:
        log("Ilmoitusvirhe: " + " | ".join(errors))
    if not sent:
        if errors:
            raise RuntimeError(" | ".join(errors))
        raise RuntimeError("Ei ilmoituskanavaa. Aseta Slack-webhook tai Telegram-tiedot.")


def notify_products(title: str, fallback: str, products: list[dict[str, Any]]) -> None:
    blocks: list[dict[str, Any]] = [
        {"type": "header", "text": {"type": "plain_text", "text": title[:150]}},
        {
            "type": "section",
            "text": {
                "type": "mrkdwn",
                "text": f"Löytyi *{len(products)}* tuote(tta) Prisma.fi Pokemon-valikoimasta.",
            },
        },
    ]
    for product in products:
        section: dict[str, Any] = {
            "type": "section",
            "text": {"type": "mrkdwn", "text": "\n".join(product_lines(product))},
        }
        if product.get("image"):
            section["accessory"] = {
                "type": "image",
                "image_url": product["image"],
                "alt_text": product["name"][:50],
            }
        blocks.append(section)
    blocks.append(
        {
            "type": "context",
            "elements": [{"type": "mrkdwn", "text": f"<{BRAND_URL}|Avaa Pokemon-sivu>"}],
        }
    )
    send_to_channels(
        slack_payload={"text": fallback, "blocks": blocks},
        telegram_text=telegram_product_message(title, products),
    )


def notify_text(text: str) -> None:
    send_to_channels(slack_payload={"text": text}, telegram_text=html_escape(text))


def diff_and_notify(snapshot: dict[str, Any], announce: bool, dry_run: bool) -> dict[str, Any]:
    state = load_state()
    known = state.setdefault("products", {})
    newly_listed: list[dict[str, Any]] = []
    newly_available: list[dict[str, Any]] = []

    for product in snapshot["matches"]:
        previous = known.get(product["id"], {})
        record = {
            "name": product["name"],
            "url": product["url"],
            "available": product["available"],
            "availability": product["availability"],
            "first_seen": previous.get("first_seen") or snapshot["checked_at"],
            "last_seen": snapshot["checked_at"],
            "alerted_listed": bool(previous.get("alerted_listed")),
            "alerted_available": bool(previous.get("alerted_available")),
        }
        if not record["alerted_listed"]:
            newly_listed.append(product)
            record["alerted_listed"] = True
        if product["available"] and not record["alerted_available"]:
            newly_available.append(product)
            record["alerted_available"] = True
        known[product["id"]] = record

    state["last_check"] = snapshot["checked_at"]
    state["consecutive_errors"] = 0
    state["error_alerted"] = False

    if dry_run:
        return {
            "newly_listed": newly_listed,
            "newly_available": newly_available,
            "would_announce": announce and not state.get("announced"),
        }

    if announce and not state.get("announced"):
        notify_text(
            "Pokemon-seuranta käynnissä. Tarkistan Prisma.fi-sivua 15 min välein "
            f"({snapshot['brand_product_count']} tuotetta nyt, "
            f"{len(snapshot['matches'])} osumaa 30th Celebrationille)."
        )
        state["announced"] = True

    if newly_available:
        notify_products(
            "Pokémon 30th Celebration on myynnissä!",
            "Pokémon 30th Celebration -kortit ovat nyt myynnissä Prismassa.",
            newly_available,
        )
        log(f"Hälytys: {len(newly_available)} tuotetta myynnissä")
    if newly_listed and not newly_available:
        notify_products(
            "Pokémon 30th Celebration listattiin Prismaan",
            "Pokémon 30th Celebration -tuotteita ilmestyi Prisma.fi-sivulle.",
            newly_listed,
        )
        log(f"Hälytys: {len(newly_listed)} uutta listattua tuotetta")
    elif newly_listed:
        available_ids = {product["id"] for product in newly_available}
        leftover = [product for product in newly_listed if product["id"] not in available_ids]
        if leftover:
            notify_products(
                "Lisää 30th Celebration -tuotteita listattiin",
                "Uusia Pokémon 30th Celebration -tuotteita ilmestyi Prismaan.",
                leftover,
            )

    save_state(state)
    return {"newly_listed": newly_listed, "newly_available": newly_available}


def handle_error(error: Exception, dry_run: bool) -> None:
    log(f"VIRHE: {error}")
    if dry_run:
        return
    state = load_state()
    state["consecutive_errors"] = int(state.get("consecutive_errors") or 0) + 1
    if state["consecutive_errors"] >= 3 and not state.get("error_alerted") and has_notifier():
        try:
            notify_text(f"Pokemon-seuranta ei saanut luettua Prismaa: {error}")
            state["error_alerted"] = True
        except Exception as slack_error:  # noqa: BLE001
            log(f"Slack-virheilmoitus epäonnistui: {slack_error}")
    save_state(state)


def run_once(announce: bool, dry_run: bool) -> int:
    try:
        snapshot = collect_matches()
    except Exception as error:  # noqa: BLE001
        handle_error(error, dry_run)
        return 1

    log(
        f"Tarkistus ok: {snapshot['brand_product_count']}/{snapshot['brand_total_count']} "
        f"tuotetta, {len(snapshot['matches'])} 30th-osumaa"
    )
    for product in snapshot["matches"]:
        log(f"  - {product['name']} ({availability_label(product['availability'])}) {product['url']}")

    if not has_notifier() and not dry_run:
        log("Ei Slack- tai Telegram-asetuksia — tulokset vain lokiin.")
        state = load_state()
        state["last_check"] = snapshot["checked_at"]
        save_state(state)
        return 0

    result = diff_and_notify(snapshot, announce=announce, dry_run=dry_run)
    if dry_run:
        log(
            f"Dry-run: uusia listauksia {len(result['newly_listed'])}, "
            f"uusia saatavia {len(result['newly_available'])}"
        )
    elif not result["newly_listed"] and not result["newly_available"]:
        log("Ei uusia 30th Celebration -hälytyksiä.")
    return 0


def self_test() -> int:
    should_match = [
        "Pokémon TCG 30th Celebration Elite Trainer Box",
        "Pokemon 30-vuotisjuhlasetti",
        "Pokémon 30th Anniversary Booster",
        "Pokemon juhlavuosi collection",
        "Pokémon TCG 30 Booster Bundle",
        "Pokemon 30",
    ]
    should_not_match = [
        "Pokemon Pehmo 30 cm Pikachu",
        "Pokemon Pehmo 30 cm",
        "4D Puzzles Pokemon 30 cm - Charmander",
        "Pokémon TCG Pokémon day -juhlatuote",
        "Pokémon TCG ME02.5 Elite Trainer Box",
        "Pokémon TCG Collector's Chest 2026",
        "Pokémonin 30-vuotisjuhlat ovat käynnissä – tästä juhlavuoden uutuuskortit!",
        "Lasten Pokemon bokserit 2-pack HY30034",
    ]
    failed = False
    for name in should_match:
        if not is_anniversary_product(name):
            print(f"FAIL: olisi pitänyt täsmätä: {name}")
            failed = True
    for name in should_not_match:
        if is_anniversary_product(name):
            print(f"FAIL: ei olisi saanut täsmätä: {name}")
            failed = True
    if not is_anniversary_product("30th Celebration Elite Trainer Box", "Pokemon", require_pokemon=True):
        print("FAIL: brand+30th Celebration olisi pitänyt täsmätä haussa")
        failed = True
    if is_anniversary_product("Decorata Party Happy Celebration banneri", require_pokemon=True):
        print("FAIL: juhlakoriste ei saisi täsmätä haussa")
        failed = True
    if failed:
        return 1
    print("Self-test ok")
    return 0


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Prisma Pokemon 30th Celebration -vahti")
    parser.add_argument("--once", action="store_true", help="Aja yksi tarkistus ja lopeta (oletus)")
    parser.add_argument("--watch", action="store_true", help="Tarkista toistuvasti")
    parser.add_argument("--interval", type=int, default=0, help="Tarkistusväli minuuteissa (--watch)")
    parser.add_argument("--announce", action="store_true", help="Lähetä käynnistysviesti")
    parser.add_argument("--test-slack", action="store_true", help="Lähetä testiviesti Slackiin")
    parser.add_argument("--test-telegram", action="store_true", help="Lähetä testiviesti Telegramiin")
    parser.add_argument(
        "--telegram-chat-id",
        action="store_true",
        help="Hae chat-id: avaa botti, lähetä sille viesti ja aja tämä",
    )
    parser.add_argument("--dry-run", action="store_true", help="Älä kirjoita tilaa äläkä lähetä ilmoituksia")
    parser.add_argument("--self-test", action="store_true", help="Aja nimensuodatuksen testit")
    return parser.parse_args()


def main() -> int:
    load_env()
    args = parse_args()
    if args.self_test:
        return self_test()
    if args.test_slack:
        post_slack({"text": "Pokemon-seurannan Slack-yhteys toimii."})
        print("Testiviesti lähetetty Slackiin.")
        return 0
    if args.telegram_chat_id:
        token, _ = telegram_creds()
        if not token:
            raise RuntimeError("Lisää TELEGRAM_BOT_TOKEN tiedostoon .env")
        request = urllib.request.Request(f"https://api.telegram.org/bot{token}/getUpdates")
        with urllib.request.urlopen(request, timeout=20) as response:
            payload = json.loads(response.read().decode("utf-8"))
        chats = []
        for update in payload.get("result") or []:
            message = update.get("message") or update.get("channel_post") or {}
            chat = message.get("chat") or {}
            if chat.get("id") is not None:
                chats.append((str(chat["id"]), chat.get("username") or chat.get("first_name") or ""))
        if not chats:
            print("Ei viestejä. Avaa botti Telegramissa, paina Start ja aja komento uudestaan.")
            return 1
        print("Löytyneet chat-id:t:")
        for chat_id, name in dict(chats).items():
            print(f"  {chat_id}  {name}".rstrip())
        return 0
    if args.test_telegram:
        post_telegram("Pokemon-seurannan Telegram-yhteys toimii.")
        print("Testiviesti lähetetty Telegramiin.")
        return 0

    interval = args.interval or int(os.environ.get("CHECK_INTERVAL_MINUTES") or 15)
    if args.watch:
        log(f"Aloitetaan seuranta, väli {interval} min")
        while True:
            run_once(announce=args.announce, dry_run=args.dry_run)
            args.announce = False
            time.sleep(max(interval, 5) * 60)
    return run_once(announce=args.announce, dry_run=args.dry_run)


if __name__ == "__main__":
    sys.exit(main())
