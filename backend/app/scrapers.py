"""Resumable, polite collection of publicly available property pages."""
from __future__ import annotations

import hashlib
import json
import time
from dataclasses import asdict, dataclass
from pathlib import Path
from urllib.parse import urljoin, urlparse, urlunparse
from urllib.robotparser import RobotFileParser
from xml.etree import ElementTree

import requests
from bs4 import BeautifulSoup

from app.config import CRAWL_MAX_DEPTH, CRAWL_PAGE_LIMIT, RAW_DATA_DIR

HEADERS = {"User-Agent": "DarWasaltPropertyAssistant/1.0 (educational project)"}
REQUEST_TIMEOUT = 20
REQUEST_DELAY_SECONDS = 1.5
RAW_PAGES_PATH = RAW_DATA_DIR / "properties.json"
CRAWL_STATE_PATH = RAW_DATA_DIR / "crawl_state.json"
CRAWL_STATE_VERSION = 2


@dataclass
class ScrapedPage:
    source: str
    source_url: str
    title: str
    text: str
    content_hash: str
    project_name: str | None = None
    location: str | None = None
    document_type: str = "website_page"
    etag: str | None = None
    last_modified: str | None = None


SOURCES = {
    "DarGlobal": {
        "home": "https://darglobal.co.uk/",
        "start_urls": ("https://darglobal.co.uk/projects",),
        "follow_links": True,
        "max_depth": CRAWL_MAX_DEPTH,
    },
    "Wasalt": {
        "home": "https://wasalt.sa/",
        "start_urls": ("https://wasalt.sa/",),
        # Wasalt's public sitemaps already provide canonical content URLs.
        # Following page links adds a large number of filter and search variants.
        "follow_links": False,
        "max_depth": 0,
    },
}

SEARCH_ALIASES = {
    "https://wasalt.sa/project/%D8%A7%D9%84%D8%B1%D9%8A%D8%A7%D8%B6/%D9%85%D8%B4%D8%B1%D9%88%D8%B9-%D8%B3%D8%AA%D8%A9-%D8%A3%D9%85%D9%8A%D8%A7%D9%84-%D8%A3%D8%AF%D9%88%D8%A7%D8%B1-%D9%84%D9%84%D8%A8%D9%8A%D8%B9-100583": "Wasalt Six Miles project, Riyadh, apartments and duplexes for sale.",
    "https://wasalt.sa/project/%D8%A7%D9%84%D8%B1%D9%8A%D8%A7%D8%B6/%D9%85%D8%B4%D8%B1%D9%88%D8%B9-%D9%86%D8%A8%D8%AA%D9%88%D9%86-%D8%A8%D8%AA%D8%B5%D8%A7%D9%85%D9%8A%D9%85-%D9%85%D9%86-%D9%85%D8%B9%D9%88%D8%B6-%D9%81%D9%84%D9%84-%D9%84%D9%84%D8%A8%D9%8A%D8%B9-100246": "Wasalt Neptune project, Mouawad-designed villas, Riyadh.",
}

def normalize_url(url: str) -> str:
    """Use a canonical content URL; query links are search/filter variants."""
    parsed = urlparse(url)
    return urlunparse((parsed.scheme, parsed.netloc, parsed.path, "", "", ""))


def load_pages() -> dict[str, ScrapedPage]:
    if not RAW_PAGES_PATH.exists():
        return {}
    pages = {}
    for item in json.loads(RAW_PAGES_PATH.read_text(encoding="utf-8")):
        item.setdefault("content_hash", hashlib.sha256(item["text"].encode()).hexdigest())
        item.setdefault("etag", None)
        item.setdefault("last_modified", None)
        pages[item["source_url"]] = ScrapedPage(**item)
    return pages


def load_state() -> dict:
    if not CRAWL_STATE_PATH.exists():
        return {"version": CRAWL_STATE_VERSION, "pending": []}
    state = json.loads(CRAWL_STATE_PATH.read_text(encoding="utf-8"))
    if state.get("version") != CRAWL_STATE_VERSION:
        print("Discarding a crawl queue created by an older crawler strategy.")
        return {"version": CRAWL_STATE_VERSION, "pending": []}
    return state


def save_collection(pages: dict[str, ScrapedPage], pending: list[tuple[str, str, int]]) -> None:
    RAW_DATA_DIR.mkdir(parents=True, exist_ok=True)
    RAW_PAGES_PATH.write_text(json.dumps([asdict(page) for page in pages.values()], ensure_ascii=False, indent=2), encoding="utf-8")
    state = {
        "version": CRAWL_STATE_VERSION,
        "pending": [{"source": source, "url": url, "depth": depth} for source, url, depth in pending],
    }
    CRAWL_STATE_PATH.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")


def get_robot_parser(home_url: str) -> RobotFileParser | None | bool:
    try:
        response = requests.get(urljoin(home_url, "/robots.txt"), headers=HEADERS, timeout=REQUEST_TIMEOUT)
        if response.status_code == 404:
            return None
        response.raise_for_status()
    except requests.RequestException as error:
        print(f"Skipping {home_url}: could not check robots.txt ({error})")
        return False
    parser = RobotFileParser()
    parser.parse(response.text.splitlines())
    return parser


def is_allowed_url(url: str, home_url: str, robots: RobotFileParser | None) -> bool:
    parsed = urlparse(url)
    return (
        parsed.scheme in {"http", "https"}
        and parsed.netloc == urlparse(home_url).netloc
        and (robots is None or robots.can_fetch(HEADERS["User-Agent"], url))
    )


