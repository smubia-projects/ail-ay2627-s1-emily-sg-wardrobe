"""Shop-page reader for the size checker.

Fetches one public product page and boils it down to the text that matters for
size and fit (schema.org product facts, the top of the page and any stretches
that mention a size chart). Ported unchanged from the student's local helper
(wardrobe-server.py). Many shops block datacenter IPs or render sizes with
JavaScript, so the frontend treats a pasted size chart as the primary input and
this reader as a best-effort extra.
"""
import gzip
import html
import ipaddress
import json
import re
import socket
import ssl
import urllib.error
import urllib.parse
import urllib.request

try:
    import certifi
    TLS = ssl.create_default_context(cafile=certifi.where())
except ImportError:
    TLS = ssl.create_default_context()
BROWSER = {"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0 Safari/537.36",
           "Accept": "text/html,application/xhtml+xml;q=0.9,*/*;q=0.8", "Accept-Language": "en-SG,en;q=0.9"}
SIZE_WORDS = re.compile(r"size (guide|chart)|measurement|\bbust\b|\bwaist\b|\bhips?\b|\bchest\b|\binseam\b|\bptp\b|\(cm\)|in cm", re.I)


def public_host(host):
    # the page may only be fetched from the public internet, never from this server or its private network
    try:
        found = socket.getaddrinfo(host, None)
    except (OSError, UnicodeError):
        return False
    return bool(found) and all(ipaddress.ip_address(f[4][0]).is_global for f in found)


class PublicRedirects(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        to = urllib.parse.urlsplit(newurl)
        if to.scheme not in ("http", "https") or not public_host(to.hostname or ""):
            raise urllib.error.URLError("redirect to a non-public address")
        return super().redirect_request(req, fp, code, msg, headers, newurl)


OPENER = urllib.request.build_opener(PublicRedirects, urllib.request.HTTPSHandler(context=TLS))


def meta(doc, key):
    k = re.escape(key)
    m = (re.search(r'<meta[^>]+(?:property|name)=["\']%s["\'][^>]*?content=["\']([^"\']*)' % k, doc, re.I)
         or re.search(r'<meta[^>]+content=["\']([^"\']*)["\'][^>]*?(?:property|name)=["\']%s["\']' % k, doc, re.I))
    return html.unescape(m.group(1)).strip() if m else ""


def products(node, out):
    # schema.org Product blocks, which most shops embed for search engines
    if isinstance(node, list):
        for n in node:
            products(n, out)
    elif isinstance(node, dict):
        kind = node.get("@type")
        if kind == "Product" or (isinstance(kind, list) and "Product" in kind) or kind == "ProductGroup":
            out.append(node)
        for v in node.values():
            if isinstance(v, (dict, list)):
                products(v, out)


def facts(doc):
    found, lines, price = [], [], ""
    for block in re.findall(r'<script[^>]+application/ld\+json[^>]*>(.*?)</script>', doc, re.S | re.I):
        try:
            products(json.loads(block.strip()), found)
        except ValueError:
            pass
    sizes = []
    for p in found[:12]:
        brand = p.get("brand")
        brand = brand.get("name") if isinstance(brand, dict) else brand
        for label, val in (("Name", p.get("name")), ("Brand", brand), ("Material", p.get("material")), ("Colour", p.get("color")),
                           ("Description", p.get("description"))):
            line = f"{label}: {str(val)[:600]}" if isinstance(val, (str, int, float)) and str(val).strip() else ""
            if line and line not in lines:
                lines.append(line)
        if isinstance(p.get("size"), (str, int, float)) and str(p["size"]) not in sizes:
            sizes.append(str(p["size"]))
        offers = p.get("offers")
        offer = offers[0] if isinstance(offers, list) and offers else offers
        if isinstance(offer, dict) and not price and offer.get("price") not in (None, ""):
            price = f"{offer.get('priceCurrency', '')} {offer.get('price')}".strip()
    if sizes:
        lines.append("Sizes sold: " + ", ".join(sizes[:20]))
    return lines, price


def visible(doc):
    doc = re.sub(r"(?is)<(script|style|noscript|svg|template|head)\b.*?</\1>", " ", doc)
    doc = re.sub(r"(?i)</t[dh]>", " | ", doc)
    doc = re.sub(r"(?i)<(br|/tr|/p|/div|/li|/h[1-6]|/section|/table|/option)[^>]*>", "\n", doc)
    text = html.unescape(re.sub(r"<[^>]+>", " ", doc))
    lines, last = [], None
    for line in text.split("\n"):
        line = re.sub(r"\s+", " ", line).strip(" |")
        if line and line != last:
            lines.append(line)
            last = line
    return "\n".join(lines)


def read_product(url):
    at = urllib.parse.urlsplit(url)
    if at.scheme not in ("http", "https") or not at.hostname or not public_host(at.hostname):
        return 400, {"code": "bad_url", "error": "That is not a public web address"}
    try:
        with OPENER.open(urllib.request.Request(url, headers=BROWSER), timeout=12) as r:
            raw, final = r.read(2_500_000), r.geturl()
            kind, charset = r.headers.get("Content-Type", ""), r.headers.get_content_charset() or "utf-8"
            if r.headers.get("Content-Encoding") == "gzip":
                raw = gzip.decompress(raw)
    except urllib.error.HTTPError as e:
        return 502, {"code": "blocked", "error": f"The shop refused ({e.code})"}
    except Exception as e:
        return 502, {"code": "unreachable", "error": str(e)[:200]}
    if "html" not in kind:
        return 502, {"code": "not_page", "error": "That link is not a web page"}
    try:
        doc = raw.decode(charset, "replace")
    except LookupError:
        doc = raw.decode("utf-8", "replace")
    lines, price = facts(doc)
    body = visible(doc)
    # the top of the page, plus the stretches further down that talk about sizes
    parts, covered = [body[:2500]], 2500
    for hit in SIZE_WORDS.finditer(body):
        if hit.start() >= covered and len(parts) < 6:
            parts.append(body[max(covered, hit.start() - 300):hit.start() + 1100])
            covered = hit.start() + 1100
    title = meta(doc, "og:title") or (re.search(r"(?is)<title[^>]*>(.*?)</title>", doc) or [None, ""])[1]
    image = meta(doc, "og:image:secure_url") or meta(doc, "og:image")
    image = re.sub(r"^http://", "https://", urllib.parse.urljoin(final, image)) if image else ""
    price = price or f"{meta(doc, 'product:price:currency')} {meta(doc, 'product:price:amount')}".strip()
    text = "\n".join(lines + [meta(doc, "og:description") or meta(doc, "description")] + ["---"] + parts)[:9000]
    return 200, {"url": final, "title": re.sub(r"\s+", " ", html.unescape(title)).strip()[:200],
                 "image": image if image.startswith("https://") else "", "price": price[:40], "text": text}
