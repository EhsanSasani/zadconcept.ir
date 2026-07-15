import json
import re
from collections import defaultdict
from datetime import datetime, timezone as dt_timezone
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import unquote, urljoin, urlsplit

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.test import Client

from main.sitemaps import sitemaps


def normalized_text(value):
    return " ".join(str(value or "").split()).casefold()


def normalized_url(value):
    """Compare canonical URLs without treating percent-encoding as a mismatch."""
    parts = urlsplit(str(value or ""))
    path = unquote(parts.path or "/")
    if path != "/":
        path = path.rstrip("/") + "/"
    return (parts.scheme.lower(), parts.netloc.lower(), path, parts.query)


class SeoHTMLParser(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.in_title = False
        self.in_jsonld = False
        self.ignored_depth = 0
        self.title_parts = []
        self.visible_text_parts = []
        self.description = ""
        self.canonical = ""
        self.robots = ""
        self.og_image = ""
        self.og_image_width = ""
        self.og_image_height = ""
        self.twitter_card = ""
        self.icon = ""
        self.html_lang = ""
        self.hrefs = set()
        self.alternate_links = {}
        self.h1_count = 0
        self.breadcrumb_nav_count = 0
        self.images_missing_dimensions = []
        self.images_missing_alt = []
        self.jsonld_parts = []
        self.jsonld_documents = []

    @property
    def title(self):
        return " ".join("".join(self.title_parts).split())

    @property
    def visible_text(self):
        return normalized_text(" ".join(self.visible_text_parts))

    def handle_starttag(self, tag, attrs):
        attributes = dict(attrs)
        tag = tag.lower()
        if tag == "html":
            self.html_lang = attributes.get("lang", "").strip().lower()
        if tag == "title":
            self.in_title = True
        elif tag in {"script", "style", "template", "noscript"}:
            if tag == "script" and attributes.get("type", "").lower() == "application/ld+json":
                self.in_jsonld = True
                self.jsonld_parts = []
            else:
                self.ignored_depth += 1
        elif tag == "h1":
            self.h1_count += 1
        elif tag == "nav" and "breadcrumb" in attributes.get("aria-label", "").casefold():
            self.breadcrumb_nav_count += 1
        elif tag == "meta" and attributes.get("name", "").lower() == "description":
            self.description = attributes.get("content", "").strip()
        elif tag == "meta" and attributes.get("name", "").lower() == "robots":
            self.robots = attributes.get("content", "").strip().lower()
        elif tag == "meta" and attributes.get("property", "").lower() == "og:image":
            self.og_image = attributes.get("content", "").strip()
        elif tag == "meta" and attributes.get("property", "").lower() == "og:image:width":
            self.og_image_width = attributes.get("content", "").strip()
        elif tag == "meta" and attributes.get("property", "").lower() == "og:image:height":
            self.og_image_height = attributes.get("content", "").strip()
        elif tag == "meta" and attributes.get("name", "").lower() == "twitter:card":
            self.twitter_card = attributes.get("content", "").strip()
        elif tag == "link":
            rel_values = attributes.get("rel", "").lower().split()
            if "canonical" in rel_values:
                self.canonical = attributes.get("href", "").strip()
            if "icon" in rel_values:
                self.icon = attributes.get("href", "").strip()
            if "alternate" in rel_values and attributes.get("hreflang"):
                self.alternate_links[attributes["hreflang"].lower()] = attributes.get("href", "").strip()
        elif tag == "a" and attributes.get("href"):
            self.hrefs.add(attributes["href"])
        elif tag == "img":
            source = attributes.get("src", "") or attributes.get("data-src", "") or "[dynamic image]"
            if not attributes.get("width") or not attributes.get("height"):
                self.images_missing_dimensions.append(source)
            if "alt" not in attributes:
                self.images_missing_alt.append(source)

    def handle_endtag(self, tag):
        tag = tag.lower()
        if tag == "title":
            self.in_title = False
        elif tag == "script" and self.in_jsonld:
            self.in_jsonld = False
            raw = "".join(self.jsonld_parts).strip()
            if raw:
                self.jsonld_documents.append(raw)
        elif tag in {"script", "style", "template", "noscript"} and self.ignored_depth:
            self.ignored_depth -= 1

    def handle_data(self, data):
        if self.in_title:
            self.title_parts.append(data)
        if self.in_jsonld:
            self.jsonld_parts.append(data)
        elif not self.ignored_depth and data.strip():
            self.visible_text_parts.append(data)


def sitemap_urls():
    urls = set()
    for sitemap_class in sitemaps.values():
        sitemap = sitemap_class()
        for page_number in range(1, sitemap.paginator.num_pages + 1):
            urls.update(item["location"] for item in sitemap.get_urls(page=page_number))
    return sorted(urls)


def node_types(node):
    values = node.get("@type", []) if isinstance(node, dict) else []
    return [values] if isinstance(values, str) else list(values)


def parse_iso_datetime(value):
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=dt_timezone.utc)
    return parsed


