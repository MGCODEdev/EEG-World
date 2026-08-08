import React, {useEffect, useId, useMemo, useRef, useState} from 'react';
import {createRoot} from 'react-dom/client';
import Highcharts from 'highcharts';
import 'highcharts/modules/heatmap';
import 'highcharts/modules/sankey';
import 'highcharts/modules/accessibility';
import {
  AppShell,
  Badge,
  Banner,
  Button,
  Card,
  CommandPalette,
  CommandPaletteEmpty,
  CommandPaletteInput,
  DateInput,
  Field,
  FileInput,
  MobileNav,
  NumberInput,
  ProgressBar,
  SideNav,
  SideNavHeading,
  SideNavItem,
  SideNavSection,
  Selector,
  StatusDot,
  Switch,
  Table,
  TextArea,
  TextInput,
  Theme,
  TopNav,
  createStaticSource,
  pixel,
  proportional,
  useToast,
} from '@astryxdesign/core';
import {ToastViewport} from '@astryxdesign/core/Toast';
import {
  Activity,
  Archive,
  Banknote,
  BookOpenText,
  ChartNoAxesCombined,
  Check,
  CircleCheck,
  Clock3,
  Command,
  Database,
  Download,
  Euro,
  ExternalLink,
  Eye,
  FileText,
  Landmark,
  LayoutDashboard,
  LogOut,
  Mail,
  MessageSquareText,
  NotebookText,
  Pencil,
  Plug,
  Plus,
  QrCode,
  ReceiptText,
  ScrollText,
  RefreshCw,
  RotateCcw,
  Settings,
  Sun,
  Trash2,
  Upload,
  UserCog,
  Users,
  X,
} from 'lucide-react';
import '@astryxdesign/core/reset.css';
import '@astryxdesign/core/astryx.css';
import '@astryxdesign/theme-neutral/theme.css';
import {eegTheme} from './eegTheme.js';
import ReleaseNotesPage from './pages/ReleaseNotesPage.jsx';
import {
  formatBytes,
  formatCurrency,
  formatDate,
  formatDateRange,
  formatDateTime,
  formatFullAddress,
  formatMonth,
  formatNumber,
  formatParticipation,
  formatParticipationShort,
  formatSignedCurrency,
  invoiceStatusLabel,
  isActivePath,
  v2Href,
} from './utils/formatters.js';
import './eegTheme.generated.css';
import './styles.css';

const adminNavItems = [
  {label: 'Dashboard', path: '/', icon: LayoutDashboard},
  {label: 'Import', path: '/import', icon: Upload},
  {label: 'Mitglieder', path: '/members', icon: Users},
  {label: 'Preise', path: '/prices', icon: Euro},
  {label: 'Abrechnungen', path: '/invoices', icon: ReceiptText},
  {label: 'Überweisungen', path: '/payments', icon: Banknote},
  {label: 'Mitgliedskonten', path: '/mitgliederkonten', icon: Landmark},
  {label: 'Kassabuch', path: '/kassabuch', icon: BookOpenText},
  {label: 'Reports', path: '/reports', icon: ChartNoAxesCombined},
  {label: 'Newsletter', path: '/newsletter', icon: Mail},
  {label: 'Mitgliedsnachrichten', path: '/admin/member-feedback', icon: MessageSquareText},
  {label: 'Release Notes', path: '/release-notes', icon: ScrollText},
  {type: 'section', label: 'Verwaltung'},
  {label: 'Benutzer', path: '/admin/users', icon: UserCog},
  {label: 'Audit-Log', path: '/admin/audit', icon: NotebookText},
  {label: 'Backup', path: '/admin/backup', icon: Archive},
  {label: 'Datenbank', path: '/admin/database', icon: Database},
  {label: 'Einstellungen', path: '/settings', icon: Settings},
];

const memberNavItems = [
  {label: 'Übersicht', path: '/portal', icon: LayoutDashboard},
  {label: 'Meine Daten', path: '/portal/data', icon: UserCog},
  {label: 'Abrechnungen', path: '/portal/invoices', icon: ReceiptText},
  {label: 'Reports', path: '/portal/reports', icon: ChartNoAxesCombined},
  {label: 'Verträge', path: '/portal/contracts', icon: BookOpenText},
];

function App() {
  return (
    <Theme theme={eegTheme} mode="light">
      <ToastViewport position="bottomEnd" maxVisible={3}>
        <V2Shell />
      </ToastViewport>
    </Theme>
  );
}

function V2Shell() {
  const data = window.EEG_V2_DATA || {};
  const user = data.user || {};
  const org = data.org || {};
  const security = data.security || {};
  const messages = data.messages || [];
  const currentPath = data.current_path || (user.role === 'admin' ? '/' : '/portal');
  const contentPath = data.content_path || `${currentPath}?embed=1`;
  const nativeData = data.native || null;
  const navItems = user.role === 'admin' ? adminNavItems : memberNavItems;
  const activeItem = useMemo(
    () => navItems.find((item) => item.path && isActivePath(currentPath, item.path)),
    [currentPath, navItems],
  );
  const iframeRef = useRef(null);
  const [isLoading, setIsLoading] = useState(!nativeData);
  const [globalWaiting, setGlobalWaiting] = useState(null);
  const [pdfPreview, setPdfPreview] = useState(null);
  const [isCommandOpen, setIsCommandOpen] = useState(false);
  const toast = useToast();
  const shownFlashToasts = useRef(new Set());
  const [isCollapsed, setIsCollapsed] = useState(() => {
    try {
      return window.localStorage.getItem('eegV2SidebarCollapsed') === '1';
    } catch (e) {
      return false;
    }
  });

  useEffect(() => {
    try {
      window.localStorage.setItem('eegV2SidebarCollapsed', isCollapsed ? '1' : '0');
    } catch (e) {}
  }, [isCollapsed]);

  useEffect(() => {
    messages.forEach((message, index) => {
      const status = flashStatus(message.category);
      if (status !== 'success' && status !== 'info') return;
      const uniqueID = `flash-${message.category || 'info'}-${index}-${message.text || ''}`;
      if (shownFlashToasts.current.has(uniqueID)) return;
      shownFlashToasts.current.add(uniqueID);
      toast({
        body: message.text,
        type: 'info',
        uniqueID,
        autoHideDuration: status === 'success' ? 4200 : 5600,
      });
    });
  }, [messages, toast]);

  useEffect(() => {
    function isPdfUrl(url) {
      try {
        const parsed = new URL(url, window.location.href);
        if (parsed.origin !== window.location.origin) return false;
        const path = parsed.pathname.toLowerCase();
        return path.endsWith('.pdf')
          || /\/invoices\/\d+\/pdf\/\d+/.test(path)
          || /\/kassabuch\/\d+\/beleg/.test(path)
          || /\/contracts\/\d+\/download/.test(path);
      } catch (e) {
        return false;
      }
    }

    function handleNativeClick(event) {
      const link = event.target.closest('a[href]');
      if (!link) return;
      const href = link.getAttribute('href') || '';
      if (!isPdfUrl(href)) return;
      if (event.shiftKey || event.ctrlKey || event.metaKey || event.altKey) return;
      if (link.target && link.target !== '_self') return;
      event.preventDefault();
      const parsed = new URL(href, window.location.href);
      parsed.searchParams.set('preview', '1');
      const downloadUrl = parsed.toString();
      parsed.searchParams.set('embed', '1');
      setPdfPreview({
        url: parsed.toString(),
        downloadUrl,
        title: link.getAttribute('title') || link.textContent.trim() || 'PDF Vorschau',
      });
    }

    const main = document.querySelector('.v2-main');
    if (main) main.addEventListener('click', handleNativeClick);
    return () => {
      if (main) main.removeEventListener('click', handleNativeClick);
    };
  }, []);

  useEffect(() => {
    function handleShortcut(event) {
      const target = event.target;
      const isTyping = target?.tagName === 'INPUT'
        || target?.tagName === 'TEXTAREA'
        || target?.tagName === 'SELECT'
        || target?.isContentEditable;
      if (isTyping) return;
      if ((event.metaKey || event.ctrlKey) && event.key.toLowerCase() === 'k') {
        event.preventDefault();
        setIsCommandOpen(true);
      }
    }
    window.addEventListener('keydown', handleShortcut);
    return () => window.removeEventListener('keydown', handleShortcut);
  }, []);

  useEffect(() => {
    function handleFrameMessage(event) {
      if (event.origin !== window.location.origin) return;
      if (event.data?.type === 'eeg-v2-loading') {
        setIsLoading(true);
        setGlobalWaiting({label: 'Seite wird geladen', detail: 'Bitte einen Moment warten.'});
      } else if (event.data?.type === 'eeg-v2-pdf-preview') {
        setIsLoading(false);
        setGlobalWaiting(null);
        setPdfPreview({
          url: event.data.url,
          downloadUrl: event.data.downloadUrl || event.data.url,
          title: event.data.title || 'PDF Vorschau',
        });
      }
    }

    window.addEventListener('message', handleFrameMessage);
    return () => window.removeEventListener('message', handleFrameMessage);
  }, []);

  useEffect(() => {
    function handleWaiting(event) {
      setGlobalWaiting({
        label: event.detail?.label || 'Bitte warten',
        detail: event.detail?.detail || 'Die Aktion wird verarbeitet.',
      });
    }
    function handleWaitingClear() {
      setGlobalWaiting(null);
    }
    window.addEventListener('eeg-v2-waiting', handleWaiting);
    window.addEventListener('eeg-v2-waiting-clear', handleWaitingClear);
    return () => {
      window.removeEventListener('eeg-v2-waiting', handleWaiting);
      window.removeEventListener('eeg-v2-waiting-clear', handleWaitingClear);
    };
  }, []);

  function syncAddressFromFrame() {
    setIsLoading(false);
    setGlobalWaiting(null);
    try {
      const frameUrl = iframeRef.current?.contentWindow?.location;
      if (!frameUrl || frameUrl.pathname.startsWith('/v2') || frameUrl.pathname === '/login') return;
      const params = new URLSearchParams(frameUrl.search);
      params.delete('embed');
      const query = params.toString();
      const nextPath = `/v2${frameUrl.pathname === '/' ? '/' : frameUrl.pathname}${query ? `?${query}` : ''}${frameUrl.hash || ''}`;
      if (window.location.pathname + window.location.search + window.location.hash !== nextPath) {
        window.history.replaceState(null, '', nextPath);
      }
    } catch (e) {
      // Downloads or browser-rendered documents can be inaccessible; the shell stays usable.
    }
  }

  function reloadContent() {
    if (nativeData) {
      setGlobalWaiting({label: 'Seite wird aktualisiert', detail: 'Die aktuellen Daten werden neu geladen.'});
      window.location.reload();
      return;
    }
    setIsLoading(true);
    setGlobalWaiting({label: 'Seite wird aktualisiert', detail: 'Die eingebettete Seite wird neu geladen.'});
    iframeRef.current?.contentWindow?.location.reload();
  }

  async function postCommand(path, fields = {}) {
    setGlobalWaiting({label: 'Aktion wird ausgeführt', detail: 'Bitte warten, die Änderung wird verarbeitet.'});
    const formData = new FormData();
    formData.set('csrf_token', security.csrf_token || '');
    Object.entries(fields).forEach(([key, value]) => formData.set(key, value));
    const response = await fetch(path, {
      method: 'POST',
      body: formData,
      credentials: 'same-origin',
    });
    if (response.redirected) {
      window.location.href = response.url;
      return;
    }
    window.location.href = fields.next || '/v2/';
  }

  const commands = useMemo(() => buildCommandItems(user), [user.role]);
  const commandById = useMemo(() => new Map(commands.map((item) => [item.id, item])), [commands]);
  const commandSource = useMemo(
    () => createStaticSource(commands, {
      keywords: (item) => item.auxiliaryData?.keywords || [],
    }),
    [commands],
  );

  function handleCommand(value) {
    const command = commandById.get(value);
    if (!command) return;
    setIsCommandOpen(false);
    const action = command.auxiliaryData?.action || {};
    if (action.type === 'post') {
      postCommand(action.path, action.fields);
      return;
    }
    if (action.type === 'reload') {
      reloadContent();
      return;
    }
    if (action.href) {
      setGlobalWaiting({label: 'Seite wird geöffnet', detail: 'Die gewünschte Ansicht wird geladen.'});
      window.location.href = action.href;
    }
  }

  function showWaiting(label = 'Bitte warten', detail = 'Die Aktion wird verarbeitet.') {
    setGlobalWaiting({label, detail});
  }

  function handleShellSubmit(event) {
    if (event.defaultPrevented) return;
    const form = event.target;
    if (!(form instanceof HTMLFormElement)) return;
    const submitter = event.nativeEvent?.submitter;
    const label = submitter?.textContent?.trim() || 'Aktion wird ausgeführt';
    window.setTimeout(() => {
      if (!event.defaultPrevented) {
        showWaiting(label, 'Bitte warten, die Anfrage wird verarbeitet.');
      }
    }, 0);
  }

  function handleShellClick(event) {
    const link = event.target.closest?.('a[href]');
    if (!link || event.defaultPrevented) return;
    if (link.target === '_blank' || link.hasAttribute('download')) return;
    if (event.metaKey || event.ctrlKey || event.shiftKey || event.altKey) return;
    const href = link.getAttribute('href') || '';
    if (!href || href.startsWith('#') || href.startsWith('mailto:') || href.startsWith('tel:')) return;
    const nextUrl = new URL(href, window.location.href);
    if (nextUrl.origin !== window.location.origin) return;
    showWaiting('Seite wird geladen', 'Bitte warten, die Ansicht wird geöffnet.');
  }

  const nativeContent = nativeData?.type === 'dashboard'
    ? <NativeDashboard data={nativeData} />
    : nativeData?.type === 'import'
      ? <NativeImport data={nativeData} csrfToken={security.csrf_token} />
    : nativeData?.type === 'prices'
      ? <NativePrices data={nativeData} csrfToken={security.csrf_token} />
    : nativeData?.type === 'price_edit'
      ? <NativePriceEdit data={nativeData} csrfToken={security.csrf_token} />
    : nativeData?.type === 'invoices'
      ? <NativeInvoices data={nativeData} />
    : nativeData?.type === 'invoice_new'
      ? <NativeInvoiceNew data={nativeData} csrfToken={security.csrf_token} />
    : nativeData?.type === 'invoice_detail'
      ? <NativeInvoiceDetail data={nativeData} csrfToken={security.csrf_token} />
    : nativeData?.type === 'payments'
      ? <NativePayments data={nativeData} csrfToken={security.csrf_token} />
    : nativeData?.type === 'cashbook'
      ? <NativeCashbook data={nativeData} csrfToken={security.csrf_token} />
    : nativeData?.type === 'member_accounts'
      ? <NativeMemberAccounts data={nativeData} />
    : nativeData?.type === 'newsletter'
      ? <NativeNewsletter data={nativeData} csrfToken={security.csrf_token} user={user} />
    : nativeData?.type === 'newsletter_form'
      ? <NativeNewsletterForm data={nativeData} csrfToken={security.csrf_token} />
    : nativeData?.type === 'newsletter_preview'
      ? <NativeNewsletterPreview data={nativeData} />
    : nativeData?.type === 'reports'
      ? <NativeReports data={nativeData} />
    : nativeData?.type === 'users'
      ? <NativeUsers data={nativeData} csrfToken={security.csrf_token} />
    : nativeData?.type === 'audit'
      ? <NativeAudit data={nativeData} />
    : nativeData?.type === 'backup'
      ? <NativeBackup data={nativeData} csrfToken={security.csrf_token} />
    : nativeData?.type === 'members'
      ? <NativeMembers data={nativeData} />
    : nativeData?.type === 'member_form'
      ? <NativeMemberForm data={nativeData} csrfToken={security.csrf_token} />
    : nativeData?.type === 'settings'
      ? <NativeSettings data={nativeData} csrfToken={security.csrf_token} />
    : nativeData?.type === 'database'
      ? <NativeDatabase data={nativeData} csrfToken={security.csrf_token} />
    : nativeData?.type === 'release_notes'
      ? <ReleaseNotesPage data={nativeData} />
    : nativeData?.type === 'portal_dashboard'
      ? <NativePortalDashboard data={nativeData} />
    : nativeData?.type === 'portal_data'
      ? <NativePortalData data={nativeData} csrfToken={security.csrf_token} />
    : nativeData?.type === 'portal_invoices'
      ? <NativePortalInvoices data={nativeData} csrfToken={security.csrf_token} />
    : nativeData?.type === 'portal_contracts'
      ? <NativePortalContracts data={nativeData} />
    : nativeData?.type === 'change_password'
      ? <NativeChangePassword csrfToken={security.csrf_token} user={user} />
      : null;

  const navSections = <V2SideNavSections navItems={navItems} currentPath={currentPath} />;
  const mobileNavSections = <V2SideNavSections navItems={navItems} currentPath={currentPath} />;
  const sideNav = (
    <SideNav
      className="v2-astryx-sidenav"
      collapsible={{
        isCollapsed,
        onCollapsedChange: setIsCollapsed,
        buttonLabel: isCollapsed ? 'Menü ausklappen' : 'Menü einklappen',
      }}
      resizable={{defaultWidth: 280, minWidth: 220, maxWidth: 420, autoSaveId: 'eeg-v2-sidebar-width'}}
      footer={
        <div className="v2-sidebar-footer">
          <span>{org.zvr || org.legal || 'ZVR bitte konfigurieren'}</span>
          <span>{org.name || 'EEG Bezeichnung bitte konfigurieren'}</span>
        </div>
      }
    >
      {navSections}
    </SideNav>
  );
  const mobileNavContent = (
    <MobileNav
      className="v2-mobile-nav"
      width={340}
      side="start"
      label="V2 Navigation"
      header={
        <div className="v2-mobile-nav-header">
          <div>
            <strong>{org.name || 'EEG'}</strong>
            <span>Version 2</span>
          </div>
        </div>
      }
    >
      <div className="v2-mobile-nav-body">
        {mobileNavSections}
        <div className="v2-mobile-nav-actions" aria-label="Mobile Schnellaktionen">
          <button type="button" onClick={() => setIsCommandOpen(true)}>
            <Command size={17} />
            <span>Befehle</span>
          </button>
          <button type="button" onClick={reloadContent}>
            <RefreshCw size={17} />
            <span>Aktualisieren</span>
          </button>
          <a href={currentPath}>
            <ExternalLink size={17} />
            <span>Klassische UI</span>
          </a>
          <a href="/logout">
            <LogOut size={17} />
            <span>Abmelden</span>
          </a>
        </div>
        <div className="v2-mobile-nav-footer">
          <span>{org.zvr || org.legal || 'ZVR bitte konfigurieren'}</span>
          <span>{org.name || 'EEG Bezeichnung bitte konfigurieren'}</span>
        </div>
      </div>
    </MobileNav>
  );

  const topNav = (
    <TopNav
      className="v2-topbar"
      label="EEG V2 Navigation"
      heading={
        <a className="v2-top-heading" href={v2Href(activeItem?.path || '/')} aria-label={`${activeItem?.label || 'Arbeitsbereich'} öffnen`}>
          <span className="v2-top-logo-frame">
            <img className="v2-top-logo" src="/static/logo.png" alt="" />
          </span>
          <span className="v2-top-copy">
            <strong>{org.name || 'EEG Verwaltung'}</strong>
            <span>{activeItem?.label || 'Arbeitsbereich'} · V2</span>
          </span>
        </a>
      }
      endContent={
        <div className="topbar-actions" aria-label="Schnellaktionen">
          <span className="v2-top-user" title={user.username || 'Benutzer'}>
            <UserCog size={16} aria-hidden="true" />
            <span>{user.username || 'Benutzer'}</span>
          </span>
          <button type="button" className="v2-top-action is-primary" onClick={() => setIsCommandOpen(true)}>
            <Command size={16} aria-hidden="true" />
            <span>Befehle</span>
          </button>
          <button type="button" className="v2-top-action is-icon topbar-action-secondary" onClick={reloadContent} aria-label="Aktualisieren" title="Aktualisieren">
            <RefreshCw size={17} aria-hidden="true" />
          </button>
          <a className="v2-top-action is-icon topbar-action-secondary" href={currentPath} aria-label="Klassische UI öffnen" title="Klassische UI">
            <ExternalLink size={17} aria-hidden="true" />
          </a>
          <a className="v2-top-action is-icon topbar-action-secondary" href="/logout" aria-label="Abmelden" title="Abmelden">
            <LogOut size={17} aria-hidden="true" />
          </a>
        </div>
      }
    />
  );

  return (
    <AppShell
      className={`v2-shell ${isCollapsed ? 'is-collapsed' : ''}`}
      variant="section"
      height={nativeContent ? 'auto' : 'fill'}
      contentPadding={0}
      sideNav={sideNav}
      topNav={topNav}
      mobileNav={{breakpoint: 'lg', content: mobileNavContent}}
    >
      <div
        id="content"
        className={`v2-main ${nativeContent ? 'is-native' : ''}`}
        onSubmit={handleShellSubmit}
        onClick={handleShellClick}
      >
        <FlashMessages messages={messages.filter((message) => ['warning', 'error'].includes(flashStatus(message.category)))} />
        <CommandPalette
          isOpen={isCommandOpen}
          onOpenChange={setIsCommandOpen}
          searchSource={commandSource}
          onValueChange={handleCommand}
          label="EEG Befehle"
          width={720}
          maxHeight={560}
          input={<CommandPaletteInput placeholder="Befehl suchen, z.B. Mitglied, Import, Backup..." />}
          emptyBootstrapText={<CommandPaletteEmpty>Tippe, um Befehle zu suchen.</CommandPaletteEmpty>}
          emptySearchText={<CommandPaletteEmpty>Kein passender Befehl gefunden.</CommandPaletteEmpty>}
          renderItem={(item) => <CommandPaletteRow item={item} />}
        />

        {nativeContent || (
          <Card className={`v2-frame-card ${isLoading ? 'is-loading' : 'is-ready'}`} padding={0}>
            {isLoading && <LoadingOverlay label="Seite wird geladen" detail="Bitte warten, die Inhalte werden vorbereitet." isInline />}
            <iframe
              ref={iframeRef}
              title="EEG V2 Inhalt"
              src={contentPath}
              className="v2-content-frame"
              onLoad={syncAddressFromFrame}
            />
          </Card>
        )}

        {pdfPreview && (
          <div className="v2-pdf-preview" role="dialog" aria-modal="true" aria-label={pdfPreview.title}>
            <div className="v2-pdf-panel">
              <div className="v2-pdf-header">
                <div>
                  <span className="v2-pdf-kicker"><FileText size={16} /> PDF</span>
                  <strong>{pdfPreview.title}</strong>
                </div>
                <div className="v2-pdf-actions">
                  <Button label="Download" icon={<Download size={16} />} href={pdfPreview.downloadUrl} target="_blank" rel="noopener" />
                  <button type="button" className="v2-pdf-close" aria-label="PDF Vorschau schließen" onClick={() => setPdfPreview(null)}>
                    <X size={18} />
                  </button>
                </div>
              </div>
              <iframe title={pdfPreview.title} src={pdfPreview.url} className="v2-pdf-frame" />
            </div>
          </div>
        )}
        {globalWaiting && <LoadingOverlay label={globalWaiting.label} detail={globalWaiting.detail} onCancel={() => setGlobalWaiting(null)} />}
      </div>
    </AppShell>
  );
}

function V2SideNavSections({navItems, currentPath}) {
  const sections = [];
  let currentSection = {title: 'Hauptnavigation', items: [], isHeaderHidden: true};
  navItems.forEach((item) => {
    if (item.type === 'section') {
      if (currentSection.items.length) sections.push(currentSection);
      currentSection = {title: item.label, items: [], isHeaderHidden: false};
      return;
    }
    currentSection.items.push(item);
  });
  if (currentSection.items.length) sections.push(currentSection);

  return sections.map((section) => (
    <SideNavSection key={section.title} title={section.title} isHeaderHidden={section.isHeaderHidden}>
      {section.items.map((item) => {
        const Icon = item.icon;
        return (
          <SideNavItem
            key={item.path}
            label={item.label}
            href={v2Href(item.path)}
            icon={<Icon size={19} strokeWidth={2.1} />}
            isSelected={isActivePath(currentPath, item.path)}
          />
        );
      })}
    </SideNavSection>
  ));
}

