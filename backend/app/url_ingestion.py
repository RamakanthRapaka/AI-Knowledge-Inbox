"""Bounded public-page fetching with pinned DNS and basic HTML extraction."""
import http.client
import ipaddress
import socket
import ssl
import time
from html.parser import HTMLParser
from urllib.parse import urljoin, urlsplit, urlunsplit
from fastapi import HTTPException

MAX_BYTES = 2_000_000

def resolve_public(url):
    try:
        parts = urlsplit(url)
        if parts.scheme not in ('http', 'https') or not parts.hostname or parts.username or parts.password:
            raise ValueError()
        port = parts.port or (443 if parts.scheme == 'https' else 80)
        if port not in (80, 443):
            raise ValueError()
        host = parts.hostname.encode('idna').decode('ascii')
        if any(ord(char) < 33 for char in url):
            raise ValueError()
    except (ValueError, UnicodeError):
        raise HTTPException(422, 'Use a public HTTP/HTTPS URL without credentials, on port 80 or 443.')
    try:
        addresses = socket.getaddrinfo(host, port, type=socket.SOCK_STREAM)
    except socket.gaierror:
        raise HTTPException(502, 'The website hostname could not be resolved.')
    for address in addresses:
        ip = ipaddress.ip_address(address[4][0])
        if not ip.is_global or (ip.version == 6 and ip.ipv4_mapped and not ip.ipv4_mapped.is_global):
            raise HTTPException(422, 'Only public websites can be imported; internal addresses are blocked.')
    if not addresses:
        raise HTTPException(502, 'The website hostname could not be resolved.')
    return parts, host, port, addresses[0]

class PageText(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.hidden = []
        self.title_mode = False
        self.title = []
        self.text = []

    def handle_starttag(self, tag, attrs):
        if tag in ('script', 'style', 'noscript', 'nav', 'footer', 'header', 'svg', 'template'):
            self.hidden.append(tag)
        if tag == 'title':
            self.title_mode = True
        if tag in ('p', 'div', 'br', 'li', 'h1', 'h2', 'h3', 'section', 'article') and not self.hidden:
            self.text.append('\n')

    def handle_endtag(self, tag):
        if tag in self.hidden:
            index = len(self.hidden) - 1 - self.hidden[::-1].index(tag)
            self.hidden = self.hidden[:index]
        if tag == 'title':
            self.title_mode = False
        if tag in ('p', 'div', 'li', 'h1', 'h2', 'h3', 'section', 'article'):
            self.text.append('\n')

    def handle_data(self, data):
        if self.title_mode:
            self.title.append(data)
        elif not self.hidden:
            self.text.append(data)

def extract(raw, content_type):
    if content_type == 'text/plain':
        return None, raw.strip()
    parser = PageText()
    parser.feed(raw)
    title = ' '.join(''.join(parser.title).split())[:300] or None
    text = '\n'.join(line for part in ''.join(parser.text).splitlines() if (line := ' '.join(part.split())))
    return title, text

def fetch_page(url):
    deadline = time.monotonic() + 25
    for redirect in range(4):
        parts, host, port, address = resolve_public(url)
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            raise HTTPException(504, 'Website import timed out.')
        connection = http.client.HTTPConnection(host, port, timeout=min(8, remaining))
        sock = None
        try:
            # Connect to the validated address directly: no second DNS lookup.
            family, kind, protocol, _, sockaddr = address
            sock = socket.socket(family, kind, protocol)
            sock.settimeout(min(8, remaining))
            sock.connect(sockaddr)
            if parts.scheme == 'https':
                sock = ssl.create_default_context().wrap_socket(sock, server_hostname=host)
            connection.sock = sock
            target = urlunsplit(('', '', parts.path or '/', parts.query, ''))
            connection.request('GET', target, headers={'User-Agent': 'KnowledgeInbox/0.1', 'Accept': 'text/html,text/plain', 'Accept-Encoding': 'identity'})
            response = connection.getresponse()
            if response.status in (301, 302, 303, 307, 308):
                location = response.getheader('Location')
                if not location or redirect == 3:
                    raise HTTPException(502, 'Website redirected too many times or supplied an invalid redirect.')
                url = urljoin(url, location)
                continue
            if not 200 <= response.status < 300:
                raise HTTPException(502, f'Website returned HTTP {response.status}.')
            content_type = response.headers.get_content_type()
            if content_type not in ('text/html', 'application/xhtml+xml', 'text/plain'):
                raise HTTPException(422, 'Only HTML pages and plain-text URLs are supported.')
            if response.getheader('Content-Encoding', 'identity').lower() != 'identity':
                raise HTTPException(422, 'The website returned an unsupported compressed response.')
            body = bytearray()
            while True:
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    raise HTTPException(504, 'Website import timed out.')
                sock.settimeout(min(8, remaining))
                block = response.read1(min(65536, MAX_BYTES + 1 - len(body)))
                if not block:
                    break
                body.extend(block)
                if len(body) > MAX_BYTES:
                    raise HTTPException(413, 'Website content exceeds the 2 MB import limit.')
            encoding = response.headers.get_content_charset() or 'utf-8'
            try:
                raw = body.decode(encoding, errors='replace')
            except LookupError:
                raw = body.decode('utf-8', errors='replace')
            title, text = extract(raw, content_type)
            if not text.strip():
                raise HTTPException(422, 'No readable text was found. JavaScript-only pages are not supported.')
            return {'raw_content': raw, 'extracted_text': text, 'title': title, 'final_url': url}
        except (TimeoutError, socket.timeout):
            raise HTTPException(504, 'Website import timed out.')
        except (OSError, http.client.HTTPException, UnicodeError, ValueError):
            raise HTTPException(502, 'Could not fetch the website securely. Check the URL or try another page.')
        finally:
            connection.close()
            if sock:
                sock.close()
