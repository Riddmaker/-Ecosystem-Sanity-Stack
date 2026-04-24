"""
Unit tests for scraper connectors — no network calls, no DB.

Covers:
  - Link extraction (extract_article_links)
  - Article ID extraction (_extract_article_id)
  - Breadcrumb parsing (_parse_breadcrumb)
  - Full article parsing (parse_article) with minimal HTML fixtures
  - Base class shared utilities (_parse_json_ld, _parse_author, _parse_datetime,
    _strip_html, _trafilatura_fallback)
"""

import json
from datetime import datetime, timezone

import pytest

from src.connectors.specific_scraper.twenty_minutes_scraper_connector import (
    TwentyMinutesScraperConnector,
)
from src.connectors.specific_scraper.watson_scraper_connector import WatsonScraperConnector
from src.connectors.specific_scraper.nau_scraper_connector import NauScraperConnector
from src.connectors.specific_scraper.blick_scraper_connector import BlickScraperConnector
from src.connectors.abstract.scraper_connector import BaseScraperConnector


# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────

def _json_ld_script(data: dict | list) -> str:
    return f'<script type="application/ld+json">{json.dumps(data)}</script>'


def _make_article_html(
    title: str = "Test Titel",
    description: str = "Test Beschreibung",
    date: str = "2024-05-01T10:00:00+02:00",
    author: str | dict | list = "Max Muster",
    article_body: str = "Artikeltext hier.",
    breadcrumb: list | None = None,
    extra_scripts: str = "",
) -> str:
    if breadcrumb is None:
        breadcrumb = [
            {"@type": "ListItem", "position": 1, "name": "Home"},
            {"@type": "ListItem", "position": 2, "name": "Schweiz"},
            {"@type": "ListItem", "position": 3, "name": "Test Titel"},
        ]

    news_article = {
        "@context": "https://schema.org",
        "@type": "NewsArticle",
        "headline": title,
        "description": description,
        "datePublished": date,
        "author": author if isinstance(author, (dict, list)) else {"@type": "Person", "name": author},
        "articleBody": article_body,
    }
    breadcrumb_ld = {
        "@context": "https://schema.org",
        "@type": "BreadcrumbList",
        "itemListElement": breadcrumb,
    }
    return f"""
    <html><head>
    {_json_ld_script(news_article)}
    {_json_ld_script(breadcrumb_ld)}
    {extra_scripts}
    </head><body></body></html>
    """


# ─────────────────────────────────────────────────────────────────────────────
# Base class utilities
# ─────────────────────────────────────────────────────────────────────────────

