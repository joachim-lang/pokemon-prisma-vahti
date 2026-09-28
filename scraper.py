#!/usr/bin/env python3
"""Seuraa Prismaa, Kärkkäistä ja Verkkokauppaa ja ilmoittaa 30th Celebration -osumista."""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import time
import uuid
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
PRISMA_CARDS_URL = "https://www.prisma.fi/tuotemerkit/pokemon/kategoria/15/elektroniikka"
SEARCH_URLS = (
    "https://www.prisma.fi/haku?search=30",
    "https://www.prisma.fi/haku?search=pokemon+30",
    "https://www.prisma.fi/haku?search=30th+celebration",
    "https://www.prisma.fi/haku?search=pokemon+30th+celebration",
    "https://www.prisma.fi/haku?search=pokemon+30th",
    "https://www.prisma.fi/haku?search=30-vuotisjuhla",
    "https://www.prisma.fi/haku?search=pokemon+30-vuotis",
    "https://www.prisma.fi/haku?search=pokemon+juhlavuosi",
    "https://www.prisma.fi/haku?search=pokemon+ultra+premium",
    "https://www.prisma.fi/haku?search=pokemon+ultra-premium",
    "https://www.prisma.fi/haku?search=30th+ultra+premium",
    "https://www.prisma.fi/haku?search=pokemon+delta+reign",
    "https://www.prisma.fi/haku?search=delta+reign",
    "https://www.prisma.fi/haku?search=pokemon+umbreon+ultra+premium",
    "https://www.prisma.fi/haku?search=pokemon+booster+bundle",
)
PRODUCT_URL = "https://www.prisma.fi/tuotteet/{sok_id}/{slug}"
KARKKAINEN_CARDS_URL = "https://www.karkkainen.com/verkkokauppa/kerailykortit"
KARKKAINEN_LISTING_URL = (
    "https://www.karkkainen.com/verkkokauppa/kerailykortit"
    "?offset={offset}&facet=attributes.Tuotemerkki%3APokemon"
)
KARKKAINEN_SEARCH_URLS = (
    "https://www.karkkainen.com/verkkokauppa/search?searchTerm=pokemon+30th+celebration",
    "https://www.karkkainen.com/verkkokauppa/search?searchTerm=30th+celebration",
    "https://www.karkkainen.com/verkkokauppa/search?searchTerm=pokemon+30-vuotis",
    "https://www.karkkainen.com/verkkokauppa/search?searchTerm=30-vuotisjuhla",
    "https://www.karkkainen.com/verkkokauppa/search?searchTerm=pokemon+ultra+premium",
    "https://www.karkkainen.com/verkkokauppa/search?searchTerm=pokemon+ultra-premium",
    "https://www.karkkainen.com/verkkokauppa/search?searchTerm=pokemon+delta+reign",
    "https://www.karkkainen.com/verkkokauppa/search?searchTerm=delta+reign",
    "https://www.karkkainen.com/verkkokauppa/search?searchTerm=pokemon+umbreon+ultra+premium",
    "https://www.karkkainen.com/verkkokauppa/search?searchTerm=pokemon+booster+bundle",
)
KARKKAINEN_BASE = "https://www.karkkainen.com/verkkokauppa"
VK_SITE = "https://www.verkkokauppa.com"
VK_ETB_PID = "1069670"
VK_ETB_URL = (
    f"{VK_SITE}/fi/product/{VK_ETB_PID}/"
    "Pokemon-TCG-30th-Elite-Trainer-Box-kerailykortit"
)
VK_CATALOG_URL = (
    f"{VK_SITE}/fi/catalog/trading-cards/kerailykortit?query=pokemon+30"
)
VK_PREMIUM_SEARCH_URL = (
    f"{VK_SITE}/fi/catalog/trading-cards/kerailykortit?query=pokemon+ultra+premium"
)
VK_DELTA_SEARCH_URL = (
    f"{VK_SITE}/fi/catalog/trading-cards/kerailykortit?query=pokemon+delta+reign"
)
VK_BUNDLE_SEARCH_URL = (
    f"{VK_SITE}/fi/catalog/trading-cards/kerailykortit?query=pokemon+booster+bundle"
)
VK_UMBREON_SEARCH_URL = (
    f"{VK_SITE}/fi/catalog/trading-cards/kerailykortit?query=pokemon+umbreon+ultra+premium"
)
VK_EXTRA_SEARCHES = (
    ("pokemon ultra premium", VK_PREMIUM_SEARCH_URL),
    ("pokemon delta reign", VK_DELTA_SEARCH_URL),
    ("pokemon booster bundle", VK_BUNDLE_SEARCH_URL),
    ("pokemon umbreon ultra premium", VK_UMBREON_SEARCH_URL),
)
VK_PRODUCT_API = "https://web-api.service.verkkokauppa.com/product/{pid}"
VK_AVAIL_API = "https://product.service.verkkokauppa.com/fi/api/v1/availability"
VK_SEARCH_API = "https://search.service.verkkokauppa.com/fi/api/v1/product-search"
# SV9 Journey Together 36-pack osuu pokemon+30 -hakuun (kuvauksessa "yli 30"), ei 30th.
VK_IGNORED_PIDS = frozenset({"980153"})
VK_WATCH_PRODUCTS = (
    {
        "pid": "1069670",
        "name": "Pokémon TCG: 30th Elite Trainer Box keräilykortit",
        "url": VK_ETB_URL,
        "price": "80.00 €",
    },
)
PRISMA_WATCH_PRODUCTS = (
    {
        "id": "111388829",
        "slug": "pokemon-elite-trainer-box-30th-111388829",
        "name": "Pokémon Elite Trainer Box 30th",
    },
)
PRISMA_FAST_SEARCH_URLS = (
    "https://www.prisma.fi/haku?search=pokemon+30th",
    "https://www.prisma.fi/haku?search=pokemon+ultra+premium",
    "https://www.prisma.fi/haku?search=pokemon+delta+reign",
    "https://www.prisma.fi/haku?search=pokemon+umbreon+ultra+premium",
    "https://www.prisma.fi/haku?search=pokemon+booster+bundle",
)
MAX_PAGES = 8
REQUEST_PAUSE_SECONDS = 1.5
FAST_CHECK_SECONDS_DEFAULT = 15
FAST_LISTINGS_SECONDS = 90
FAST_KARKKAINEN_SECONDS = 180
RATE_LIMIT_STATUSES = frozenset({403, 429, 503})
MAX_BACKOFF_SECONDS = 180

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
    r"""
    (?<!\d)30(?:[.,]\d+)?
    (?:
        \s*[x×]\s*\d+(?:[.,]\d+)?(?:\s*(?:cm|mm))?
        |
        \s*(?:cm|mm|cl|ml|g|kg|kpl)\b
    )
    """,
    re.IGNORECASE | re.VERBOSE,
)
# Sivun markkinointibanneri, ei myynnissä oleva tuote.
IGNORED_MARKETING_RE = re.compile(
    r"30-vuotisjuhlat ovat k[aä]ynniss|tästä juhlavuoden uutuuskortit",
    re.IGNORECASE,
)
# Vanhat booster-laatikot, joita pokemon+30 -haku voi nostaa.
IGNORED_BOOSTER_RE = re.compile(
    r"journey\s*together|\bsv9\b|scarlet\s*(?:and|&)\s*violet",
    re.IGNORECASE,
)
BOOSTER_NAME_RE = re.compile(r"booster", re.IGNORECASE)
BOOSTER_BUNDLE_RE = re.compile(r"booster\s*bundle", re.IGNORECASE)
ULTRA_PREMIUM_RE = re.compile(r"ultra[\s-]*premium|\bupc\b", re.IGNORECASE)
DELTA_REIGN_RE = re.compile(r"delta\s*reign", re.IGNORECASE)
ETB_RE = re.compile(r"elite\s*trainer\s*box|\betb\b", re.IGNORECASE)
UMBREON_RE = re.compile(r"umbreon", re.IGNORECASE)
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
    "Chrome/140.0.0.0 Safari/537.36"
)


