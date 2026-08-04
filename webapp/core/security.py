"""Wiederverwendbare Sicherheits- und Validierungsfunktionen."""

import os
from html import escape
from html.parser import HTMLParser
from urllib.parse import urljoin, urlparse


class NewsletterHTMLSanitizer(HTMLParser):
    """Kleine Allowlist für Newsletter-HTML ohne externe Abhängigkeit."""

    ALLOWED_TAGS = {
        'a', 'b', 'br', 'blockquote', 'div', 'em', 'h2', 'h3', 'h4', 'hr',
        'i', 'img', 'li', 'ol', 'p', 'span', 'strong', 'table', 'tbody',
        'td', 'th', 'thead', 'tr', 'u', 'ul',
    }
    ALLOWED_ATTRS = {
        'a': {'href', 'title'},
        'img': {'src', 'alt', 'width', 'height'},
        'table': {'width'},
        'td': {'colspan', 'rowspan'},
        'th': {'colspan', 'rowspan'},
    }
    SAFE_URL_SCHEMES = {'http', 'https', 'mailto'}
    VOID_TAGS = {'br', 'hr', 'img'}

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.parts = []

    def _safe_attrs(self, tag, attrs):
        allowed = self.ALLOWED_ATTRS.get(tag, set())
        safe_attrs = []
        for key, value in attrs:
            key = (key or '').lower()
            value = value or ''
            if key not in allowed:
                continue
            if key in {'href', 'src'}:
                parsed = urlparse(value.strip())
                if parsed.scheme.lower() not in self.SAFE_URL_SCHEMES:
                    continue
            safe_attrs.append(f'{key}="{escape(value, quote=True)}"')
        return (' ' + ' '.join(safe_attrs)) if safe_attrs else ''

    def handle_starttag(self, tag, attrs):
        tag = tag.lower()
        if tag in self.ALLOWED_TAGS:
            self.parts.append(f'<{tag}{self._safe_attrs(tag, attrs)}>')

    def handle_endtag(self, tag):
        tag = tag.lower()
        if tag in self.ALLOWED_TAGS and tag not in self.VOID_TAGS:
            self.parts.append(f'</{tag}>')

    def handle_data(self, data):
        self.parts.append(escape(data))

    def handle_entityref(self, name):
        self.parts.append(f'&{name};')

    def handle_charref(self, name):
        self.parts.append(f'&#{name};')


def sanitize_newsletter_html(html):
    sanitizer = NewsletterHTMLSanitizer()
    sanitizer.feed(html or '')
    sanitizer.close()
    return ''.join(sanitizer.parts)


def is_safe_redirect_url(target, host_url):
    """Erlaubt nur relative oder auf denselben Host zeigende Weiterleitungen."""
    if not target:
        return False
    reference = urlparse(host_url)
    candidate = urlparse(urljoin(host_url, target))
    return candidate.scheme in {'http', 'https'} and reference.netloc == candidate.netloc


MIN_PASSWORD_LENGTH = int(os.environ.get('EEG_MIN_PASSWORD_LENGTH', '12'))

_WEAK_PASSWORDS = {
    '123456789012', '1234567890123', 'passwort1234', 'password1234',
    'passwort2024', 'passwort2025', 'passwort2026', 'password2024',
    'password2025', 'password2026', 'qwertzuiopas', 'qwertyuiopas',
    'administrator', 'willkommen12', 'willkommen123', 'sommer2025!',
    'geheim123456', 'iloveyou1234', 'letmein12345', 'trustno1234',
}


def validate_password(password, username=None):
    """Prüft ein neues Passwort und liefert eine Fehlermeldung oder ``''``."""
    password = password or ''
    if len(password) < MIN_PASSWORD_LENGTH:
        return (f'Passwort muss mindestens {MIN_PASSWORD_LENGTH} Zeichen haben. '
                'Eine Passphrase aus mehreren Woertern ist am einfachsten zu merken.')
    normalized = password.strip().lower()
    if normalized in _WEAK_PASSWORDS:
        return 'Dieses Passwort ist zu leicht zu erraten. Bitte ein anderes waehlen.'
    if len(set(normalized)) < 5:
        return 'Passwort besteht aus zu wenigen unterschiedlichen Zeichen.'
    if username and len(username) >= 3 and username.strip().lower() in normalized:
        return 'Passwort darf den Benutzernamen nicht enthalten.'
    return ''