class TestBaseSharedUtilities:
    """Tests for static helpers inherited by all scrapers."""

    def setup_method(self):
        # Use watson as a concrete stand-in for the base class
        self.connector = WatsonScraperConnector()

    def test_parse_datetime_valid(self):
        dt = self.connector._parse_datetime("2024-05-01T10:00:00+02:00")
        assert dt.year == 2024
        assert dt.month == 5

    def test_parse_datetime_none_returns_now(self):
        dt = self.connector._parse_datetime(None)
        assert isinstance(dt, datetime)
        assert dt.tzinfo is not None

    def test_parse_datetime_invalid_returns_now(self):
        dt = self.connector._parse_datetime("not-a-date")
        assert isinstance(dt, datetime)

    def test_parse_author_dict(self):
        assert self.connector._parse_author({"name": "Anna Müller"}) == "Anna Müller"

    def test_parse_author_list_of_dicts(self):
        assert self.connector._parse_author([{"name": "Peter"}, {"name": "Hans"}]) == "Peter"

    def test_parse_author_nested_list(self):
        # nau.ch quirk: [[{"name": "..."}]]
        assert self.connector._parse_author([[{"name": "Redaktion"}]]) == "Redaktion"

    def test_parse_author_string(self):
        assert self.connector._parse_author("Redaktion") == "Redaktion"

    def test_parse_author_none(self):
        assert self.connector._parse_author(None) is None

    def test_strip_html(self):
        html = "<p>Hallo <b>Welt</b>!</p>"
        assert self.connector._strip_html(html) == "Hallo Welt !"

    def test_parse_json_ld_single_object(self):
        html = _make_article_html()
        from bs4 import BeautifulSoup
        soup = BeautifulSoup(html, "html.parser")
        news, crumbs, author = BaseScraperConnector._parse_json_ld(soup)
        assert news.get("headline") == "Test Titel"
        assert len(crumbs) == 3
        assert author is None  # no standalone Person block

    def test_parse_json_ld_with_graph(self):
        data = {
            "@context": "https://schema.org",
            "@graph": [
                {"@type": "NewsArticle", "headline": "Graph Artikel"},
                {"@type": "BreadcrumbList", "itemListElement": [
                    {"name": "Home"}, {"name": "Wirtschaft"},
                ]},
            ]
        }
        html = f"<html><head>{_json_ld_script(data)}</head><body></body></html>"
        from bs4 import BeautifulSoup
        soup = BeautifulSoup(html, "html.parser")
        news, crumbs, _ = BaseScraperConnector._parse_json_ld(soup)
        assert news["headline"] == "Graph Artikel"
        assert len(crumbs) == 2

    def test_parse_json_ld_with_standalone_person(self):
        data = [
            {"@type": "NewsArticle", "headline": "Artikel"},
            {"@type": "Person", "name": "Johanna"},
        ]
        html = f"<html><head>{_json_ld_script(data)}</head><body></body></html>"
        from bs4 import BeautifulSoup
        soup = BeautifulSoup(html, "html.parser")
        _, _, author = BaseScraperConnector._parse_json_ld(soup)
        assert author == "Johanna"

    def test_base_parse_breadcrumb_drops_home_and_last(self):
        items = [
            {"name": "Home"},
            {"name": "Schweiz"},
            {"name": "Artikel Titel"},
        ]
        category, tags = BaseScraperConnector._parse_breadcrumb(items)
        assert category == "Schweiz"
        assert tags == []

    def test_base_parse_breadcrumb_multiple_crumbs(self):
        items = [
            {"name": "Home"},
            {"name": "Wirtschaft"},
            {"name": "Börse"},
            {"name": "Artikel Titel"},
        ]
        category, tags = BaseScraperConnector._parse_breadcrumb(items)
        assert category == "Wirtschaft"
        assert tags == ["Börse"]

    def test_base_parse_breadcrumb_empty(self):
        category, tags = BaseScraperConnector._parse_breadcrumb([])
        assert category is None
        assert tags == []


# ─────────────────────────────────────────────────────────────────────────────
# 20 Minuten
# ─────────────────────────────────────────────────────────────────────────────

