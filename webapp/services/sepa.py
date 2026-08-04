"""Erzeugung und Validierung von SEPA-EPC-QR-Daten."""

import io
import re
import unicodedata


SEPA_ALLOWED_CHARS = set(
    "abcdefghijklmnopqrstuvwxyz"
    "ABCDEFGHIJKLMNOPQRSTUVWXYZ"
    "0123456789/-?:().,'+ "
)
SEPA_REPLACEMENTS = {
    'ä': 'ae', 'ö': 'oe', 'ü': 'ue', 'Ä': 'Ae', 'Ö': 'Oe', 'Ü': 'Ue', 'ß': 'ss',
    '&': 'und', '"': "'", '_': '-', '–': '-', '—': '-',
}
EPC_MAX_PAYLOAD_BYTES = 331


def sepa_text(value, limit):
    text = ''.join(SEPA_REPLACEMENTS.get(char, char) for char in str(value or ''))
    text = unicodedata.normalize('NFKD', text).encode('ascii', 'ignore').decode('ascii')
    text = ''.join(char if char in SEPA_ALLOWED_CHARS else ' ' for char in text)
    return ' '.join(text.split())[:limit]


def normalize_iban(value):
    """Prüft Format und Prüfziffer der IBAN und entfernt Leerzeichen."""
    iban = re.sub(r'\s+', '', str(value or '')).upper()
    if not iban:
        raise ValueError('Für den QR-Code ist keine IBAN hinterlegt.')
    if not re.fullmatch(r'[A-Z]{2}[0-9]{2}[A-Z0-9]{11,30}', iban):
        raise ValueError('Die IBAN hat kein gültiges Format.')
    rearranged = iban[4:] + iban[:4]
    if int(''.join(str(int(char, 36)) for char in rearranged)) % 97 != 1:
        raise ValueError('Die IBAN ist ungültig, die Prüfziffer stimmt nicht.')
    return iban


def build_epc_payload(recipient, iban, amount, remittance='', bic=''):
    """Erstellt einen Datensatz nach EPC069-12 für SEPA Credit Transfer."""
    name = sepa_text(recipient, 70)
    if not name:
        raise ValueError('Für den QR-Code fehlt der Name des Empfängers.')
    amount = round(float(amount), 2)
    if not 0.01 <= amount <= 999999999.99:
        raise ValueError('Der Betrag lässt sich nicht als QR-Code darstellen.')
    lines = [
        'BCD', '002', '1', 'SCT', sepa_text(bic, 11).replace(' ', ''),
        name, normalize_iban(iban), f'EUR{amount:.2f}', '', '',
        sepa_text(remittance, 140), '',
    ]
    payload = '\n'.join(lines).rstrip('\n')
    if len(payload.encode('utf-8')) > EPC_MAX_PAYLOAD_BYTES:
        raise ValueError('Die Zahlungsdaten sind für einen QR-Code zu lang.')
    return payload


def render_epc_qr_svg(payload):
    """Rendert einen EPC-QR-Code als skalierbares SVG."""
    import qrcode
    import qrcode.image.svg

    qr = qrcode.QRCode(
        error_correction=qrcode.constants.ERROR_CORRECT_M,
        box_size=10,
        border=2,
    )
    qr.add_data(payload)
    qr.make(fit=True)
    buffer = io.BytesIO()
    qr.make_image(image_factory=qrcode.image.svg.SvgPathImage).save(buffer)
    return buffer.getvalue().decode('utf-8')