function buildCommandItems(user) {
  const isAdmin = user.role === 'admin';
  const base = isAdmin ? [
    commandItem('nav-dashboard', 'Dashboard öffnen', 'Navigation', LayoutDashboard, '/v2/', 'Übersicht, Startseite, Home', 'Zur Übersicht wechseln'),
    commandItem('nav-import', 'Import öffnen', 'Navigation', Upload, '/v2/import', 'Messwerte, EDA, Excel, Daten importieren', 'Messwertdateien hochladen'),
    commandItem('nav-members', 'Mitglied suchen', 'Navigation', Users, '/v2/members', 'Mitglieder, Teilnehmer, suchen, bearbeiten', 'Mitgliederliste öffnen'),
    commandItem('nav-prices', 'Preise öffnen', 'Navigation', Euro, '/v2/prices', 'Tarife, Preis, kWh', 'Preishistorie und neue Preise'),
    commandItem('nav-invoices', 'Abrechnungen öffnen', 'Navigation', ReceiptText, '/v2/invoices', 'Rechnungen, Quartal, Abrechnung', 'Alle Abrechnungen anzeigen'),
    commandItem('nav-payments', 'Überweisungen öffnen', 'Navigation', Banknote, '/v2/payments', 'Zahlungen, Buchungen, Rückstand', 'Offene Forderungen und Gutschriften'),
    commandItem('nav-reports', 'Reports öffnen', 'Navigation', ChartNoAxesCombined, '/v2/reports', 'Auswertung, Bericht, Verbrauch, Erzeugung', 'Energieberichte öffnen'),
    commandItem('nav-newsletter', 'Newsletter öffnen', 'Navigation', Mail, '/v2/newsletter', 'Mailing, Rundschreiben, Empfänger', 'Newsletter verwalten'),
    commandItem('action-new-member', 'Neues Mitglied anlegen', 'Aktionen', Plus, '/v2/members/new', 'Teilnehmer erstellen, Mitglied hinzufügen', 'Neue Mitgliedsmaske öffnen'),
    commandItem('action-new-invoice', 'Neue Abrechnung erstellen', 'Aktionen', ReceiptText, '/v2/invoices/new', 'Abrechnung, Rechnung, Quartal', 'Abrechnungsassistent öffnen'),
    commandItem('action-new-newsletter', 'Newsletter-Entwurf anlegen', 'Aktionen', Mail, '/v2/newsletter', 'Neuer Newsletter, Entwurf', 'Newsletter-Seite mit Entwurfsformular öffnen'),
    commandItem('action-backup-run', 'Backup jetzt erstellen', 'Aktionen', Archive, null, 'Sicherung, Backup, manuell, zip', 'Lokales Backup sofort starten', {
      type: 'post',
      path: '/admin/backup/run',
      fields: {next: '/v2/admin/backup'},
    }),
    commandItem('nav-users', 'Benutzerverwaltung öffnen', 'Verwaltung', UserCog, '/v2/admin/users', 'User, Einladung, Rollen', 'Benutzer und Verträge'),
    commandItem('nav-audit', 'Audit-Log öffnen', 'Verwaltung', NotebookText, '/v2/admin/audit', 'Protokoll, Log, Sicherheit', 'Aktivitäten prüfen'),
    commandItem('nav-backup', 'Backup-Seite öffnen', 'Verwaltung', Archive, '/v2/admin/backup', 'Backup, Restore, Google Drive', 'Backup und Wiederherstellung'),
    commandItem('nav-database', 'Datenbankwartung öffnen', 'Verwaltung', Database, '/v2/admin/database', 'Wartung, Qualität, Defragmentierung', 'Datenbank prüfen und optimieren'),
    commandItem('nav-settings', 'Einstellungen öffnen', 'Verwaltung', Settings, '/v2/settings', 'SMTP, Verein, Konto, Organisation', 'Systemeinstellungen öffnen'),
  ] : [
    commandItem('portal-dashboard', 'Meine Übersicht öffnen', 'Navigation', LayoutDashboard, '/v2/portal', 'Portal, Startseite', 'Persönliche Übersicht'),
    commandItem('portal-data', 'Meine Daten öffnen', 'Navigation', UserCog, '/v2/portal/data', 'Stammdaten, Adresse, Newsletter', 'Eigene Stammdaten'),
    commandItem('portal-invoices', 'Meine Abrechnungen öffnen', 'Navigation', ReceiptText, '/v2/portal/invoices', 'Rechnungen, Konto, Historie', 'Eigene Abrechnungen'),
    commandItem('portal-reports', 'Meine Reports öffnen', 'Navigation', ChartNoAxesCombined, '/v2/portal/reports', 'Berichte, Verbrauch', 'Persönliche Auswertung'),
    commandItem('portal-contracts', 'Meine Verträge öffnen', 'Navigation', BookOpenText, '/v2/portal/contracts', 'Verträge, PDF', 'Vertragsunterlagen'),
  ];
  return [
    ...base,
    commandItem('action-refresh', 'Aktuelle Seite neu laden', 'Sitzung', RefreshCw, null, 'Reload, aktualisieren', 'Aktuelle V2-Ansicht aktualisieren', {type: 'reload'}),
    commandItem('action-logout', 'Abmelden', 'Sitzung', LogOut, '/logout', 'Logout, Sitzung beenden', 'Von der Webapp abmelden'),
  ];
}

function commandItem(id, label, group, icon, href, keywords, description, actionOverride) {
  return {
    id,
    label,
    auxiliaryData: {
      group,
      icon,
      description,
      keywords: String(keywords || '').split(',').map((keyword) => keyword.trim()).filter(Boolean),
      action: actionOverride || {href},
    },
  };
}

function CommandPaletteRow({item}) {
  const Icon = item.auxiliaryData?.icon || Command;
  const group = item.auxiliaryData?.group || 'Befehl';
  const description = item.auxiliaryData?.description || '';
  return (
    <div className="v2-command-row">
      <span className="v2-command-icon"><Icon size={18} /></span>
      <span className="v2-command-copy">
        <strong>{item.label}</strong>
        {description && <small>{description}</small>}
      </span>
      <span className="v2-command-group">{group}</span>
    </div>
  );
}

function NativeDashboard({data}) {
  const stats = data.stats || {};
  const maxKwh = Math.max(...(data.monthly || []).map((row) => Number(row.kwh) || 0), 1);

  return (
    <div className="v2-native-page v2-dashboard-page">
      <div className="v2-page-heading">
        <div className="v2-page-title">
          <LayoutDashboard size={34} strokeWidth={1.8} />
          <h2>Dashboard</h2>
        </div>
        <a className="v2-primary-action" href="/v2/import">
          <Plus size={22} />
          <span>Daten importieren</span>
        </a>
      </div>

      <section className="v2-dashboard-stats" aria-label="Dashboard Kennzahlen">
        <DashboardStat icon={Users} label="Aktive Mitglieder" value={formatNumber(stats.members)} />
        <DashboardStat icon={Activity} label="Messwerte" value={formatNumber(stats.measurements)} />
        <DashboardStat icon={Upload} label="Importe" value={formatNumber(stats.batches)} />
        <DashboardStat icon={ReceiptText} label="Abrechnungen" value={formatNumber(stats.invoices)} />
      </section>

      <section className="v2-dashboard-grid">
        <Card className="v2-native-card v2-dashboard-card" padding={0}>
          <div className="v2-dashboard-card-title">
            <Upload size={24} />
            <h3>Letzte Messdaten</h3>
          </div>
          <div className="v2-table-wrap">
            <table className="v2-native-table v2-dashboard-table">
              <thead>
                <tr>
                  <th>Datei</th>
                  <th>Zeitraum</th>
                  <th>Status</th>
                  <th>Aktion</th>
                </tr>
              </thead>
              <tbody>
                {(data.imports || []).length ? data.imports.map((row, index) => (
                  <tr key={`${row.imported_at}-${index}`}>
                    <td><strong>{row.source_file || 'Importdatei'}</strong></td>
                    <td>{formatDateRange(row.period_start, row.period_end)}</td>
                    <td><StatusPill value={row.data_status} /></td>
                    <td className="v2-table-action">
                      <a className="v2-icon-action" href="/v2/import" aria-label="Import öffnen" title="Öffnen">
                        <ExternalLink size={18} />
                      </a>
                    </td>
                  </tr>
                )) : (
                  <tr><td colSpan="4"><EmptyState text="Noch keine Importdaten vorhanden." /></td></tr>
                )}
              </tbody>
            </table>
          </div>
        </Card>

        <Card className="v2-native-card v2-dashboard-card" padding={0}>
          <div className="v2-dashboard-card-title">
            <ReceiptText size={24} />
            <h3>Aktuelle Abrechnungen</h3>
          </div>
          <div className="v2-table-wrap">
            <table className="v2-native-table v2-dashboard-table">
              <thead>
                <tr>
                  <th>Zeitraum</th>
                  <th>Status</th>
                  <th>Daten</th>
                  <th>Aktion</th>
                </tr>
              </thead>
              <tbody>
                {(data.invoices || []).length ? data.invoices.map((row) => (
                  <tr key={row.id}>
                    <td><strong>{formatDateRange(row.period_from, row.period_to)}</strong></td>
                    <td>{invoiceStatusLabel(row.status)}</td>
                    <td><StatusPill value={row.data_status || row.status} /></td>
                    <td className="v2-table-action">
                      <a className="v2-icon-action" href={`/v2/invoices/${row.id}`} aria-label="Abrechnung öffnen" title="Öffnen">
                        <ExternalLink size={18} />
                      </a>
                    </td>
                  </tr>
                )) : (
                  <tr><td colSpan="4"><EmptyState text="Noch keine Abrechnungen vorhanden." /></td></tr>
                )}
              </tbody>
            </table>
          </div>
        </Card>
      </section>

      <Card className="v2-native-card v2-dashboard-card" padding={0}>
        <div className="v2-dashboard-card-title">
          <ChartNoAxesCombined size={24} />
          <h3>Verbrauch in der EEG</h3>
          <a className="v2-dashboard-title-action" href="/v2/reports">Reports öffnen</a>
        </div>
        <div className="v2-dashboard-bars">
          {(data.monthly || []).length ? data.monthly.map((row) => {
            const value = Number(row.kwh) || 0;
            return (
              <div className="v2-dashboard-bar-row" key={row.period_start}>
                <span>{formatMonth(row.period_start)}</span>
                <div className="v2-bar-track"><div style={{width: `${Math.max((value / maxKwh) * 100, 3)}%`}} /></div>
                <strong>{formatNumber(value, 1)} kWh</strong>
              </div>
            );
          }) : <EmptyState text="Noch keine Monatswerte vorhanden." />}
        </div>
      </Card>
    </div>
  );
}

function FlashMessages({messages}) {
  if (!messages.length) return null;
  return (
    <div className="v2-flashes" role="status" aria-live="polite">
      {messages.map((message, index) => (
        <Banner
          key={`${message.category}-${index}`}
          status={flashStatus(message.category)}
          title={message.text}
          container="section"
          isDismissable={flashStatus(message.category) !== 'error'}
        />
      ))}
    </div>
  );
}

function flashStatus(category) {
  const normalized = String(category || 'info').toLowerCase();
  if (normalized === 'danger' || normalized === 'error') return 'error';
  if (normalized === 'warning') return 'warning';
  if (normalized === 'success') return 'success';
  return 'info';
}

function StatusBannerStack({children}) {
  const items = React.Children.toArray(children).filter(Boolean);
  if (!items.length) return null;
  return <div className="v2-status-banners">{items}</div>;
}

function StatusLine({variant = 'neutral', label, children, isPulsing = false}) {
  return (
    <span className="v2-status-line">
      <StatusDot variant={variant} label={label} isPulsing={isPulsing} />
      <span>{children || label}</span>
    </span>
  );
}

function ProcessingStatus({label, description, variant = 'accent'}) {
  return (
    <div className="v2-processing-status" role="status" aria-live="polite">
      <StatusLine variant={variant} label={label} isPulsing>{label}</StatusLine>
      {description && <p>{description}</p>}
      <ProgressBar label={label} isIndeterminate variant={variant} isLabelHidden />
    </div>
  );
}

function LoadingOverlay({label = 'Bitte warten', detail = '', isInline = false}) {
  return (
    <div className={isInline ? 'v2-loading is-inline' : 'v2-global-loading'} role="status" aria-live="polite" aria-busy="true">
      <div className="v2-loading-card">
        <div className="v2-loading-mark" aria-hidden="true">
          <span />
          <span />
          <span />
        </div>
        <strong>{label}</strong>
        {detail && <p>{detail}</p>}
      </div>
    </div>
  );
}

function ImportResultProgress({results}) {
  if (!results.length) return null;
  const successCount = results.filter((row) => String(row.status || '').toLowerCase() === 'success').length;
  const value = Math.round((successCount / results.length) * 100);
  const hasErrors = successCount !== results.length;
  return (
    <div className="v2-result-progress">
      <div className="v2-result-progress-copy">
        <StatusLine variant={hasErrors ? 'error' : 'success'} label={hasErrors ? 'Import mit Fehlern' : 'Import erfolgreich'}>
          {successCount} von {results.length} Datei{results.length === 1 ? '' : 'en'} erfolgreich verarbeitet
        </StatusLine>
      </div>
      <ProgressBar
        label="Import-Ergebnis"
        value={value}
        max={100}
        hasValueLabel
        variant={hasErrors ? 'error' : 'success'}
      />
    </div>
  );
}

function FormTextInput({name, defaultValue = '', type = 'text', ...props}) {
  const [value, setValue] = useState(String(defaultValue ?? ''));
  return (
    <TextInput
      {...props}
      type={type}
      value={value}
      onChange={setValue}
      htmlName={name}
      width="100%"
    />
  );
}

function FormTextArea({name, defaultValue = '', ...props}) {
  const [value, setValue] = useState(String(defaultValue ?? ''));
  const handleChange = (nextValue) => {
    setValue(nextValue);
    props.onChange?.(nextValue);
  };
  return (
    <TextArea
      {...props}
      value={value}
      onChange={handleChange}
      htmlName={name}
      width="100%"
    />
  );
}

function FormNumberInput({name, defaultValue = null, ...props}) {
  const initial = defaultValue === '' || defaultValue == null ? null : Number(defaultValue);
  const [value, setValue] = useState(Number.isFinite(initial) ? initial : null);
  return (
    <NumberInput
      {...props}
      value={value}
      onChange={setValue}
      htmlName={name}
      width="100%"
    />
  );
}

function FormDateInput({name, defaultValue = '', ...props}) {
  const [value, setValue] = useState(defaultValue || undefined);
  return (
    <>
      <DateInput
        {...props}
        value={value}
        onChange={setValue}
        width="100%"
      />
      <input type="hidden" name={name} value={value || ''} />
    </>
  );
}

function FormSelector({name, defaultValue = '', options, ...props}) {
  const [value, setValue] = useState(String(defaultValue ?? ''));
  return (
    <>
      <Selector
        {...props}
        options={options}
        value={value}
        onChange={(next) => setValue(next || '')}
        width="100%"
      />
      <input type="hidden" name={name} value={value} />
    </>
  );
}

function FormSwitch({name, submitValue = '1', defaultChecked = false, ...props}) {
  const [checked, setChecked] = useState(Boolean(defaultChecked));
  return (
    <>
      <Switch
        {...props}
        value={checked}
        onChange={setChecked}
        labelSpacing="spread"
      />
      {checked && <input type="hidden" name={name} value={submitValue} />}
    </>
  );
}

function FormFileInput({name, onFilesChange, isMultiple = false, ...props}) {
  const [value, setValue] = useState(isMultiple ? [] : null);
  function handleChange(nextValue) {
    const normalized = nextValue || (isMultiple ? [] : null);
    setValue(normalized);
    onFilesChange?.(normalized);
  }
  return (
    <FileInput
      {...props}
      name={name}
      value={value}
      onChange={handleChange}
      isMultiple={isMultiple}
      width="100%"
    />
  );
}

function FormChoiceCards({name, label, description, options, defaultValue}) {
  const inputID = useId();
  const labelID = useId();
  const [value, setValue] = useState(defaultValue || options[0]?.value || '');
  return (
    <Field label={label} description={description} inputID={inputID} labelID={labelID} isGroupLabel width="100%">
      <div className="v2-choice-card-group" role="radiogroup" aria-labelledby={labelID}>
        {options.map((option) => (
          <label key={option.value} className={`v2-choice-card ${value === option.value ? 'is-selected' : ''}`}>
            <input
              id={`${inputID}-${option.value}`}
              type="radio"
              name={name}
              value={option.value}
              checked={value === option.value}
              onChange={() => setValue(option.value)}
            />
            <span className={`v2-status-choice ${option.tone || ''}`}>{option.label}</span>
          </label>
        ))}
      </div>
    </Field>
  );
}

async function submitMultipartFormWithFiles(event, fileFields) {
  event.preventDefault();
  const form = event.currentTarget;
  const formData = new FormData(form);
  for (const field of fileFields) {
    const files = Array.isArray(field.files)
      ? field.files
      : field.files
        ? [field.files]
        : [];
    if (!files.length) {
      window.alert(field.requiredMessage || 'Bitte zuerst eine Datei auswählen.');
      return;
    }
    formData.delete(field.name);
    files.forEach((file) => formData.append(field.name, file, file.name));
  }
  window.dispatchEvent(new CustomEvent('eeg-v2-waiting', {
    detail: {label: 'Dateien werden verarbeitet', detail: 'Bitte warten, Upload und Verarbeitung laufen.'},
  }));
  try {
    const response = await fetch(form.action, {
      method: form.method || 'POST',
      body: formData,
      credentials: 'same-origin',
    });
    const html = await response.text();
    document.open();
    document.write(html);
    document.close();
  } catch (error) {
    window.dispatchEvent(new CustomEvent('eeg-v2-waiting-clear'));
    throw error;
  }
}

function NativeImport({data, csrfToken}) {
  const [importFiles, setImportFiles] = useState([]);
  const [isImporting, setIsImporting] = useState(false);
  const results = data.results || [];
  const previews = data.previews || [];
  const previewErrors = data.preview_errors || [];
  const imports = data.imports || [];
  const activeImports = imports.filter((row) => !row.replaced_at);
  const provisionalCount = activeImports.filter((row) => row.data_status !== 'final').length;
  const finalCount = activeImports.filter((row) => row.data_status === 'final').length;
  return (
    <div className="v2-native-page v2-import-page">
      <div className="v2-page-heading">
        <div className="v2-page-title">
          <Upload size={34} strokeWidth={1.8} />
          <h2>Daten-Import</h2>
        </div>
      </div>

      <StatusBannerStack>
        {isImporting && (
          <Banner
            status="info"
            title="Datei wird geprüft"
            description="Die Datei wird nur validiert. Messdaten werden in diesem Schritt nicht verändert."
            container="section"
          >
            <ProcessingStatus label="Prüfung läuft" description="Struktur, Zeitraum, Vollständigkeit und Integrität werden geprüft." />
          </Banner>
        )}
        <Banner
          status={provisionalCount ? 'warning' : 'success'}
          title={provisionalCount ? 'Vorläufige Messdaten vorhanden' : 'Importstatus in Ordnung'}
          description={provisionalCount
            ? `${formatNumber(provisionalCount)} aktive Importdatei${provisionalCount === 1 ? '' : 'en'} ist/sind vorläufig. Abrechnungen daraus bleiben eine Vorschau und dürfen nicht final versendet werden.`
            : `${formatNumber(finalCount)} aktive Importdatei${finalCount === 1 ? '' : 'en'} ist/sind final oder es sind noch keine aktiven Importdateien vorhanden.`}
          container="section"
          isDismissable={!provisionalCount}
        />
      </StatusBannerStack>

      <Card className="v2-native-card v2-import-card" padding={0}>
        <div className="v2-dashboard-card-title">
          <Upload size={24} />
          <h3>EDA Excel-Dateien hochladen</h3>
        </div>
        <form
          className="v2-import-form"
          method="post"
          encType="multipart/form-data"
          action="/v2/import"
          onSubmit={(event) => {
            if (Array.isArray(importFiles) ? importFiles.length : Boolean(importFiles)) {
              setIsImporting(true);
            }
            submitMultipartFormWithFiles(event, [{name: 'files', files: importFiles, requiredMessage: 'Bitte mindestens eine Excel-Datei auswählen.'}])
              .catch(() => setIsImporting(false));
          }}
        >
          <input type="hidden" name="csrf_token" value={csrfToken || ''} />
          <input type="hidden" name="import_action" value="preview" />
          <FormFileInput
            name="files"
            label="Excel-Dateien"
            description="EDA Energiedatenreport-Dateien im Format RC*_YYYY-MM-DDThh_mm-*.xlsx"
            accept=".xlsx"
            isMultiple
            isRequired
            mode="dropzone"
            placeholder="Dateien auswählen oder hier ablegen"
            onFilesChange={setImportFiles}
          />

          <FormChoiceCards
            name="data_status"
            label="Datenstatus"
            description="Vorläufige Daten dienen der Vorschau, finale Daten erlauben den Abschluss."
            defaultValue="provisional"
            options={[
              {value: 'provisional', label: 'Vorläufig', tone: 'is-provisional'},
              {value: 'final', label: 'Final', tone: 'is-final'},
            ]}
          />

          <FormSwitch
            name="overwrite"
            label="Bestehende Daten überschreiben"
            description="Bei Überschneidung werden vorhandene Werte im Zeitraum ersetzt."
          />

          <button type="submit" className="v2-primary-action v2-submit-action">
            <Upload size={20} />
            <span>Datei prüfen und Vorschau anzeigen</span>
          </button>
          <small>In diesem Schritt werden noch keine Messdaten verändert.</small>
        </form>
      </Card>

      {previewErrors.length > 0 && (
        <Banner
          status="error"
          title="Vorschau konnte nicht erstellt werden"
          description={previewErrors.map((item) => `${item.filename}: ${item.error}`).join(' · ')}
          container="section"
        />
      )}

      {previews.map((item, index) => {
        const preview = item.preview || {};
        const warnings = preview.warnings || [];
        return (
          <Card className="v2-native-card v2-import-card" padding={0} key={`${item.filename}-${index}`}>
            <div className="v2-dashboard-card-title">
              <CircleCheck size={24} />
              <h3>Importvorschau – noch nicht importiert</h3>
            </div>
            <div className="v2-import-form v2-import-preview">
              <StatusLine variant={item.has_blocking_errors ? 'error' : 'success'} label={item.filename}>
                Datenbank unverändert · Vorschau gültig bis {formatDateTime(item.expires_at)}
              </StatusLine>
              <div className="v2-summary-grid">
                <div><small>Datenzeitraum</small><strong>{formatDateTime(preview.data_available_from)} – {formatDateTime(preview.data_available_until)}</strong></div>
                <div><small>Zählpunkte</small><strong>{formatNumber(preview.metering_point_count)}</strong></div>
                <div><small>Messreihen</small><strong>{formatNumber(preview.series_count)}</strong></div>
                <div><small>Messwerte</small><strong>{formatNumber(preview.measurement_count)}</strong></div>
              </div>
              <p>
                <StatusPill value={item.data_status} /> · SHA-256 {String(preview.sha256 || '').slice(0, 16)}… · {formatNumber(preview.size_bytes)} Byte
                {item.overwrite ? ' · Überschreiben aktiviert' : ''}
              </p>
              {warnings.length ? (
                <ul>
                  {warnings.map((warning, warningIndex) => (
                    <li className={warning.severity === 'error' ? 'v2-error-text' : ''} key={`${warning.code}-${warningIndex}`}>
                      {warning.message}
                    </li>
                  ))}
                </ul>
              ) : <StatusLine variant="success" label="Keine strukturellen Warnungen erkannt" />}

              {!item.has_blocking_errors && (
                <form method="post" action="/v2/import">
                  <input type="hidden" name="csrf_token" value={csrfToken || ''} />
                  <input type="hidden" name="import_action" value="confirm" />
                  <input type="hidden" name="preview_token" value={item.token || ''} />
                  <label className="v2-checkbox-row">
                    <input type="checkbox" name="confirm_import" value="1" required />
                    <span>Ich habe Zeitraum, Datenstatus und Warnungen geprüft und bestätige den Import.</span>
                  </label>
                  <button type="submit" className="v2-primary-action v2-submit-action">
                    <CircleCheck size={20} />
                    <span>Jetzt verbindlich importieren</span>
                  </button>
                </form>
              )}
              {item.has_blocking_errors && <StatusLine variant="error" label="Import wegen blockierender Fehler gesperrt" />}
              <form method="post" action="/v2/import">
                <input type="hidden" name="csrf_token" value={csrfToken || ''} />
                <input type="hidden" name="import_action" value="cancel" />
                <input type="hidden" name="preview_token" value={item.token || ''} />
                <button type="submit" className="v2-action-button">Vorschau verwerfen</button>
              </form>
            </div>
          </Card>
        );
      })}

      <ImportResultProgress results={results} />

      {results.length > 0 && (
        <ImportTable
          title="Import-Ergebnis"
          icon={CircleCheck}
          columns={['Datei', 'Datenstatus', 'Importierte Werte', 'Überschrieben', 'Status', 'Importiert am']}
          rows={results}
          renderRow={(row, index) => (
            <tr key={`${row.filename}-${index}`}>
              <td><strong>{row.filename || 'Datei'}</strong></td>
              <td><StatusPill value={row.data_status} /></td>
              <td className="v2-number-cell">{formatNumber(row.records)}</td>
              <td className="v2-number-cell">{formatNumber(row.overwritten)}</td>
              <td>
                <StatusPill value={row.status} />
                {row.error && <small className="v2-error-text">{row.error}</small>}
              </td>
              <td>{formatDateTime(row.imported_at)}</td>
            </tr>
          )}
        />
      )}

      <ImportTable
        title="Importierte Werte"
        icon={NotebookText}
        columns={['Datei', 'Datenstatus', 'Importierte Werte', 'Überschrieben', 'Status', 'Importiert am', 'Von']}
        rows={data.history || []}
        emptyText="Noch keine Import-Historie vorhanden."
        renderRow={(row) => (
          <tr key={row.id}>
            <td><strong>{row.filename || 'Datei'}</strong></td>
            <td><StatusPill value={row.data_status} /></td>
            <td className="v2-number-cell">{formatNumber(row.records_imported)}</td>
            <td className="v2-number-cell">{formatNumber(row.records_overwritten)}</td>
            <td>
              <StatusPill value={row.status} />
              {row.error_message && <small className="v2-error-text">{row.error_message}</small>}
            </td>
            <td>{formatDateTime(row.imported_at)}</td>
            <td>{row.imported_by || 'system'}</td>
          </tr>
        )}
      />

      <ImportTable
        title="Vorhandene Importe"
        icon={Database}
        columns={['Datei', 'Zeitraum', 'Status', 'Importiert am']}
        rows={imports}
        emptyText="Noch keine Importdateien vorhanden."
        renderRow={(row) => (
          <tr key={row.id}>
            <td><strong>{row.source_file || 'Importdatei'}</strong></td>
            <td>{formatDateRange(row.period_start, row.period_end)}</td>
            <td><StatusPill value={row.replaced_at ? 'replaced' : row.data_status} /></td>
            <td>{formatDateTime(row.imported_at)}</td>
          </tr>
        )}
      />
    </div>
  );
}