class TestTwentyMinutesConnector:

    def setup_method(self):
        self.c = TwentyMinutesScraperConnector()

    # --- Link extraction ---

    def test_extract_article_links_basic(self):
        html = """
        <html><body>
          <a href="/story/wie-die-schweiz-schlaeft-103543041">Artikel</a>
          <a href="/story/breaking-news-987654321">News</a>
          <a href="/impressum">Impressum</a>
        </body></html>
        """
        links = self.c.extract_article_links(html, "https://www.20min.ch")
        assert any("103543041" in l for l in links)
        assert any("987654321" in l for l in links)
        assert not any("impressum" in l for l in links)

    def test_extract_article_links_deduplicates(self):
        html = """
        <html><body>
          <a href="/story/doppelt-103543041">A</a>
          <a href="/story/doppelt-103543041">B</a>
        </body></html>
        """
        links = self.c.extract_article_links(html, "")
        assert links.count("https://www.20min.ch/story/doppelt-103543041") == 1

    def test_extract_article_links_strips_query_params(self):
        html = '<html><body><a href="/story/titel-111222333?utm_source=foo">A</a></body></html>'
        links = self.c.extract_article_links(html, "")
        assert all("?" not in l for l in links)

    # --- Article ID ---

    def test_extract_article_id(self):
        assert self.c._extract_article_id("https://www.20min.ch/story/wie-die-schweiz-103543041") == "103543041"

    def test_extract_article_id_no_match(self):
        assert self.c._extract_article_id("https://www.20min.ch/impressum") is None

    # --- Breadcrumb ---

    def test_parse_breadcrumb_filters_news(self):
        items = [
            {"name": "News"},
            {"item": {"name": "Wirtschaft"}},
            {"name": "Artikel Titel"},
        ]
        category, tags = self.c._parse_breadcrumb(items)
        assert category == "Wirtschaft"
        assert tags == []

    def test_parse_breadcrumb_multiple_tags(self):
        items = [
            {"name": "News"},
            {"item": {"name": "Sport"}},
            {"name": "Fussball"},
            {"name": "Artikel Titel"},
        ]
        category, tags = self.c._parse_breadcrumb(items)
        assert category == "Sport"
        assert tags == ["Fussball"]

    # --- detect article type ---

    def test_detect_article_type_standard(self):
        assert self.c._detect_article_type({"@type": "NewsArticle"}) == "standard"

    def test_detect_article_type_liveblog(self):
        assert self.c._detect_article_type({"@type": "LiveBlogPosting"}) == "liveblog"
        assert self.c._detect_article_type({"alternativeHeadline": "Live-Ticker: Spiel"}) == "liveblog"

    # --- Full parse ---

    def test_parse_article_returns_article(self):
        html = _make_article_html(
            title="Schweizer Parlament streitet",
            article_body="Der Nationalrat debattierte stundenlang.",
        )
        article = self.c.parse_article(html, "https://www.20min.ch/story/test-103543041")
        assert article.title == "Schweizer Parlament streitet"
        assert "Nationalrat debattierte" in article.content
        assert article.source == "20min.ch"
        assert article.source_article_id == "103543041"

    def test_parse_article_with_alternative_headline(self):
        data = {
            "@type": "NewsArticle",
            "headline": "Haupttitel",
            "alternativeHeadline": "Untertitel hier",
            "articleBody": "Inhalt.",
            "datePublished": "2024-05-01T10:00:00Z",
        }
        html = f"<html><head>{_json_ld_script(data)}</head><body></body></html>"
        article = self.c.parse_article(html, "https://www.20min.ch/story/test-999000001")
        assert "[Unterzeile: Untertitel hier]" in article.content

    def test_parse_article_missing_article_body_uses_fallback(self, monkeypatch):
        monkeypatch.setattr(
            "src.connectors.abstract.scraper_connector.BaseScraperConnector._trafilatura_fallback",
            staticmethod(lambda html, url: "Trafilatura Fallback Text"),
        )
        data = {
            "@type": "NewsArticle",
            "headline": "Kein Body",
            "datePublished": "2024-05-01T10:00:00Z",
        }
        html = f"<html><head>{_json_ld_script(data)}</head><body><p>Trafilatura Fallback Text</p></body></html>"
        article = self.c.parse_article(html, "https://www.20min.ch/story/test-123456789")
        assert article.content == "Trafilatura Fallback Text"


# ─────────────────────────────────────────────────────────────────────────────
# Watson
# ─────────────────────────────────────────────────────────────────────────────

