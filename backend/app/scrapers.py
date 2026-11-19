"""Polite, deliberately small scrapers for publicly accessible site pages."""
from __future__ import annotations

import json
import time
from dataclasses import asdict, dataclass
from pathlib import Path
from urllib.parse import urljoin, urlparse
from urllib.robotparser import RobotFileParser

import requests
from bs4 import BeautifulSoup

from app.config import RAW_DATA_DIR

HEADERS = {"User-Agent": "DarWasaltPropertyAssistant/1.0 (educational project)"}
REQUEST_TIMEOUT = 20
REQUEST_DELAY_SECONDS = 1.5
MAX_PAGES_PER_SOURCE = 12


@dataclass
class ScrapedPage:
    source: str
    source_url: str
    title: str
    text: str
    project_name: str | None = None
    location: str | None = None
    document_type: str = "website_page"


SOURCES = {
    "DarGlobal": {
        "home": "https://www.darglobal.com/",
        "allowed_paths": ("/", "/projects", "/project"),
    },
    "Wasalt": {
        "home": "https://wasalt.sa/",
        "allowed_paths": ("/", "/en", "/projects", "/property"),
    },
}


def robots_allow(url: str) -> bool:
    """Return False when robots.txt cannot be read or disallows our user agent."""
    robots_url = urljoin(url, "/robots.txt")
    try:
        response = requests.get(robots_url, headers=HEADERS, timeout=REQUEST_TIMEOUT)
        if response.status_code == 404:
            return True
        response.raise_for_status()
    except requests.RequestException as error:
        print(f"Skipping {url}: could not check robots.txt ({error})")
        return False

    parser = RobotFileParser()
    parser.parse(response.text.splitlines())
    return parser.can_fetch(HEADERS["User-Agent"], url)


def is_allowed_link(url: str, source_config: dict[str, object]) -> bool:
    parsed = urlparse(url)
    home_domain = urlparse(str(source_config["home"])).netloc
    allowed_paths = tuple(str(path) for path in source_config["allowed_paths"])
    return parsed.netloc == home_domain and (
        parsed.path == "/" or any(
            path != "/" and parsed.path.startswith(path) for path in allowed_paths
        )
    )


def extract_page(source: str, url: str) -> tuple[ScrapedPage | None, BeautifulSoup | None]:
    try:
        response = requests.get(url, headers=HEADERS, timeout=REQUEST_TIMEOUT)
        response.raise_for_status()
    except requests.RequestException as error:
        print(f"Skipping {url}: {error}")
        return None, None

    soup = BeautifulSoup(response.text, "html.parser")
    for unwanted in soup(["script", "style", "noscript", "svg", "footer", "nav"]):
        unwanted.decompose()
    title = soup.title.get_text(" ", strip=True) if soup.title else source
    text = soup.get_text(" ", strip=True)
    if len(text) < 80:
        return None, soup
    return ScrapedPage(source=source, source_url=url, title=title, text=text), soup


def scrape_source(source: str) -> list[ScrapedPage]:
    config = SOURCES[source]
    home_url = str(config["home"])
    if not robots_allow(home_url):
        print(f"Skipping {source}: robots.txt does not permit collection.")
        return []

    pending_urls = [home_url]
    visited_urls: set[str] = set()
    pages: list[ScrapedPage] = []
    while pending_urls and len(visited_urls) < MAX_PAGES_PER_SOURCE:
        url = pending_urls.pop(0)
        if url in visited_urls or not is_allowed_link(url, config):
            continue
        visited_urls.add(url)
        page, soup = extract_page(source, url)
        if page:
            pages.append(page)
        if soup:
            for link in soup.find_all("a", href=True):
                candidate = urljoin(url, link["href"]).split("#")[0]
                if candidate not in visited_urls and is_allowed_link(candidate, config):
                    pending_urls.append(candidate)
        time.sleep(REQUEST_DELAY_SECONDS)
    return pages


def scrape_all() -> list[ScrapedPage]:
    all_pages: list[ScrapedPage] = []
    for source in SOURCES:
        all_pages.extend(scrape_source(source))
    return all_pages


def save_raw_pages(pages: list[ScrapedPage], output_path: Path | None = None) -> Path:
    RAW_DATA_DIR.mkdir(parents=True, exist_ok=True)
    output_path = output_path or RAW_DATA_DIR / "properties.json"
    output_path.write_text(json.dumps([asdict(page) for page in pages], ensure_ascii=False, indent=2), encoding="utf-8")
    return output_path