function ImportTable({title, icon: Icon, columns, rows, renderRow, emptyText}) {
  return (
    <Card className="v2-native-card v2-import-card" padding={0}>
      <div className="v2-dashboard-card-title">
        <Icon size={24} />
        <h3>{title}</h3>
      </div>
      <div className="v2-table-wrap">
        <table className="v2-native-table v2-import-table">
          <thead>
            <tr>
              {columns.map((column) => <th key={column}>{column}</th>)}
            </tr>
          </thead>
          <tbody>
            {rows.length ? rows.map(renderRow) : (
              <tr><td colSpan={columns.length}><EmptyState text={emptyText || 'Noch keine Daten vorhanden.'} /></td></tr>
            )}
          </tbody>
        </table>
      </div>
    </Card>
  );
}

function NativePrices({data, csrfToken}) {
  const prices = data.prices || [];

  return (
    <div className="v2-native-page v2-prices-page">
      <div className="v2-page-heading">
        <div className="v2-page-title">
          <Euro size={34} strokeWidth={1.8} />
          <h2>Preise verwalten</h2>
        </div>
      </div>

      <Card className="v2-native-card v2-prices-card" padding={0}>
        <div className="v2-dashboard-card-title">
          <Plus size={24} />
          <h3>Neuen Preis anlegen</h3>
        </div>
        <form className="v2-price-form" method="post" action="/v2/prices">
          <input type="hidden" name="csrf_token" value={csrfToken || ''} />
          <FormDateInput name="valid_from" label="Gültig von" isRequired />
          <FormDateInput name="valid_to" label="Gültig bis" isRequired />
          <FormNumberInput name="price_consumption" label="Verbrauch" defaultValue={10.0} step={0.1} units="ct/kWh" isRequired />
          <FormNumberInput name="price_generation" label="Erzeugung" defaultValue={8.0} step={0.1} units="ct/kWh" isRequired />
          <FormTextInput name="description" label="Beschreibung" placeholder="z.B. Q3/2026" isOptional />
          <button type="submit" className="v2-primary-action v2-submit-action">
            <Plus size={20} />
            <span>Anlegen</span>
          </button>
        </form>
      </Card>

      <Card className="v2-native-card v2-prices-card" padding={0}>
        <div className="v2-dashboard-card-title">
          <Euro size={24} />
          <h3>Preishistorie</h3>
        </div>
        <div className="v2-table-wrap">
          <table className="v2-native-table v2-prices-table">
            <thead>
              <tr>
                <th>Zeitraum</th>
                <th>Verbrauch</th>
                <th>Erzeugung</th>
                <th>Marge</th>
                <th>Beschreibung</th>
                <th>Status</th>
                <th>Aktionen</th>
              </tr>
            </thead>
            <tbody>
              {prices.length ? prices.map((price) => {
                const margin = Number(price.price_consumption || 0) - Number(price.price_generation || 0);
                return (
                  <tr key={price.id}>
                    <td><strong>{formatDateRange(price.valid_from, price.valid_to)}</strong></td>
                    <td className="v2-number-cell">{formatNumber(price.price_consumption, 1)} ct/kWh</td>
                    <td className="v2-number-cell">{formatNumber(price.price_generation, 1)} ct/kWh</td>
                    <td className="v2-number-cell">{formatNumber(margin, 1)} ct/kWh</td>
                    <td>{price.description || '-'}</td>
                    <td>
                      {price.invoice
                        ? <span className="v2-tag is-warning">Abrechnung #{price.invoice.id}</span>
                        : <span className="v2-tag is-muted">Keine Abrechnung</span>}
                    </td>
                    <td className="v2-table-action">
                      <div className="v2-row-actions">
                        <a className="v2-icon-action" href={`/v2/prices/${price.id}/edit`} aria-label="Preis bearbeiten" title="Bearbeiten">
                          <Pencil size={18} />
                        </a>
                        <form method="post" action={`/prices/${price.id}/delete`} onSubmit={(event) => confirmPriceDelete(event, Boolean(price.invoice))}>
                          <input type="hidden" name="csrf_token" value={csrfToken || ''} />
                          <button type="submit" className="v2-icon-action is-danger" aria-label="Preis löschen" title="Löschen">
                            <Trash2 size={18} />
                          </button>
                        </form>
                      </div>
                    </td>
                  </tr>
                );
              }) : (
                <tr><td colSpan="7"><EmptyState text="Noch keine Preise angelegt." /></td></tr>
              )}
            </tbody>
          </table>
        </div>
      </Card>
    </div>
  );
}

function NativeMemberAccounts({data}) {
  const accounts = data.accounts || [];
  const summary = data.summary || {};

  return (
    <div className="v2-native-page v2-member-accounts-page">
      <div className="v2-page-heading">
        <div className="v2-page-title">
          <Landmark size={34} strokeWidth={1.8} />
          <h2>Mitgliedskonten</h2>
        </div>
        <div className="v2-page-actions">
          <a className="v2-action-button" href="/v2/payments">
            <Banknote size={18} />
            <span>Überweisungen</span>
          </a>
        </div>
      </div>

      <section className="v2-cashbook-stats" aria-label="Kontenkennzahlen">
        <DashboardStat icon={ReceiptText} label="Offene Forderungen" value={formatCurrency(summary.claims)} />
        <DashboardStat icon={Euro} label="Offene Guthaben" value={formatCurrency(Math.abs(summary.credits || 0))} />
        <DashboardStat icon={Landmark} label="Saldo gesamt" value={formatSignedCurrency(summary.balance)} />
        <DashboardStat icon={Clock3} label="Im Buchungsrückstand" value={formatCurrency(summary.overdue)} />
      </section>

      <Card className="v2-native-card" padding={0}>
        <div className="v2-dashboard-card-title">
          <Users size={24} />
          <h3>Kontosaldo je Mitglied</h3>
        </div>
        <div className="v2-table-wrap">
          <table className="v2-native-table">
            <thead>
              <tr>
                <th>Mitglied</th>
                <th>Abgerechnet</th>
                <th>Gebucht</th>
                <th>Saldo</th>
                <th>Status</th>
                <th>Letzte Buchung</th>
                <th>Konto</th>
              </tr>
            </thead>
            <tbody>
              {accounts.length ? accounts.map((account) => (
                <tr key={account.member_id}>
                  <td><strong>{account.member_name}</strong></td>
                  <td className="v2-number-cell">{formatCurrency(account.invoiced_total)}</td>
                  <td className="v2-number-cell">{formatCurrency(account.booked_total)}</td>
                  <td className={`v2-number-cell ${account.balance > 0 ? 'is-negative' : account.balance < 0 ? 'is-positive' : ''}`}>
                    {formatSignedCurrency(account.balance)}
                  </td>
                  <td>
                    {Math.abs(account.balance) < 0.005
                      ? <span className="v2-tag is-muted">ausgeglichen</span>
                      : account.balance > 0
                        ? <span className="v2-tag is-warning">Forderung</span>
                        : <span className="v2-tag">Guthaben</span>}
                    {Boolean(account.deviating_rows) && <> <span className="v2-tag is-warning">{account.deviating_rows}× Abweichung</span></>}
                    {Boolean(account.overdue) && <> <span className="v2-tag is-warning">Rückstand</span></>}
                  </td>
                  <td>{account.last_booking_date ? formatDate(account.last_booking_date) : '-'}</td>
                  <td className="v2-table-action">
                    <a className="v2-icon-action" href={`/mitgliederkonten/${account.member_id}`}
                       aria-label="Kontoauszug öffnen" title="Kontoauszug öffnen">
                      <NotebookText size={18} />
                    </a>
                  </td>
                </tr>
              )) : (
                <tr><td colSpan="7"><EmptyState text="Noch keine Abrechnungen vorhanden." /></td></tr>
              )}
            </tbody>
          </table>
        </div>
      </Card>
    </div>
  );
}

function NativeCashbook({data, csrfToken}) {
  const [receiptFile, setReceiptFile] = useState(null);
  const entries = data.entries || [];
  const categories = data.categories || [];
  const filters = data.filters || {};
  const summary = data.summary || {};
  const methods = data.methods || {};
  const directions = data.directions || {};
  const query = new URLSearchParams(Object.entries(filters).filter(([, value]) => value)).toString();
  const exportSuffix = query ? `?${query}` : '';

  return (
    <div className="v2-native-page v2-cashbook-page">
      <div className="v2-page-heading">
        <div className="v2-page-title">
          <BookOpenText size={34} strokeWidth={1.8} />
          <div>
            <h2>Vereinskassabuch</h2>
            <small className="v2-page-subtitle">Berichtszeitraum: {data.period?.label || 'gesamter Zeitraum'}</small>
          </div>
        </div>
        <div className="v2-page-actions">
          <a className="v2-action-button" href={`/kassabuch/export.csv${exportSuffix}`}>
            <Download size={18} />
            <span>CSV</span>
          </a>
          <a className="v2-action-button" href={`/kassabuch/export.xlsx${exportSuffix}`}>
            <Download size={18} />
            <span>Excel</span>
          </a>
          <a className="v2-action-button" href={`/kassabuch/export.pdf${exportSuffix}`} title="PDF Vorschau">
            <FileText size={18} />
            <span>PDF</span>
          </a>
        </div>
      </div>

      <section className="v2-cashbook-stats" aria-label="Kassabuch Kennzahlen">
        <DashboardStat icon={Clock3} label="Anfangssaldo" value={formatCurrency(summary.opening_balance)} />
        <DashboardStat icon={Banknote} label="Einnahmen im Zeitraum" value={formatCurrency(summary.income_total)} />
        <DashboardStat icon={ReceiptText} label="Ausgaben im Zeitraum" value={formatCurrency(summary.expense_total)} />
        <DashboardStat icon={Landmark} label={`Endsaldo (${formatNumber(summary.entry_count, 0)} Buchungen)`} value={formatSignedCurrency(summary.closing_balance)} />
      </section>

      <Card className="v2-native-card v2-cashbook-card" padding={0}>
        <div className="v2-dashboard-card-title">
          <Plus size={24} />
          <h3>Neue Buchung erfassen</h3>
        </div>
        <form
          className="v2-cashbook-form"
          method="post"
          action="/kassabuch/new"
          encType="multipart/form-data"
          onSubmit={(event) => {
            if (receiptFile) {
              submitMultipartFormWithFiles(event, [{name: 'receipt', files: receiptFile}]);
            }
          }}
        >
          <input type="hidden" name="csrf_token" value={csrfToken || ''} />
          <input type="hidden" name="next" value="/v2/kassabuch" />
          <FormDateInput name="entry_date" label="Datum" defaultValue={data.today || ''} isRequired />
          <FormSelector
            name="direction"
            label="Art"
            defaultValue="expense"
            isRequired
            options={Object.entries(directions).map(([value, label]) => ({value, label}))}
          />
          <FormNumberInput name="amount_eur" label="Betrag" step={0.01} units="€" isRequired />
          <FormSelector
            name="payment_method"
            label="Zahlungsart"
            defaultValue="transfer"
            isRequired
            options={Object.entries(methods).map(([value, label]) => ({value, label}))}
          />
          <FormSelector
            name="category_id"
            label="Kategorie"
            defaultValue=""
            placeholder="Kategorie wählen"
            options={[{value: '', label: 'Ohne Kategorie'}, ...categories.map((category) => ({value: String(category.id), label: category.name}))]}
            hasSearch={categories.length > 8}
            searchPlaceholder="Kategorie suchen..."
          />
          <FormTextInput name="description" label="Begründung" placeholder="z.B. Bewirtung Generalversammlung" isRequired />
          <FormTextInput name="counterparty" label="Zahler / Empfänger" placeholder="optional" isOptional />
          <FormFileInput
            name="receipt"
            label="Beleg"
            description="PDF, JPG oder PNG, max. 10 MB."
            accept=".pdf,.jpg,.jpeg,.png"
            placeholder="Beleg auswählen"
            onFilesChange={setReceiptFile}
          />
          <button type="submit" className="v2-primary-action v2-submit-action">
            <Plus size={20} />
            <span>Speichern</span>
          </button>
        </form>
      </Card>

      <Card className="v2-native-card v2-cashbook-card" padding={0}>
        <div className="v2-dashboard-card-title">
          <SearchIcon />
          <h3>Filter</h3>
        </div>
        <form className="v2-cashbook-filter" method="get" action="/v2/kassabuch">
          <FormDateInput name="date_from" label="Von" defaultValue={filters.date_from || ''} hasClear />
          <FormDateInput name="date_to" label="Bis" defaultValue={filters.date_to || ''} hasClear />
          <FormSelector
            name="year"
            label="Jahr"
            defaultValue={filters.year || ''}
            options={[{value: '', label: 'Alle'}, ...(data.years || []).map((year) => ({value: year, label: year}))]}
          />
          <FormSelector
            name="category"
            label="Kategorie"
            defaultValue={filters.category || ''}
            options={[{value: '', label: 'Alle'}, ...(data.by_category || []).map((row) => ({value: row.category, label: row.category}))]}
            hasSearch={(data.by_category || []).length > 8}
            searchPlaceholder="Kategorie suchen..."
          />
          <FormSelector
            name="direction"
            label="Art"
            defaultValue={filters.direction || ''}
            options={[{value: '', label: 'Alle'}, ...Object.entries(directions).map(([value, label]) => ({value, label}))]}
          />
          <FormSelector
            name="method"
            label="Zahlungsart"
            defaultValue={filters.method || ''}
            options={[{value: '', label: 'Alle'}, ...Object.entries(methods).map(([value, label]) => ({value, label}))]}
          />
          <FormTextInput name="search" label="Suche" defaultValue={filters.search || ''} placeholder="Text..." isOptional />
          <div className="v2-cashbook-filter-actions">
            <button type="submit" className="v2-primary-action v2-submit-action">
              <Eye size={20} />
              <span>Filtern</span>
            </button>
            <a href="/v2/kassabuch" className="v2-action-button">
              <RotateCcw size={18} />
              <span>Zurücksetzen</span>
            </a>
          </div>
        </form>
      </Card>

      <Card className="v2-native-card v2-cashbook-card" padding={0}>
        <div className="v2-dashboard-card-title">
          <NotebookText size={24} />
          <h3>Bewegungen</h3>
        </div>
        <div className="v2-table-wrap">
          <table className="v2-native-table v2-cashbook-table">
            <thead>
              <tr>
                <th>Beleg-Nr</th>
                <th>Datum</th>
                <th>Kategorie</th>
                <th>Begründung</th>
                <th>Zahler / Empfänger</th>
                <th>Zahlungsart</th>
                <th>Betrag</th>
                <th>Saldo</th>
                <th>Beleg</th>
                <th>Aktionen</th>
              </tr>
            </thead>
            <tbody>
              {entries.length ? entries.map((entry) => (
                <tr key={`${entry.source}-${entry.id}`}>
                  <td>
                    <strong>{entry.sequence_number}</strong>
                    {entry.reference && <><br /><small className="v2-muted">{entry.reference}</small></>}
                  </td>
                  <td>{formatDate(entry.entry_date)}</td>
                  <td>
                    {entry.category}
                    {entry.source === 'energy' && <><br /><span className="v2-tag is-muted">automatisch</span></>}
                  </td>
                  <td>{entry.description}</td>
                  <td>{entry.counterparty || '-'}</td>
                  <td>{methods[entry.payment_method] || entry.payment_method}</td>
                  <td className={`v2-number-cell ${entry.direction === 'income' ? 'is-positive' : 'is-negative'}`}>
                    {formatSignedCurrency(entry.signed_amount)}
                  </td>
                  <td className="v2-number-cell">{formatCurrency(entry.balance)}</td>
                  <td>
                    {entry.has_receipt
                      ? <a className="v2-icon-action" href={`/kassabuch/${entry.id}/beleg`} aria-label="Beleg öffnen" title="Beleg öffnen"><FileText size={18} /></a>
                      : <span className="v2-tag is-muted">-</span>}
                  </td>
                  <td className="v2-table-action">
                    {entry.deletable ? (
                      <form
                        method="post"
                        action={`/kassabuch/${entry.id}/delete`}
                        onSubmit={(event) => {
                          if (!window.confirm(`Buchung ${entry.sequence_number} (${entry.reference}) wirklich löschen?`)) event.preventDefault();
                        }}
                      >
                        <input type="hidden" name="csrf_token" value={csrfToken || ''} />
                        <input type="hidden" name="next" value="/v2/kassabuch" />
                        <button type="submit" className="v2-icon-action is-danger" aria-label="Buchung löschen" title="Löschen">
                          <Trash2 size={18} />
                        </button>
                      </form>
                    ) : <span className="v2-tag is-muted">aus Abrechnung</span>}
                  </td>
                </tr>
              )) : (
                <tr><td colSpan="10"><EmptyState text="Keine Buchungen für diese Auswahl." /></td></tr>
              )}
            </tbody>
          </table>
        </div>
      </Card>

      <div className="v2-cashbook-reports">
        <Card className="v2-native-card v2-cashbook-card" padding={0}>
          <div className="v2-dashboard-card-title">
            <ChartNoAxesCombined size={24} />
            <h3>Auswertung nach Kategorie</h3>
          </div>
          <div className="v2-table-wrap">
            <table className="v2-native-table">
              <thead>
                <tr>
                  <th>Kategorie</th>
                  <th>Buchungen</th>
                  <th>Einnahmen</th>
                  <th>Ausgaben</th>
                  <th>Ergebnis</th>
                </tr>
              </thead>
              <tbody>
                {(data.by_category || []).length ? data.by_category.map((row) => (
                  <tr key={row.category}>
                    <td><strong>{row.category}</strong></td>
                    <td className="v2-number-cell">{formatNumber(row.count, 0)}</td>
                    <td className="v2-number-cell is-positive">{formatCurrency(row.income)}</td>
                    <td className="v2-number-cell is-negative">{formatCurrency(row.expense)}</td>
                    <td className="v2-number-cell">{formatSignedCurrency(row.result)}</td>
                  </tr>
                )) : <tr><td colSpan="5"><EmptyState text="Keine Daten." /></td></tr>}
              </tbody>
            </table>
          </div>
        </Card>

        <Card className="v2-native-card v2-cashbook-card" padding={0}>
          <div className="v2-dashboard-card-title">
            <Clock3 size={24} />
            <h3>Auswertung nach Jahr</h3>
          </div>
          <div className="v2-table-wrap">
            <table className="v2-native-table">
              <thead>
                <tr>
                  <th>Jahr</th>
                  <th>Buchungen</th>
                  <th>Einnahmen</th>
                  <th>Ausgaben</th>
                  <th>Ergebnis</th>
                </tr>
              </thead>
              <tbody>
                {(data.by_year || []).length ? data.by_year.map((row) => (
                  <tr key={row.year}>
                    <td><strong>{row.year}</strong></td>
                    <td className="v2-number-cell">{formatNumber(row.count, 0)}</td>
                    <td className="v2-number-cell is-positive">{formatCurrency(row.income)}</td>
                    <td className="v2-number-cell is-negative">{formatCurrency(row.expense)}</td>
                    <td className="v2-number-cell">{formatSignedCurrency(row.result)}</td>
                  </tr>
                )) : <tr><td colSpan="5"><EmptyState text="Keine Daten." /></td></tr>}
              </tbody>
            </table>
          </div>
        </Card>
      </div>

      <Card className="v2-native-card v2-cashbook-card" padding={0}>
        <div className="v2-dashboard-card-title">
          <Settings size={24} />
          <h3>Kategorien verwalten</h3>
        </div>
        <form className="v2-cashbook-category-form" method="post" action="/kassabuch/kategorien">
          <input type="hidden" name="csrf_token" value={csrfToken || ''} />
          <input type="hidden" name="next" value="/v2/kassabuch" />
          <FormTextInput name="name" label="Neue Kategorie" placeholder="z.B. Vereinsausflug" isRequired />
          <FormSelector
            name="direction"
            label="Verwendung"
            defaultValue="both"
            options={[
              {value: 'both', label: 'Einnahme und Ausgabe'},
              {value: 'income', label: 'Nur Einnahme'},
              {value: 'expense', label: 'Nur Ausgabe'},
            ]}
          />
          <button type="submit" className="v2-primary-action v2-submit-action">
            <Plus size={20} />
            <span>Anlegen</span>
          </button>
        </form>
        <div className="v2-cashbook-category-list">
          {categories.map((category) => (
            <span key={category.id} className="v2-cashbook-category-chip">
              {category.name}
              <form
                method="post"
                action={`/kassabuch/kategorien/${category.id}/delete`}
                onSubmit={(event) => {
                  if (!window.confirm(`Kategorie "${category.name}" entfernen?`)) event.preventDefault();
                }}
              >
                <input type="hidden" name="csrf_token" value={csrfToken || ''} />
                <input type="hidden" name="next" value="/v2/kassabuch" />
                <button type="submit" className="v2-icon-action is-danger" aria-label="Kategorie entfernen" title="Entfernen">
                  <X size={16} />
                </button>
              </form>
            </span>
          ))}
        </div>
      </Card>
    </div>
  );
}

function NativeInvoices({data}) {
  const invoices = data.invoices || [];
  const provisionalInvoices = invoices.filter((invoice) => invoice.data_status !== 'final');
  const draftInvoices = invoices.filter((invoice) => invoice.status === 'draft');
  const columns = [
    {key: 'id', header: '#', width: pixel(70), renderCell: (invoice) => <strong>{invoice.id}</strong>},
    {key: 'period', header: 'Zeitraum', width: proportional(1.2, {minWidth: 190}), renderCell: (invoice) => formatDateRange(invoice.period_from, invoice.period_to)},
    {key: 'total_kwh_traded', header: 'kWh gehandelt', align: 'end', width: pixel(150), renderCell: (invoice) => `${formatNumber(invoice.total_kwh_traded, 1)} kWh`},
    {key: 'total_income', header: 'Einnahmen', align: 'end', width: pixel(130), renderCell: (invoice) => formatCurrency(invoice.total_income)},
    {key: 'total_expense', header: 'Ausgaben', align: 'end', width: pixel(130), renderCell: (invoice) => formatCurrency(invoice.total_expense)},
    {key: 'total_margin', header: 'Marge', align: 'end', width: pixel(130), renderCell: (invoice) => <strong>{formatCurrency(invoice.total_margin)}</strong>},
    {key: 'data_status', header: 'Daten', width: pixel(120), renderCell: (invoice) => <StatusPill value={invoice.data_status} />},
    {key: 'status', header: 'Status', width: proportional(.9, {minWidth: 160}), renderCell: (invoice) => invoiceStatusLabel(invoice.status)},
    {key: 'actions', header: 'Aktionen', align: 'end', width: pixel(95), renderCell: (invoice) => (
      <a className="v2-icon-action" href={`/v2/invoices/${invoice.id}`} aria-label={`Abrechnung ${invoice.id} öffnen`} title="Öffnen">
        <Eye size={18} />
      </a>
    )},
  ];

  return (
    <div className="v2-native-page v2-invoices-page">
      <div className="v2-page-heading">
        <div className="v2-page-title">
          <ReceiptText size={34} strokeWidth={1.8} />
          <h2>Abrechnungen</h2>
        </div>
        <a className="v2-primary-action" href="/v2/invoices/new">
          <Plus size={22} />
          <span>Neue Abrechnung</span>
        </a>
      </div>

      <StatusBannerStack>
        {provisionalInvoices.length > 0 && (
          <Banner
            status="warning"
            title="Abrechnung noch nicht finalisierbar"
            description={`${formatNumber(provisionalInvoices.length)} Abrechnung${provisionalInvoices.length === 1 ? '' : 'en'} basiert/basieren auf vorläufigen Daten. Versand und finaler Abschluss sind erst mit finalen Messdaten erlaubt.`}
            container="section"
          />
        )}
        {draftInvoices.length > 0 && (
          <Banner
            status="info"
            title="Entwürfe vorhanden"
            description={`${formatNumber(draftInvoices.length)} Abrechnung${draftInvoices.length === 1 ? '' : 'en'} ist/sind noch als Entwurf gespeichert.`}
            container="section"
            isDismissable
          />
        )}
      </StatusBannerStack>

      <Card className="v2-native-card v2-invoices-card" padding={0}>
        <div className="v2-table-wrap">
          {invoices.length ? (
            <Table
              className="v2-astryx-table v2-invoices-table"
              data={invoices}
              columns={columns}
              idKey="id"
              density="compact"
              dividers="rows"
              hasHover
              textOverflow="wrap"
            />
          ) : <EmptyState text="Noch keine Abrechnungen erstellt." />}
        </div>
      </Card>
    </div>
  );
}