class RateLimitError(RuntimeError):
    def __init__(self, status: int, url: str, retry_after: int | None = None) -> None:
        self.status = status
        self.url = url
        self.retry_after = retry_after
        extra = f", retry-after {retry_after}s" if retry_after else ""
        super().__init__(f"HTTP {status} {url}{extra}")


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


def env_int(name: str, default: int) -> int:
    raw = (os.environ.get(name) or "").strip()
    if not raw:
        return default
    try:
        return int(raw)
    except ValueError:
        return default


def fetch_html(url: str) -> str:
    return _http_get(
        url,
        accept="text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    )


def fetch_json(url: str, referer: str = VK_SITE + "/") -> Any:
    body = _http_get(
        url,
        accept="application/json",
        extra_headers={"Origin": VK_SITE, "Referer": referer},
    )
    return json.loads(body)


def retry_after_seconds(error: urllib.error.HTTPError) -> int | None:
    raw = error.headers.get("Retry-After") if error.headers else None
    if not raw:
        return None
    try:
        return max(1, int(raw))
    except ValueError:
        return None


def _http_get(url: str, *, accept: str, extra_headers: dict[str, str] | None = None) -> str:
    headers = {
        "User-Agent": USER_AGENT,
        "Accept": accept,
        "Accept-Language": "fi-FI,fi;q=0.9,en;q=0.8",
    }
    if extra_headers:
        headers.update(extra_headers)
    last_limit: RateLimitError | None = None
    for attempt in range(3):
        request = urllib.request.Request(url, headers=headers)
        try:
            with urllib.request.urlopen(request, timeout=25) as response:
                return response.read().decode("utf-8", "replace")
        except urllib.error.HTTPError as error:
            if error.code not in RATE_LIMIT_STATUSES:
                raise
            wait = retry_after_seconds(error) or min(10 * (2**attempt), 60)
            last_limit = RateLimitError(error.code, url, retry_after=wait)
            log(f"Kauppa hidasti ({error.code}), odotetaan {wait}s")
            time.sleep(wait)
    assert last_limit is not None
    raise last_limit


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
    return is_purchasable(availability)


def is_purchasable(availability: dict[str, bool]) -> bool:
    """Prisma: faded #b7d4c2 vs active #037842. Myymälälippu ei riitä."""
    return bool(availability.get("ecom") or availability.get("click_and_collect"))


def looks_like_pokemon_product(name: str, brand: str = "") -> bool:
    return bool(POKEMON_RE.search(name) or TCG_RE.search(name) or re.search(r"pokemon", brand, re.I))


def name_for_match(name: str) -> str:
    return MEASUREMENT_30_RE.sub(" ", name)


def is_ignored_marketing(name: str) -> bool:
    return bool(IGNORED_MARKETING_RE.search(name))


def is_ignored_booster(name: str, product_id: str = "") -> bool:
    pid = product_id.split(":")[-1] if product_id else ""
    return pid in VK_IGNORED_PIDS or bool(IGNORED_BOOSTER_RE.search(name))


def is_booster_product(name: str) -> bool:
    return (
        bool(BOOSTER_NAME_RE.search(name))
        and bool(POKEMON_RE.search(name))
        and not is_ignored_booster(name)
    )


def is_booster_bundle_product(name: str) -> bool:
    return bool(BOOSTER_BUNDLE_RE.search(name)) and bool(POKEMON_RE.search(name))


def is_ultra_premium_product(name: str) -> bool:
    return bool(ULTRA_PREMIUM_RE.search(name)) and bool(POKEMON_RE.search(name))


def is_etb_product(name: str) -> bool:
    return bool(ETB_RE.search(name)) and bool(POKEMON_RE.search(name))


def is_delta_reign_product(name: str) -> bool:
    return bool(DELTA_REIGN_RE.search(name)) and bool(POKEMON_RE.search(name))


def is_priority_set(name: str) -> bool:
    return is_anniversary_product(name, require_pokemon=True) or is_delta_reign_product(name)


def is_priority_product(name: str, product_id: str = "") -> bool:
    """ETB-restock, Ultra-Premium (etenkin Umbreon) ja Booster Bundle."""
    if is_ignored_booster(name, product_id) or is_ignored_marketing(name):
        return False
    if not looks_like_pokemon_product(name):
        return False
    if is_etb_product(name) and is_priority_set(name):
        return True
    if is_ultra_premium_product(name) and (
        is_priority_set(name) or bool(UMBREON_RE.search(name))
    ):
        return True
    if is_booster_bundle_product(name) and is_priority_set(name):
        return True
    return False


def is_watched_drop(name: str, product_id: str = "") -> bool:
    return is_priority_product(name, product_id)


def is_anniversary_product(name: str, brand: str = "", require_pokemon: bool = False) -> bool:
    if is_ignored_marketing(name) or is_ignored_booster(name):
        return False
    if require_pokemon and not looks_like_pokemon_product(name, brand):
        return False
    return bool(MATCH_RE.search(name_for_match(name)))


def should_watch_product(
    name: str,
    brand: str = "",
    require_pokemon: bool = False,
    allow_booster: bool = False,
    product_id: str = "",
) -> bool:
    if is_ignored_booster(name, product_id) or is_ignored_marketing(name):
        return False
    if is_priority_product(name, product_id):
        return True
    if allow_booster and is_watched_drop(name, product_id):
        return True
    return False


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
        "url": PRODUCT_URL.format(sok_id=sok_id, slug=slug) if sok_id and slug else BRAND_URL,
        "price": cents_to_euros(raw.get("finalPrice") if raw.get("finalPrice") is not None else raw.get("price")),
        "image": raw.get("mainImage"),
        "source": source,
        "store": "Prisma",
        "availability": availability,
        "available": is_purchasable(availability),
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
        url = PRISMA_CARDS_URL if page == 1 else f"{PRISMA_CARDS_URL}?page={page}"
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


def fetch_prisma_brand_watch() -> list[dict[str, Any]]:
    collected: dict[str, dict[str, Any]] = {}
    page = 1
    while page <= 3:
        url = PRISMA_CARDS_URL if page == 1 else f"{PRISMA_CARDS_URL}?page={page}"
        page_props = parse_next_data(fetch_html(url))
        batch = products_from_page(page_props, "prisma-cards")
        if not batch:
            break
        for product in batch:
            if product["id"] and should_watch_product(
                product["name"],
                product.get("brand", ""),
                require_pokemon=True,
                allow_booster=True,
                product_id=product.get("id") or "",
            ):
                collected[product["id"]] = product
        page += 1
        time.sleep(REQUEST_PAUSE_SECONDS)
    return list(collected.values())


def fetch_prisma_cart_availability(sok_id: str, slug: str) -> dict[str, bool]:
    url = PRODUCT_URL.format(sok_id=sok_id, slug=slug)
    page_props = parse_next_data(fetch_html(url))
    raw = (page_props.get("availability") or {}).get(sok_id) or {}
    return {
        "ecom": bool(raw.get("ecom")),
        "click_and_collect": bool(raw.get("clickAndCollect")),
        "store": bool(raw.get("brickAndMortar")),
    }


def enrich_prisma_cart_status(products: list[dict[str, Any]]) -> None:
    for product in products:
        if product.get("store") != "Prisma" or not product.get("id") or not product.get("slug"):
            continue
        try:
            availability = fetch_prisma_cart_availability(product["id"], product["slug"])
            product["availability"] = availability
            product["available"] = is_purchasable(availability)
        except Exception as error:  # noqa: BLE001
            log(f"Prisma tuotesivu {product['id']}: {error}")
        time.sleep(REQUEST_PAUSE_SECONDS)


def fetch_search_products() -> list[dict[str, Any]]:
    collected: dict[str, dict[str, Any]] = {}
    for url in SEARCH_URLS:
        page_props = parse_next_data(fetch_html(url))
        for product in products_from_page(page_props, "search"):
            if product["id"] and should_watch_product(
                product["name"],
                product.get("brand", ""),
                require_pokemon=True,
                product_id=product.get("id") or "",
            ):
                collected[product["id"]] = product
        time.sleep(REQUEST_PAUSE_SECONDS)
    return list(collected.values())


def parse_karkkainen_listing(html: str) -> dict[str, Any]:
    match = NEXT_DATA_RE.search(html)
    if not match:
        raise RuntimeError("Kärkkäisen sivulta ei löytynyt tuotetietoja (__NEXT_DATA__).")
    fallback = json.loads(match.group(1)).get("props", {}).get("pageProps", {}).get("fallback") or {}
    listings = [
        value
        for value in fallback.values()
        if isinstance(value, dict) and isinstance(value.get("contents"), list) and "total" in value
    ]
    if not listings:
        raise RuntimeError("Kärkkäisen tuotelistaa ei löytynyt.")
    return max(listings, key=lambda item: len(item.get("contents") or []))


def karkkainen_price(raw: dict[str, Any]) -> str | None:
    prices = raw.get("price") or []
    for usage in ("Display", "Offer"):
        for item in prices:
            if item.get("usage") == usage and item.get("value") is not None:
                try:
                    return f"{float(item['value']):.2f} €"
                except (TypeError, ValueError):
                    continue
    return None


def karkkainen_url(raw: dict[str, Any]) -> str:
    href = str((raw.get("seo") or {}).get("href") or "").strip()
    if href.startswith("http"):
        return href
    if href.startswith("/verkkokauppa"):
        return "https://www.karkkainen.com" + href
    if href.startswith("/"):
        return KARKKAINEN_BASE + href
    return KARKKAINEN_CARDS_URL


def normalize_karkkainen_product(raw: dict[str, Any], source: str) -> dict[str, Any]:
    product_id = str(raw.get("partNumber") or raw.get("id") or "").strip()
    buyable = str(raw.get("buyable") or "").lower() == "true"
    availability = {"ecom": buyable, "click_and_collect": False, "store": False}
    image = raw.get("thumbnail")
    if isinstance(image, str):
        image = image.replace("h_80", "h_234").replace("w_80", "w_234")
    return {
        "id": f"karkkainen:{product_id}" if product_id else "",
        "name": str(raw.get("name") or "").strip(),
        "slug": str((raw.get("seo") or {}).get("href") or "").strip(),
        "brand": str(raw.get("manufacturer") or "").strip(),
        "url": karkkainen_url(raw),
        "price": karkkainen_price(raw),
        "image": image,
        "source": source,
        "store": "Kärkkäinen",
        "availability": availability,
        "available": buyable,
    }


def fetch_karkkainen_products() -> tuple[list[dict[str, Any]], int]:
    collected: dict[str, dict[str, Any]] = {}
    total = 0
    offset = 0
    page = 1
    while page <= MAX_PAGES:
        listing = parse_karkkainen_listing(fetch_html(KARKKAINEN_LISTING_URL.format(offset=offset)))
        total = int(listing.get("total") or 0)
        batch = listing.get("contents") or []
        if not batch:
            break
        for raw in batch:
            if not isinstance(raw, dict):
                continue
            product = normalize_karkkainen_product(raw, "karkkainen")
            if product["id"]:
                collected[product["id"]] = product
        if len(collected) >= total:
            break
        offset += max(len(batch), 1)
        page += 1
        time.sleep(REQUEST_PAUSE_SECONDS)
    return list(collected.values()), total


def fetch_karkkainen_cards() -> list[dict[str, Any]]:
    collected: dict[str, dict[str, Any]] = {}
    offset = 0
    page = 1
    while page <= 3:
        url = KARKKAINEN_CARDS_URL if offset <= 0 else f"{KARKKAINEN_CARDS_URL}?offset={offset}"
        listing = parse_karkkainen_listing(fetch_html(url))
        batch = listing.get("contents") or []
        if not batch:
            break
        for raw in batch:
            if not isinstance(raw, dict):
                continue
            product = normalize_karkkainen_product(raw, "karkkainen-cards")
            if product["id"] and should_watch_product(
                product["name"],
                product.get("brand", ""),
                require_pokemon=True,
                allow_booster=True,
                product_id=product.get("id") or "",
            ):
                collected[product["id"]] = product
        offset += max(len(batch), 1)
        page += 1
        time.sleep(REQUEST_PAUSE_SECONDS)
    return list(collected.values())


def fetch_karkkainen_search() -> list[dict[str, Any]]:
    collected: dict[str, dict[str, Any]] = {}
    for url in KARKKAINEN_SEARCH_URLS:
        listing = parse_karkkainen_listing(fetch_html(url))
        for raw in listing.get("contents") or []:
            if not isinstance(raw, dict):
                continue
            product = normalize_karkkainen_product(raw, "karkkainen-search")
            if product["id"] and should_watch_product(
                product["name"],
                product.get("brand", ""),
                require_pokemon=True,
                product_id=product.get("id") or "",
            ):
                collected[product["id"]] = product
        time.sleep(REQUEST_PAUSE_SECONDS)
    return list(collected.values())


def fetch_karkkainen_watch() -> list[dict[str, Any]]:
    collected: dict[str, dict[str, Any]] = {}
    for product in fetch_karkkainen_search() + fetch_karkkainen_cards():
        if product.get("id"):
            collected[product["id"]] = product
    return list(collected.values())


def localized_text(value: Any) -> str:
    if isinstance(value, dict):
        for key in ("fi", "en", "sv"):
            if value.get(key):
                return str(value[key]).strip()
        for item in value.values():
            if item:
                return str(item).strip()
        return ""
    return str(value or "").strip()


def vk_price(raw: dict[str, Any]) -> str | None:
    price = raw.get("price")
    if isinstance(price, dict) and price.get("current") is not None:
        try:
            return f"{float(price['current']):.2f} €"
        except (TypeError, ValueError):
            pass
    articles = raw.get("articles") or []
    if articles and isinstance(articles[0], dict):
        nested = (articles[0].get("price") or {}) if isinstance(articles[0].get("price"), dict) else {}
        if nested.get("current") is not None:
            try:
                return f"{float(nested['current']):.2f} €"
            except (TypeError, ValueError):
                return None
    return None


def vk_href(raw: dict[str, Any], pid: str) -> str:
    href = localized_text(raw.get("href"))
    if not href:
        articles = raw.get("articles") or []
        if articles and isinstance(articles[0], dict):
            href = str(articles[0].get("href") or "").strip()
    if href.startswith("/"):
        return VK_SITE + href
    if href.startswith("http"):
        return href
    slug = localized_text(raw.get("slug")) or "tuote"
    return f"{VK_SITE}/fi/product/{pid}/{slug}" if pid else VK_CATALOG_URL


def vk_image(raw: dict[str, Any]) -> str | None:
    images = raw.get("images") or raw.get("marketingImages") or []
    if isinstance(images, list) and images:
        first = images[0]
        if isinstance(first, str) and first.startswith("http"):
            return first
        if isinstance(first, dict):
            for key in ("orig", "url", "src", "href"):
                value = first.get(key)
                if isinstance(value, str) and value.startswith("http"):
                    return value
    return None


def vk_is_purchasable(availability: dict[str, Any] | None) -> bool:
    """Harmaa ostoskori = ei voi ostaa; sininen = isPurchasable."""
    availability = availability or {}
    flags = availability.get("flags") or {}
    if flags.get("isSoldOut"):
        return False
    stocks = availability.get("stocks") or {}
    shipment = stocks.get("shipment") or {}
    if shipment.get("isPurchasable"):
        return True
    pickup = stocks.get("pickup") or {}
    if isinstance(pickup, dict):
        for location in pickup.values():
            if isinstance(location, dict) and location.get("isPurchasable"):
                return True
    return False


def vk_availability_flags(availability: dict[str, Any] | None) -> dict[str, bool]:
    buyable = vk_is_purchasable(availability)
    return {"ecom": buyable, "click_and_collect": False, "store": False}


def fetch_vk_availabilities(pids: list[str]) -> dict[str, dict[str, Any]]:
    if not pids:
        return {}
    query = urllib.parse.urlencode({"pids": ",".join(pids)})
    payload = fetch_json(f"{VK_AVAIL_API}?{query}", referer=VK_CATALOG_URL)
    found: dict[str, dict[str, Any]] = {}
    for row in payload or []:
        if isinstance(row, dict) and row.get("pid") is not None:
            found[str(row["pid"])] = row
    return found


def normalize_vk_product(
    raw: dict[str, Any],
    availability_raw: dict[str, Any] | None,
    source: str,
    notify_listed: bool,
) -> dict[str, Any]:
    pid = str(raw.get("pid") or raw.get("id") or "").strip()
    name = localized_text(raw.get("name"))
    brand_raw = raw.get("brand")
    if isinstance(brand_raw, dict):
        brand = localized_text(brand_raw.get("name") or brand_raw)
    else:
        brand = localized_text(brand_raw)
    availability = vk_availability_flags(availability_raw)
    return {
        "id": f"verkkokauppa:{pid}" if pid else "",
        "name": name,
        "slug": localized_text(raw.get("slug")),
        "brand": brand,
        "url": vk_href(raw, pid),
        "price": vk_price(raw),
        "image": vk_image(raw),
        "source": source,
        "store": "Verkkokauppa",
        "availability": availability,
        "available": availability["ecom"],
        "notify_listed": notify_listed,
    }


def fetch_verkkokauppa_etb() -> dict[str, Any]:
    raw = fetch_json(VK_PRODUCT_API.format(pid=VK_ETB_PID), referer=VK_ETB_URL)
    if not isinstance(raw, dict):
        raise RuntimeError("Verkkokaupan ETB-vastaus on odottamattomassa muodossa.")
    avail = fetch_vk_availabilities([VK_ETB_PID]).get(VK_ETB_PID, {})
    product = normalize_vk_product(raw, avail, "verkkokauppa-etb", notify_listed=False)
    if not product["id"]:
        raise RuntimeError("Verkkokaupan ETB:ltä puuttuu tuote-id.")
    return product


def fetch_verkkokauppa_search(query_text: str, referer: str = VK_CATALOG_URL) -> tuple[list[dict[str, Any]], int]:
    query = urllib.parse.urlencode(
        {
            "filter[base+category][]": "trading_cards",
            "page[number]": "1",
            "page[size]": "48",
            "sort": "-score",
            "filter[q]": query_text,
            "sessionId": str(uuid.uuid4()),
            "private": "true",
            "include": "campaigns,category,salesCategories.parent,brand,facets",
        }
    )
    payload = fetch_json(f"{VK_SEARCH_API}?{query}", referer=referer)
    items = payload.get("data") or []
    total = int((payload.get("meta") or {}).get("totalResults") or len(items))
    raw_products: list[dict[str, Any]] = []
    for item in items:
        if not isinstance(item, dict):
            continue
        attrs = dict(item.get("attributes") or {})
        attrs["pid"] = str(item.get("id") or attrs.get("pid") or "").strip()
        if attrs["pid"]:
            raw_products.append(attrs)
    avails = fetch_vk_availabilities([item["pid"] for item in raw_products])
    products = [
        normalize_vk_product(raw, avails.get(raw["pid"]), "verkkokauppa-catalog", notify_listed=True)
        for raw in raw_products
    ]
    return products, total


def fetch_verkkokauppa_catalog() -> tuple[list[dict[str, Any]], int]:
    return fetch_verkkokauppa_search("pokemon 30", VK_CATALOG_URL)


def fetch_verkkokauppa_extra_searches() -> tuple[list[dict[str, Any]], int]:
    collected: dict[str, dict[str, Any]] = {}
    total = 0
    for query_text, referer in VK_EXTRA_SEARCHES:
        products, count = fetch_verkkokauppa_search(query_text, referer)
        total += count
        for product in products:
            if product.get("id"):
                collected[product["id"]] = product
        time.sleep(0.4)
    return list(collected.values()), total


def collect_vk_drop_listings(products: list[dict[str, Any]], exclude_ids: set[str]) -> list[dict[str, Any]]:
    return [
        product
        for product in products
        if product.get("id")
        and product["id"] not in exclude_ids
        and is_watched_drop(product["name"], product["id"])
    ]


def fetch_verkkokauppa_watch() -> tuple[dict[str, Any], list[dict[str, Any]], int]:
    etb = fetch_verkkokauppa_etb()
    time.sleep(REQUEST_PAUSE_SECONDS)
    catalog, total = fetch_verkkokauppa_catalog()
    time.sleep(REQUEST_PAUSE_SECONDS)
    extra, extra_total = fetch_verkkokauppa_extra_searches()
    exclude = {etb["id"]}
    drops = collect_vk_drop_listings(catalog + extra, exclude)
    return etb, drops, total + extra_total


def vk_watch_product(spec: dict[str, str], availability_raw: dict[str, Any] | None) -> dict[str, Any]:
    availability = vk_availability_flags(availability_raw)
    return {
        "id": f"verkkokauppa:{spec['pid']}",
        "name": spec["name"],
        "slug": "",
        "brand": "Pokemon",
        "url": spec["url"],
        "price": spec.get("price"),
        "image": None,
        "source": "verkkokauppa-fast",
        "store": "Verkkokauppa",
        "availability": availability,
        "available": availability["ecom"],
        "stock_updated_at": str((availability_raw or {}).get("updatedAt") or ""),
        "notify_listed": False,
    }


def extra_vk_watch_from_state() -> list[dict[str, str]]:
    extra: list[dict[str, str]] = []
    seen = {spec["pid"] for spec in VK_WATCH_PRODUCTS}
    for product_id, record in (load_state().get("products") or {}).items():
        if not str(product_id).startswith("verkkokauppa:"):
            continue
        pid = str(product_id).split(":")[-1]
        if pid in seen:
            continue
        name = str((record or {}).get("name") or "")
        url = str((record or {}).get("url") or "")
        if not url or not is_priority_product(name, str(product_id)):
            continue
        extra.append({"pid": pid, "name": name, "url": url})
        seen.add(pid)
    return extra


def collect_fast_vk_stock() -> list[dict[str, Any]]:
    specs = list(VK_WATCH_PRODUCTS) + extra_vk_watch_from_state()
    avails = fetch_vk_availabilities([spec["pid"] for spec in specs])
    return [vk_watch_product(spec, avails.get(spec["pid"])) for spec in specs]


def fetch_prisma_watch_products() -> list[dict[str, Any]]:
    products: list[dict[str, Any]] = []
    for spec in PRISMA_WATCH_PRODUCTS:
        availability = fetch_prisma_cart_availability(spec["id"], spec["slug"])
        products.append(
            {
                "id": spec["id"],
                "name": spec["name"],
                "slug": spec["slug"],
                "brand": "Pokemon",
                "url": PRODUCT_URL.format(sok_id=spec["id"], slug=spec["slug"]),
                "price": None,
                "image": None,
                "source": "prisma-fast",
                "store": "Prisma",
                "availability": availability,
                "available": is_purchasable(availability),
                "notify_listed": False,
            }
        )
        time.sleep(0.35)
    return products


def fetch_prisma_fast_search() -> list[dict[str, Any]]:
    collected: dict[str, dict[str, Any]] = {}
    for url in PRISMA_FAST_SEARCH_URLS:
        page_props = parse_next_data(fetch_html(url))
        for product in products_from_page(page_props, "prisma-fast-search"):
            if product["id"] and should_watch_product(
                product["name"],
                product.get("brand", ""),
                require_pokemon=True,
                allow_booster=True,
                product_id=product.get("id") or "",
            ):
                collected[product["id"]] = product
        time.sleep(0.4)
    return list(collected.values())


def collect_fast_vk_drops() -> list[dict[str, Any]]:
    catalog, _total = fetch_verkkokauppa_catalog()
    time.sleep(0.4)
    extra, _extra_total = fetch_verkkokauppa_extra_searches()
    watched = {f"verkkokauppa:{spec['pid']}" for spec in VK_WATCH_PRODUCTS}
    return collect_vk_drop_listings(catalog + extra, watched)


def collect_fast_matches(*, include_listings: bool, include_karkkainen: bool) -> dict[str, Any]:
    errors: list[str] = []
    matches: dict[str, dict[str, Any]] = {}

    def add(products: list[dict[str, Any]]) -> None:
        for product in products:
            if product.get("id"):
                matches[product["id"]] = product

    stock, stock_errors = collect_store_matches(collect_fast_vk_stock, "Verkkokauppa-nopea")
    errors.extend(stock_errors)
    add(stock)

    if include_listings:
        boosters, booster_errors = collect_store_matches(collect_fast_vk_drops, "Verkkokauppa-haku")
        prisma_search, prisma_search_errors = collect_store_matches(fetch_prisma_fast_search, "Prisma-haku")
        prisma_brand, prisma_brand_errors = collect_store_matches(fetch_prisma_brand_watch, "Prisma-lista")
        prisma_watch, prisma_watch_errors = collect_store_matches(fetch_prisma_watch_products, "Prisma-ostoskori")
        errors.extend(booster_errors)
        errors.extend(prisma_search_errors)
        errors.extend(prisma_brand_errors)
        errors.extend(prisma_watch_errors)
        add(boosters)
        add(prisma_search)
        add(prisma_brand)
        add(prisma_watch)
        enrich_prisma_cart_status(
            [
                product
                for product in matches.values()
                if product.get("store") == "Prisma"
                and product.get("slug")
                and product.get("source") != "prisma-fast"
                and is_priority_product(product["name"], product.get("id") or "")
            ]
        )

    if include_karkkainen:
        karkkainen, karkkainen_errors = collect_store_matches(fetch_karkkainen_watch, "Kärkkäinen")
        errors.extend(karkkainen_errors)
        add(karkkainen)

    add(stock)
    if errors and not matches:
        raise RuntimeError(" | ".join(errors))

    return {
        "checked_at": now_iso(),
        "brand_product_count": sum(1 for item in matches.values() if item.get("store") == "Prisma"),
        "brand_total_count": len(PRISMA_WATCH_PRODUCTS),
        "karkkainen_product_count": sum(1 for item in matches.values() if item.get("store") == "Kärkkäinen"),
        "karkkainen_total_count": 0,
        "verkkokauppa_product_count": sum(1 for item in matches.values() if item.get("store") == "Verkkokauppa"),
        "matches": list(matches.values()),
        "errors": errors,
        "fast": True,
    }


def collect_store_matches(fetcher, label: str) -> tuple[list[dict[str, Any]], list[str]]:
    try:
        return fetcher(), []
    except RateLimitError:
        raise
    except Exception as error:  # noqa: BLE001
        message = f"{label}: {error}"
        log(f"VIRHE {message}")
        return [], [message]


def collect_matches() -> dict[str, Any]:
    errors: list[str] = []
    matches: dict[str, dict[str, Any]] = {}

    def add_matches(
        products: list[dict[str, Any]],
        require_pokemon: bool = False,
        allow_booster: bool = False,
    ) -> None:
        for product in products:
            if product.get("id") and should_watch_product(
                product["name"],
                product.get("brand", ""),
                require_pokemon=require_pokemon,
                allow_booster=allow_booster,
                product_id=product.get("id") or "",
            ):
                matches.setdefault(product["id"], product)

    prisma_result, prisma_errors = collect_store_matches(
        lambda: (fetch_brand_products(), fetch_search_products()),
        "Prisma",
    )
    karkkainen_result, karkkainen_errors = collect_store_matches(
        lambda: (fetch_karkkainen_products(), fetch_karkkainen_watch()),
        "Kärkkäinen",
    )
    vk_result, vk_errors = collect_store_matches(fetch_verkkokauppa_watch, "Verkkokauppa")
    errors.extend(prisma_errors)
    errors.extend(karkkainen_errors)
    errors.extend(vk_errors)

    prisma_products, prisma_total, prisma_search = [], 0, []
    if prisma_result:
        (prisma_products, prisma_total), prisma_search = prisma_result
        add_matches(prisma_products)
        add_matches(prisma_search, require_pokemon=True)

    karkkainen_products, karkkainen_total, karkkainen_search = [], 0, []
    if karkkainen_result:
        (karkkainen_products, karkkainen_total), karkkainen_search = karkkainen_result
        add_matches(karkkainen_products)
        add_matches(karkkainen_search, require_pokemon=True)

    vk_etb, vk_boosters, vk_total = {}, [], 0
    if vk_result:
        vk_etb, vk_boosters, vk_total = vk_result
        if vk_etb.get("id"):
            matches.setdefault(vk_etb["id"], vk_etb)
        for product in vk_boosters:
            matches.setdefault(product["id"], product)

    if errors and not prisma_products and not karkkainen_products and not vk_etb:
        raise RuntimeError(" | ".join(errors))

    enrich_prisma_cart_status([product for product in matches.values() if product.get("store") == "Prisma"])

    return {
        "checked_at": now_iso(),
        "brand_product_count": len(prisma_products),
        "brand_total_count": prisma_total,
        "karkkainen_product_count": len(karkkainen_products),
        "karkkainen_total_count": karkkainen_total,
        "verkkokauppa_product_count": vk_total,
        "matches": list(matches.values()),
        "errors": errors,
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
        f"{price} · {availability_label(product['availability'])} · {product.get('store') or 'Prisma'}",
    ]


def telegram_product_message(title: str, products: list[dict[str, Any]]) -> str:
    lines = [f"<b>{html_escape(title)}</b>", ""]
    for product in products:
        name = html_escape(product["name"])
        price = html_escape(product.get("price") or "hinta ei tiedossa")
        avail = html_escape(availability_label(product["availability"]))
        store = html_escape(product.get("store") or "Prisma")
        lines.append(name)
        lines.append(f"{price} · {avail} · {store}")
        lines.append(f'<a href="{product["url"]}">Avaa ja osta →</a>')
        lines.append("")
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
                "text": f"Löytyi *{len(products)}* tuote(tta) Prismasta / Kärkkäiseltä / Verkkokaupasta.",
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
            "elements": [
                {
                    "type": "mrkdwn",
                    "text": (
                        f"<{PRISMA_CARDS_URL}|Prisma> · "
                        f"<{KARKKAINEN_CARDS_URL}|Kärkkäinen> · "
                        f"<{VK_CATALOG_URL}|Verkkokauppa>"
                    ),
                }
            ],
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
            if product.get("notify_listed", True):
                newly_listed.append(product)
            record["alerted_listed"] = True
        if product["available"]:
            if not record["alerted_available"]:
                newly_available.append(product)
                record["alerted_available"] = True
        else:
            record["alerted_available"] = False
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

    announce_key = "announced_fast" if snapshot.get("fast") else "announced"
    if announce and not state.get(announce_key):
        if snapshot.get("fast"):
            notify_text(
                "Pokemon-vahti juoksee GitHubissa. Ostoskori tarkistetaan noin 15 s välein "
                "jokaisen ajon aikana; Ultra-Premium, boosterit ja Prisma samassa loopissa. "
                "Läppärin ei tarvitse olla auki."
            )
        else:
            notify_text(
                "Pokemon-seuranta käynnissä. Tarkistan Prismaa, Kärkkäistä ja Verkkokauppaa 5 min välein "
                f"(Prisma {snapshot['brand_product_count']}, "
                f"Kärkkäinen {snapshot.get('karkkainen_product_count', 0)}, "
                f"Verkkokauppa {snapshot.get('verkkokauppa_product_count', 0)}, "
                f"{len(snapshot['matches'])} osumaa)."
            )
        state[announce_key] = True

    if newly_available:
        notify_products(
            "OSTA NYT — 30th Celebration myynnissä",
            "Pokémon 30th Celebration on nyt ostettavissa. Avaa linkki heti.",
            newly_available,
        )
        log(f"Hälytys: {len(newly_available)} tuotetta myynnissä")
    if newly_listed and not newly_available:
        notify_products(
            "Pokémon 30th Celebration listattiin",
            "Pokémon 30th Celebration -tuotteita ilmestyi myyntiin.",
            newly_listed,
        )
        log(f"Hälytys: {len(newly_listed)} uutta listattua tuotetta")
    elif newly_listed:
        available_ids = {product["id"] for product in newly_available}
        leftover = [product for product in newly_listed if product["id"] not in available_ids]
        if leftover:
            notify_products(
                "Lisää 30th Celebration -tuotteita listattiin",
                "Uusia Pokémon 30th Celebration -tuotteita ilmestyi myyntiin.",
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
            notify_text(f"Pokemon-seuranta ei saanut luettua kauppoja: {error}")
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
        f"Tarkistus ok: Prisma {snapshot['brand_product_count']}/{snapshot['brand_total_count']}, "
        f"Kärkkäinen {snapshot.get('karkkainen_product_count', 0)}/"
        f"{snapshot.get('karkkainen_total_count', 0)}, "
        f"Verkkokauppa {snapshot.get('verkkokauppa_product_count', 0)}, "
        f"{len(snapshot['matches'])} osumaa"
    )
    for product in snapshot["matches"]:
        log(
            f"  - [{product.get('store') or '?'}] {product['name']} "
            f"({availability_label(product['availability'])}) {product['url']}"
        )

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


def sleep_for(seconds: float, deadline: float | None) -> bool:
    if seconds <= 0:
        return deadline is not None and time.monotonic() >= deadline
    if deadline is None:
        time.sleep(seconds)
        return False
    left = deadline - time.monotonic()
    if left <= 0:
        return True
    time.sleep(min(seconds, left))
    return time.monotonic() >= deadline


def run_fast(dry_run: bool, duration_seconds: int = 0) -> int:
    interval = max(8, env_int("FAST_CHECK_SECONDS", FAST_CHECK_SECONDS_DEFAULT))
    deadline = time.monotonic() + duration_seconds if duration_seconds > 0 else None
    log(
        f"Nopea vahti käynnissä, ostoskori {interval} s välein"
        + (f", kesto {duration_seconds}s" if duration_seconds else "")
    )
    first = True
    last_listings = 0.0
    last_karkkainen = 0.0
    extra_delay = 0
    while True:
        if deadline is not None and time.monotonic() >= deadline:
            log("Nopea vahti: aikaraja täynnä, lopetetaan tämä ajo.")
            return 0
        now = time.monotonic()
        include_listings = first or now - last_listings >= FAST_LISTINGS_SECONDS
        include_karkkainen = first or now - last_karkkainen >= FAST_KARKKAINEN_SECONDS
        try:
            snapshot = collect_fast_matches(
                include_listings=include_listings,
                include_karkkainen=include_karkkainen,
            )
        except RateLimitError as error:
            extra_delay = min(max(error.retry_after or 30, extra_delay * 2 or 30), MAX_BACKOFF_SECONDS)
            log(f"VIRHE: {error}. Hidastetaan {extra_delay}s")
            if sleep_for(interval + extra_delay, deadline):
                return 0
            first = False
            continue
        except Exception as error:  # noqa: BLE001
            handle_error(error, dry_run)
            if sleep_for(interval + extra_delay, deadline):
                return 0
            first = False
            continue

        extra_delay = max(0, extra_delay - interval)
        if include_listings:
            last_listings = now
        if include_karkkainen:
            last_karkkainen = now

        available = [product for product in snapshot["matches"] if product.get("available")]
        if first or available or include_listings:
            stock_ages = [
                f"{product['id'].split(':')[-1]} {product['stock_updated_at']}"
                for product in snapshot["matches"]
                if product.get("stock_updated_at")
            ]
            log(
                f"Nopea tarkistus: {len(snapshot['matches'])} seurannassa, "
                f"{len(available)} ostettavissa"
                + (f" [{'; '.join(stock_ages)}]" if stock_ages else "")
                + (f", virheet: {'; '.join(snapshot['errors'])}" if snapshot.get("errors") else "")
            )
            for product in available:
                log(f"  - Myynnissä [{product.get('store')}] {product['name']} {product['url']}")

        if not has_notifier() and not dry_run:
            log("Ei Slack- tai Telegram-asetuksia — tulokset vain lokiin.")
            state = load_state()
            state["last_check"] = snapshot["checked_at"]
            save_state(state)
        else:
            result = diff_and_notify(snapshot, announce=first, dry_run=dry_run)
            if dry_run:
                log(
                    f"Dry-run: uusia listauksia {len(result['newly_listed'])}, "
                    f"uusia saatavia {len(result['newly_available'])}"
                )
            elif result["newly_available"] or result["newly_listed"]:
                log(
                    f"Hälytys lähetetty: {len(result['newly_available'])} ostettavissa, "
                    f"{len(result['newly_listed'])} uutta listausta"
                )

        first = False
        if sleep_for(interval + extra_delay, deadline):
            log("Nopea vahti: aikaraja täynnä, lopetetaan tämä ajo.")
            return 0


def self_test() -> int:
    should_match = [
        "Pokémon TCG 30th Celebration Elite Trainer Box",
        "Pokemon 30-vuotisjuhlasetti",
        "Pokémon 30th Anniversary Booster",
        "Pokemon juhlavuosi collection",
        "Pokémon TCG 30 Booster Bundle",
        "Pokemon 30",
        "Pokemon 30th Celebration Elite Trainer Box keräilykortit",
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
        "Today 30x40cm juliste",
        "Nina kulta MDF 30x30 pleksikehys",
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
    if is_purchasable({"ecom": False, "click_and_collect": False, "store": True}):
        print("FAIL: faded ostoskori / pelkkä myymälälippu ei saa olla ostettavissa")
        failed = True
    if not is_purchasable({"ecom": True, "click_and_collect": False, "store": False}):
        print("FAIL: vihreä ostoskori (ecom) olisi pitänyt olla ostettavissa")
        failed = True
    if not is_anniversary_product("30th Celebration Elite Trainer Box", "Pokemon", require_pokemon=True):
        print("FAIL: brand+30th Celebration olisi pitänyt täsmätä haussa")
        failed = True
    if is_anniversary_product("Decorata Party Happy Celebration banneri", require_pokemon=True):
        print("FAIL: juhlakoriste ei saisi täsmätä haussa")
        failed = True
    for name in (
        "Happy Birthday 30 valkoinen lautasliina",
        "30 Happy Birthday 6 kpl ilmapallo",
        "Today 30x40cm juliste",
    ):
        if is_anniversary_product(name, require_pokemon=True):
            print(f"FAIL: hakukohina ei saisi täsmätä: {name}")
            failed = True
    journey = "Pokemon SV9 Journey Together Booster keräilykortit, 36-pack"
    if is_booster_product(journey) or should_watch_product(
        journey, require_pokemon=True, allow_booster=True, product_id="verkkokauppa:980153"
    ):
        print("FAIL: Journey Together Booster ei saisi täsmätä")
        failed = True
    if is_booster_product("Magic the Gathering Marvel's Spider-Man Play Booster, 30-PACK"):
        print("FAIL: MTG-booster ei saisi täsmätä")
        failed = True
    if should_watch_product(
        "Pokémon TCG ME05 Pitch Black Booster Bundle",
        require_pokemon=True,
        allow_booster=True,
    ):
        print("FAIL: ME05-booster ei saisi tulla 30th-vahtiin")
        failed = True
    if not is_booster_product("Pokémon TCG 30th Celebration Booster Bundle"):
        print("FAIL: 30th Booster Bundle olisi pitänyt täsmätä")
        failed = True
    if not should_watch_product(
        "Pokémon TCG 30th Celebration Booster Bundle",
        require_pokemon=True,
        allow_booster=True,
    ):
        print("FAIL: 30th Booster Bundle olisi pitänyt tulla vahtiin")
        failed = True
    if is_ultra_premium_product("Pokémon TCG Charizard Super Premium Collection"):
        print("FAIL: Super Premium ei ole Ultra-Premium")
        failed = True
    if not is_ultra_premium_product("Pokémon Mega Charizard Ultra Premium Collection"):
        print("FAIL: Ultra Premium Collection olisi pitänyt tunnistaa")
        failed = True
    if should_watch_product(
        "Pokémon Mega Charizard Ultra Premium Collection",
        require_pokemon=True,
        allow_booster=True,
    ) or is_watched_drop("Pokémon Mega Charizard Ultra Premium Collection"):
        print("FAIL: vanha Ultra-Premium ei saisi tulla 30th-vahtiin")
        failed = True
    if not is_watched_drop("Pokémon TCG 30th Celebration Ultra-Premium Collection"):
        print("FAIL: 30th Ultra-Premium olisi pitänyt tulla vahtiin")
        failed = True
    if not should_watch_product(
        "Pokemon 30th Ultra Premium Collection",
        require_pokemon=True,
    ):
        print("FAIL: 30th Ultra Premium search-osumaa ei saisi jättää")
        failed = True
    if should_watch_product("Pokémon Poster Coll 30th", require_pokemon=True):
        print("FAIL: 30th-juliste ei ole prioriteetti")
        failed = True
    if should_watch_product("Pokémon 30th Anniversary Booster", require_pokemon=True):
        print("FAIL: pelkkä booster ilman bundlea ei ole prioriteetti")
        failed = True
    if not is_priority_product("Pokémon TCG Umbreon Ultra Premium Collection"):
        print("FAIL: Umbreon Ultra-Premium olisi pitänyt olla prioriteetti")
        failed = True
    if not should_watch_product(
        "Pokemon 30th Celebration Elite Trainer Box",
        require_pokemon=True,
    ):
        print("FAIL: 30th ETB olisi pitänyt jäädä vahtiin")
        failed = True
    if is_delta_reign_product("Pokemon ME05 Pitch Black Booster Bundle"):
        print("FAIL: ME05 ei ole Delta Reign")
        failed = True
    if not is_delta_reign_product("Pokémon TCG Delta Reign Elite Trainer Box"):
        print("FAIL: Delta Reign ETB olisi pitänyt tunnistaa")
        failed = True
    if not is_watched_drop("Pokémon TCG Delta Reign Booster Bundle") or not should_watch_product(
        "Pokemon Delta Reign Ultra Premium Collection",
        require_pokemon=True,
    ):
        print("FAIL: Delta Reign -tuote olisi pitänyt tulla vahtiin ilman 30th-sanaa")
        failed = True
    sample = telegram_product_message(
        "OSTA NYT — 30th Celebration myynnissä",
        [
            {
                "name": "Pokémon TCG: 30th Elite Trainer Box keräilykortit",
                "url": VK_ETB_URL,
                "price": "80.00 €",
                "availability": {"ecom": True, "click_and_collect": False, "store": False},
                "store": "Verkkokauppa",
            }
        ],
    )
    if "Avaa ja osta" not in sample or VK_ETB_URL not in sample:
        print("FAIL: Telegram-viestissä pitää olla suora ostolinkki")
        failed = True
    if vk_is_purchasable({"flags": {"isSoldOut": True}, "stocks": {"shipment": {"isPurchasable": False}}}):
        print("FAIL: harmaa Verkkokauppa-ostoskori ei saa olla ostettavissa")
        failed = True
    if not vk_is_purchasable(
        {"flags": {"isSoldOut": False}, "stocks": {"shipment": {"isPurchasable": True}}}
    ):
        print("FAIL: sininen Verkkokauppa-ostoskori olisi pitänyt olla ostettavissa")
        failed = True
    if "PokemonAvailabilityWatch" in USER_AGENT:
        print("FAIL: User-Agent ei saa mainostaa bottia")
        failed = True
    if "Chrome/" not in USER_AGENT:
        print("FAIL: User-Agentin pitäisi näyttää tavalliselta Chrome-selaimelta")
        failed = True
    limited = RateLimitError(429, "https://example.com", retry_after=20)
    if limited.status != 429 or limited.retry_after != 20:
        print("FAIL: RateLimitError-kentät väärin")
        failed = True
    if not sleep_for(0, time.monotonic() - 1):
        print("FAIL: umpeutuneen aikarajan pitäisi lopettaa heti")
        failed = True
    if failed:
        return 1
    print("Self-test ok")
    return 0


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Prisma, Kärkkäinen ja Verkkokauppa Pokemon 30th Celebration -vahti")
    parser.add_argument("--once", action="store_true", help="Aja yksi hidas tarkistus ja lopeta (oletus)")
    parser.add_argument("--fast", action="store_true", help="Nopea ostoskorivahti, oletus 15 s")
    parser.add_argument(
        "--fast-for",
        type=int,
        default=0,
        metavar="SEK",
        help="Nopea vahti N sekuntia (GitHub Actions), sitten lopeta",
    )
    parser.add_argument("--watch", action="store_true", help="Hidas täysi tarkistus toistuvasti")
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

    interval = args.interval or env_int("CHECK_INTERVAL_MINUTES", 5)
    if args.fast or args.fast_for:
        return run_fast(dry_run=args.dry_run, duration_seconds=args.fast_for)
    if args.watch:
        log(f"Aloitetaan seuranta, väli {interval} min")
        while True:
            run_once(announce=args.announce, dry_run=args.dry_run)
            args.announce = False
            time.sleep(max(interval, 5) * 60)
    return run_once(announce=args.announce, dry_run=args.dry_run)


if __name__ == "__main__":
    sys.exit(main())