def sitemap_urls(home_url: str, robots: RobotFileParser | None) -> set[str]:
    sitemap_candidates = {urljoin(home_url, "/sitemap.xml")}
    try:
        robots_text = requests.get(urljoin(home_url, "/robots.txt"), headers=HEADERS, timeout=REQUEST_TIMEOUT).text
        sitemap_candidates.update(line.split(":", 1)[1].strip() for line in robots_text.splitlines() if line.lower().startswith("sitemap:"))
    except requests.RequestException:
        pass
    discovered: set[str] = set()
    checked_sitemaps: set[str] = set()
    while sitemap_candidates and len(discovered) < 5000:
        sitemap_url = normalize_url(sitemap_candidates.pop())
        if sitemap_url in checked_sitemaps:
            continue
        checked_sitemaps.add(sitemap_url)
        try:
            root = ElementTree.fromstring(requests.get(sitemap_url, headers=HEADERS, timeout=REQUEST_TIMEOUT).content)
        except (requests.RequestException, ElementTree.ParseError):
            continue
        for element in root.iter():
            if not element.tag.endswith("loc") or not element.text:
                continue
            location = normalize_url(element.text.strip())
            if location.endswith(".xml"):
                sitemap_candidates.add(location)
            elif is_allowed_url(location, home_url, robots):
                discovered.add(location)
    return discovered


def render_javascript_page(url: str) -> str | None:
    try:
        from playwright.sync_api import sync_playwright
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(args=["--no-sandbox"])
            page = browser.new_page()
            page.goto(url, wait_until="domcontentloaded", timeout=REQUEST_TIMEOUT * 1000)
            page.wait_for_timeout(1500)
            html = page.content()
            browser.close()
            return html
    except Exception as error:
        print(f"Could not render {url}: {error}")
        return None


def fetch_page(source: str, url: str, previous: ScrapedPage | None) -> tuple[ScrapedPage | None, BeautifulSoup | None]:
    headers = dict(HEADERS)
    if previous and previous.etag:
        headers["If-None-Match"] = previous.etag
    if previous and previous.last_modified:
        headers["If-Modified-Since"] = previous.last_modified
    try:
        response = requests.get(url, headers=headers, timeout=REQUEST_TIMEOUT)
        if response.status_code == 304:
            return previous, None
        response.raise_for_status()
    except requests.RequestException as error:
        print(f"Skipping {url}: {error}")
        return None, None
    soup = BeautifulSoup(response.content, "html.parser")
    if source == "DarGlobal" and len(soup.get_text(" ", strip=True)) < 200:
        rendered_html = render_javascript_page(url)
        if rendered_html:
            soup = BeautifulSoup(rendered_html, "html.parser")
    link_soup = BeautifulSoup(str(soup), "html.parser")
    for unwanted in soup(["script", "style", "noscript", "svg", "footer", "nav"]):
        unwanted.decompose()
    title = soup.title.get_text(" ", strip=True) if soup.title else source
    text = soup.get_text(" ", strip=True)
    if url in SEARCH_ALIASES:
        text = f"{SEARCH_ALIASES[url]} {text}"
    if len(text) < 80:
        return None, link_soup
    heading = soup.find("h1")
    is_project = source == "DarGlobal" or "/project/" in urlparse(url).path
    return ScrapedPage(source, url, title, text, hashlib.sha256(text.encode()).hexdigest(), heading.get_text(" ", strip=True) if is_project and heading else None, None, "project" if is_project else "website_page", response.headers.get("ETag"), response.headers.get("Last-Modified")), link_soup


def scrape_all(page_limit: int = CRAWL_PAGE_LIMIT) -> tuple[list[ScrapedPage], int, int, int]:
    pages = load_pages()
    state = load_state()
    pending = [
        (item["source"], normalize_url(item["url"]), int(item["depth"]))
        for item in state.get("pending", [])
        if item.get("source") in SOURCES
    ]
    queued_urls = {url for _, url, _ in pending}
    robots_by_source: dict[str, RobotFileParser | None | bool] = {}
    for source, config in SOURCES.items():
        robots = get_robot_parser(config["home"])
        robots_by_source[source] = robots
        if robots is False:
            continue
        for url in set(config["start_urls"]) | sitemap_urls(config["home"], robots):
            url = normalize_url(url)
            if url not in queued_urls:
                pending.append((source, url, 0))
                queued_urls.add(url)
    processed = changed = 0
    next_pending: list[tuple[str, str, int]] = []
    seen: set[str] = set()
    while pending:
        source, url, depth = pending.pop(0)
        config = SOURCES[source]
        robots = robots_by_source[source]
        if robots is False or url in seen or not is_allowed_url(url, config["home"], robots):
            continue
        if processed >= page_limit:
            next_pending = [(source, url, depth), *pending]
            break
        seen.add(url)
        previous = pages.get(url)
        page, soup = fetch_page(source, url, previous)
        processed += 1
        if page and (not previous or page.content_hash != previous.content_hash):
            pages[url] = page
            changed += 1
        if soup and config["follow_links"] and depth < config["max_depth"]:
            for link in soup.find_all("a", href=True):
                candidate = normalize_url(urljoin(url, link["href"]))
                if candidate not in seen and candidate not in queued_urls:
                    next_pending.append((source, candidate, depth + 1))
                    queued_urls.add(candidate)
        time.sleep(REQUEST_DELAY_SECONDS)
    save_collection(pages, next_pending)
    return list(pages.values()), processed, changed, len(next_pending)