function NativeInvoiceNew({data, csrfToken}) {
  const importStatus = data.import_status || {};
  const price = data.price || {};
  return (
    <div className="v2-native-page v2-invoice-new-page">
      <div className="v2-page-heading">
        <div className="v2-page-title">
          <ReceiptText size={34} strokeWidth={1.8} />
          <h2>Neue Abrechnung</h2>
        </div>
      </div>

      <StatusBannerStack>
        <Banner
          status={importStatus.is_final ? 'success' : 'warning'}
          title={importStatus.is_final ? 'Finale Daten für den Vorschlagszeitraum' : 'Vorschau mit vorläufigen Daten möglich'}
          description={importStatus.is_final
            ? 'Für den vorgeschlagenen Zeitraum liegen finale Messdaten vor.'
            : (importStatus.reason || 'Solange Daten vorläufig sind, kann die Abrechnung nur als Vorschau erstellt werden. Versand und Abschluss bleiben gesperrt.')}
          container="section"
        />
      </StatusBannerStack>

      <Card className="v2-native-card v2-invoice-new-card" padding={0}>
        <div className="v2-dashboard-card-title">
          <Plus size={24} />
          <div>
            <h3>Abrechnungszeitraum wählen</h3>
            <p>Standard ist das vorige Quartal. Vorperioden mit offenen Buchungen werden automatisch berücksichtigt.</p>
          </div>
        </div>
        <form className="v2-settings-form" method="post" action="/v2/invoices/new">
          <input type="hidden" name="csrf_token" value={csrfToken || ''} />
          <div className="v2-form-section">
            <FormDateInput name="period_from" label="Von" defaultValue={data.suggested_from || ''} isRequired />
            <FormDateInput name="period_to" label="Bis" defaultValue={data.suggested_to || ''} isRequired />
          </div>
          <div className="v2-inline-note">
            Aktueller Preisvorschlag: Verbrauch {formatNumber(price.consumption, 1)} ct/kWh · Erzeugung {formatNumber(price.generation, 1)} ct/kWh
          </div>
          <div className="v2-form-actions">
            <button type="submit" className="v2-primary-action v2-submit-action" onClick={(event) => confirmInvoiceCreate(event, !importStatus.is_final)}>
              <ReceiptText size={20} />
              <span>Abrechnung erstellen</span>
            </button>
          </div>
        </form>
      </Card>
    </div>
  );
}

function NativeInvoiceDetail({data, csrfToken}) {
  const invoice = data.invoice || {};
  const members = data.members || [];
  const emails = data.emails || [];
  const importStatus = data.import_status || {};
  const blocker = data.finalization_blocker || '';
  const canSend = !blocker;
  const memberColumns = [
    {key: 'member', header: 'Mitglied', width: proportional(1.3, {minWidth: 240}), renderCell: (row) => <><strong>{row.member_name}</strong>{row.member_email && <small>{row.member_email}</small>}</>},
    {key: 'cons', header: 'Bezug', align: 'end', width: pixel(140), renderCell: (row) => `${formatNumber(row.cons_kwh, 1)} kWh`},
    {key: 'gen', header: 'Erzeugung', align: 'end', width: pixel(140), renderCell: (row) => `${formatNumber(row.gen_kwh, 1)} kWh`},
    {key: 'energy', header: 'Energie', align: 'end', width: pixel(130), renderCell: (row) => formatSignedCurrency(row.energy_net_eur)},
    {key: 'carryover', header: 'Vorperioden', align: 'end', width: pixel(140), renderCell: (row) => Number(row.carryover_eur) ? <span className="v2-tag is-warning">{formatSignedCurrency(row.carryover_eur)}</span> : '-'},
    {key: 'net', header: 'Gesamt', align: 'end', width: pixel(130), renderCell: (row) => <strong>{formatSignedCurrency(row.net_eur)}</strong>},
    {key: 'email', header: 'Mail', width: pixel(110), renderCell: (row) => <StatusPill value={row.email_sent ? 'sent' : 'draft'} />},
    {key: 'actions', header: 'Aktionen', align: 'end', width: pixel(155), renderCell: (row) => (
      <div className="v2-row-actions">
        <a className="v2-icon-action" href={`/invoices/${invoice.id}/pdf/${row.member_id}`} aria-label="PDF öffnen" title="PDF öffnen">
          <FileText size={18} />
        </a>
        <form method="post" action={`/invoices/${invoice.id}/send/${row.member_id}`} onSubmit={(event) => confirmInvoiceSend(event, canSend)}>
          <input type="hidden" name="csrf_token" value={csrfToken || ''} />
          <button type="submit" className={`v2-icon-action ${canSend ? '' : 'is-disabled'}`} disabled={!canSend} aria-label="E-Mail senden" title={canSend ? 'E-Mail senden' : 'Versand gesperrt'}>
            <Mail size={18} />
          </button>
        </form>
      </div>
    )},
  ];
  const emailColumns = [
    {key: 'sent_at', header: 'Zeitpunkt', width: pixel(170), renderCell: (row) => row.sent_at || '-'},
    {key: 'member', header: 'Mitglied', width: proportional(1, {minWidth: 220}), renderCell: (row) => row.member_name || row.email || '-'},
    {key: 'subject', header: 'Betreff', width: proportional(1.6, {minWidth: 280}), renderCell: (row) => row.subject || '-'},
    {key: 'status', header: 'Status', width: pixel(130), renderCell: (row) => <StatusPill value={row.status} />},
  ];
  return (
    <div className="v2-native-page v2-invoice-detail-page">
      <div className="v2-page-heading">
        <div className="v2-page-title">
          <ReceiptText size={34} strokeWidth={1.8} />
          <h2>Abrechnung #{invoice.id}</h2>
        </div>
        <div className="v2-page-actions">
          <a className="v2-action-button" href={`/invoices/${invoice.id}`}><Eye size={18} /><span>Altansicht</span></a>
          <form method="post" action={`/invoices/${invoice.id}/regenerate`} onSubmit={(event) => confirmRegenerateInvoice(event)}>
            <input type="hidden" name="csrf_token" value={csrfToken || ''} />
            <button type="submit" className="v2-action-button"><RefreshCw size={18} /><span>Neu berechnen</span></button>
          </form>
        </div>
      </div>

      <StatusBannerStack>
        {blocker && <Banner status="warning" title="Versand und Abschluss gesperrt" description={blocker} container="section" />}
        {!blocker && <Banner status="success" title="Abrechnung kann versendet werden" description="Für diesen Zeitraum liegen finale Daten vor und die Abrechnung ist versandbereit." container="section" isDismissable />}
      </StatusBannerStack>

      <section className="v2-dashboard-stats" aria-label="Abrechnung Kennzahlen">
        <DashboardStat icon={Activity} label="Gehandelte Energie" value={`${formatNumber(invoice.total_kwh_traded, 1)} kWh`} />
        <DashboardStat icon={Euro} label="Einnahmen" value={formatCurrency(invoice.total_income)} />
        <DashboardStat icon={Banknote} label="Ausgaben" value={formatCurrency(invoice.total_expense)} />
        <DashboardStat icon={ReceiptText} label="Marge" value={formatCurrency(invoice.total_margin)} />
      </section>

      <Card className="v2-native-card v2-invoice-detail-card" padding={0}>
        <div className="v2-dashboard-card-title">
          <Users size={24} />
          <div>
            <h3>Mitgliederabrechnungen</h3>
            <p>{formatDateRange(invoice.period_from, invoice.period_to)} · <StatusPill value={importStatus.data_status || invoice.data_status} /></p>
          </div>
        </div>
        <div className="v2-table-wrap">
          {members.length ? (
            <Table className="v2-astryx-table v2-invoice-members-table" data={members} columns={memberColumns} idKey="member_id" density="compact" dividers="rows" hasHover textOverflow="wrap" verticalAlign="top" />
          ) : <EmptyState text="Keine Mitgliederpositionen vorhanden." />}
        </div>
        <div className="v2-form-actions">
          <form method="post" action={`/invoices/${invoice.id}/send`} onSubmit={(event) => confirmInvoiceSend(event, canSend)}>
            <input type="hidden" name="csrf_token" value={csrfToken || ''} />
            <button type="submit" className="v2-primary-action v2-submit-action" disabled={!canSend}>
              <Mail size={20} />
              <span>Alle Rechnungen senden</span>
            </button>
          </form>
          <form method="post" action={`/invoices/${invoice.id}/finalize`} onSubmit={(event) => confirmInvoiceFinalize(event, canSend)}>
            <input type="hidden" name="csrf_token" value={csrfToken || ''} />
            <button type="submit" className="v2-action-button" disabled={!canSend}>
              <Check size={18} />
              <span>Final abschließen</span>
            </button>
          </form>
        </div>
      </Card>

      <Card className="v2-native-card v2-invoice-detail-card" padding={0}>
        <div className="v2-dashboard-card-title">
          <Mail size={24} />
          <h3>E-Mail-Protokoll</h3>
        </div>
        <div className="v2-table-wrap">
          {emails.length ? <Table className="v2-astryx-table" data={emails} columns={emailColumns} idKey="id" density="compact" dividers="rows" hasHover textOverflow="wrap" /> : <EmptyState text="Noch keine E-Mails versendet." />}
        </div>
      </Card>
    </div>
  );
}

function confirmInvoiceCreate(event, isProvisional) {
  const message = isProvisional
    ? 'Diese Abrechnung wird nur als vorläufige Vorschau erstellt. Versand und Abschluss bleiben gesperrt. Fortfahren?'
    : 'Abrechnung für diesen Zeitraum erstellen?';
  if (!window.confirm(message)) event.preventDefault();
}

function confirmRegenerateInvoice(event) {
  if (!window.confirm('Abrechnung wirklich neu berechnen? Bestehende Positionen werden ersetzt.')) event.preventDefault();
}

function confirmInvoiceSend(event, canSend) {
  if (!canSend || !window.confirm('Rechnung per E-Mail senden?')) event.preventDefault();
}

function confirmInvoiceFinalize(event, canFinalize) {
  if (!canFinalize || !window.confirm('Abrechnung endgültig abschließen? Danach sollte sie nicht mehr geändert werden.')) event.preventDefault();
}