class TestWatsonConnector:

    def setup_method(self):
        self.c = WatsonScraperConnector()

    # --- Link extraction ---

    def test_extract_article_links_basic(self):
        html = """
        <html><body>
          <a href="/schweiz/123456-bundesrat-entscheid">Artikel</a>
          <a href="/sport/987654-fussball-ergebnis">Sport</a>
          <a href="/ueber-uns">Über uns</a>
        </body></html>
        """
        links = self.c.extract_article_links(html, "https://www.watson.ch")
        assert any("123456-bundesrat" in l for l in links)
        assert any("987654-fussball" in l for l in links)
        assert not any("ueber-uns" in l for l in links)

    def test_extract_article_links_only_watson_domain(self):
        html = """
        <html><body>
          <a href="https://www.watson.ch/schweiz/123456-inland">Watson</a>
          <a href="https://www.srf.ch/schweiz/123456-extern">Extern</a>
        </body></html>
        """
        links = self.c.extract_article_links(html, "")
        assert len(links) == 1
        assert "watson" in links[0]

    def test_extract_article_links_deduplicates(self):
        html = """
        <html><body>
          <a href="/schweiz/123456-doppelt">A</a>
          <a href="/schweiz/123456-doppelt">B</a>
        </body></html>
        """
        links = self.c.extract_article_links(html, "")
        assert len(links) == 1

    # --- Article ID ---

    def test_extract_article_id(self):
        url = "https://www.watson.ch/schweiz/1234567-bern-entscheid"
        assert self.c._extract_article_id(url) == "1234567"

    def test_extract_article_id_no_match(self):
        assert self.c._extract_article_id("https://www.watson.ch/ueber-uns") is None

    # --- Breadcrumb ---

    def test_parse_breadcrumb_skips_last(self):
        items = [
            {"name": "Schweiz"},
            {"name": "Bern"},
            {"name": "Artikel Titel"},
        ]
        category, tags = self.c._parse_breadcrumb(items)
        assert category == "Schweiz"
        assert tags == ["Bern"]

    def test_parse_breadcrumb_single_item(self):
        items = [{"name": "Schweiz"}]
        # items[:-1] → empty
        category, tags = self.c._parse_breadcrumb(items)
        assert category is None
        assert tags == []

    # --- Full parse ---

    def test_parse_article_returns_article(self):
        html = _make_article_html(
            title="Bern stimmt ab",
            article_body="Heute fand die Abstimmung statt.",
        )
        article = self.c.parse_article(html, "https://www.watson.ch/schweiz/1234567-bern-stimmt-ab")
        assert article.title == "Bern stimmt ab"
        assert "Abstimmung" in article.content
        assert article.source == "watson.ch"
        assert article.source_article_id == "1234567"

    def test_parse_article_strips_html_from_article_body(self):
        data = {
            "@type": "NewsArticle",
            "headline": "Mit HTML Body",
            "articleBody": "<p>Paragraph mit <b>Fett</b>.</p>",
            "datePublished": "2024-05-01T10:00:00Z",
        }
        html = f"<html><head>{_json_ld_script(data)}</head><body></body></html>"
        article = self.c.parse_article(html, "https://www.watson.ch/schweiz/9999999-test")
        assert "<p>" not in article.content
        assert "Paragraph mit Fett ." in article.content

    def test_parse_article_prepends_lead(self):
        data = {
            "@type": "NewsArticle",
            "headline": "Titel",
            "description": "Kurze Zusammenfassung.",
            "articleBody": "Ausführlicher Text.",
            "datePublished": "2024-05-01T10:00:00Z",
        }
        html = f"<html><head>{_json_ld_script(data)}</head><body></body></html>"
        article = self.c.parse_article(html, "https://www.watson.ch/schweiz/1111111-titel")
        assert article.content.startswith("[Lead: Kurze Zusammenfassung.]")


# ─────────────────────────────────────────────────────────────────────────────
# Nau
# ─────────────────────────────────────────────────────────────────────────────

