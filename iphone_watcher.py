#!/usr/bin/env python3
"""Seuraa iPhone 17 256 Gt laventelin kertahintaa ja hälyttää alle kynnyksen."""

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
from typing import Any, Callable

ROOT = Path(__file__).resolve().parent
DATA_DIR = ROOT / "data"
STATE_PATH = DATA_DIR / "iphone_state.json"
LOG_PATH = DATA_DIR / "iphone.log"

PRODUCT_NAME = "iPhone 17 256 Gt laventeli"
DEFAULT_THRESHOLD = 800.0
REQUEST_PAUSE_SECONDS = 1.2
NEXT_DATA_RE = re.compile(
    r'<script id="__NEXT_DATA__" type="application/json">(.*?)</script>',
    re.DOTALL,
)
LD_JSON_RE = re.compile(
    r'<script[^>]+application/ld\+json[^>]*>(.*?)</script>',
    re.IGNORECASE | re.DOTALL,
)
PRICE_TOKEN_RE = re.compile(
    r"(\d{1,2}(?:[\s\u00a0]\d{3})+|\d+)(?:[.,](\d{1,2}))?"
)
KERTAMAKSU_RE = re.compile(
    r"Kertamaksu.{0,320}?price-now[^>]*>\s*([0-9\s\u00a0]+)",
    re.IGNORECASE | re.DOTALL,
)
ELISA_OWN_PRICE_RE = re.compile(
    r'data-testid="vendor-price-elisa"[^>]*>.*?<span>\s*Elisa\s*</span>\s*<span>\s*([0-9\s\u00a0.,]+)',
    re.IGNORECASE | re.DOTALL,
)

USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/122.0.0.0 Safari/537.36 IphonePriceWatch/1.0"
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
        os.environ.setdefault(key.strip(), value.strip().strip("'").strip('"'))


def threshold() -> float:
    raw = (os.environ.get("IPHONE_PRICE_THRESHOLD") or "").strip()
    if not raw:
        return DEFAULT_THRESHOLD
    try:
        return float(raw.replace(",", "."))
    except ValueError:
        return DEFAULT_THRESHOLD


def fetch(url: str, accept: str = "text/html,application/xhtml+xml") -> str:
    request = urllib.request.Request(
        url,
        headers={
            "User-Agent": USER_AGENT,
            "Accept": accept,
            "Accept-Language": "fi-FI,fi;q=0.9,en;q=0.8",
        },
    )
    with urllib.request.urlopen(request, timeout=25) as response:
        return response.read().decode("utf-8", "replace")


def fetch_json(url: str) -> Any:
    return json.loads(fetch(url, accept="application/json"))


def parse_fi_price(text: str) -> float | None:
    if not text:
        return None
    match = PRICE_TOKEN_RE.search(str(text).replace("\u00a0", " "))
    if not match:
        return None
    whole = match.group(1).replace(" ", "")
    fraction = match.group(2) or "0"
    try:
        value = float(f"{whole}.{fraction}")
    except ValueError:
        return None
    if value < 200 or value > 2500:
        return None
    return value


def cents_to_euros(value: Any) -> float | None:
    try:
        amount = int(value)
    except (TypeError, ValueError):
        return None
    euros = amount / 100
    if euros < 200 or euros > 2500:
        return None
    return euros


def format_price(value: float | None) -> str:
    if value is None:
        return "hinta ei tiedossa"
    return f"{value:.2f} €".replace(".", ",")


def iter_ld_objects(html: str) -> list[Any]:
    objects: list[Any] = []
    for match in LD_JSON_RE.finditer(html):
        raw = match.group(1).strip()
        try:
            payload = json.loads(raw)
        except json.JSONDecodeError:
            continue
        objects.append(payload)
    return objects


def walk(obj: Any) -> list[dict[str, Any]]:
    found: list[dict[str, Any]] = []
    if isinstance(obj, dict):
        found.append(obj)
        for value in obj.values():
            found.extend(walk(value))
    elif isinstance(obj, list):
        for value in obj:
            found.extend(walk(value))
    return found


def ld_consumer_price(html: str) -> float | None:
    prices: list[float] = []
    for payload in iter_ld_objects(html):
        for item in walk(payload):
            types = item.get("@type")
            type_names = types if isinstance(types, list) else [types]
            if "Offer" not in type_names:
                continue
            name = str(item.get("name") or "")
            if re.search(r"business|excl\.?\s*vat|alv\s*0", name, re.I):
                continue
            parsed = parse_fi_price(item.get("price"))
            if parsed is not None:
                prices.append(parsed)
            for spec in item.get("priceSpecification") or []:
                if not isinstance(spec, dict):
                    continue
                if spec.get("valueAddedTaxIncluded") is False:
                    continue
                price_type = str(spec.get("priceType") or "")
                if "Strikethrough" in price_type:
                    continue
                parsed = parse_fi_price(spec.get("price"))
                if parsed is not None:
                    prices.append(parsed)
    return min(prices) if prices else None


