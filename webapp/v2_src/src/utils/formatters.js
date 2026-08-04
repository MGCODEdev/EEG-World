export function formatNumber(value, digits = 0) {
  const number = Number(value) || 0;
  return new Intl.NumberFormat('de-AT', {
    minimumFractionDigits: digits,
    maximumFractionDigits: digits,
  }).format(number);
}

export function formatCurrency(value) {
  return new Intl.NumberFormat('de-AT', {
    style: 'currency',
    currency: 'EUR',
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  }).format(Number(value) || 0);
}

export function formatSignedCurrency(value) {
  const number = Number(value) || 0;
  if (number > 0) return `+${formatCurrency(number)}`;
  if (number < 0) return `-${formatCurrency(Math.abs(number))}`;
  return formatCurrency(0);
}

export function formatBytes(value) {
  const bytes = Number(value) || 0;
  if (bytes < 1024) return `${formatNumber(bytes)} B`;
  if (bytes < 1024 * 1024) return `${formatNumber(bytes / 1024, 1)} KB`;
  if (bytes < 1024 * 1024 * 1024) return `${formatNumber(bytes / 1024 / 1024, 1)} MB`;
  return `${formatNumber(bytes / 1024 / 1024 / 1024, 2)} GB`;
}

export function formatDate(value) {
  if (!value) return '';
  const dateValue = String(value).slice(0, 10);
  const date = new Date(`${dateValue}T00:00:00`);
  if (Number.isNaN(date.getTime())) return value;
  return new Intl.DateTimeFormat('de-AT', {day: '2-digit', month: '2-digit', year: 'numeric'}).format(date);
}

export function formatDateTime(value) {
  if (!value) return '-';
  const normalized = String(value).includes('T') ? value : String(value).replace(' ', 'T');
  const date = new Date(normalized.endsWith('Z') ? normalized : `${normalized}Z`);
  if (Number.isNaN(date.getTime())) return value;
  return new Intl.DateTimeFormat('de-AT', {
    day: '2-digit', month: '2-digit', year: 'numeric', hour: '2-digit', minute: '2-digit',
  }).format(date);
}

export function formatMonth(value) {
  if (!value) return 'Unbekannt';
  const date = new Date(`${value}T00:00:00`);
  if (Number.isNaN(date.getTime())) return value;
  return new Intl.DateTimeFormat('de-AT', {month: 'long', year: 'numeric'}).format(date);
}

export function formatDateRange(from, to) {
  if (!from && !to) return 'Zeitraum offen';
  if (from === to || !to) return formatDate(from);
  return `${formatDate(from)} - ${formatDate(to)}`;
}

export function formatParticipation(value) {
  const number = Number(value);
  if (!Number.isFinite(number)) return 'Teilnahme nicht gesetzt';
  return `${formatNumber(number * 100, number % 1 ? 1 : 0)} % Teilnahme`;
}

export function formatParticipationShort(value) {
  const number = Number(value);
  if (!Number.isFinite(number)) return '-';
  return `${formatNumber(number * 100, number % 1 ? 1 : 0)}%`;
}

export function formatFullAddress(member) {
  const street = member.address_street || '';
  const location = formatLocation(member.address_zip, member.address_city);
  return [street, location !== 'Kein Ort' ? location : ''].filter(Boolean).join(', ') || 'Keine Adresse';
}

export function formatLocation(zip, city) {
  return [zip, city].filter(Boolean).join(' ') || 'Kein Ort';
}

export function invoiceStatusLabel(status) {
  const labels = {draft: 'Noch nicht abgeschlossen', sent: 'Versendet', paid: 'Bezahlt'};
  return labels[status] || status || 'Status offen';
}

export function isActivePath(currentPath, itemPath) {
  if (itemPath === '/') return currentPath === '/';
  return currentPath === itemPath || currentPath.startsWith(`${itemPath}/`);
}

export function v2Href(path) {
  if (path === '/') return '/v2/';
  return `/v2${path}`;
}