class Command(BaseCommand):
    help = "Crawl public sitemap URLs and report SEO, schema, and HTML contract violations."

    def add_arguments(self, parser):
        parser.add_argument("--output", help="Optional JSON report path.")
        parser.add_argument("--fail-on-error", action="store_true")
        parser.add_argument("--skip-links", action="store_true")

    def handle(self, *args, **options):
        errors = []
        warnings = []
        page_results = []
        title_urls = defaultdict(list)
        description_urls = defaultdict(list)
        discovered_links = set()
        sitemap_set = set(sitemap_urls())
        canonical_host = urlsplit(settings.ZAD_SITE_URL).netloc
        if canonical_host in settings.ALLOWED_HOSTS or "*" in settings.ALLOWED_HOSTS:
            audit_host = canonical_host
        elif "testserver" in settings.ALLOWED_HOSTS:
            audit_host = "testserver"
        else:
            audit_host = settings.ALLOWED_HOSTS[0]
        client = Client(HTTP_HOST=audit_host)

        for url in sorted(sitemap_set):
            parts = urlsplit(url)
            request_target = parts.path + (f"?{parts.query}" if parts.query else "")
            response = client.get(request_target, secure=True)
            page = {"url": url, "status": response.status_code}
            page_results.append(page)

            if response.status_code != 200:
                errors.append(f"{url}: sitemap URL returned {response.status_code}")
                continue

            body = response.content.decode(response.charset or "utf-8", errors="replace")
            parser = SeoHTMLParser()
            parser.feed(body)
            page.update(
                {
                    "title": parser.title,
                    "description": parser.description,
                    "canonical": parser.canonical,
                    "robots": parser.robots,
                    "h1_count": parser.h1_count,
                    "html_lang": parser.html_lang,
                }
            )
            title_urls[parser.title].append(url)
            description_urls[parser.description].append(url)

            if not parser.title or parser.title.lower() in {"zad", "| zad"}:
                errors.append(f"{url}: missing or generic title")
            if not parser.description or "view  at zad" in parser.description.lower():
                errors.append(f"{url}: missing or invalid meta description")
            if normalized_url(parser.canonical) != normalized_url(url):
                errors.append(f"{url}: canonical is {parser.canonical or 'missing'}")
            if "noindex" in parser.robots:
                errors.append(f"{url}: sitemap page is marked noindex")
            if parser.h1_count != 1:
                errors.append(f"{url}: expected exactly one visible H1, found {parser.h1_count}")
            if not parser.html_lang:
                errors.append(f"{url}: html lang is missing")
            if not parser.og_image:
                errors.append(f"{url}: missing og:image")
            if not parser.og_image_width or not parser.og_image_height:
                errors.append(f"{url}: missing og:image dimensions")
            if parser.twitter_card != "summary_large_image":
                errors.append(f"{url}: missing or invalid twitter:card")
            if not parser.icon:
                errors.append(f"{url}: missing favicon link")
            if parser.images_missing_dimensions:
                errors.append(
                    f"{url}: {len(parser.images_missing_dimensions)} image(s) lack width/height"
                )
            if parser.images_missing_alt:
                errors.append(f"{url}: {len(parser.images_missing_alt)} image(s) lack alt")
            if "zad.ir" in body:
                errors.append(f"{url}: legacy zad.ir domain found")

            if len(parser.jsonld_documents) != 1:
                errors.append(
                    f"{url}: expected one JSON-LD graph, found {len(parser.jsonld_documents)}"
                )

            for raw_json in parser.jsonld_documents:
                try:
                    document = json.loads(raw_json)
                except ValueError:
                    errors.append(f"{url}: invalid JSON-LD")
                    continue
                nodes = document.get("@graph", []) if isinstance(document, dict) else []
                if not isinstance(nodes, list):
                    errors.append(f"{url}: JSON-LD @graph must be a list")
                    continue

                for node in nodes:
                    types = node_types(node)
                    if "BreadcrumbList" in types and not parser.breadcrumb_nav_count:
                        errors.append(f"{url}: BreadcrumbList exists without a visible breadcrumb nav")

                    if "FAQPage" in types:
                        entities = node.get("mainEntity", [])
                        if not entities:
                            errors.append(f"{url}: FAQPage has no questions")
                        for entity in entities:
                            question = normalized_text(entity.get("name"))
                            answer = normalized_text(
                                (entity.get("acceptedAnswer") or {}).get("text")
                            )
                            if not question or not answer:
                                errors.append(f"{url}: FAQPage has an empty question or answer")
                            elif question not in parser.visible_text or answer not in parser.visible_text:
                                errors.append(f"{url}: FAQ schema content is not visible verbatim")

                    if "Product" in types:
                        if not normalized_text(node.get("name")):
                            errors.append(f"{url}: Product JSON-LD has an empty name")
                        if "seller" in node:
                            errors.append(f"{url}: seller must be nested inside Offer, not Product")
                        offer = node.get("offers")
                        if offer:
                            for key in ("price", "priceCurrency", "availability", "url", "seller"):
                                if not offer.get(key):
                                    errors.append(f"{url}: Product Offer is missing {key}")
                            if offer.get("priceCurrency") != "IRR":
                                errors.append(f"{url}: Product Offer currency must be IRR")

                    if "Event" in types:
                        end_date = parse_iso_datetime(node.get("endDate"))
                        if (
                            end_date
                            and end_date < datetime.now(dt_timezone.utc)
                            and node.get("eventStatus") == "https://schema.org/EventScheduled"
                        ):
                            errors.append(f"{url}: past Event is still marked EventScheduled")

            if parts.path == "/international-orders/":
                for language in ("fa", "en", "x-default"):
                    if language not in parser.alternate_links:
                        errors.append(f"{url}: missing hreflang {language}")
            if parts.path == "/en/international-orders/":
                if parser.html_lang != "en":
                    errors.append(f"{url}: English page must use lang=en")
                for language in ("fa", "en", "x-default"):
                    if language not in parser.alternate_links:
                        errors.append(f"{url}: missing hreflang {language}")

            for href in parser.hrefs:
                resolved = urlsplit(urljoin(settings.ZAD_SITE_URL, href))
                if resolved.netloc != canonical_host:
                    continue
                if resolved.path.startswith(("/static/", "/media/", "/admin/", "/lead-request/")):
                    continue
                discovered_links.add(
                    resolved.path + (f"?{resolved.query}" if resolved.query else "")
                )

        for title, urls in title_urls.items():
            if title and len(urls) > 1:
                errors.append(f"Duplicate title {title!r}: {', '.join(urls)}")
        for description, urls in description_urls.items():
            if description and len(urls) > 1:
                errors.append(f"Duplicate description {description!r}: {', '.join(urls)}")

        if not options["skip_links"]:
            for path in sorted(discovered_links):
                response = client.get(path, secure=True, follow=False)
                if 300 <= response.status_code < 400:
                    errors.append(
                        f"Internal link points to redirect {path}: HTTP {response.status_code} -> "
                        f"{response.headers.get('Location', '')}"
                    )
                elif response.status_code >= 400:
                    errors.append(f"Broken internal link {path}: HTTP {response.status_code}")

        sitemap_paths = {urlsplit(url).path for url in sitemap_set}
        discovered_paths = {urlsplit(path).path for path in discovered_links}
        unlinked_sitemap_paths = sorted(
            path for path in sitemap_paths - discovered_paths if path != "/"
        )
        if unlinked_sitemap_paths:
            warnings.append(
                "Sitemap URLs not discovered through internal links: "
                + ", ".join(unlinked_sitemap_paths)
            )

        robots_response = client.get("/robots.txt", secure=True)
        if robots_response.status_code != 200:
            errors.append("robots.txt did not return 200")
        robots_body = robots_response.content.decode(errors="replace")
        if f"Sitemap: {settings.ZAD_SITE_URL}/sitemap.xml" not in robots_body:
            errors.append("robots.txt does not declare the canonical sitemap URL")
        for agent in ("OAI-SearchBot", "Claude-SearchBot", "PerplexityBot"):
            if f"User-agent: {agent}" not in robots_body:
                errors.append(f"robots.txt is missing search crawler policy for {agent}")

        report = {
            "site": settings.ZAD_SITE_URL,
            "pages_checked": len(page_results),
            "links_checked": 0 if options["skip_links"] else len(discovered_links),
            "errors": errors,
            "warnings": warnings,
            "pages": page_results,
        }

        if options.get("output"):
            output_path = Path(options["output"])
            output_path.parent.mkdir(parents=True, exist_ok=True)
            output_path.write_text(
                json.dumps(report, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )

        for warning in warnings:
            self.stdout.write(self.style.WARNING(warning))
        if errors:
            for error in errors:
                self.stderr.write(self.style.ERROR(error))
            if options["fail_on_error"]:
                raise CommandError(f"SEO audit failed with {len(errors)} error(s).")
        else:
            self.stdout.write(
                self.style.SUCCESS(
                    f"SEO audit passed: {len(page_results)} pages, "
                    f"{report['links_checked']} internal links, "
                    f"{len(warnings)} warning(s)."
                )
            )