def parse_verkkokauppa(_html: str | None = None) -> float:
    data = fetch_json("https://web-api.service.verkkokauppa.com/product/1011416")
    price = parse_fi_price((data.get("price") or {}).get("current"))
    if price is None:
        raise RuntimeError("Verkkokauppa.com ei palauttanut hintaa.")
    return price


def parse_gigantti(html: str) -> float:
    price = ld_consumer_price(html)
    if price is None:
        raise RuntimeError("Gigantin sivulta ei löytynyt kertahintaa.")
    return price


def parse_dna(html: str) -> float:
    match = NEXT_DATA_RE.search(html)
    if not match:
        raise RuntimeError("DNA-sivulta ei löytynyt tuotetietoja.")
    product = json.loads(match.group(1)).get("props", {}).get("pageProps", {}).get("product") or {}
    for option in product.get("priceOptions") or []:
        length = option.get("contractLength")
        if length is None or int(length) != 0:
            continue
        for charge in option.get("oneTimeCharges") or []:
            if charge.get("otcCode") == "devicePrice":
                price = cents_to_euros(charge.get("grossSellingPrice"))
                if price is not None:
                    return price
        price = cents_to_euros(option.get("grossContractTotalPrice"))
        if price is not None:
            return price
    price = ld_consumer_price(html)
    if price is not None:
        return price
    raise RuntimeError("DNA:n kertahintaa (ilman liittymää) ei löytynyt.")


def parse_elisa(html: str) -> float:
    match = ELISA_OWN_PRICE_RE.search(html)
    if match:
        price = parse_fi_price(match.group(1))
        if price is not None:
            return price
    price = ld_consumer_price(html)
    if price is None:
        raise RuntimeError("Elisan sivulta ei löytynyt kertahintaa.")
    return price


def parse_telia(html: str) -> float:
    match = KERTAMAKSU_RE.search(html)
    if match:
        price = parse_fi_price(match.group(1))
        if price is not None:
            return price
    fallback = re.search(r"Kertamaksu.{0,80}?([0-9\s\u00a0]{3,7})\s*€", html, re.I | re.S)
    if fallback:
        price = parse_fi_price(fallback.group(1))
        if price is not None:
            return price
    raise RuntimeError("Telian kertamaksua ei löytynyt.")


def parse_power(html: str) -> float:
    price = ld_consumer_price(html)
    if price is None:
        raise RuntimeError("Powerin sivulta ei löytynyt kertahintaa.")
    return price


StoreParser = Callable[[str], float]

STORES: list[dict[str, Any]] = [
    {
        "id": "verkkokauppa",
        "name": "Verkkokauppa.com",
        "url": "https://www.verkkokauppa.com/fi/product/1011416/Apple-iPhone-17-256-Gt-puhelin-laventeli",
        "fetch": "json",
        "parse": parse_verkkokauppa,
    },
    {
        "id": "gigantti",
        "name": "Gigantti",
        "url": "https://www.gigantti.fi/product/puhelimet-tabletit-ja-alykellot/puhelimet/iphone-17-5g-alypuhelin-256-gb-laventeli/982721",
        "parse": parse_gigantti,
    },
    {
        "id": "dna",
        "name": "DNA",
        "url": "https://kauppa.dna.fi/tuote/p/apple-iphone-17-5g-256-gt-laventeli",
        "parse": parse_dna,
    },
    {
        "id": "elisa",
        "name": "Elisa",
        "url": "https://elisa.fi/kauppa/tuote/apple-iphone-17-256-gt-5g",
        "parse": parse_elisa,
    },
    {
        "id": "telia",
        "name": "Telia",
        "url": "https://www.telia.fi/kauppa/tuote/apple-iphone-17",
        "parse": parse_telia,
    },
    {
        "id": "power",
        "name": "Power",
        "url": "https://www.power.fi/puhelimet-ja-kamerat/puhelimet/apple-iphone-17-256-gt-laventeli/p-4157287/",
        "parse": parse_power,
    },
]


def check_store(store: dict[str, Any]) -> dict[str, Any]:
    result = {
        "id": store["id"],
        "name": store["name"],
        "url": store["url"],
        "price": None,
        "error": None,
    }
    try:
        html = ""
        if store.get("fetch") != "json":
            html = fetch(store["url"])
        result["price"] = store["parse"](html)
    except Exception as error:  # noqa: BLE001
        result["error"] = str(error)
        log(f"VIRHE {store['name']}: {error}")
    return result