function NativePayments({data, csrfToken}) {
  const payments = data.payments || [];
  const summary = data.summary || {};
  const today = data.today || '';
  const bookedEntries = data.booked_entries || [];
  const bookedSort = data.booked_sort || 'date';
  const bookedDir = data.booked_dir || 'desc';
  const [qrRow, setQrRow] = useState(null);
  const openClaims = payments.filter((row) => !row.paid && !row.is_settled_by_carryover && Number(row.net_total) > 0);
  const openCredits = payments.filter((row) => !row.paid && !row.is_settled_by_carryover && Number(row.net_total) < 0);
  const carried = payments.filter((row) => row.is_settled_by_carryover);
  const paid = payments.filter((row) => row.paid);
  const overdueCount = Number(summary.overdue_count) || 0;
  const previousPeriodOpenCount = payments.filter((row) => row.is_previous_period_open && !row.is_settled_by_carryover && !row.paid).length;
  const paymentWorkTotal = openClaims.length + openCredits.length + paid.length;
  const paymentProgress = paymentWorkTotal ? Math.round((paid.length / paymentWorkTotal) * 100) : 100;
  const openClaimColumns = [
    {key: 'member', header: 'Mitglied', width: proportional(1.1, {minWidth: 200}), renderCell: (row) => <><strong>{row.member_name}</strong><PaymentFlags row={row} /></>},
    {key: 'period', header: 'Zeitraum', width: proportional(.95, {minWidth: 180}), renderCell: (row) => <>{formatDateRange(row.period_from, row.period_to)}{row.is_overdue && <small>aktiv seit {formatDate(row.due_on)}</small>}</>},
    {key: 'amount', header: 'Betrag', align: 'end', width: pixel(130), renderCell: (row) => <span className="v2-money-negative">{formatCurrency(row.net_total)}</span>},
    {key: 'purpose', header: 'Verwendungszweck', width: proportional(1.7, {minWidth: 300}), renderCell: (row) => (
      <>
        <span>EEG-Abr. {row.invoice_id}/{String(row.period_from || '').slice(0, 4)} - {row.member_name}</span>
        {Number(row.carryover_total) !== 0 && <small>davon Vorperioden: {formatCurrency(row.carryover_total)}</small>}
      </>
    )},
    {key: 'booking_date', header: 'Buchungsdatum', width: pixel(165), renderCell: (row) => <PaymentDateInput row={row} today={today} />},
    {key: 'action', header: 'Aktion', align: 'end', width: pixel(130), renderCell: (row) => <PaymentPaidForm row={row} csrfToken={csrfToken} label="Gebucht" />},
  ];
  const openCreditColumns = [
    {key: 'member', header: 'Mitglied', width: proportional(1.1, {minWidth: 200}), renderCell: (row) => <strong>{row.member_name}</strong>},
    {key: 'period', header: 'Zeitraum', width: proportional(.95, {minWidth: 180}), renderCell: (row) => formatDateRange(row.period_from, row.period_to)},
    {key: 'amount', header: 'Gutschrift', align: 'end', width: pixel(130), renderCell: (row) => <span className="v2-money-positive">{formatCurrency(Math.abs(Number(row.net_total) || 0))}</span>},
    {key: 'bank', header: 'Bankverbindung', width: proportional(1.7, {minWidth: 300}), renderCell: (row) => (
      <>
        {Number(row.carryover_total) !== 0 && <small>davon Vorperioden: {formatCurrency(row.carryover_total)}</small>}
        {row.iban ? <span>{row.account_holder || row.member_name}<small>{row.iban}</small></span> : <span className="v2-error-text">Keine IBAN hinterlegt</span>}
      </>
    )},
    {key: 'booking_date', header: 'Buchungsdatum', width: pixel(165), renderCell: (row) => <PaymentDateInput row={row} today={today} />},
    {key: 'action', header: 'Aktion', align: 'end', width: pixel(170), renderCell: (row) => (
      <div className="v2-payment-actions">
        {row.sepa?.qr_url && (
          <button
            type="button"
            className="v2-icon-action"
            onClick={() => setQrRow(row)}
            aria-label="QR-Code für Überweisung"
            title="QR-Code für Überweisung"
          >
            <QrCode size={18} />
          </button>
        )}
        <PaymentPaidForm row={row} csrfToken={csrfToken} label="Überwiesen" />
      </div>
    )},
  ];
  const carriedColumns = [
    {key: 'member', header: 'Mitglied', width: proportional(1.2, {minWidth: 220}), renderCell: (row) => row.member_name},
    {key: 'invoice', header: 'Ursprüngliche Abrechnung', width: proportional(1.2, {minWidth: 230}), renderCell: (row) => `#${row.invoice_id} · ${formatDateRange(row.period_from, row.period_to)}`},
    {key: 'amount', header: 'Vorgetragener Betrag', align: 'end', width: pixel(180), renderCell: (row) => formatSignedCurrency(row.net_total)},
    {key: 'carried_to', header: 'Berücksichtigt in', width: proportional(1, {minWidth: 180}), renderCell: (row) => <span className="v2-tag is-muted">Abrechnung #{row.carried_forward_to_invoice_id}</span>},
  ];
  return (
    <div className="v2-native-page v2-payments-page">
      <div className="v2-page-heading">
        <div className="v2-page-title">
          <Banknote size={34} strokeWidth={1.8} />
          <h2>Überweisungen & Forderungen</h2>
        </div>
      </div>

      <StatusBannerStack>
        {overdueCount > 0 && (
          <Banner
            status="warning"
            title="Buchungsrückstände aktiv"
            description={`${formatNumber(overdueCount)} offene Buchung${overdueCount === 1 ? '' : 'en'} ist/sind länger als 7 Tage nach der Abrechnung offen.`}
            container="section"
          />
        )}
        {previousPeriodOpenCount > 0 && (
          <Banner
            status="warning"
            title="Offene Vorperioden vorhanden"
            description={`${formatNumber(previousPeriodOpenCount)} Buchung${previousPeriodOpenCount === 1 ? '' : 'en'} aus früheren Perioden ist/sind noch offen und müssen in der aktuellen Sicht berücksichtigt werden.`}
            container="section"
          />
        )}
        {overdueCount === 0 && openClaims.length === 0 && openCredits.length === 0 && (
          <Banner
            status="success"
            title="Keine offenen Buchungen"
            description="Alle sichtbaren Forderungen und Gutschriften sind erledigt."
            container="section"
            isDismissable
          />
        )}
      </StatusBannerStack>

      <div className="v2-payment-health">
        <StatusLine
          variant={overdueCount > 0 ? 'warning' : openClaims.length || openCredits.length ? 'accent' : 'success'}
          label="Zahlungsstatus"
        >
          {formatNumber(paid.length)} von {formatNumber(paymentWorkTotal)} Buchungen erledigt
        </StatusLine>
        <ProgressBar
          label="Gebuchte Zahlungen"
          value={paymentProgress}
          max={100}
          hasValueLabel
          variant={overdueCount > 0 ? 'warning' : 'success'}
        />
      </div>

      <section className="v2-payment-summary" aria-label="Zahlungsübersicht">
        <span className="v2-tag is-danger">{formatNumber(summary.open_claims_count)} offen (Forderungen)</span>
        <span className="v2-tag is-warning">{formatNumber(summary.overdue_count)} Buchungsrückstand</span>
        <span className="v2-tag is-success">{formatNumber(summary.paid_count)} gebucht</span>
        <span className="v2-tag is-info">{formatNumber(summary.open_credits_count)} offen (Gutschriften)</span>
      </section>

      <PaymentTable
        title="Offene Forderungen (Mitglied -> EEG)"
        tone="danger"
        rows={openClaims}
        emptyText="Keine offenen Forderungen"
        footerLabel="Gesamt offene Forderungen"
        footerValue={summary.open_claims_total}
        columns={openClaimColumns}
      />

      <PaymentTable
        title="Offene Gutschriften (EEG -> Mitglied)"
        tone="info"
        rows={openCredits}
        emptyText="Keine offenen Gutschriften"
        footerLabel="Gesamt offene Gutschriften"
        footerValue={Math.abs(Number(summary.open_credits_total) || 0)}
        columns={openCreditColumns}
      />

      {carried.length > 0 && (
        <PaymentTable
          title="In Folgeabrechnung berücksichtigte Vorperioden"
          tone="muted"
          rows={carried}
          columns={carriedColumns}
        />
      )}

      <BookedPaymentsTable
        entries={bookedEntries}
        sort={bookedSort}
        dir={bookedDir}
        csrfToken={csrfToken}
      />

      <QrModal
        isOpen={!!qrRow}
        onClose={() => setQrRow(null)}
        row={qrRow}
      />
    </div>
  );
}

function PaymentTable({title, tone, rows, columns, emptyText, footerLabel, footerValue}) {
  return (
    <Card className={`v2-native-card v2-payments-card is-${tone || 'default'}`} padding={0}>
      <div className="v2-dashboard-card-title">
        <Banknote size={24} />
        <h3>{title}</h3>
      </div>
      <div className="v2-table-wrap">
        {rows.length ? (
          <Table
            className="v2-astryx-table v2-payments-table"
            data={rows}
            columns={columns}
            idKey={(row) => `${row.invoice_id}-${row.member_id}`}
            density="compact"
            dividers="rows"
            hasHover
            textOverflow="wrap"
            verticalAlign="top"
          />
        ) : <EmptyState text={emptyText || 'Keine Daten vorhanden.'} />}
      </div>
      {rows.length > 0 && footerLabel && (
        <div className="v2-table-footer-summary">
          <strong>{footerLabel}</strong>
          <span>{formatCurrency(footerValue)}</span>
        </div>
      )}
    </Card>
  );
}

function SortLink({sortKey, label, currentSort, currentDir, anchor}) {
  const nextDir = currentSort === sortKey && currentDir === 'desc' ? 'asc' : 'desc';
  const arrow = currentSort === sortKey ? (currentDir === 'asc' ? '↑' : '↓') : '↕';
  const href = `/v2/payments?booked_sort=${sortKey}&booked_dir=${nextDir}${anchor ? `#${anchor}` : ''}`;
  return (
    <a href={href} className="v2-sort-link">
      {label} <span className="v2-sort-arrow">{arrow}</span>
    </a>
  );
}

function BookedPaymentsTable({entries, sort, dir, csrfToken}) {
  return (
    <Card className="v2-native-card v2-payments-card is-success" padding={0} id="gebuchte-zahlungen">
      <div className="v2-dashboard-card-title">
        <Banknote size={24} />
        <h3>
          Gebuchte Zahlungen
          <small> – {entries.length} Buchungen</small>
        </h3>
      </div>
      <div className="v2-table-wrap">
        {entries.length ? (
          <table className="v2-native-table v2-payments-booked-table">
            <thead>
              <tr>
                <th><SortLink sortKey="member" label="Mitglied" currentSort={sort} currentDir={dir} anchor="gebuchte-zahlungen" /></th>
                <th><SortLink sortKey="period" label="Zeitraum" currentSort={sort} currentDir={dir} anchor="gebuchte-zahlungen" /></th>
                <th className="v2-number-cell"><SortLink sortKey="amount" label="Gebuchter Betrag" currentSort={sort} currentDir={dir} anchor="gebuchte-zahlungen" /></th>
                <th><SortLink sortKey="date" label="Gebucht am" currentSort={sort} currentDir={dir} anchor="gebuchte-zahlungen" /></th>
                <th>Aktion</th>
              </tr>
            </thead>
            <tbody>
              {entries.map((entry) => {
                const row = entry.row || {};
                const booking = entry.booking || {};
                const isLegacy = entry.kind === 'legacy';
                const key = `${entry.kind}-${row.invoice_id || 0}-${row.member_id || 0}-${booking.id || 0}`;
                return (
                  <tr key={key}>
                    <td>
                      <strong>{row.member_name}</strong>
                      {entry.total_bookings > 1 && (
                        <><br /><small className="v2-tag is-muted">Teilbuchung {entry.position}/{entry.total_bookings}</small></>
                      )}
                      {isLegacy && (
                        <><br /><small className="v2-tag is-muted">Altbestand</small></>
                      )}
                      {!row.paid && (
                        <><br /><small className="v2-error-text">offen: {formatCurrency(row.open_amount)}</small></>
                      )}
                    </td>
                    <td>{formatDateRange(row.period_from, row.period_to)}</td>
                    <td className="v2-number-cell">{formatSignedCurrency(entry.amount)}</td>
                    <td>{formatDate(entry.booking_date)}</td>
                    <td className="v2-table-action">
                      <form method="post" action="/payments/mark_unpaid" onSubmit={(event) => confirmPaymentReset(event)}>
                        <input type="hidden" name="csrf_token" value={csrfToken || ''} />
                        <input type="hidden" name="next" value="/v2/payments" />
                        <input type="hidden" name="invoice_id" value={row.invoice_id} />
                        <input type="hidden" name="member_id" value={row.member_id} />
                        <input type="hidden" name="change_reason" value="" />
                        <button type="submit" className="v2-icon-action is-warning" aria-label="Buchung zurücksetzen" title="Buchung zurücksetzen">
                          <RotateCcw size={18} />
                        </button>
                      </form>
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        ) : <EmptyState text="Noch keine Zahlungen gebucht" />}
      </div>
    </Card>
  );
}

function QrModal({isOpen, onClose, row}) {
  if (!isOpen || !row) return null;
  const qrUrl = row.sepa?.qr_url || '';
  const amount = Math.abs(Number(row.net_total) || 0);
  return (
    <div className="v2-modal-overlay" onClick={onClose} role="dialog" aria-modal="true" aria-label="QR-Code für SEPA-Überweisung">
      <div className="v2-modal-content" onClick={(event) => event.stopPropagation()}>
        <div className="v2-modal-header">
          <h3><QrCode size={20} /> Überweisung per QR-Code</h3>
          <button type="button" className="v2-icon-action" onClick={onClose} aria-label="Schließen"><X size={20} /></button>
        </div>
        <div className="v2-modal-body">
          {qrUrl && (
            <div className="v2-qr-wrap">
              <img src={qrUrl} alt="QR-Code für die SEPA-Überweisung" />
            </div>
          )}
          <table className="v2-native-table v2-qr-details">
            <tbody>
              <tr><th>Empfänger</th><td>{row.sepa?.name}</td></tr>
              <tr><th>IBAN</th><td className="v2-monospace">{row.sepa?.iban}</td></tr>
              {row.sepa?.bic && <tr><th>BIC</th><td className="v2-monospace">{row.sepa?.bic}</td></tr>}
              <tr><th>Betrag</th><td><strong>{formatCurrency(amount)}</strong></td></tr>
              <tr><th>Verwendungszweck</th><td>{row.sepa?.reference}</td></tr>
            </tbody>
          </table>
          <p className="v2-muted">Mit der Banking-App scannen (SEPA-Überweisung nach EPC069-12, auch GiroCode genannt). Empfänger, IBAN, Betrag und Verwendungszweck sind enthalten.</p>
        </div>
        <div className="v2-modal-footer">
          <button type="button" className="v2-action-button" onClick={onClose}>Schließen</button>
        </div>
      </div>
    </div>
  );
}

function PaymentFlags({row}) {
  return (
    <div className="v2-payment-flags">
      {row.is_overdue && <span className="v2-tag is-warning">Buchungsrückstand</span>}
      {row.is_previous_period_open && <span className="v2-tag is-muted">Vorperiode offen</span>}
    </div>
  );
}

function PaymentDateInput({row, today}) {
  const id = `book-payment-${row.invoice_id}-${row.member_id}`;
  const [value, setValue] = useState(today || '');
  return (
    <div className="v2-payment-date-field">
      <DateInput
        label="Buchungsdatum"
        isLabelHidden
        value={value}
        onChange={(next) => setValue(next || '')}
        max={today}
        isRequired
        width="100%"
      />
      <input type="hidden" name="booking_date" value={value || ''} form={id} />
    </div>
  );
}

function PaymentPaidForm({row, csrfToken, label}) {
  const id = `book-payment-${row.invoice_id}-${row.member_id}`;
  return (
    <form method="post" action="/payments/mark_paid" id={id} onSubmit={(event) => confirmPaymentBooking(event, label)}>
      <input type="hidden" name="csrf_token" value={csrfToken || ''} />
      <input type="hidden" name="next" value="/v2/payments" />
      <input type="hidden" name="invoice_id" value={row.invoice_id} />
      <input type="hidden" name="member_id" value={row.member_id} />
      <button type="submit" className="v2-action-button">
        <Check size={16} />
        <span>{label}</span>
      </button>
    </form>
  );
}

function confirmPaymentBooking(event, label) {
  if (!window.confirm(`Diese Buchung wirklich als "${label}" mit dem eingegebenen Buchungsdatum speichern?`)) {
    event.preventDefault();
  }
}

function confirmPaymentReset(event) {
  if (!window.confirm('Diese Buchung wirklich stornieren und wieder auf offen setzen?')) {
    event.preventDefault();
    return;
  }
  const reason = window.prompt(
    'Änderungsgrund (mindestens 5 Zeichen).\n'
    + 'Der Grund wird bei der Buchung angezeigt und im Audit-Log gespeichert.', '');
  if (reason === null || reason.trim().length < 5) {
    if (reason !== null) window.alert('Bitte einen Änderungsgrund mit mindestens 5 Zeichen angeben.');
    event.preventDefault();
    return;
  }
  const field = event.currentTarget.querySelector('input[name="change_reason"]');
  if (field) field.value = reason.trim();
}

function confirmBackupDelete(event, name, actionLabel) {
  if (!window.confirm(`Backup "${name}" wirklich ${actionLabel}?`)) {
    event.preventDefault();
  }
}

function NativeNewsletter({data, csrfToken, user}) {
  const newsletters = data.newsletters || [];

  return (
    <div className="v2-native-page v2-newsletter-page">
      <div className="v2-page-heading">
        <div className="v2-page-title">
          <Mail size={34} strokeWidth={1.8} />
          <h2>Newsletter</h2>
        </div>
      </div>

      <section className="v2-payment-summary" aria-label="Newsletter Übersicht">
        <span className="v2-tag is-info">{formatNumber(data.recipient_count)} aktive Empfänger</span>
        <span className="v2-tag is-muted">{formatNumber(newsletters.length)} Newsletter</span>
      </section>

      <Card className="v2-native-card v2-newsletter-card" padding={0}>
        <div className="v2-dashboard-card-title">
          <Plus size={24} />
          <div>
            <h3>Neuen Newsletter anlegen</h3>
            <p>Der Newsletter wird als Entwurf gespeichert und kann danach getestet oder versendet werden.</p>
          </div>
        </div>
        <form className="v2-newsletter-form" method="post" action="/newsletter/new">
          <input type="hidden" name="csrf_token" value={csrfToken || ''} />
          <input type="hidden" name="next" value="/v2/newsletter" />
          <FormTextInput name="subject" label="Betreff" placeholder="z.B. EEG Neuigkeiten - Juli 2026" isRequired />
          <FormTextArea
            name="body_html"
            label="Inhalt"
            description="Einfachen Text oder sicheres HTML eingeben. Der Inhalt wird serverseitig bereinigt."
            rows={8}
            isRequired
          />
          <button type="submit" className="v2-primary-action v2-submit-action">
            <Plus size={20} />
            <span>Entwurf speichern</span>
          </button>
        </form>
      </Card>

      <Card className="v2-native-card v2-newsletter-card" padding={0}>
        <div className="v2-table-wrap">
          <table className="v2-native-table v2-newsletter-table">
            <thead>
              <tr>
                <th>Betreff</th>
                <th>Erstellt</th>
                <th>Versendet</th>
                <th>Empfänger</th>
                <th>Aktionen</th>
              </tr>
            </thead>
            <tbody>
              {newsletters.length ? newsletters.map((newsletter) => {
                const sent = Boolean(newsletter.sent_at);
                return (
                  <tr key={newsletter.id}>
                    <td><strong>{newsletter.subject}</strong></td>
                    <td>
                      {formatDateTime(newsletter.created_at)}
                      <small>von {newsletter.created_by || 'system'}</small>
                    </td>
                    <td>{sent ? <span className="v2-tag is-success">{formatDateTime(newsletter.sent_at)}</span> : <span className="v2-tag is-warning">Entwurf</span>}</td>
                    <td className="v2-number-cell">{formatNumber(newsletter.recipients_count)}</td>
                    <td className="v2-table-action">
                      <div className="v2-row-actions">
                        <a className="v2-icon-action" href={`/newsletter/${newsletter.id}/preview`} target="_blank" rel="noopener" aria-label="Vorschau" title="Vorschau">
                          <Eye size={18} />
                        </a>
                        {!sent && (
                          <>
                            <a className="v2-icon-action" href={`/v2/newsletter/${newsletter.id}/edit`} aria-label="Newsletter bearbeiten" title="Bearbeiten">
                              <Pencil size={18} />
                            </a>
                            <form method="post" action={`/newsletter/${newsletter.id}/test`} onSubmit={(event) => confirmNewsletterTest(event)}>
                              <input type="hidden" name="csrf_token" value={csrfToken || ''} />
                              <input type="hidden" name="next" value="/v2/newsletter" />
                              <input type="hidden" name="test_email" value={user?.email || ''} />
                              <button type="submit" className="v2-icon-action is-warning" aria-label="Test senden" title="Test senden">
                                <Mail size={18} />
                              </button>
                            </form>
                            <form method="post" action={`/newsletter/${newsletter.id}/send`} onSubmit={(event) => confirmNewsletterSend(event)}>
                              <input type="hidden" name="csrf_token" value={csrfToken || ''} />
                              <input type="hidden" name="next" value="/v2/newsletter" />
                              <button type="submit" className="v2-icon-action is-success" aria-label="Newsletter senden" title="Senden">
                                <ExternalLink size={18} />
                              </button>
                            </form>
                          </>
                        )}
                        <form method="post" action={`/newsletter/${newsletter.id}/delete`} onSubmit={(event) => confirmNewsletterDelete(event)}>
                          <input type="hidden" name="csrf_token" value={csrfToken || ''} />
                          <input type="hidden" name="next" value="/v2/newsletter" />
                          <button type="submit" className="v2-icon-action is-danger" aria-label="Newsletter löschen" title="Löschen">
                            <Trash2 size={18} />
                          </button>
                        </form>
                      </div>
                    </td>
                  </tr>
                );
              }) : (
                <tr><td colSpan="5"><EmptyState text="Noch keine Newsletter erstellt." /></td></tr>
              )}
            </tbody>
          </table>
        </div>
      </Card>
    </div>
  );
}

function confirmNewsletterSend(event) {
  if (!window.confirm('Newsletter an alle aktiven Mitglieder versenden?')) {
    event.preventDefault();
  }
}

function confirmNewsletterDelete(event) {
  if (!window.confirm('Newsletter wirklich löschen?')) {
    event.preventDefault();
  }
}

function confirmNewsletterTest(event) {
  const email = event.currentTarget.querySelector('input[name="test_email"]')?.value || '';
  if (!email) {
    window.alert('Für den aktuellen Benutzer ist keine Test-E-Mail-Adresse hinterlegt.');
    event.preventDefault();
    return;
  }
  if (!window.confirm(`Test-E-Mail an ${email} senden?`)) {
    event.preventDefault();
  }
}

function confirmPriceDelete(event, hasInvoice) {
  const message = hasInvoice
    ? 'Für diesen Preis existiert bereits eine Abrechnung. Löschen kann zu Inkonsistenzen führen. Wirklich löschen?'
    : 'Diesen Preis wirklich löschen?';
  if (!window.confirm(message)) {
    event.preventDefault();
  }
}

function NativeReports({data}) {
  const report = data.report || null;
  const members = data.members || [];
  const aggregations = data.aggregations || {};
  const charts = report?.charts || {};
  const totals = report?.totals || {};
  const chartOptions = report ? createReportChartOptions(report, charts, totals) : {};

  return (
    <div className="v2-native-page v2-reports-page">
      <div className="v2-page-heading">
        <div className="v2-page-title">
          <ChartNoAxesCombined size={34} strokeWidth={1.8} />
          <h2>Energieberichte</h2>
        </div>
      </div>

      <Card className="v2-native-card v2-reports-card" padding={0}>
        <form className="v2-report-form" method="get" action="/v2/reports">
          <FormSelector
            name="member_id"
            label="Teilnehmer"
            defaultValue={data.selected_member?.id || ''}
            options={members.map((member) => ({value: String(member.id), label: member.name}))}
            hasSearch={members.length > 8}
            searchPlaceholder="Mitglied suchen..."
          />
          <FormDateInput name="date_from" label="Von" defaultValue={data.period_from} min={data.min_date} max={data.max_date} />
          <FormDateInput name="date_to" label="Bis" defaultValue={data.period_to} min={data.min_date} max={data.max_date} />
          <FormSelector
            name="aggregation"
            label="Ansicht"
            defaultValue={data.aggregation}
            options={Object.entries(aggregations).map(([key, cfg]) => ({value: key, label: cfg.label}))}
          />
          <button type="submit" className="v2-primary-action v2-submit-action">
            <ChartNoAxesCombined size={20} />
            <span>Anzeigen</span>
          </button>
        </form>
      </Card>

      {!report ? (
        <Card className="v2-native-card v2-reports-card" padding={0}>
          <EmptyState text="Für den gewählten Zeitraum sind keine auswertbaren Messdaten vorhanden." />
        </Card>
      ) : (
        <>
          <Card className="v2-native-card v2-reports-card" padding={0}>
            <div className="v2-report-explainer">
              <div>
                <h3>Was diese Seite zeigt</h3>
                <p>
                  Die Auswertung zeigt, wie viel Strom im gewählten Zeitraum verbraucht,
                  aus der EEG bezogen, selbst erzeugt oder ins öffentliche Netz geliefert wurde.
                </p>
              </div>
              <div className="v2-report-notes">
                {(report.data_notes || []).slice(0, 3).map((note, index) => (
                  <span key={index}>{note}</span>
                ))}
              </div>
            </div>
          </Card>

          <section className="v2-report-kpis" aria-label="Report Kennzahlen">
            <ReportKpi label="Stromverbrauch" value={`${formatNumber(totals.consumption, 1)} kWh`} meta={`EEG ${formatNumber(totals.eeg, 1)} · Netz ${formatNumber(totals.grid, 1)} kWh`} />
            <ReportKpi label="Anteil aus der EEG" value={`${formatNumber(totals.eeg_share, 1)}%`} meta={`Gemeinschaft Ø ${formatNumber(report.community?.avg_eeg_share, 1)}%`} />
            <ReportKpi label="Erzeugte Energie" value={`${formatNumber(totals.generation, 1)} kWh`} meta={`An EEG ${formatNumber(totals.eeg_feed, 1)} · Netz ${formatNumber(totals.public_feed, 1)} kWh`} />
            <ReportKpi label="Geschätzter Vorteil" value={formatCurrency(totals.savings)} meta={`${formatNumber(totals.avg_savings_per_kwh, 3)} EUR/kWh Vergleich`} />
          </section>

          <section className="v2-report-grid">
            <ReportPanel title="Woher kam der Strom?" description="Zeigt, welcher Anteil Ihres Verbrauchs aus der EEG und welcher aus dem öffentlichen Netz kam." icon={ChartNoAxesCombined}>
              <HighchartsChart options={chartOptions.energySplit} />
            </ReportPanel>
            <ReportPanel title="Entwicklung über die Zeit" description="Die Fläche zeigt, wie sich Netzbezug, EEG-Bezug und Erzeugung im Zeitraum entwickelt haben." icon={Activity}>
              <HighchartsChart options={chartOptions.development} />
            </ReportPanel>
          </section>

          <section className="v2-report-grid">
            <ReportPanel title="Monatsvergleich" description="Vergleicht Verbrauch, Lieferung an die EEG und den EEG-Anteil pro Auswertungsabschnitt." icon={Database}>
              <HighchartsChart options={chartOptions.monthly} />
            </ReportPanel>
            <ReportPanel title="EEG-Anteil am Verbrauch" description="Eine einfache Gegenüberstellung: lokal aus der EEG bezogen oder aus dem öffentlichen Netz." icon={CircleCheck}>
              <HighchartsChart options={chartOptions.eegShare} />
            </ReportPanel>
          </section>

          <section className="v2-report-grid is-wide-left">
            <ReportPanel title="Wann wird am meisten Strom gebraucht?" description="Dunklere Felder bedeuten mehr Verbrauch. So sieht man typische starke Stunden nach Wochentagen." icon={Database} tall>
              <HighchartsChart options={chartOptions.heatmap} tall />
            </ReportPanel>
            <ReportPanel title="Typischer Tag" description="Der Durchschnitt je Stunde zeigt, wann der Verbrauch an einem normalen Tag eher hoch ist." icon={Clock3} tall>
              <HighchartsChart options={chartOptions.typicalDay} tall />
            </ReportPanel>
          </section>

          <section className="v2-report-grid">
            <ReportPanel title="Stromfluss einfach dargestellt" description="Diese Darstellung zeigt grob, wohin erzeugte Energie fließt und woher der Verbrauch gedeckt wurde." icon={ChartNoAxesCombined}>
              <HighchartsChart options={chartOptions.flow} />
            </ReportPanel>
            <ReportPanel title="Kosten mit und ohne EEG" description="Ein Vergleichswert, der den geschätzten finanziellen Vorteil der EEG sichtbar macht." icon={Euro}>
              <HighchartsChart options={chartOptions.cost} />
            </ReportPanel>
          </section>

          <section className="v2-report-grid">
            <ReportPanel title="Vorteil über die Zeit" description="Kumulierte Schätzung des Vorteils im gewählten Zeitraum." icon={Euro}>
              <HighchartsChart options={chartOptions.savings} />
            </ReportPanel>
            <ReportPanel title="Ihr Beitrag zur Gemeinschaft" description="Zeigt, wie viel erzeugte Energie an die EEG und wie viel ins öffentliche Netz geliefert wurde." icon={Users}>
              <HighchartsChart options={chartOptions.community} />
            </ReportPanel>
          </section>

          <section className="v2-report-grid">
            <ReportPanel title="Verbrauchsspitzen" description="Hilft zu erkennen, zu welchen Zeitpunkten der Stromverbrauch besonders hoch war." icon={Activity}>
              <HighchartsChart options={chartOptions.peaks} />
            </ReportPanel>
            <ReportPanel title="Einfache Hinweise" description="Kurze Hinweise aus den gemessenen Daten. Sie sind als Orientierung gedacht." icon={NotebookText}>
              <div className="v2-report-hints">
                {(report.optimisation_hints || []).map((hint, index) => <span className="v2-tag is-info" key={index}>{hint}</span>)}
              </div>
              <div className="v2-report-hint-meta">
                {report.best_day && <span>Höchster EEG-Anteil: {report.best_day.day} · {formatNumber(report.best_day.eeg_share, 1)}%</span>}
                {report.weakest_day && <span>Niedrigster EEG-Anteil: {report.weakest_day.day} · {formatNumber(report.weakest_day.eeg_share, 1)}%</span>}
                <span>EEG-Lieferanteil: {formatNumber(report.community?.member_generation_share, 1)}%</span>
              </div>
            </ReportPanel>
          </section>

          <section className="v2-report-grid">
            <ReportPanel title="Sind die Daten vollständig?" description="Eine schnelle Einschätzung der Datenqualität. Je vollständiger, desto belastbarer sind die Aussagen." icon={CircleCheck}>
              <HighchartsChart options={chartOptions.quality} compact />
            </ReportPanel>
            <ReportPanel title="Fehlende oder verspätete Messwerte" description="Zeigt je Monat, ob Messwerte fehlen. Das ist wichtig für verlässliche Abrechnungen." icon={Database}>
              <HighchartsChart options={chartOptions.missing} />
            </ReportPanel>
          </section>

          <Card className="v2-native-card v2-reports-card" padding={0}>
            <div className="v2-dashboard-card-title">
              <Clock3 size={24} />
              <h3>Höchste Verbrauchsmomente</h3>
            </div>
            <div className="v2-table-wrap">
              <table className="v2-native-table v2-report-table">
                <thead><tr><th>Zeitpunkt</th><th>Strommenge</th></tr></thead>
                <tbody>
                  {(report.peaks || []).length ? report.peaks.map((peak) => (
                    <tr key={peak.ts}>
                      <td>{formatDateTime(peak.ts)}</td>
                      <td className="v2-number-cell">{formatNumber(peak.kwh, 3)} kWh</td>
                    </tr>
                  )) : <tr><td colSpan="2"><EmptyState text="Keine auffälligen Spitzen gefunden." /></td></tr>}
                </tbody>
              </table>
            </div>
          </Card>
        </>
      )}
    </div>
  );
}

function ReportKpi({label, value, meta}) {
  return (
    <div className="v2-report-kpi">
      <span>{label}</span>
      <strong>{value}</strong>
      <small>{meta}</small>
    </div>
  );
}

function ReportPanel({title, description, icon: Icon, children, tall}) {
  return (
    <Card className={`v2-native-card v2-reports-card ${tall ? 'is-tall' : ''}`} padding={0}>
      <div className="v2-dashboard-card-title">
        <Icon size={24} />
        <div>
          <h3>{title}</h3>
          {description && <p>{description}</p>}
        </div>
      </div>
      <div className="v2-report-panel-body">{children}</div>
    </Card>
  );
}

let highchartsConfigured = false;

function configureHighcharts() {
  if (highchartsConfigured) return;
  highchartsConfigured = true;
  Highcharts.setOptions({
    chart: {
      backgroundColor: 'transparent',
      spacing: [10, 12, 10, 10],
      style: {fontFamily: 'Inter, ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif'},
    },
    title: {text: null},
    credits: {enabled: false},
    legend: {
      itemStyle: {color: reportChartColors.dark, fontWeight: '500', fontSize: '13px'},
      itemHoverStyle: {color: reportChartColors.teal},
    },
    xAxis: {
      lineColor: 'rgba(18,38,43,.2)',
      tickColor: 'rgba(18,38,43,.18)',
      labels: {style: reportChartText.label},
      title: {style: reportChartText.axisTitle},
    },
    yAxis: {
      gridLineColor: 'rgba(18,38,43,.08)',
      labels: {style: reportChartText.label},
      title: {style: reportChartText.axisTitle},
    },
    tooltip: {
      backgroundColor: 'rgba(255,255,255,.96)',
      borderColor: 'rgba(47,143,137,.24)',
      borderRadius: 8,
      shadow: true,
      style: {color: reportChartColors.dark, fontSize: '13px'},
    },
    plotOptions: {
      series: {
        borderRadius: 3,
        marker: {enabled: false},
        states: {inactive: {opacity: .72}},
      },
    },
  });
}

function HighchartsChart({options, tall, compact}) {
  const containerRef = useRef(null);

  useEffect(() => {
    if (!containerRef.current || !options) return undefined;
    configureHighcharts();
    const chart = Highcharts.chart(containerRef.current, options);
    return () => chart.destroy();
  }, [options]);

  return <div ref={containerRef} className={`v2-highchart ${tall ? 'is-tall' : ''} ${compact ? 'is-compact' : ''}`} />;
}

const reportChartColors = {
  dark: '#17252a',
  teal: '#2f8582',
  tealLight: '#3aafa9',
  mint: '#dff3f2',
  amber: '#d99229',
  red: '#c94747',
  blue: '#477b9e',
  green: '#4e8a7a',
};

const reportChartText = {
  label: {color: '#52666a', fontSize: '13px', fontWeight: '400'},
  axisTitle: {color: '#52666a', fontSize: '13px', fontWeight: '500'},
};

function kwhTooltip() {
  return `<span style="color:${this.color}">●</span> ${this.series.name}: <b>${Highcharts.numberFormat(this.y, 2, ',', '.')} kWh</b>`;
}

function createReportChartOptions(report, charts, totals) {
  const heatValues = (charts.heatmap || []).map((point) => Number(point[2]) || 0);
  const heatMax = Math.max(1, ...heatValues);
  const heatmapPoints = (charts.heatmap || []).map((point) => ({
    x: Number(point[0]),
    y: Number(point[1]),
    value: Number(point[2]) || 0,
  }));
  const hours = Array.from({length: 24}, (_, index) => `${index}:00`);
  const labels = charts.labels || [];

  return {
    energySplit: {
      chart: {type: 'pie'},
      tooltip: {pointFormat: '<b>{point.y:.2f} kWh</b> · {point.percentage:.1f}%'},
      plotOptions: {pie: {innerSize: '64%', dataLabels: {enabled: true, format: '{point.name}<br><b>{point.percentage:.0f}%</b>', style: {fontSize: '12px', fontWeight: '500'}}}},
      series: [{
        name: 'Stromverbrauch',
        colors: [reportChartColors.teal, reportChartColors.amber],
        data: [
          ['Strom aus der EEG', Number(totals.eeg) || 0],
          ['Strom aus dem Netz', Number(totals.grid) || 0],
        ],
      }],
    },
    development: {
      chart: {type: 'area'},
      xAxis: {categories: labels},
      yAxis: {title: {text: 'kWh'}},
      tooltip: {shared: true, pointFormatter: kwhTooltip},
      plotOptions: {area: {stacking: 'normal', fillOpacity: .24}},
      series: [
        {name: 'Strom aus der EEG', data: charts.eeg || [], color: reportChartColors.teal},
        {name: 'Strom aus dem Netz', data: charts.grid || [], color: reportChartColors.amber},
        {name: 'Selbst erzeugt', data: charts.generation || [], color: reportChartColors.tealLight, type: 'line', lineWidth: 3},
      ],
    },
    monthly: {
      chart: {zoomType: 'x'},
      xAxis: {categories: labels},
      yAxis: [{title: {text: 'kWh'}}, {title: {text: 'EEG-Anteil %'}, opposite: true, max: 100}],
      tooltip: {shared: true},
      plotOptions: {column: {stacking: 'normal'}},
      series: [
        {type: 'column', name: 'Strom aus der EEG', data: charts.eeg || [], color: reportChartColors.teal},
        {type: 'column', name: 'Strom aus dem Netz', data: charts.grid || [], color: reportChartColors.amber},
        {type: 'column', name: 'An die EEG geliefert', data: charts.eeg_feed || [], color: reportChartColors.green},
        {type: 'line', name: 'Anteil aus der EEG', data: charts.eeg_share || [], color: reportChartColors.dark, yAxis: 1, tooltip: {valueSuffix: ' %'}},
      ],
    },
    heatmap: {
      chart: {type: 'heatmap'},
      xAxis: {categories: hours, title: {text: 'Stunde'}, min: -0.5, max: 23.5, tickInterval: 2, startOnTick: false, endOnTick: false},
      yAxis: {categories: ['Mo', 'Di', 'Mi', 'Do', 'Fr', 'Sa', 'So'], title: {text: 'Wochentag'}, reversed: true, min: -0.5, max: 6.5, startOnTick: false, endOnTick: false},
      colorAxis: {
        min: 0,
        max: heatMax,
        stops: [[0, '#f6fbfa'], [0.18, '#cfece9'], [0.45, '#74c7c1'], [0.72, reportChartColors.teal], [1, reportChartColors.dark]],
      },
      tooltip: {
        formatter: function formatter() {
          return `<b>${Highcharts.numberFormat(this.point.value, 2, ',', '.')} kWh</b><br>${this.series.yAxis.categories[this.point.y]} ${this.series.xAxis.categories[this.point.x]}`;
        },
      },
      plotOptions: {heatmap: {colsize: 1, rowsize: 1, marker: {enabled: true, symbol: 'rect'}, borderWidth: 1, borderColor: 'rgba(18,38,43,.12)', nullColor: '#f4f7f6'}},
      series: [{name: 'Stromverbrauch', data: heatmapPoints, colsize: 1, rowsize: 1, dataLabels: {enabled: false}}],
    },
    typicalDay: {
      chart: {type: 'areaspline'},
      xAxis: {categories: hours},
      yAxis: {title: {text: 'Ø kWh je Stunde'}},
      tooltip: {pointFormat: '<b>{point.y:.3f} kWh</b>'},
      series: [{name: 'Typischer Stromverbrauch', data: charts.typical_day || [], color: reportChartColors.teal, fillOpacity: .22}],
    },
    eegShare: {
      chart: {type: 'pie'},
      tooltip: {pointFormat: '<b>{point.y:.2f} kWh</b> · {point.percentage:.1f}%'},
      plotOptions: {pie: {innerSize: '68%', dataLabels: {enabled: true, format: '{point.name}<br><b>{point.percentage:.0f}%</b>', style: {fontSize: '12px', fontWeight: '500'}}}},
      series: [{name: 'Stromquelle', colors: [reportChartColors.teal, reportChartColors.amber], data: [['Aus der EEG', Number(totals.eeg) || 0], ['Aus dem Netz', Number(totals.grid) || 0]]}],
    },
    flow: {
      chart: {type: 'sankey'},
      tooltip: {pointFormat: '<b>{point.weight:.2f} kWh</b>'},
      series: [{keys: ['from', 'to', 'weight'], data: (charts.sankey || []).filter((row) => row[2] > 0), colors: [reportChartColors.amber, reportChartColors.teal, reportChartColors.green, reportChartColors.blue], name: 'Stromfluss'}],
    },
    cost: {
      chart: {type: 'bar'},
      xAxis: {categories: ['Vergleich', 'Mit EEG']},
      yAxis: {title: {text: 'EUR'}},
      tooltip: {pointFormat: '<b>{point.y:.2f} €</b>'},
      series: [{name: 'Geschätzter Betrag', data: [Number(totals.cost_without) || 0, Number(totals.cost_actual) || 0], color: reportChartColors.teal}],
    },
    savings: {
      chart: {type: 'areaspline'},
      xAxis: {categories: labels},
      yAxis: {title: {text: 'EUR'}},
      tooltip: {pointFormat: '<b>{point.y:.2f} €</b>'},
      series: [{name: 'Gesamter Vorteil', data: charts.cumulative_savings || [], color: reportChartColors.green, fillOpacity: .24}],
    },
    community: {
      chart: {type: 'column'},
      xAxis: {categories: labels},
      yAxis: {title: {text: 'kWh'}},
      tooltip: {shared: true, pointFormatter: kwhTooltip},
      series: [
        {name: 'An die EEG geliefert', data: charts.eeg_feed || [], color: reportChartColors.green},
        {name: 'Ins öffentliche Netz geliefert', data: charts.public_feed || [], color: reportChartColors.amber},
      ],
    },
    peaks: {
      chart: {zoomType: 'x'},
      xAxis: {type: 'datetime'},
      yAxis: {title: {text: 'kWh je Stunde'}},
      tooltip: {xDateFormat: '%d.%m.%Y %H:%M', pointFormat: '<b>{point.y:.3f} kWh</b>'},
      series: [
        {type: 'line', name: 'Stromverbrauch pro Stunde', data: charts.peak_line || [], color: reportChartColors.teal, lineWidth: 2},
        {type: 'scatter', name: 'Höchste Werte', data: charts.peak_markers || [], color: reportChartColors.red, marker: {enabled: true, radius: 4, symbol: 'circle'}},
      ],
    },
    quality: {
      chart: {type: 'pie'},
      tooltip: {pointFormat: '<b>{point.y}</b> Werte · {point.percentage:.1f}%'},
      plotOptions: {pie: {innerSize: '58%', dataLabels: {enabled: true, format: '{point.name}: {point.percentage:.0f}%', style: {fontSize: '12px', fontWeight: '500'}}}},
      series: [{name: 'Qualität', colors: [reportChartColors.teal, reportChartColors.amber, reportChartColors.red, reportChartColors.blue], data: (charts.quality || []).map((row) => [row.quality, row.cnt])}],
      subtitle: {text: `${formatNumber(report.quality_summary?.completeness, 1)}% vollständige Messwerte`, style: {fontSize: '13px', color: '#52666a'}},
    },
    missing: {
      chart: {type: 'column'},
      xAxis: {categories: (charts.missing_by_month || []).map((row) => row.month)},
      yAxis: [{title: {text: 'Anzahl'}}, {title: {text: 'Vollständigkeit %'}, opposite: true, max: 100}],
      tooltip: {shared: true},
      series: [
        {name: 'Fehlende Messwerte', data: (charts.missing_by_month || []).map((row) => row.missing), color: reportChartColors.red},
        {type: 'line', name: 'Vollständige Daten', data: (charts.missing_by_month || []).map((row) => row.completeness), color: reportChartColors.teal, yAxis: 1, tooltip: {valueSuffix: ' %'}},
      ],
    },
  };
}

function SplitBar({items}) {
  const total = items.reduce((sum, item) => sum + (Number(item.value) || 0), 0) || 1;
  return (
    <div className="v2-split">
      <div className="v2-split-bar">
        {items.map((item) => <div key={item.label} className={`is-${item.color}`} style={{width: `${Math.max((Number(item.value) || 0) / total * 100, 3)}%`}} />)}
      </div>
      {items.map((item) => (
        <div className="v2-split-row" key={item.label}>
          <span>{item.label}</span>
          <strong>{formatNumber(item.value, 1)} kWh</strong>
        </div>
      ))}
    </div>
  );
}

function SeriesBars({labels, values, unit, accent}) {
  const max = Math.max(...values.map((value) => Math.abs(Number(value) || 0)), 1);
  const rows = labels.map((label, index) => ({label, value: Number(values[index]) || 0})).slice(-12);
  return (
    <div className="v2-series-bars">
      {rows.map((row) => (
        <div className="v2-series-row" key={row.label}>
          <span>{row.label}</span>
          <div className="v2-bar-track"><div className={`is-${accent}`} style={{width: `${Math.max(Math.abs(row.value) / max * 100, 3)}%`}} /></div>
          <strong>{unit === 'EUR' ? formatCurrency(row.value) : `${formatNumber(row.value, 1)} ${unit}`}</strong>
        </div>
      ))}
    </div>
  );
}

function HeatmapGrid({points}) {
  const values = points.map((point) => Number(point[2]) || 0);
  const max = Math.max(...values, 1);
  const lookup = new Map(points.map((point) => [`${point[0]}-${point[1]}`, Number(point[2]) || 0]));
  const days = ['Mo', 'Di', 'Mi', 'Do', 'Fr', 'Sa', 'So'];
  const hours = Array.from({length: 24}, (_, index) => index);
  return (
    <div className="v2-heatmap">
      <div />
      {hours.map((hour) => <span key={hour}>{hour % 4 === 0 ? hour : ''}</span>)}
      {days.map((day, y) => (
        <React.Fragment key={day}>
          <strong>{day}</strong>
          {hours.map((hour) => {
            const value = lookup.get(`${hour}-${y}`) || 0;
            return <i key={`${hour}-${day}`} style={{opacity: Math.max(value / max, .08)}} title={`${day} ${hour}:00 · ${formatNumber(value, 2)} kWh`} />;
          })}
        </React.Fragment>
      ))}
    </div>
  );
}

function NativeUsers({data, csrfToken}) {
  const users = data.users || [];
  const members = data.members || [];
  const contractMembers = data.contract_members || [];
  const contracts = data.contracts || [];
  const [contractFile, setContractFile] = useState(null);

  return (
    <div className="v2-native-page v2-users-page">
      <div className="v2-page-heading">
        <div className="v2-page-title">
          <UserCog size={34} strokeWidth={1.8} />
          <h2>Benutzerverwaltung</h2>
        </div>
      </div>

      <Card className="v2-native-card v2-users-card" padding={0}>
        <div className="v2-dashboard-card-title">
          <Plus size={24} />
          <h3>Neuen Benutzer anlegen</h3>
        </div>
        <form className="v2-user-form" method="post" action="/admin/users/create">
          <input type="hidden" name="csrf_token" value={csrfToken || ''} />
          <input type="hidden" name="next" value="/v2/admin/users" />
          <FormSelector
            name="member_id"
            label="Mitglied"
            defaultValue=""
            placeholder="Mitglied wählen"
            isRequired
            options={members.map((member) => ({
              value: String(member.id),
              label: `${member.name}${member.email ? ` (${member.email})` : ''}`,
            }))}
            hasSearch={members.length > 8}
            searchPlaceholder="Mitglied suchen..."
          />
          <FormSelector
            name="role"
            label="Rolle"
            defaultValue="member"
            options={[
              {value: 'member', label: 'Teilnehmer'},
              {value: 'admin', label: 'Administrator'},
            ]}
          />
          <button type="submit" className="v2-primary-action v2-submit-action" disabled={!members.length}>
            <Mail size={20} />
            <span>Anlegen & Einladung senden</span>
          </button>
        </form>
        {!members.length && <div className="v2-inline-note">Für alle aktiven Mitglieder ist bereits ein Benutzer vorhanden.</div>}
      </Card>

      <Card className="v2-native-card v2-users-card" padding={0}>
        <div className="v2-dashboard-card-title">
          <Users size={24} />
          <h3>Alle Benutzer</h3>
        </div>
        <div className="v2-table-wrap">
          <table className="v2-native-table v2-users-table">
            <thead>
              <tr>
                <th>Benutzername</th>
                <th>E-Mail-Adresse</th>
                <th>Mitglied</th>
                <th>Rolle</th>
                <th>Einladung</th>
                <th>Erstellt</th>
                <th>Aktionen</th>
              </tr>
            </thead>
            <tbody>
              {users.length ? users.map((user) => (
                <tr key={user.id}>
                  <td>
                    <strong>{user.username}</strong>
                  </td>
                  <td>
                    <form className="v2-user-email-form" method="post" action={`/admin/users/${user.id}/email`}>
                      <input type="hidden" name="csrf_token" value={csrfToken || ''} />
                      <input type="hidden" name="next" value="/v2/admin/users" />
                      <input
                        type="email"
                        name="email"
                        defaultValue={user.email || ''}
                        maxLength="254"
                        autoComplete="email"
                        aria-label={`E-Mail-Adresse für ${user.username}`}
                        placeholder="name@beispiel.at"
                      />
                      <button type="submit" className="v2-icon-action" aria-label={`E-Mail-Adresse für ${user.username} speichern`} title="E-Mail-Adresse speichern">
                        <Check size={18} />
                      </button>
                    </form>
                  </td>
                  <td>{user.member_name || '-'}</td>
                  <td>
                    <span className={`v2-tag ${user.role === 'admin' ? 'is-warning' : 'is-info'}`}>
                      {user.role === 'admin' ? 'Admin' : 'Teilnehmer'}
                    </span>
                    {user.role === 'admin' && (
                      <form method="post" action={`/admin/users/${user.id}/feedback-email`}>
                        <input type="hidden" name="csrf_token" value={csrfToken || ''} />
                        <input type="hidden" name="next" value="/v2/admin/users" />
                        <input type="hidden" name="enabled" value="0" />
                        <label className="v2-user-mail-toggle" title="Mitgliedsnachrichten per E-Mail erhalten">
                          <input type="checkbox" name="enabled" value="1" defaultChecked={Boolean(user.admin_feedback_email)} onChange={(event) => event.currentTarget.form.submit()} />
                          <span>EEG-Post per Mail</span>
                        </label>
                      </form>
                    )}
                  </td>
                  <td>
                    {user.invite_open
                      ? <span className="v2-tag is-muted">Offen</span>
                      : <span className="v2-tag is-success">Aktiv</span>}
                  </td>
                  <td>{formatDate(user.created_at)}</td>
                  <td className="v2-table-action">
                    <div className="v2-row-actions">
                      <form method="post" action={`/admin/users/${user.id}/invite`} onSubmit={(event) => confirmUserInvite(event, user.email)}>
                        <input type="hidden" name="csrf_token" value={csrfToken || ''} />
                        <input type="hidden" name="next" value="/v2/admin/users" />
                        <input type="hidden" name="invite_action" value="send" />
                        <button type="submit" className="v2-icon-action" aria-label="Einladung senden" title="Einladung senden">
                          <Mail size={18} />
                        </button>
                      </form>
                      {user.member_id && !user.invite_open && (
                        <>
                          <form method="post" action={`/admin/users/${user.id}/mobile-link`}>
                            <input type="hidden" name="csrf_token" value={csrfToken || ''} />
                            <input type="hidden" name="next" value="/v2/admin/users" />
                            <button type="submit" className="v2-icon-action" aria-label="iPhone-App verbinden" title="iPhone-App verbinden">
                              <QrCode size={18} />
                            </button>
                          </form>
                          <form method="post" action={`/admin/users/${user.id}/mobile-access/revoke`} onSubmit={(event) => {
                            if (!window.confirm(`Alle ${user.mobile_sessions || ''} App-Sitzungen dieses Benutzers widerrufen?`)) event.preventDefault();
                          }}>
                            <input type="hidden" name="csrf_token" value={csrfToken || ''} />
                            <input type="hidden" name="next" value="/v2/admin/users" />
                            <button type="submit" className="v2-icon-action is-danger" aria-label="App-Zugänge widerrufen" title="App-Zugänge widerrufen">
                              <Plug size={18} />
                            </button>
                          </form>
                        </>
                      )}
                      <form method="post" action={`/admin/users/${user.id}/toggle-role`} onSubmit={(event) => confirmUserRoleChange(event)}>
                        <input type="hidden" name="csrf_token" value={csrfToken || ''} />
                        <input type="hidden" name="next" value="/v2/admin/users" />
                        <button type="submit" className="v2-icon-action is-warning" aria-label="Rolle ändern" title="Rolle ändern">
                          <RotateCcw size={18} />
                        </button>
                      </form>
                      {Number(user.id) !== Number(data.current_user_id) && (
                        <form method="post" action={`/admin/users/${user.id}/delete`} onSubmit={(event) => confirmUserDelete(event)}>
                          <input type="hidden" name="csrf_token" value={csrfToken || ''} />
                          <input type="hidden" name="next" value="/v2/admin/users" />
                          <button type="submit" className="v2-icon-action is-danger" aria-label="Benutzer löschen" title="Löschen">
                            <Trash2 size={18} />
                          </button>
                        </form>
                      )}
                    </div>
                  </td>
                </tr>
              )) : (
                <tr><td colSpan="7"><EmptyState text="Noch keine Benutzer vorhanden." /></td></tr>
              )}
            </tbody>
          </table>
        </div>
      </Card>

      <Card className="v2-native-card v2-users-card" padding={0}>
        <div className="v2-dashboard-card-title">
          <Upload size={24} />
          <h3>Vertrag hochladen</h3>
        </div>
        <form
          className="v2-contract-form"
          method="post"
          action="/admin/contracts/upload"
          encType="multipart/form-data"
          onSubmit={(event) => submitMultipartFormWithFiles(event, [{name: 'file', files: contractFile, requiredMessage: 'Bitte eine PDF-Datei auswählen.'}])}
        >
          <input type="hidden" name="csrf_token" value={csrfToken || ''} />
          <input type="hidden" name="next" value="/v2/admin/users" />
          <FormSelector
            name="member_id"
            label="Mitglied"
            defaultValue=""
            placeholder="Mitglied wählen"
            isRequired
            options={contractMembers.map((member) => ({value: String(member.id), label: member.name}))}
            hasSearch={contractMembers.length > 8}
            searchPlaceholder="Mitglied suchen..."
          />
          <FormSelector
            name="type"
            label="Vertragstyp"
            defaultValue="bezieher"
            isRequired
            options={[
              {value: 'bezieher', label: 'Bezieher-Vertrag'},
              {value: 'einspeiser', label: 'Einspeiser-Vertrag'},
            ]}
          />
          <FormFileInput
            name="file"
            label="Datei"
            description="PDF-Vertrag auswählen."
            accept=".pdf"
            isRequired
            placeholder="PDF auswählen"
            onFilesChange={setContractFile}
          />
          <button type="submit" className="v2-primary-action v2-submit-action" disabled={!contractMembers.length}>
            <Upload size={20} />
            <span>Hochladen</span>
          </button>
        </form>
      </Card>

      <Card className="v2-native-card v2-users-card" padding={0}>
        <div className="v2-dashboard-card-title">
          <Archive size={24} />
          <h3>Hochgeladene Verträge</h3>
        </div>
        <div className="v2-table-wrap">
          <table className="v2-native-table v2-contracts-table">
            <thead>
              <tr>
                <th>Mitglied</th>
                <th>Typ</th>
                <th>Datei</th>
                <th>Hochgeladen</th>
                <th>Aktionen</th>
              </tr>
            </thead>
            <tbody>
              {contracts.length ? contracts.map((contract) => (
                <tr key={contract.id}>
                  <td><strong>{contract.member_name}</strong></td>
                  <td><span className={`v2-tag ${contract.type === 'einspeiser' ? 'is-warning' : 'is-info'}`}>{contract.type === 'einspeiser' ? 'Einspeiser' : 'Bezieher'}</span></td>
                  <td><span className="v2-file-label"><FileText size={18} />{contract.filename}</span></td>
                  <td>
                    {contract.uploaded_at || '-'}
                    {contract.uploaded_by && <small>von {contract.uploaded_by}</small>}
                  </td>
                  <td className="v2-table-action">
                    <div className="v2-row-actions">
                      <a className="v2-icon-action" href={`/contracts/${contract.id}/download`} aria-label="Vertrag öffnen" title="Vertrag öffnen">
                        <FileText size={18} />
                      </a>
                      <form method="post" action={`/contracts/${contract.id}/delete`} onSubmit={(event) => confirmContractDelete(event)}>
                        <input type="hidden" name="csrf_token" value={csrfToken || ''} />
                        <input type="hidden" name="next" value="/v2/admin/users" />
                        <button type="submit" className="v2-icon-action is-danger" aria-label="Vertrag löschen" title="Löschen">
                          <Trash2 size={18} />
                        </button>
                      </form>
                    </div>
                  </td>
                </tr>
              )) : (
                <tr><td colSpan="5"><EmptyState text="Keine Verträge vorhanden." /></td></tr>
              )}
            </tbody>
          </table>
        </div>
      </Card>
    </div>
  );
}

function confirmUserInvite(event, email) {
  const message = email
    ? `Einladung neu an ${email} senden?`
    : 'Für diesen Benutzer ist keine E-Mail-Adresse hinterlegt. Trotzdem einen neuen Einladungslink erzeugen?';
  if (!window.confirm(message)) {
    event.preventDefault();
  }
}

function confirmUserRoleChange(event) {
  if (!window.confirm('Rolle dieses Benutzers wirklich ändern?')) {
    event.preventDefault();
  }
}

function confirmUserDelete(event) {
  if (!window.confirm('Benutzer wirklich löschen?')) {
    event.preventDefault();
  }
}

function confirmContractDelete(event) {
  if (!window.confirm('Vertrag wirklich löschen?')) {
    event.preventDefault();
  }
}

function NativeAudit({data}) {
  const logs = data.logs || [];
  const stats = data.stats || {};
  const filters = data.filters || {};
  const pagination = data.pagination || {};
  const actions = data.actions || [];
  const columns = [
    {key: 'timestamp', header: 'Zeitpunkt', width: pixel(170), renderCell: (log) => (
      <span className="v2-audit-time" title={`Gespeichert: ${log.timestamp || '-'} UTC`}>{log.timestamp_display || '-'}</span>
    )},
    {key: 'username', header: 'Benutzer', width: proportional(.8, {minWidth: 150}), renderCell: (log) => <strong>{log.username || '-'}</strong>},
    {key: 'action', header: 'Aktion', width: proportional(1, {minWidth: 190}), renderCell: (log) => <span className={`v2-tag ${auditActionTone(log.action)}`}>{auditActionLabel(log.action)}</span>},
    {key: 'detail', header: 'Detail', width: proportional(2.2, {minWidth: 360}), renderCell: (log) => <span className="v2-audit-detail">{log.detail || '-'}</span>},
    {key: 'ip', header: 'IP', width: pixel(140), renderCell: (log) => <span className="v2-audit-ip">{log.ip || '-'}</span>},
  ];

  return (
    <div className="v2-native-page v2-audit-page">
      <div className="v2-page-heading">
        <div className="v2-page-title">
          <NotebookText size={34} strokeWidth={1.8} />
          <h2>Audit-Log</h2>
        </div>
      </div>

      <section className="v2-audit-stats" aria-label="Audit Kennzahlen">
        <DashboardStat icon={NotebookText} label="Einträge gesamt" value={formatNumber(stats.total_entries)} />
        <DashboardStat icon={Clock3} label="Einträge heute" value={formatNumber(stats.today_entries)} />
        <DashboardStat icon={Users} label="Aktive Benutzer heute" value={formatNumber(stats.active_users)} />
      </section>

      <Card className="v2-native-card v2-audit-card" padding={0}>
        <div className="v2-dashboard-card-title">
          <SearchIcon />
          <h3>Filter</h3>
        </div>
        <form className="v2-audit-filter" method="get" action="/v2/admin/audit">
          <FormSelector
            name="action"
            label="Aktion"
            defaultValue={filters.action || ''}
            options={[{value: '', label: 'Alle'}, ...actions.map((action) => ({value: action, label: auditActionLabel(action)}))]}
            hasSearch={actions.length > 8}
            searchPlaceholder="Aktion suchen..."
          />
          <FormTextInput name="user" label="Benutzer" defaultValue={filters.user || ''} placeholder="Name..." isOptional />
          <FormDateInput name="date_from" label="Von" defaultValue={filters.date_from || ''} hasClear />
          <FormDateInput name="date_to" label="Bis" defaultValue={filters.date_to || ''} hasClear />
          <div className="v2-audit-filter-actions">
            <button type="submit" className="v2-primary-action v2-submit-action">
              <Eye size={20} />
              <span>Filtern</span>
            </button>
            <a href="/v2/admin/audit" className="v2-action-button">
              <RotateCcw size={18} />
              <span>Zurücksetzen</span>
            </a>
          </div>
        </form>
      </Card>

      <Card className="v2-native-card v2-audit-card" padding={0}>
        <div className="v2-dashboard-card-title">
          <NotebookText size={24} />
          <div>
            <h3>Protokoll</h3>
            <p>{formatNumber(pagination.total)} Ergebnis{Number(pagination.total) === 1 ? '' : 'se'} · Anzeige in {data.timezone || 'Europe/Vienna'}</p>
          </div>
        </div>
        <div className="v2-table-wrap">
          {logs.length ? (
            <Table
              className="v2-astryx-table v2-audit-table"
              data={logs}
              columns={columns}
              idKey="id"
              density="compact"
              dividers="rows"
              hasHover
              textOverflow="wrap"
              verticalAlign="top"
            />
          ) : <EmptyState text="Keine Einträge für den gewählten Filter gefunden." />}
        </div>
        <AuditPagination pagination={pagination} filters={filters} />
      </Card>
    </div>
  );
}

function NativeBackup({data, csrfToken}) {
  const info = data.info || {};
  const settings = data.settings || {};
  const googleDrive = data.google_drive || {};
  const localBackups = data.local_backups || [];
  const driveBackups = data.drive_backups || [];
  const driveConnected = Boolean(googleDrive.connected);
  const [backupRunning, setBackupRunning] = useState(false);
  const weekdayOptions = [
    {value: '0', label: 'Montag'},
    {value: '1', label: 'Dienstag'},
    {value: '2', label: 'Mittwoch'},
    {value: '3', label: 'Donnerstag'},
    {value: '4', label: 'Freitag'},
    {value: '5', label: 'Samstag'},
    {value: '6', label: 'Sonntag'},
  ];
  const localColumns = [
    {key: 'name', header: 'Datei', width: proportional(1.7, {minWidth: 320}), renderCell: (backup) => <strong>{backup.name}</strong>},
    {key: 'kind', header: 'Typ', width: pixel(130), renderCell: (backup) => <span className={`v2-tag ${backup.kind === 'Automatisch' ? 'is-info' : 'is-muted'}`}>{backup.kind || 'Backup'}</span>},
    {key: 'created_at', header: 'Erstellt', width: pixel(170), renderCell: (backup) => backup.created_at_display || formatDateTime(backup.created_at)},
    {key: 'size', header: 'Größe', align: 'end', width: pixel(120), renderCell: (backup) => formatBytes(backup.size)},
    {key: 'actions', header: 'Aktionen', align: 'end', width: pixel(150), renderCell: (backup) => (
      <div className="v2-row-actions">
        <form method="post" action="/admin/backup/upload-drive">
          <input type="hidden" name="csrf_token" value={csrfToken || ''} />
          <input type="hidden" name="next" value="/v2/admin/backup" />
          <input type="hidden" name="backup_name" value={backup.name} />
          <button
            type="submit"
            className={`v2-icon-action ${driveConnected ? 'is-success' : 'is-disabled'}`}
            disabled={!driveConnected}
            aria-label="Nach Google Drive kopieren"
            title={driveConnected ? 'Nach Google Drive kopieren' : 'Google Drive ist nicht verbunden'}
          >
            <Upload size={18} />
          </button>
        </form>
        <form method="post" action="/admin/backup/delete" onSubmit={(event) => confirmBackupDelete(event, backup.name, 'lokal löschen')}>
          <input type="hidden" name="csrf_token" value={csrfToken || ''} />
          <input type="hidden" name="next" value="/v2/admin/backup" />
          <input type="hidden" name="backup_name" value={backup.name} />
          <button type="submit" className="v2-icon-action is-danger" aria-label="Lokales Backup löschen" title="Löschen">
            <Trash2 size={18} />
          </button>
        </form>
      </div>
    )},
  ];
  const driveColumns = [
    {key: 'name', header: 'Datei', width: proportional(1.8, {minWidth: 340}), renderCell: (backup) => <strong>{backup.name}</strong>},
    {key: 'created_at', header: 'Erstellt', width: pixel(170), renderCell: (backup) => backup.created_at_display || formatDateTime(backup.created_at)},
    {key: 'size', header: 'Größe', align: 'end', width: pixel(120), renderCell: (backup) => formatBytes(backup.size)},
    {key: 'actions', header: 'Aktionen', align: 'end', width: pixel(150), renderCell: (backup) => (
      <div className="v2-row-actions">
        {backup.web_view_link && (
          <a className="v2-icon-action" href={backup.web_view_link} target="_blank" rel="noopener" aria-label="In Google Drive öffnen" title="In Google Drive öffnen">
            <ExternalLink size={18} />
          </a>
        )}
        <form method="post" action="/admin/backup/google/delete" onSubmit={(event) => confirmBackupDelete(event, backup.name, 'aus Google Drive entfernen')}>
          <input type="hidden" name="csrf_token" value={csrfToken || ''} />
          <input type="hidden" name="next" value="/v2/admin/backup" />
          <input type="hidden" name="drive_file_id" value={backup.id} />
          <button type="submit" className="v2-icon-action is-danger" aria-label="Google Drive Backup löschen" title="Aus Drive löschen">
            <Trash2 size={18} />
          </button>
        </form>
      </div>
    )},
  ];

  return (
    <div className="v2-native-page v2-backup-page">
      <div className="v2-page-heading">
        <div className="v2-page-title">
          <Archive size={34} strokeWidth={1.8} />
          <h2>Backup & Wiederherstellung</h2>
        </div>
        <div className="v2-page-actions">
          <form method="post" action="/admin/backup/run" onSubmit={() => setBackupRunning(true)}>
            <input type="hidden" name="csrf_token" value={csrfToken || ''} />
            <input type="hidden" name="next" value="/v2/admin/backup" />
            <button type="submit" className="v2-primary-action">
              <Plus size={20} />
              <span>Lokales Backup</span>
            </button>
          </form>
          <a className="v2-action-button" href="/backup">
            <Download size={18} />
            <span>Sofort-Download</span>
          </a>
          <a className="v2-action-button" href="/admin/backup">
            <Settings size={18} />
            <span>Konfiguration</span>
          </a>
        </div>
      </div>

      <StatusBannerStack>
        {backupRunning && (
          <Banner
            status="info"
            title="Backup läuft"
            description="Die Sicherung wird erstellt. Bitte warten, bis die Seite neu geladen wurde."
            container="section"
          >
            <ProcessingStatus label="Backup läuft" description="Datenbank, Rechnungsdateien und relevante Anwendungsdaten werden gepackt." />
          </Banner>
        )}
        {googleDrive.error && (
          <Banner
            status="error"
            title="Google Drive konnte nicht verbunden werden"
            description={googleDrive.error}
            container="section"
          />
        )}
        {data.drive_backups_error && (
          <Banner
            status="error"
            title="Google Drive Backups konnten nicht geladen werden"
            description={data.drive_backups_error}
            container="section"
          />
        )}
        {!googleDrive.error && !data.drive_backups_error && (
          <Banner
            status={driveConnected ? 'success' : 'warning'}
            title={driveConnected ? 'Google Drive verbunden' : 'Google Drive nicht verbunden'}
            description={driveConnected
              ? 'Lokale Backups können zusätzlich nach Google Drive kopiert und dort verwaltet werden.'
              : googleDrive.client_configured
                ? 'OAuth ist vorbereitet. Verbinde Google Drive, damit Sicherungskopien extern abgelegt werden können.'
                : 'OAuth ist noch nicht vollständig eingerichtet. Ohne Verbindung bleiben Backups nur lokal.'}
            container="section"
            isDismissable={driveConnected}
          />
        )}
      </StatusBannerStack>

      <section className="v2-backup-summary" aria-label="Backup Status">
        <DashboardStat icon={Database} label="Datenbank" value={formatBytes(info.db_size)} />
        <DashboardStat icon={FileText} label="Rechnungsdateien" value={formatNumber(info.invoice_count)} />
        <DashboardStat icon={Archive} label="PDF-Speicher" value={formatBytes(info.invoice_size)} />
        <DashboardStat
          icon={Upload}
          label="Google Drive"
          value={<StatusLine variant={driveConnected ? 'success' : 'warning'} label={driveConnected ? 'Google Drive verbunden' : 'Google Drive nicht verbunden'}>{driveConnected ? 'Verbunden' : 'Nicht verbunden'}</StatusLine>}
        />
      </section>

      <Card className="v2-native-card v2-backup-card" padding={0}>
        <div className="v2-dashboard-card-title">
          <Settings size={24} />
          <div>
            <h3>Backup-Konfiguration</h3>
            <p>Zeitplan, Aufbewahrung, Mail-Backup und Google-Drive-Kopie.</p>
          </div>
        </div>
        <form className="v2-backup-settings-form" method="post" action="/admin/backup/settings">
          <input type="hidden" name="csrf_token" value={csrfToken || ''} />
          <input type="hidden" name="next" value="/v2/admin/backup" />

          <div className="v2-form-section">
            <FormSwitch
              name="backup_auto_enabled"
              label="Automatisches Backup"
              description="Erstellt täglich ein lokales Backup nach Zeitplan."
              defaultChecked={settings.auto_enabled}
            />
            <FormTextInput
              name="backup_auto_time"
              label="Zeitpunkt"
              defaultValue={settings.auto_time || '02:00'}
              placeholder="02:00"
              labelTooltip="Format: HH:MM"
            />
          </div>

          <div className="v2-form-section is-four">
            <FormNumberInput name="backup_retention_daily" label="Täglich" defaultValue={settings.retention_daily ?? 3} min={0} max={31} isIntegerOnly units="Tage" />
            <FormNumberInput name="backup_retention_weekly" label="Wöchentlich" defaultValue={settings.retention_weekly ?? 4} min={0} max={104} isIntegerOnly units="Wochen" />
            <FormNumberInput name="backup_retention_monthly" label="Monatlich" defaultValue={settings.retention_monthly ?? 6} min={0} max={120} isIntegerOnly units="Monate" />
            <FormNumberInput name="backup_retention_yearly" label="Jährlich" defaultValue={settings.retention_yearly ?? 3} min={0} max={20} isIntegerOnly units="Jahre" />
          </div>

          <div className="v2-form-section is-four">
            <FormSwitch
              name="backup_email_enabled"
              label="Wöchentliches Mail-Backup"
              description="Sendet eine ZIP-Kopie per E-Mail."
              defaultChecked={settings.email_enabled}
            />
            <FormSelector
              name="backup_email_weekday"
              label="Wochentag"
              defaultValue={String(settings.email_weekday ?? 6)}
              options={weekdayOptions}
            />
            <FormTextInput name="backup_email_time" label="Uhrzeit" defaultValue={settings.email_time || '03:00'} placeholder="03:00" />
            <FormNumberInput name="backup_email_max_mb" label="Max. Größe" defaultValue={settings.email_max_mb ?? 20} min={1} max={2000} isIntegerOnly units="MB" />
          </div>

          <div className="v2-form-section">
            <FormTextInput name="backup_email_to" label="Empfänger E-Mail" type="email" defaultValue={settings.email_to || ''} placeholder="backup@example.org" />
            <FormTextInput name="backup_drive_folder_id" label="Google Drive Ordner-ID" defaultValue={settings.drive_folder_id || ''} placeholder="Leer = Meine Ablage" isOptional />
            <FormSwitch
              name="backup_drive_enabled"
              label="Automatisch nach Google Drive kopieren"
              description={driveConnected ? 'Nach jedem automatischen Backup wird eine Kopie hochgeladen.' : 'Google Drive muss zuerst verbunden werden.'}
              defaultChecked={settings.drive_enabled && driveConnected}
              isDisabled={!driveConnected}
              disabledMessage="Google Drive ist noch nicht verbunden."
            />
          </div>

          <div className="v2-form-actions">
            <button type="submit" className="v2-primary-action v2-submit-action">
              <Check size={20} />
              <span>Konfiguration speichern</span>
            </button>
          </div>
        </form>
      </Card>

      <Card className="v2-native-card v2-backup-card" padding={0}>
        <div className="v2-dashboard-card-title">
          <Archive size={24} />
          <div>
            <h3>Lokale Backups</h3>
            <p>{formatNumber(localBackups.length)} Datei{localBackups.length === 1 ? '' : 'en'} · automatische Sicherung {settings.auto_enabled ? `aktiv um ${settings.auto_time}` : 'inaktiv'}</p>
          </div>
        </div>
        <div className="v2-table-wrap">
          {localBackups.length ? (
            <Table
              className="v2-astryx-table v2-backup-table"
              data={localBackups}
              columns={localColumns}
              idKey="name"
              density="compact"
              dividers="rows"
              hasHover
              textOverflow="wrap"
              verticalAlign="top"
            />
          ) : <EmptyState text="Noch keine lokalen Backups vorhanden." />}
        </div>
      </Card>

      <Card className="v2-native-card v2-backup-card" padding={0}>
        <div className="v2-dashboard-card-title">
          <Upload size={24} />
          <div>
            <h3>Google Drive Backups</h3>
            <p>{driveConnected ? `${formatNumber(driveBackups.length)} Datei${driveBackups.length === 1 ? '' : 'en'} gefunden` : 'Google Drive ist noch nicht verbunden'}</p>
          </div>
        </div>
        {!driveConnected && (
          <div className="v2-backup-drive-hint">
            <span className={`v2-tag ${googleDrive.client_configured ? 'is-info' : 'is-warning'}`}>{googleDrive.client_configured ? 'OAuth eingerichtet' : 'OAuth fehlt'}</span>
            <a className="v2-action-button" href="/admin/backup/google/connect?next=/v2/admin/backup">
              <ExternalLink size={18} />
              <span>Google Drive verbinden</span>
            </a>
          </div>
        )}
        <div className="v2-table-wrap">
          {driveConnected && driveBackups.length ? (
            <Table
              className="v2-astryx-table v2-backup-table"
              data={driveBackups}
              columns={driveColumns}
              idKey="id"
              density="compact"
              dividers="rows"
              hasHover
              textOverflow="wrap"
              verticalAlign="top"
            />
          ) : driveConnected ? <EmptyState text="Keine Google Drive Backups gefunden." /> : null}
        </div>
      </Card>
    </div>
  );
}

function SearchIcon() {
  return <Eye size={24} />;
}

function AuditPagination({pagination, filters}) {
  const page = Number(pagination.page) || 1;
  const totalPages = Number(pagination.total_pages) || 0;
  if (totalPages <= 1) return null;
  const pages = [];
  const start = Math.max(1, page - 2);
  const end = Math.min(totalPages, page + 2);
  for (let current = start; current <= end; current += 1) {
    pages.push(current);
  }
  return (
    <nav className="v2-pagination" aria-label="Audit-Log Seiten">
      <a className={page <= 1 ? 'is-disabled' : ''} href={auditPageHref(page - 1, filters)}>Zurück</a>
      {pages.map((current) => (
        <a key={current} className={current === page ? 'is-active' : ''} href={auditPageHref(current, filters)}>{current}</a>
      ))}
      <a className={page >= totalPages ? 'is-disabled' : ''} href={auditPageHref(page + 1, filters)}>Weiter</a>
    </nav>
  );
}

function auditPageHref(page, filters) {
  const params = new URLSearchParams();
  params.set('page', String(Math.max(1, page)));
  Object.entries(filters || {}).forEach(([key, value]) => {
    if (value) params.set(key, value);
  });
  return `/v2/admin/audit?${params.toString()}`;
}

function auditActionLabel(action) {
  const labels = {
    login: 'Anmeldung',
    login_failed: 'Login fehlgeschlagen',
    logout: 'Abmeldung',
    page_view: 'Seitenaufruf',
    password_change: 'Passwort geändert',
    import: 'Datenimport',
    member_create: 'Mitglied angelegt',
    member_edit: 'Mitglied bearbeitet',
    member_delete: 'Mitglied deaktiviert',
    price_create: 'Preis angelegt',
    price_edit: 'Preis bearbeitet',
    price_delete: 'Preis gelöscht',
    invoice_create: 'Abrechnung erstellt',
    invoice_send: 'E-Mail gesendet',
    invoice_send_all: 'Alle E-Mails gesendet',
    invoice_send_blocked: 'Versand blockiert',
    invoice_finalize: 'Abrechnung finalisiert',
    invoice_finalize_blocked: 'Abschluss blockiert',
    pdf_download: 'PDF heruntergeladen',
    pdf_access_denied: 'PDF-Zugriff verweigert',
    payment_paid: 'Zahlung gebucht',
    payment_unpaid: 'Zahlung storniert',
    payment_paid_failed: 'Zahlung fehlgeschlagen',
    payment_unpaid_failed: 'Storno fehlgeschlagen',
    user_create: 'Benutzer angelegt',
    user_delete: 'Benutzer gelöscht',
    user_role_change: 'Rolle geändert',
    user_reinvite: 'Einladung erneuert',
    contract_upload: 'Vertrag hochgeladen',
    contract_download: 'Vertrag heruntergeladen',
    contract_delete: 'Vertrag gelöscht',
    invite_accept: 'Einladung angenommen',
    settings_update: 'Einstellungen geändert',
    backup_manual: 'Backup erstellt',
    backup_auto: 'Auto-Backup',
    backup_delete: 'Backup gelöscht',
    backup_download: 'Backup heruntergeladen',
    backup_restore: 'Backup wiederhergestellt',
    backup_drive_connect: 'Google Drive verbunden',
    backup_drive_disconnect: 'Google Drive getrennt',
    backup_drive_upload: 'Drive-Upload',
    backup_drive_failed: 'Drive-Upload fehlgeschlagen',
    backup_drive_delete: 'Drive-Backup gelöscht',
    database_quality_check: 'DB-Qualitätscheck',
    database_maintenance: 'DB-Wartung',
    portal_data_update: 'Stammdaten aktualisiert',
    newsletter_create: 'Newsletter erstellt',
    newsletter_edit: 'Newsletter bearbeitet',
    newsletter_send: 'Newsletter versendet',
    newsletter_test: 'Newsletter-Test',
    newsletter_delete: 'Newsletter gelöscht',
    newsletter_optout: 'Newsletter abbestellt',
    newsletter_optin: 'Newsletter abonniert',
  };
  return labels[action] || action || 'Unbekannt';
}

function auditActionTone(action) {
  const value = String(action || '');
  if (value.includes('failed') || value.includes('denied') || value.includes('blocked')) return 'is-danger';
  if (value.includes('delete') || value.includes('logout') || value.includes('unpaid')) return 'is-warning';
  if (value.includes('login') || value.includes('accept') || value.includes('paid') || value.includes('connect')) return 'is-success';
  if (value.includes('backup') || value.includes('database')) return 'is-muted';
  return 'is-info';
}

function NativeMemberForm({data, csrfToken}) {
  const member = data.member || {};
  const isEdit = data.mode === 'edit';
  return (
    <div className="v2-native-page v2-member-form-page">
      <div className="v2-page-heading">
        <div className="v2-page-title">
          <Users size={34} strokeWidth={1.8} />
          <h2>{isEdit ? 'Mitglied bearbeiten' : 'Neues Mitglied'}</h2>
        </div>
      </div>
      <Card className="v2-native-card v2-settings-card" padding={0}>
        <div className="v2-dashboard-card-title">
          <UserCog size={24} />
          <div>
            <h3>Stammdaten</h3>
            <p>Kontakt, Zählpunkte, Teilnahmefaktor und Zahlungsdaten.</p>
          </div>
        </div>
        <form className="v2-settings-form" method="post" action={isEdit ? `/v2/members/${member.id}/edit` : '/v2/members/new'} onSubmit={(event) => confirmMemberSave(event, isEdit, member.name)}>
          <input type="hidden" name="csrf_token" value={csrfToken || ''} />
          <div className="v2-form-block-title">Kontakt</div>
          <div className="v2-form-section">
            <FormTextInput name="name" label="Name" defaultValue={member.name || ''} isRequired />
            <FormTextInput name="email" label="E-Mail" type="email" defaultValue={member.email || ''} isOptional />
            <FormTextInput name="phone" label="Telefon" defaultValue={member.phone || ''} isOptional />
          </div>
          <div className="v2-form-section">
            <FormTextInput name="address_street" label="Straße" defaultValue={member.address_street || ''} isOptional />
            <FormTextInput name="address_zip" label="PLZ" defaultValue={member.address_zip || ''} isOptional />
            <FormTextInput name="address_city" label="Ort" defaultValue={member.address_city || ''} isOptional />
          </div>
          <div className="v2-form-block-title">Zählpunkte</div>
          <div className="v2-form-section">
            <FormTextInput name="bezug_zp" label="Bezug-Zählpunkt" defaultValue={member.bezug_zp || ''} placeholder="AT00 0000 0000 0000 0000" isOptional />
            <FormDateInput name="bezug_ab" label="Bezug ab" defaultValue={member.bezug_ab || ''} />
          </div>
          <div className="v2-form-section">
            <FormTextInput name="einspeiser_zp" label="Einspeiser-Zählpunkt" defaultValue={member.einspeiser_zp || ''} placeholder="AT00 0000 0000 0000 0000" isOptional />
            <FormDateInput name="einspeiser_ab" label="Einspeiser ab" defaultValue={member.einspeiser_ab || ''} />
          </div>
          <div className="v2-form-section">
            <FormNumberInput name="teilnahme" label="Teilnahmefaktor" defaultValue={member.teilnahme ?? 1} min={0} max={1} step={0.01} />
            {isEdit && (
              <FormSwitch name="active" label="Mitglied aktiv" description="Inaktive Mitglieder werden in der Abrechnung nicht mehr als aktiv geführt." defaultChecked={Boolean(member.active)} />
            )}
          </div>
          <div className="v2-form-block-title">Bankdaten</div>
          <div className="v2-form-section">
            <FormTextInput name="account_holder" label="Kontoinhaber" defaultValue={member.account_holder || ''} isOptional />
            <FormTextInput name="iban" label="IBAN" defaultValue={member.iban || ''} isOptional />
            <FormTextInput name="bic" label="BIC" defaultValue={member.bic || ''} isOptional />
          </div>
          <div className="v2-form-block-title">Newsletter</div>
          <div className="v2-form-section">
            <FormSwitch
              name="newsletter_enabled"
              label="Newsletter erhalten"
              description={member.newsletter_optout ? 'Mitglied erhält aktuell keine Newsletter-E-Mails.' : 'Mitglied erhält Newsletter-E-Mails.'}
              defaultChecked={!isEdit || !member.newsletter_optout}
            />
          </div>
          <div className="v2-form-actions">
            <button type="submit" className="v2-primary-action v2-submit-action">
              <Check size={20} />
              <span>Speichern</span>
            </button>
            <a href="/v2/members" className="v2-action-button"><X size={18} /><span>Abbrechen</span></a>
          </div>
        </form>
        {isEdit && (
          <form className="v2-danger-form" method="post" action={`/members/${member.id}/delete`} onSubmit={(event) => confirmMemberDeactivate(event, member.name)}>
            <input type="hidden" name="csrf_token" value={csrfToken || ''} />
            <input type="hidden" name="next" value="/v2/members" />
            <button type="submit" className="v2-action-button is-danger"><Trash2 size={18} /><span>Mitglied deaktivieren</span></button>
          </form>
        )}
      </Card>
    </div>
  );
}

function NativePriceEdit({data, csrfToken}) {
  const price = data.price || {};
  const invoice = data.invoice;
  return (
    <div className="v2-native-page v2-price-edit-page">
      <div className="v2-page-heading">
        <div className="v2-page-title">
          <Euro size={34} strokeWidth={1.8} />
          <h2>Preis bearbeiten</h2>
        </div>
      </div>
      {invoice && (
        <Banner
          status="warning"
          title={`Abrechnung #${invoice.id} nutzt diesen Zeitraum`}
          description="Nach Preisänderungen muss die betroffene Abrechnung neu berechnet werden."
          container="section"
        />
      )}
      <Card className="v2-native-card v2-prices-card" padding={0}>
        <div className="v2-dashboard-card-title">
          <Euro size={24} />
          <h3>Preiszeitraum</h3>
        </div>
        <form className="v2-price-form" method="post" action={`/v2/prices/${price.id}/edit`} onSubmit={(event) => confirmPriceEdit(event, Boolean(invoice))}>
          <input type="hidden" name="csrf_token" value={csrfToken || ''} />
          <FormDateInput name="valid_from" label="Gültig von" defaultValue={price.valid_from || ''} isRequired />
          <FormDateInput name="valid_to" label="Gültig bis" defaultValue={price.valid_to || ''} isRequired />
          <FormNumberInput name="price_consumption" label="Verbrauch" defaultValue={price.price_consumption ?? 10} step={0.1} units="ct/kWh" isRequired />
          <FormNumberInput name="price_generation" label="Erzeugung" defaultValue={price.price_generation ?? 8} step={0.1} units="ct/kWh" isRequired />
          <FormTextInput name="description" label="Beschreibung" defaultValue={price.description || ''} isOptional />
          <button type="submit" className="v2-primary-action v2-submit-action">
            <Check size={20} />
            <span>Preis speichern</span>
          </button>
          <a href="/v2/prices" className="v2-action-button"><X size={18} /><span>Abbrechen</span></a>
        </form>
      </Card>
    </div>
  );
}

function NativeNewsletterForm({data, csrfToken}) {
  const newsletter = data.newsletter || {};
  const isEdit = data.mode === 'edit';
  const [body, setBody] = useState(newsletter.body_html || '');
  return (
    <div className="v2-native-page v2-newsletter-form-page">
      <div className="v2-page-heading">
        <div className="v2-page-title">
          <Mail size={34} strokeWidth={1.8} />
          <h2>{isEdit ? 'Newsletter bearbeiten' : 'Neuer Newsletter'}</h2>
        </div>
      </div>
      {newsletter.sent_at && (
        <Banner status="warning" title="Newsletter wurde bereits versendet" description="Bereits versendete Newsletter können nicht mehr bearbeitet werden." container="section" />
      )}
      <Card className="v2-native-card v2-newsletter-card" padding={0}>
        <div className="v2-dashboard-card-title">
          <Mail size={24} />
          <div>
            <h3>Inhalt</h3>
            <p>HTML ist erlaubt und wird serverseitig bereinigt.</p>
          </div>
        </div>
        <form className="v2-newsletter-editor-form" method="post" action={isEdit ? `/v2/newsletter/${newsletter.id}/edit` : '/v2/newsletter/new'} onSubmit={(event) => confirmNewsletterSave(event)}>
          <input type="hidden" name="csrf_token" value={csrfToken || ''} />
          <FormTextInput name="subject" label="Betreff" defaultValue={newsletter.subject || ''} placeholder="z.B. EEG Neuigkeiten - Juli 2026" isRequired />
          <FormTextArea name="body_html" label="Inhalt (HTML)" defaultValue={body} rows={13} onChange={setBody} isRequired />
          <div className="v2-newsletter-preview-box">
            <strong>Live-Vorschau</strong>
            <div dangerouslySetInnerHTML={{__html: body || '<p>Noch kein Inhalt.</p>'}} />
          </div>
          <div className="v2-form-actions">
            <button type="submit" className="v2-primary-action v2-submit-action" disabled={Boolean(newsletter.sent_at)}>
              <Check size={20} />
              <span>Newsletter speichern</span>
            </button>
            <a href="/v2/newsletter" className="v2-action-button"><X size={18} /><span>Abbrechen</span></a>
          </div>
        </form>
      </Card>
    </div>
  );
}

function NativeNewsletterPreview({data}) {
  const newsletter = data.newsletter || {};
  return (
    <div className="v2-native-page v2-newsletter-preview-page">
      <div className="v2-page-heading">
        <div className="v2-page-title">
          <Eye size={34} strokeWidth={1.8} />
          <h2>Newsletter Vorschau</h2>
        </div>
        <div className="v2-page-actions">
          <a href={`/v2/newsletter/${newsletter.id}/edit`} className="v2-action-button"><Pencil size={18} /><span>Bearbeiten</span></a>
          <a href="/v2/newsletter" className="v2-action-button"><X size={18} /><span>Zurück</span></a>
        </div>
      </div>
      <Card className="v2-native-card v2-newsletter-preview-card" padding={0}>
        <div className="v2-dashboard-card-title">
          <Mail size={24} />
          <h3>{newsletter.subject}</h3>
        </div>
        <iframe className="v2-newsletter-preview-frame" title="Newsletter Vorschau" srcDoc={data.html || ''} />
      </Card>
    </div>
  );
}

function NativeChangePassword({csrfToken, user}) {
  const target = user?.role === 'admin' ? '/v2/' : '/v2/portal';
  return (
    <div className="v2-native-page v2-password-page">
      <div className="v2-page-heading">
        <div className="v2-page-title">
          <KeyIcon />
          <h2>Passwort ändern</h2>
        </div>
      </div>
      <Card className="v2-native-card v2-password-card" padding={0}>
        <div className="v2-dashboard-card-title">
          <KeyIcon />
          <div>
            <h3>Neues Passwort setzen</h3>
            <p>Mindestens 12 Zeichen. Eine Passphrase aus mehreren Wörtern ist sicher und leicht zu merken.</p>
          </div>
        </div>
        <form className="v2-settings-form" method="post" action="/v2/change-password">
          <input type="hidden" name="csrf_token" value={csrfToken || ''} />
          <div className="v2-form-section">
            <FormTextInput name="old_password" label="Altes Passwort" type="password" isRequired />
            <FormTextInput name="new_password" label="Neues Passwort" type="password" minLength={12} isRequired />
            <FormTextInput name="confirm_password" label="Neues Passwort bestätigen" type="password" minLength={12} isRequired />
          </div>
          <div className="v2-form-actions">
            <button type="submit" className="v2-primary-action v2-submit-action">
              <Check size={20} />
              <span>Passwort ändern</span>
            </button>
            <a href={target} className="v2-action-button"><X size={18} /><span>Abbrechen</span></a>
          </div>
        </form>
      </Card>
    </div>
  );
}

function KeyIcon() {
  return <Command size={24} />;
}

function confirmMemberSave(event, isEdit, name) {
  const message = isEdit ? `Änderungen an "${name || 'Mitglied'}" speichern?` : 'Neues Mitglied anlegen?';
  if (!window.confirm(message)) event.preventDefault();
}

function confirmMemberDeactivate(event, name) {
  if (!window.confirm(`Mitglied "${name || ''}" wirklich deaktivieren? Das Mitglied wird nicht gelöscht, sondern als inaktiv markiert.`)) {
    event.preventDefault();
  }
}

function confirmPriceEdit(event, hasInvoice) {
  const message = hasInvoice
    ? 'Preis speichern? Für diesen Zeitraum existiert bereits eine Abrechnung und sie muss danach neu berechnet werden.'
    : 'Preisänderung speichern?';
  if (!window.confirm(message)) event.preventDefault();
}

function confirmNewsletterSave(event) {
  if (!window.confirm('Newsletter speichern?')) event.preventDefault();
}

function NativeSettings({data, csrfToken}) {
  const settings = data.settings || {};
  const mailErrors = data.mail_errors || [];
  return (
    <div className="v2-native-page v2-settings-page">
      <div className="v2-page-heading">
        <div className="v2-page-title">
          <Settings size={34} strokeWidth={1.8} />
          <h2>Einstellungen</h2>
        </div>
      </div>
      <StatusBannerStack>
        <Banner
          status={data.smtp_configured ? 'success' : 'warning'}
          title={data.smtp_configured ? 'E-Mail-Versand ist konfiguriert' : 'E-Mail-Konfiguration unvollständig'}
          description={data.smtp_configured ? 'SMTP- und Absenderdaten sind vollständig.' : (mailErrors.join(' ') || 'Bitte SMTP-Server, Absender und Antwortadresse prüfen.')}
          container="section"
        />
      </StatusBannerStack>
      <Card className="v2-native-card v2-settings-card" padding={0}>
        <div className="v2-dashboard-card-title">
          <Mail size={24} />
          <div>
            <h3>Mail, Verein & Zahlungskonto</h3>
            <p>Diese Daten werden für Rechnungen, Newsletter und öffentliche Kontaktangaben verwendet.</p>
          </div>
        </div>
        <form className="v2-settings-form" method="post" action="/v2/settings">
          <input type="hidden" name="csrf_token" value={csrfToken || ''} />
          <div className="v2-form-block-title">SMTP</div>
          <div className="v2-form-section is-four">
            <FormTextInput name="smtp_host" label="SMTP Server" defaultValue={settings.smtp_host || ''} placeholder="smtp.example.org" />
            <FormNumberInput name="smtp_port" label="Port" defaultValue={settings.smtp_port || 587} min={1} max={65535} isIntegerOnly />
            <FormTextInput name="smtp_user" label="Benutzer" defaultValue={settings.smtp_user || ''} isOptional />
            <FormTextInput name="smtp_pass" label="Passwort" type="password" defaultValue="" placeholder={settings.smtp_pass ? 'Gespeichert, leer lassen zum Behalten' : ''} isOptional />
          </div>
          <div className="v2-form-section">
            <FormTextInput name="smtp_from" label="SMTP Absender" defaultValue={settings.smtp_from || ''} type="email" isOptional />
            <FormSelector
              name="smtp_tls"
              label="SMTP TLS"
              defaultValue={settings.smtp_tls || 'starttls'}
              options={[
                {value: 'starttls', label: 'Aktiv (STARTTLS)'},
                {value: 'ssl', label: 'SSL/TLS'},
                {value: 'none', label: 'Aus'},
              ]}
            />
          </div>
          <div className="v2-form-block-title">Absender</div>
          <div className="v2-form-section">
            <FormTextInput name="mail_from_address" label="Absender E-Mail" type="email" defaultValue={settings.mail_from_address || ''} />
            <FormTextInput name="mail_from_name" label="Absendername" defaultValue={settings.mail_from_name || ''} />
            <FormTextInput name="mail_reply_to" label="Antwort an" type="email" defaultValue={settings.mail_reply_to || ''} />
            <FormTextInput name="mail_reply_to_name" label="Antwortname" defaultValue={settings.mail_reply_to_name || ''} />
          </div>
          <div className="v2-form-block-title">Verein</div>
          <div className="v2-form-section">
            <FormTextInput name="org_name" label="EEG Bezeichnung" defaultValue={settings.org_name || ''} />
            <FormTextInput name="org_email" label="Kontakt E-Mail" type="email" defaultValue={settings.org_email || ''} isOptional />
            <FormTextInput name="org_website" label="Website" defaultValue={settings.org_website || ''} isOptional />
          </div>
          <div className="v2-form-section">
            <FormTextInput name="org_legal" label="Vereinsdaten / ZVR" defaultValue={settings.org_legal || ''} />
            <FormTextInput name="org_address" label="Adresse" defaultValue={settings.org_address || ''} />
          </div>
          <div className="v2-form-block-title">Zahlungskonto</div>
          <div className="v2-form-section">
            <FormTextInput name="payment_recipient" label="Empfänger" defaultValue={settings.payment_recipient || ''} isOptional />
            <FormTextInput name="payment_iban" label="IBAN" defaultValue={settings.payment_iban || ''} isOptional />
            <FormTextInput name="payment_bic" label="BIC" defaultValue={settings.payment_bic || ''} isOptional />
          </div>
          <div className="v2-form-block-title">Standard-Mail für Abrechnungen</div>
          <div className="v2-form-section">
            <FormTextInput name="email_subject" label="Betreff" defaultValue={settings.email_subject || ''} />
            <FormTextArea name="email_body" label="Nachricht" defaultValue={settings.email_body || ''} rows={7} />
          </div>
          <div className="v2-form-actions">
            <button type="submit" className="v2-primary-action v2-submit-action">
              <Check size={20} />
              <span>Einstellungen speichern</span>
            </button>
          </div>
        </form>
      </Card>
    </div>
  );
}

function NativeDatabase({data, csrfToken}) {
  const stats = data.stats || {};
  const tables = stats.tables || [];
  const checkResult = data.check_result;
  const maintenanceResult = data.maintenance_result;
  const tableColumns = [
    {key: 'name', header: 'Tabelle', width: proportional(1, {minWidth: 260}), renderCell: (row) => <strong>{row.name}</strong>},
    {key: 'count', header: 'Datensätze', align: 'end', width: pixel(160), renderCell: (row) => formatNumber(row.count)},
  ];
  return (
    <div className="v2-native-page v2-database-page">
      <div className="v2-page-heading">
        <div className="v2-page-title">
          <Database size={34} strokeWidth={1.8} />
          <h2>Datenbank</h2>
        </div>
      </div>
      <section className="v2-dashboard-stats" aria-label="Datenbank Kennzahlen">
        <DashboardStat icon={Database} label="Datenbankgröße" value={formatBytes(stats.db_size)} />
        <DashboardStat icon={Archive} label="WAL-Datei" value={formatBytes(stats.wal_size)} />
        <DashboardStat icon={Activity} label="Freie Seiten" value={formatNumber(stats.freelist_count)} />
        <DashboardStat icon={RefreshCw} label="Fragmentierung" value={`${formatNumber(stats.fragmentation_mb, 2)} MB`} />
      </section>
      <Card className="v2-native-card v2-database-card" padding={0}>
        <div className="v2-dashboard-card-title">
          <CircleCheck size={24} />
          <div>
            <h3>Qualitätscheck</h3>
            <p>Prüft Integrität, Fremdschlüssel und häufige Datenfehler.</p>
          </div>
        </div>
        <form className="v2-form-actions" method="post" action="/v2/admin/database">
          <input type="hidden" name="csrf_token" value={csrfToken || ''} />
          <input type="hidden" name="database_action" value="check" />
          <button type="submit" className="v2-primary-action v2-submit-action">
            <CircleCheck size={20} />
            <span>Qualitätscheck starten</span>
          </button>
        </form>
        {checkResult && <DatabaseCheckResult result={checkResult} />}
      </Card>
      <Card className="v2-native-card v2-database-card" padding={0}>
        <div className="v2-dashboard-card-title">
          <RefreshCw size={24} />
          <div>
            <h3>Wartung</h3>
            <p>Für Defragmentierung wird vorher automatisch ein lokales Backup erstellt.</p>
          </div>
        </div>
        <form className="v2-maintenance-grid" method="post" action="/v2/admin/database">
          <input type="hidden" name="csrf_token" value={csrfToken || ''} />
          <input type="hidden" name="database_action" value="maintenance" />
          {[
            ['checkpoint', 'WAL bereinigen'],
            ['analyze', 'Statistiken aktualisieren'],
            ['optimize', 'SQLite optimieren'],
            ['vacuum', 'Defragmentieren'],
            ['full', 'Komplettwartung'],
          ].map(([value, label]) => (
            <button key={value} type="submit" name="maintenance_action" value={value} className="v2-action-button" onClick={(event) => confirmDatabaseMaintenance(event, value)}>
              <RefreshCw size={18} />
              <span>{label}</span>
            </button>
          ))}
        </form>
        {maintenanceResult && (
          <div className="v2-inline-note">
            {maintenanceResult.label} abgeschlossen. Größe: {formatBytes(maintenanceResult.before_size)} → {formatBytes(maintenanceResult.after_size)}
            {maintenanceResult.backup_filename ? ` · Backup: ${maintenanceResult.backup_filename}` : ''}
          </div>
        )}
      </Card>
      <Card className="v2-native-card v2-database-card" padding={0}>
        <div className="v2-dashboard-card-title">
          <Database size={24} />
          <div>
            <h3>Tabellen</h3>
            <p>{stats.db_path}</p>
          </div>
        </div>
        <div className="v2-table-wrap">
          {tables.length ? <Table className="v2-astryx-table" data={tables} columns={tableColumns} idKey="name" density="compact" dividers="rows" hasHover /> : <EmptyState text="Keine Tabellen gefunden." />}
        </div>
      </Card>
    </div>
  );
}

function DatabaseCheckResult({result}) {
  return (
    <div className="v2-quality-result">
      <StatusLine variant={result.status === 'ok' ? 'success' : result.status === 'error' ? 'error' : 'warning'} label={result.summary}>
        Geprüft am {formatDateTime(result.checked_at)}
      </StatusLine>
      <div className="v2-table-wrap">
        <table className="v2-native-table">
          <thead><tr><th>Prüfung</th><th>Status</th><th>Hinweis</th><th>Anzahl</th></tr></thead>
          <tbody>
            {(result.results || []).map((row) => (
              <tr key={row.title}>
                <td><strong>{row.title}</strong></td>
                <td><span className={`v2-tag ${row.status === 'ok' ? 'is-success' : row.status === 'error' ? 'is-danger' : 'is-warning'}`}>{row.status === 'ok' ? 'OK' : row.status}</span></td>
                <td>{row.detail}</td>
                <td className="v2-number-cell">{formatNumber(row.count)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}

function confirmDatabaseMaintenance(event, action) {
  if ((action === 'vacuum' || action === 'full') && !window.confirm('Diese Wartung kann kurz dauern. Es wird vorher ein Backup erstellt. Fortfahren?')) {
    event.preventDefault();
  }
}

function NativePortalDashboard({data}) {
  const member = data.member;
  const account = data.account || {};
  const stats = data.stats || {};
  return (
    <div className="v2-native-page v2-portal-page">
      <div className="v2-page-heading">
        <div className="v2-page-title">
          <LayoutDashboard size={34} strokeWidth={1.8} />
          <h2>Mein EEG Konto</h2>
        </div>
      </div>
      {!member ? (
        <Banner status="warning" title="Kein Mitglied zugeordnet" description="Dieses Benutzerkonto ist keinem Mitglied zugeordnet." container="section" />
      ) : (
        <>
          <section className="v2-dashboard-stats" aria-label="Kontostand">
            <DashboardStat icon={Banknote} label="Aktueller Kontostand" value={formatSignedCurrency(account.balance)} />
            <DashboardStat icon={ReceiptText} label="Offene Forderungen" value={formatCurrency(account.open_claims)} />
            <DashboardStat icon={Euro} label="Guthaben" value={formatCurrency(Math.abs(Number(account.open_credits) || 0))} />
            <DashboardStat icon={Clock3} label="Buchungsrückstand" value={formatCurrency(account.overdue_claims)} />
          </section>
          <Card className="v2-native-card" padding={0}>
            <div className="v2-dashboard-card-title">
              <Activity size={24} />
              <div>
                <h3>Letzte Abrechnung</h3>
                <p>{stats.invoice_id ? `Abrechnung #${stats.invoice_id}` : 'Noch keine Abrechnung vorhanden'}</p>
              </div>
            </div>
            <div className="v2-portal-summary-grid">
              <MetricCard icon={Plug} label="Bezug" value={`${formatNumber(stats.consumption_kwh, 1)} kWh`} />
              <MetricCard icon={Sun} label="Erzeugung" value={`${formatNumber(stats.generation_kwh, 1)} kWh`} />
              <MetricCard icon={ReceiptText} label="Summe" value={formatSignedCurrency(stats.net_total)} tone="teal" />
            </div>
          </Card>
          <PortalInvoiceTable invoices={data.invoices || []} />
          <PortalAccountHistory account={account} />
        </>
      )}
    </div>
  );
}

function NativePortalData({data, csrfToken}) {
  const member = data.member || {};
  if (!member.id) {
    return <div className="v2-native-page"><Banner status="warning" title="Kein Mitglied zugeordnet" description="Dieses Benutzerkonto ist keinem Mitglied zugeordnet." container="section" /></div>;
  }
  return (
    <div className="v2-native-page v2-portal-data-page">
      <div className="v2-page-heading">
        <div className="v2-page-title">
          <UserCog size={34} strokeWidth={1.8} />
          <h2>Meine Stammdaten</h2>
        </div>
      </div>
      <Card className="v2-native-card v2-settings-card" padding={0}>
        <div className="v2-dashboard-card-title">
          <UserCog size={24} />
          <div>
            <h3>Kontaktdaten</h3>
            <p>Änderungen werden direkt in den Stammdaten gespeichert.</p>
          </div>
        </div>
        <form className="v2-settings-form" method="post" action="/v2/portal/data">
          <input type="hidden" name="csrf_token" value={csrfToken || ''} />
          <div className="v2-form-section">
            <FormTextInput name="name" label="Name" defaultValue={member.name || ''} isRequired />
            <FormTextInput name="email" label="E-Mail" type="email" defaultValue={member.email || ''} isOptional />
            <FormTextInput name="phone" label="Telefon" defaultValue={member.phone || ''} isOptional />
          </div>
          <div className="v2-form-section">
            <FormTextInput name="address_street" label="Straße" defaultValue={member.address_street || ''} isOptional />
            <FormTextInput name="address_zip" label="PLZ" defaultValue={member.address_zip || ''} isOptional />
            <FormTextInput name="address_city" label="Ort" defaultValue={member.address_city || ''} isOptional />
          </div>
          <div className="v2-form-section">
            <FormTextInput name="account_holder" label="Kontoinhaber" defaultValue={member.account_holder || ''} isOptional />
            <FormTextInput name="iban" label="IBAN" defaultValue={member.iban || ''} isOptional />
            <FormTextInput name="bic" label="BIC" defaultValue={member.bic || ''} isOptional />
          </div>
          <div className="v2-form-section">
            <FormSwitch
              name="newsletter_enabled"
              label="Newsletter erhalten"
              description={member.newsletter_optout ? 'Du erhältst aktuell keine Newsletter-E-Mails.' : 'Du erhältst aktuell Newsletter-E-Mails.'}
              defaultChecked={!member.newsletter_optout}
            />
            <div className="v2-inline-note">
              Zählpunkte: Bezug {member.bezug_zp || '-'} · Einspeisung {member.einspeiser_zp || '-'}
            </div>
          </div>
          <div className="v2-form-actions">
            <button type="submit" className="v2-primary-action v2-submit-action">
              <Check size={20} />
              <span>Stammdaten speichern</span>
            </button>
          </div>
        </form>
      </Card>
    </div>
  );
}

function NativePortalInvoices({data, csrfToken}) {
  const account = data.account || {};
  return (
    <div className="v2-native-page v2-portal-invoices-page">
      <div className="v2-page-heading">
        <div className="v2-page-title">
          <ReceiptText size={34} strokeWidth={1.8} />
          <h2>Meine Abrechnungen</h2>
        </div>
      </div>
      <section className="v2-dashboard-stats" aria-label="Kontostand">
        <DashboardStat icon={Banknote} label="Aktueller Kontostand" value={formatSignedCurrency(account.balance)} />
        <DashboardStat icon={ReceiptText} label="Offene Forderungen" value={formatCurrency(account.open_claims)} />
        <DashboardStat icon={Euro} label="Guthaben" value={formatCurrency(Math.abs(Number(account.open_credits) || 0))} />
        <DashboardStat icon={Clock3} label="Buchungsrückstand" value={formatCurrency(account.overdue_claims)} />
      </section>
      <PortalInvoiceTable invoices={data.invoices || []} memberId={data.member_id} csrfToken={csrfToken} />
      <PortalAccountHistory account={account} />
    </div>
  );
}

function NativePortalContracts({data}) {
  const contracts = data.contracts || [];
  const columns = [
    {key: 'type', header: 'Typ', width: pixel(160), renderCell: (row) => <span className={`v2-tag ${row.type === 'einspeiser' ? 'is-warning' : 'is-info'}`}>{row.type === 'einspeiser' ? 'Einspeiser' : 'Bezieher'}</span>},
    {key: 'filename', header: 'Datei', width: proportional(1.7, {minWidth: 320}), renderCell: (row) => <strong>{row.filename}</strong>},
    {key: 'uploaded_at', header: 'Hochgeladen', width: pixel(170), renderCell: (row) => formatDateTime(row.uploaded_at)},
    {key: 'actions', header: 'Aktionen', align: 'end', width: pixel(100), renderCell: (row) => <a className="v2-icon-action" href={`/contracts/${row.id}/download`} aria-label="Vertrag öffnen" title="Vertrag öffnen"><FileText size={18} /></a>},
  ];
  return (
    <div className="v2-native-page v2-portal-contracts-page">
      <div className="v2-page-heading">
        <div className="v2-page-title">
          <Archive size={34} strokeWidth={1.8} />
          <h2>Meine Verträge</h2>
        </div>
      </div>
      <Card className="v2-native-card" padding={0}>
        <div className="v2-table-wrap">
          {contracts.length ? <Table className="v2-astryx-table" data={contracts} columns={columns} idKey="id" density="compact" dividers="rows" hasHover textOverflow="wrap" /> : <EmptyState text="Noch keine Verträge vorhanden." />}
        </div>
      </Card>
    </div>
  );
}

function PortalInvoiceTable({invoices, memberId, csrfToken}) {
  const rows = invoices || [];
  const columns = [
    {key: 'id', header: '#', width: pixel(70), renderCell: (row) => <strong>{row.id}</strong>},
    {key: 'period', header: 'Zeitraum', width: proportional(1.2, {minWidth: 200}), renderCell: (row) => formatDateRange(row.period_from, row.period_to)},
    {key: 'total_kwh', header: 'Energie', align: 'end', width: pixel(130), renderCell: (row) => `${formatNumber(row.total_kwh, 1)} kWh`},
    {key: 'net_total', header: 'Betrag', align: 'end', width: pixel(130), renderCell: (row) => <strong>{formatSignedCurrency(row.net_total)}</strong>},
    {key: 'status', header: 'Status', width: pixel(140), renderCell: (row) => <StatusPill value={row.paid ? 'paid' : row.status} />},
    {key: 'data', header: 'Daten', width: pixel(120), renderCell: (row) => <StatusPill value={row.data_status} />},
    {key: 'actions', header: 'Aktionen', align: 'end', width: pixel(130), renderCell: (row) => memberId ? (
      <div className="v2-row-actions">
        <a className="v2-icon-action" href={`/invoices/${row.id}/pdf/${memberId}`} aria-label="PDF öffnen" title="PDF öffnen"><FileText size={18} /></a>
        <form method="post" action={`/portal/invoices/${row.id}/send`}>
          <input type="hidden" name="csrf_token" value={csrfToken || ''} />
          <input type="hidden" name="next" value="/v2/portal/invoices" />
          <button type="submit" className="v2-icon-action is-success" aria-label="PDF per E-Mail senden" title="PDF per E-Mail senden">
            <Mail size={18} />
          </button>
        </form>
      </div>
    ) : null},
  ];
  return (
    <Card className="v2-native-card" padding={0}>
      <div className="v2-dashboard-card-title">
        <ReceiptText size={24} />
        <h3>Abrechnungen</h3>
      </div>
      <div className="v2-table-wrap">
        {rows.length ? <Table className="v2-astryx-table" data={rows} columns={columns} idKey="id" density="compact" dividers="rows" hasHover textOverflow="wrap" /> : <EmptyState text="Noch keine Abrechnungen vorhanden." />}
      </div>
    </Card>
  );
}

function PortalAccountHistory({account}) {
  const history = account?.history || [];
  return (
    <Card className="v2-native-card" padding={0}>
      <div className="v2-dashboard-card-title">
        <Clock3 size={24} />
        <h3>Buchungshistorie</h3>
      </div>
      <div className="v2-table-wrap">
        <table className="v2-native-table">
          <thead><tr><th>Datum</th><th>Beschreibung</th><th>Status</th><th>Betrag</th><th>Saldo danach</th></tr></thead>
          <tbody>
            {history.length ? history.map((row, index) => (
              <tr key={`${row.invoice_id}-${row.kind}-${index}`}>
                <td>{formatDate(row.date)}</td>
                <td><strong>{row.label}</strong>{row.is_previous_period_open && <small>Offen aus Vorperiode</small>}</td>
                <td><span className={`v2-tag ${row.status === 'gebucht' ? 'is-success' : row.status === 'offen' ? 'is-warning' : 'is-muted'}`}>{row.status}</span></td>
                <td className="v2-number-cell">{formatSignedCurrency(row.amount)}</td>
                <td className="v2-number-cell"><strong>{formatSignedCurrency(row.balance_after)}</strong></td>
              </tr>
            )) : <tr><td colSpan="5"><EmptyState text="Noch keine Buchungen vorhanden." /></td></tr>}
          </tbody>
        </table>
      </div>
    </Card>
  );
}

function NativeMembers({data}) {
  const members = data.members || [];
  const columns = [
    {key: 'name', header: 'Name', width: proportional(1.3, {minWidth: 230}), renderCell: (member) => <strong>{member.name || 'Ohne Namen'}</strong>},
    {key: 'type', header: 'Typ', width: proportional(1.05, {minWidth: 210}), renderCell: (member) => (
      <div className="v2-member-types">
        {member.bezug_zp && <span className="v2-tag v2-member-type is-consumer"><Plug />Bezieher</span>}
        {member.einspeiser_zp && <span className="v2-tag v2-member-type is-producer"><Sun />Erzeuger</span>}
      </div>
    )},
    {key: 'email', header: <Mail size={20} />, align: 'center', width: pixel(70), renderCell: (member) => <MailIconState enabled={Boolean(member.email)} />},
    {key: 'bank', header: <Landmark size={20} />, align: 'center', width: pixel(70), renderCell: (member) => <BankIconState enabled={Boolean(member.has_bank)} />},
    {key: 'address', header: 'Adresse', width: proportional(1.8, {minWidth: 320}), renderCell: (member) => formatFullAddress(member)},
    {key: 'tf', header: 'TF', align: 'end', width: pixel(80), renderCell: (member) => formatParticipationShort(member.teilnahme)},
    {key: 'status', header: 'Status', width: pixel(110), renderCell: (member) => <StatusPill value={member.active ? 'active' : 'inactive'} />},
    {key: 'actions', header: 'Aktionen', align: 'end', width: pixel(95), renderCell: (member) => (
      <a className="v2-icon-action" href={`/v2/members/${member.id}/edit`} aria-label={`${member.name || 'Mitglied'} bearbeiten`} title="Bearbeiten">
        <Pencil size={19} />
      </a>
    )},
  ];

  return (
    <div className="v2-native-page v2-members-page">
      <div className="v2-page-heading">
        <div className="v2-page-title">
          <Users size={34} strokeWidth={1.8} />
          <h2>Mitglieder</h2>
        </div>
        <a className="v2-primary-action" href="/v2/members/new">
          <Plus size={22} />
          <span>Neues Mitglied</span>
        </a>
      </div>

      <Card className="v2-native-card v2-members-card" padding={0}>
        <div className="v2-table-wrap">
          {members.length ? (
            <Table
              className="v2-astryx-table v2-members-table"
              data={members}
              columns={columns}
              idKey="id"
              density="compact"
              dividers="rows"
              hasHover
              textOverflow="wrap"
            />
          ) : <EmptyState text="Noch keine Mitglieder vorhanden." />}
        </div>
      </Card>
    </div>
  );
}

function MetricCard({icon: Icon, label, value, tone}) {
  return (
    <Card className={`v2-metric-card ${tone === 'teal' ? 'is-teal' : ''}`} padding={0}>
      <div className="v2-metric-icon"><Icon size={20} /></div>
      <span>{label}</span>
      <strong>{value}</strong>
    </Card>
  );
}

function DashboardStat({icon: Icon, label, value}) {
  const hasNodeValue = React.isValidElement(value);
  return (
    <div className="v2-dashboard-stat">
      <Icon size={24} />
      <span>{label}</span>
      <strong className={hasNodeValue ? 'has-node-value' : ''}>{value}</strong>
    </div>
  );
}

function NativeLinkButton({href, icon, label}) {
  return (
    <a className="v2-action-button" href={href}>
      {icon}
      <span>{label}</span>
    </a>
  );
}

function MailIconState({enabled}) {
  return <Mail className={enabled ? 'is-enabled' : 'is-disabled'} size={23} strokeWidth={2.1} />;
}

function BankIconState({enabled}) {
  return <Landmark className={enabled ? 'is-enabled' : 'is-disabled'} size={23} strokeWidth={2.1} />;
}

function StatusPill({value}) {
  const normalized = String(value || '').toLowerCase();
  const labels = {
    final: 'Final',
    provisional: 'Vorläufig',
    replaced: 'Ersetzt',
    success: 'Erfolgreich',
    error: 'Fehler',
    draft: 'Entwurf',
    sent: 'Versendet',
    paid: 'Bezahlt',
    finalized: 'Finalisiert',
    active: 'Aktiv',
    inactive: 'Inaktiv',
    newsletter_on: 'Ja',
    newsletter_off: 'Nein',
  };
  const icon = normalized === 'final' || normalized === 'active' || normalized === 'paid' || normalized === 'newsletter_on'
    ? <CircleCheck size={14} />
    : <Clock3 size={14} />;
  return <span className={`v2-tag v2-status-pill is-${normalized || 'default'}`}>{icon}{labels[normalized] || value || 'Offen'}</span>;
}

function EmptyState({text}) {
  return <div className="v2-empty">{text}</div>;
}

createRoot(document.getElementById('root')).render(<App />);
