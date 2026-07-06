import React, {useEffect, useMemo, useRef, useState} from 'react';
import {createRoot} from 'react-dom/client';
import {Badge, Button, Card, Theme} from '@astryxdesign/core';
import {neutralTheme} from '@astryxdesign/theme-neutral';
import {
  Archive,
  Banknote,
  BookOpenText,
  ChartNoAxesCombined,
  ChevronLeft,
  ChevronRight,
  Database,
  Download,
  Euro,
  ExternalLink,
  FileText,
  LayoutDashboard,
  LogOut,
  Mail,
  NotebookText,
  ReceiptText,
  RefreshCw,
  Settings,
  Upload,
  UserCog,
  Users,
  X,
} from 'lucide-react';
import '@astryxdesign/core/reset.css';
import '@astryxdesign/core/astryx.css';
import '@astryxdesign/theme-neutral/theme.css';
import './styles.css';

const adminNavItems = [
  {label: 'Dashboard', path: '/', icon: LayoutDashboard},
  {label: 'Import', path: '/import', icon: Upload},
  {label: 'Mitglieder', path: '/members', icon: Users},
  {label: 'Preise', path: '/prices', icon: Euro},
  {label: 'Abrechnungen', path: '/invoices', icon: ReceiptText},
  {label: 'Überweisungen', path: '/payments', icon: Banknote},
  {label: 'Reports', path: '/reports', icon: ChartNoAxesCombined},
  {label: 'Newsletter', path: '/newsletter', icon: Mail},
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
    <Theme theme={neutralTheme} mode="light">
      <V2Shell />
    </Theme>
  );
}

function V2Shell() {
  const data = window.EEG_V2_DATA || {};
  const user = data.user || {};
  const org = data.org || {};
  const currentPath = data.current_path || (user.role === 'admin' ? '/' : '/portal');
  const contentPath = data.content_path || `${currentPath}?embed=1`;
  const navItems = user.role === 'admin' ? adminNavItems : memberNavItems;
  const activeItem = useMemo(
    () => navItems.find((item) => item.path && isActivePath(currentPath, item.path)),
    [currentPath, navItems],
  );
  const iframeRef = useRef(null);
  const [isLoading, setIsLoading] = useState(true);
  const [pdfPreview, setPdfPreview] = useState(null);
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
    function handleFrameMessage(event) {
      if (event.origin !== window.location.origin) return;
      if (event.data?.type === 'eeg-v2-loading') {
        setIsLoading(true);
      } else if (event.data?.type === 'eeg-v2-pdf-preview') {
        setIsLoading(false);
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

  function syncAddressFromFrame() {
    setIsLoading(false);
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
    setIsLoading(true);
    iframeRef.current?.contentWindow?.location.reload();
  }

  return (
    <div className={`v2-shell ${isCollapsed ? 'is-collapsed' : ''}`}>
      <aside className="v2-sidebar">
        <a className="v2-brand" href="/v2/" title={org.name || 'EEG'}>
          <img src="/static/logo.png" alt="" />
          <div className="v2-brand-text">
            <strong>{org.name || 'EEG'}</strong>
            <span>Version 2</span>
          </div>
        </a>

        <button
          type="button"
          className="v2-collapse-button"
          aria-label={isCollapsed ? 'Menü ausklappen' : 'Menü einklappen'}
          title={isCollapsed ? 'Menü ausklappen' : 'Menü einklappen'}
          onClick={() => setIsCollapsed((value) => !value)}
        >
          {isCollapsed ? <ChevronRight size={18} /> : <ChevronLeft size={18} />}
        </button>

        <nav aria-label="V2 Navigation">
          {navItems.map((item) => {
            if (item.type === 'section') {
              return <div key={item.label} className="nav-section">{item.label}</div>;
            }
            const Icon = item.icon;
            return (
              <a
                key={item.path}
                href={v2Href(item.path)}
                className={isActivePath(currentPath, item.path) ? 'active' : ''}
                title={item.label}
              >
                <Icon className="nav-icon" size={19} strokeWidth={2.1} />
                <span className="nav-label">{item.label}</span>
              </a>
            );
          })}
        </nav>

        <div className="v2-sidebar-footer">
          <span>{org.zvr || org.legal || 'ZVR bitte konfigurieren'}</span>
          <span>{org.name || 'EEG Bezeichnung bitte konfigurieren'}</span>
        </div>
      </aside>
      <main className="v2-main">
        <header className="v2-topbar">
          <div className="v2-title-group">
            <div className="v2-kicker">
              <span>EEG Verwaltung</span>
              <span>V2</span>
            </div>
            <h1>{activeItem?.label || 'Arbeitsbereich'}</h1>
          </div>
          <div className="topbar-actions">
            <Badge label={user.username || 'Benutzer'} variant="teal" />
            <Button label="Aktualisieren" icon={<RefreshCw size={16} />} clickAction={reloadContent} />
            <Button label="Klassische UI" icon={<ExternalLink size={16} />} href={currentPath} />
            <Button label="Abmelden" icon={<LogOut size={16} />} href="/logout" variant="ghost" />
          </div>
        </header>

        <Card className={`v2-frame-card ${isLoading ? 'is-loading' : 'is-ready'}`} padding={0}>
          {isLoading && <div className="v2-loading">Seite wird geladen...</div>}
          <iframe
            ref={iframeRef}
            title="EEG V2 Inhalt"
            src={contentPath}
            className="v2-content-frame"
            onLoad={syncAddressFromFrame}
          />
        </Card>

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
      </main>
    </div>
  );
}

function isActivePath(currentPath, itemPath) {
  if (itemPath === '/') return currentPath === '/';
  return currentPath === itemPath || currentPath.startsWith(`${itemPath}/`);
}

function v2Href(path) {
  if (path === '/') return '/v2/';
  return `/v2${path}`;
}

createRoot(document.getElementById('root')).render(<App />);