class TestNauConnector:

    def setup_method(self):
        self.c = NauScraperConnector()

    # --- Link extraction ---

    def test_extract_article_links_basic(self):
        html = """
        <html><body>
          <a href="/news/inland/bundesrat-beschluss-12345678">Artikel</a>
          <a href="/sport/fussball-ergebnis-99887766">Sport</a>
          <a href="/impressum">Impressum</a>
        </body></html>
        """
        links = self.c.extract_article_links(html, "https://www.nau.ch")
        assert any("12345678" in l for l in links)
        assert any("99887766" in l for l in links)
        assert not any("impressum" in l for l in links)

    def test_extract_article_links_only_nau_domain(self):
        html = """
        <html><body>
          <a href="https://www.nau.ch/news/inland-12345678">Nau</a>
          <a href="https://www.srf.ch/news/inland-12345678">SRF</a>
        </body></html>
        """
        links = self.c.extract_article_links(html, "")
        assert len(links) == 1

    def test_extract_article_links_deduplicates(self):
        html = """
        <html><body>
          <a href="/news/doppelt-12345678">A</a>
          <a href="/news/doppelt-12345678">B</a>
        </body></html>
        """
        links = self.c.extract_article_links(html, "")
        assert len(links) == 1

    # --- Article ID ---

    def test_extract_article_id(self):
        url = "https://www.nau.ch/news/inland/bundesrat-beschluss-12345678"
        assert self.c._extract_article_id(url) == "12345678"

    def test_extract_article_id_no_match(self):
        assert self.c._extract_article_id("https://www.nau.ch/impressum") is None

    # --- Breadcrumb ---

    def test_parse_breadcrumb_no_trailing_skip(self):
        # Nau doesn't put article title in breadcrumb — don't drop last item
        items = [
            {"name": "Home"},
            {"name": "News"},
            {"name": "Inland"},
        ]
        category, tags = self.c._parse_breadcrumb(items)
        assert category == "News"
        assert tags == ["Inland"]

    def test_parse_breadcrumb_filters_home(self):
        items = [
            {"name": "Home"},
            {"item": {"name": "Sport"}},
        ]
        category, tags = self.c._parse_breadcrumb(items)
        assert category == "Sport"

    # --- Full parse ---

    def test_parse_article_returns_article(self, monkeypatch):
        monkeypatch.setattr(
            "src.connectors.abstract.scraper_connector.BaseScraperConnector._trafilatura_fallback",
            staticmethod(lambda html, url: "Nau Artikeltext."),
        )
        html = _make_article_html(title="Nau Artikel", description="Kurz.")
        article = self.c.parse_article(html, "https://www.nau.ch/news/test-12345678")
        assert article.title == "Nau Artikel"
        assert article.source == "nau.ch"
        assert article.source_article_id == "12345678"
        assert "Nau Artikeltext." in article.content

    def test_parse_article_nested_author(self, monkeypatch):
        monkeypatch.setattr(
            "src.connectors.abstract.scraper_connector.BaseScraperConnector._trafilatura_fallback",
            staticmethod(lambda html, url: "Text."),
        )
        data = {
            "@type": "NewsArticle",
            "headline": "Test",
            "author": [[{"@type": "Person", "name": "Redaktion nau.ch"}]],
            "datePublished": "2024-05-01T10:00:00Z",
        }
        html = f"<html><head>{_json_ld_script(data)}</head><body></body></html>"
        article = self.c.parse_article(html, "https://www.nau.ch/news/test-99887766")
        assert article.author == "Redaktion nau.ch"

    def test_parse_article_prepends_lead_if_not_duplicate(self, monkeypatch):
        monkeypatch.setattr(
            "src.connectors.abstract.scraper_connector.BaseScraperConnector._trafilatura_fallback",
            staticmethod(lambda html, url: "Weiterer Inhalt."),
        )
        data = {
            "@type": "NewsArticle",
            "headline": "Test",
            "description": "Lead Beschreibung.",
            "datePublished": "2024-05-01T10:00:00Z",
        }
        html = f"<html><head>{_json_ld_script(data)}</head><body></body></html>"
        article = self.c.parse_article(html, "https://www.nau.ch/news/test-12345679")
        assert article.content.startswith("[Lead: Lead Beschreibung.]")


# ─────────────────────────────────────────────────────────────────────────────
# Blick
# ─────────────────────────────────────────────────────────────────────────────