def collect_prices() -> dict[str, Any]:
    results: list[dict[str, Any]] = []
    for index, store in enumerate(STORES):
        results.append(check_store(store))
        if index < len(STORES) - 1:
            time.sleep(REQUEST_PAUSE_SECONDS)
    priced = [item for item in results if item["price"] is not None]
    return {
        "checked_at": now_iso(),
        "threshold": threshold(),
        "results": results,
        "best": min(priced, key=lambda item: item["price"]) if priced else None,
        "errors": [item for item in results if item["error"]],
    }


def load_state() -> dict[str, Any]:
    if not STATE_PATH.exists():
        return {"stores": {}, "last_check": None, "consecutive_errors": 0, "error_alerted": False, "announced": False}
    return json.loads(STATE_PATH.read_text(encoding="utf-8"))


def save_state(state: dict[str, Any]) -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    STATE_PATH.write_text(json.dumps(state, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def slack_webhook() -> str:
    return (os.environ.get("SLACK_WEBHOOK_URL") or "").strip()


def telegram_creds() -> tuple[str, str]:
    return (os.environ.get("TELEGRAM_BOT_TOKEN") or "").strip(), (os.environ.get("TELEGRAM_CHAT_ID") or "").strip()


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
        raise RuntimeError("SLACK_WEBHOOK_URL puuttuu.")
    request = urllib.request.Request(
        webhook,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=20) as response:
        body = response.read().decode("utf-8", "replace")
        if response.status >= 300:
            raise RuntimeError(f"Slack vastasi {response.status}: {body}")


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
        raise RuntimeError(" | ".join(errors) if errors else "Ei ilmoituskanavaa.")


def snapshot_lines(snapshot: dict[str, Any]) -> list[str]:
    lines = []
    for item in snapshot["results"]:
        if item["price"] is not None:
            lines.append(f"{item['name']}: {format_price(item['price'])}")
        else:
            lines.append(f"{item['name']}: virhe ({item['error']})")
    return lines


def telegram_price_message(title: str, items: list[dict[str, Any]], footer: str = "") -> str:
    lines = [f"<b>{html_escape(title)}</b>", ""]
    for item in items:
        name = html_escape(item["name"])
        price = html_escape(format_price(item.get("price")))
        lines.append(f'<a href="{item["url"]}">{name}</a>: {price}')
    if footer:
        lines.extend(["", html_escape(footer)])
    return "\n".join(lines).strip()


def notify_drops(items: list[dict[str, Any]], limit: float) -> None:
    title = f"{PRODUCT_NAME} alle {limit:.0f} €"
    fallback = f"{PRODUCT_NAME} putosi alle {limit:.0f} €: " + ", ".join(
        f"{item['name']} {format_price(item['price'])}" for item in items
    )
    blocks = [
        {"type": "header", "text": {"type": "plain_text", "text": title[:150]}},
        {
            "type": "section",
            "text": {"type": "mrkdwn", "text": "Kertahinta ilman liittymää."},
        },
    ]
    for item in items:
        blocks.append(
            {
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": f"*<{item['url']}|{item['name']}>*\n{format_price(item['price'])}",
                },
            }
        )
    send_to_channels(
        slack_payload={"text": fallback, "blocks": blocks},
        telegram_text=telegram_price_message(title, items, "Kertahinta ilman liittymää."),
    )


def notify_text(text: str) -> None:
    send_to_channels(slack_payload={"text": text}, telegram_text=html_escape(text))


def diff_and_notify(snapshot: dict[str, Any], announce: bool, dry_run: bool) -> dict[str, Any]:
    state = load_state()
    known = state.setdefault("stores", {})
    limit = snapshot["threshold"]
    drops: list[dict[str, Any]] = []

    for item in snapshot["results"]:
        previous = known.get(item["id"], {})
        record = {
            "name": item["name"],
            "url": item["url"],
            "price": item["price"],
            "error": item["error"],
            "last_seen": snapshot["checked_at"],
            "alerted_below": bool(previous.get("alerted_below")),
        }
        if item["price"] is not None:
            if item["price"] < limit and not record["alerted_below"]:
                drops.append(item)
                record["alerted_below"] = True
            elif item["price"] >= limit:
                record["alerted_below"] = False
        known[item["id"]] = record

    state["last_check"] = snapshot["checked_at"]
    if snapshot["errors"] and not any(item["price"] is not None for item in snapshot["results"]):
        state["consecutive_errors"] = int(state.get("consecutive_errors") or 0) + 1
    else:
        state["consecutive_errors"] = 0
        state["error_alerted"] = False

    if dry_run:
        return {"drops": drops, "would_announce": announce and not state.get("announced")}

    if announce and not state.get("announced"):
        lines = snapshot_lines(snapshot)
        notify_text(
            f"{PRODUCT_NAME} -hintavahti käynnissä (kynnys alle {limit:.0f} €).\n" + "\n".join(lines)
        )
        state["announced"] = True

    if drops:
        notify_drops(drops, limit)
        log("Hälytys: " + ", ".join(f"{item['name']} {format_price(item['price'])}" for item in drops))

    save_state(state)
    return {"drops": drops}


def handle_error(error: Exception, dry_run: bool) -> None:
    log(f"VIRHE: {error}")
    if dry_run:
        return
    state = load_state()
    state["consecutive_errors"] = int(state.get("consecutive_errors") or 0) + 1
    if state["consecutive_errors"] >= 3 and not state.get("error_alerted") and has_notifier():
        try:
            notify_text(f"iPhone-hintavahti ei saanut luettua kauppoja: {error}")
            state["error_alerted"] = True
        except Exception as notify_error:  # noqa: BLE001
            log(f"Virheilmoitus epäonnistui: {notify_error}")
    save_state(state)


def run_once(announce: bool, dry_run: bool) -> int:
    try:
        snapshot = collect_prices()
    except Exception as error:  # noqa: BLE001
        handle_error(error, dry_run)
        return 1

    limit = snapshot["threshold"]
    log(f"Tarkistus ok: kynnys alle {limit:.0f} €")
    for item in snapshot["results"]:
        if item["price"] is not None:
            flag = " ALLE" if item["price"] < limit else ""
            log(f"  - {item['name']}: {format_price(item['price'])}{flag} {item['url']}")
        else:
            log(f"  - {item['name']}: VIRHE {item['error']}")

    if not any(item["price"] is not None for item in snapshot["results"]):
        handle_error(RuntimeError("Yksikään kauppa ei palauttanut hintaa."), dry_run)
        return 1

    if not has_notifier() and not dry_run:
        log("Ei Slack- tai Telegram-asetuksia — tulokset vain lokiin.")
        state = load_state()
        state["last_check"] = snapshot["checked_at"]
        save_state(state)
        return 0

    result = diff_and_notify(snapshot, announce=announce, dry_run=dry_run)
    if dry_run:
        log(f"Dry-run: putoamia {len(result['drops'])}")
    elif not result["drops"]:
        log("Ei uusia alle-kynnys-hälytyksiä.")
    return 0


def self_test() -> int:
    failed = False
    cases = {
        "1 149": 1149.0,
        "1\u00a0149": 1149.0,
        "899,00": 899.0,
        "799.00": 799.0,
        "1149": 1149.0,
    }
    for raw, expected in cases.items():
        got = parse_fi_price(raw)
        if got != expected:
            print(f"FAIL parse_fi_price({raw!r}) = {got}, odotettu {expected}")
            failed = True
    if parse_fi_price("5,99") is not None:
        print("FAIL: toimituskulu ei saisi kelvata puhelimen hinnaksi")
        failed = True
    if cents_to_euros(99900) != 999.0:
        print("FAIL: DNA-sentit")
        failed = True
    html = '''<script type="application/ld+json">{"@type":"Product","offers":[
      {"@type":"Offer","name":"Standard Price","price":"899","priceCurrency":"EUR"},
      {"@type":"Offer","name":"Business Price (Excl. VAT)","price":"716.33","priceCurrency":"EUR"}
    ]}</script>'''
    if ld_consumer_price(html) != 899.0:
        print(f"FAIL: Gigantti-tarjous {ld_consumer_price(html)}")
        failed = True
    if failed:
        return 1
    print("Self-test ok")
    return 0


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=f"{PRODUCT_NAME} -hintavahti")
    parser.add_argument("--once", action="store_true", help="Aja yksi tarkistus ja lopeta (oletus)")
    parser.add_argument("--announce", action="store_true", help="Lähetä käynnistysviesti nykyisillä hinnoilla")
    parser.add_argument("--dry-run", action="store_true", help="Älä kirjoita tilaa äläkä lähetä ilmoituksia")
    parser.add_argument("--self-test", action="store_true", help="Aja hinnan jäsennystestit")
    return parser.parse_args()


def main() -> int:
    load_env()
    args = parse_args()
    if args.self_test:
        return self_test()
    return run_once(announce=args.announce, dry_run=args.dry_run)


if __name__ == "__main__":
    sys.exit(main())