class TestBlickConnector:

    def setup_method(self):
        self.c = BlickScraperConnector()

    # --- Link extraction ---

    def test_extract_article_links_basic(self):
        html = """
        <html><body>
          <a href="/schweiz/politik/bundesrat-entscheid-id123456789.html">Artikel</a>
          <a href="/sport/fussball-id987654321.html">Sport</a>
          <a href="/impressum">Impressum</a>
        </body></html>
        """
        links = self.c.extract_article_links(html, "https://www.blick.ch")
        assert any("id123456789" in l for l in links)
        assert any("id987654321" in l for l in links)
        assert not any("impressum" in l for l in links)

    def test_extract_article_links_filters_unknown_sections(self):
        html = """
        <html><body>
          <a href="/podcast/folge-id123456789.html">Podcast</a>
          <a href="/schweiz/news-id987654321.html">Schweiz</a>
        </body></html>
        """
        links = self.c.extract_article_links(html, "")
        # podcast is not in NEWS_SECTIONS, schweiz is
        assert len(links) == 1
        assert "schweiz" in links[0]

    def test_extract_article_links_deduplicates(self):
        html = """
        <html><body>
          <a href="/schweiz/test-id123456789.html">A</a>
          <a href="/schweiz/test-id123456789.html">B</a>
        </body></html>
        """
        links = self.c.extract_article_links(html, "")
        assert len(links) == 1

    def test_extract_article_links_strips_query_params(self):
        html = '<html><body><a href="/schweiz/test-id123456789.html?ref=nav">A</a></body></html>'
        links = self.c.extract_article_links(html, "")
        assert all("?" not in l for l in links)

    # --- Article ID ---

    def test_extract_article_id(self):
        url = "https://www.blick.ch/schweiz/politik/titel-id123456789.html"
        assert self.c._extract_article_id(url) == "123456789"

    def test_extract_article_id_no_match(self):
        assert self.c._extract_article_id("https://www.blick.ch/impressum") is None

    # --- Breadcrumb ---

    def test_parse_breadcrumb_blick_structure(self):
        # Blick: Home > Category > (Sub) > Article title — skip first AND last
        items = [
            {"name": "Home"},
            {"name": "Schweiz"},
            {"name": "Politik"},
            {"name": "Artikel Titel"},
        ]
        category, tags = self.c._parse_breadcrumb(items)
        assert category == "Schweiz"
        assert tags == ["Politik"]

    def test_parse_breadcrumb_single_middle_crumb(self):
        items = [
            {"name": "Home"},
            {"name": "Sport"},
            {"name": "Artikel Titel"},
        ]
        category, tags = self.c._parse_breadcrumb(items)
        assert category == "Sport"
        assert tags == []

    # --- Article body extraction ---

    def test_extract_article_body_from_article_tag(self):
        from bs4 import BeautifulSoup
        html = """
        <html><body>
          <article>
            <p>Kurzer Satz.</p>
            <p>Dieser Satz ist lang genug um extrahiert zu werden ja wirklich.</p>
            <p>Kurz.</p>
          </article>
          <aside><p>Dieser Nebensatz soll nicht erscheinen weil er in aside ist.</p></aside>
        </body></html>
        """
        soup = BeautifulSoup(html, "html.parser")
        body = self.c._extract_article_body(soup)
        assert "lang genug" in body
        assert "Nebensatz" not in body

    def test_extract_article_body_min_length_filter(self):
        from bs4 import BeautifulSoup
        html = "<html><body><article><p>Kurz.</p><p>Ein sehr langer Paragraph der mehr als vierzig Zeichen hat.</p></article></body></html>"
        soup = BeautifulSoup(html, "html.parser")
        body = self.c._extract_article_body(soup)
        assert "Kurz." not in body
        assert "langer Paragraph" in body

    # --- Full parse ---

    def test_parse_article_returns_article(self):
        breadcrumb = [
            {"name": "Home"},
            {"name": "Schweiz"},
            {"name": "Artikel Titel"},
        ]
        html = _make_article_html(
            title="Blick Artikel",
            description="Blick Lead.",
            breadcrumb=breadcrumb,
        )
        # Inject a proper article body since blick uses <article> tag
        from bs4 import BeautifulSoup
        soup = BeautifulSoup(html, "html.parser")
        article_el = soup.new_tag("article")
        p = soup.new_tag("p")
        p.string = "Dies ist ein ausreichend langer Paragraph damit er extrahiert wird."
        article_el.append(p)
        soup.body.append(article_el)
        html_with_body = str(soup)

        article = self.c.parse_article(html_with_body, "https://www.blick.ch/schweiz/test-id123456789.html")
        assert article.title == "Blick Artikel"
        assert article.source == "blick.ch"
        assert article.source_article_id == "123456789"
        assert "[Lead: Blick Lead.]" in article.content
