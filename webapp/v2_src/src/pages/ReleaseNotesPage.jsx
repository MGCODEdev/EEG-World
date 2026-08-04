import React from 'react';
import {Card} from '@astryxdesign/core';
import {ScrollText} from 'lucide-react';
import {formatDate} from '../utils/formatters.js';

export default function ReleaseNotesPage({data}) {
  const notes = data.release_notes || [];
  return (
    <div className="v2-native-page v2-release-notes-page">
      <div className="v2-page-heading"><div className="v2-page-title">
        <ScrollText size={34} strokeWidth={1.8} />
        <div><h2>Release Notes</h2><small className="v2-page-subtitle">Letzte Änderungen am EEG Portal</small></div>
      </div></div>
      <div className="v2-release-notes-grid">
        <div className="v2-release-notes-list">
          {notes.length ? notes.map((note) => (
            <Card key={`${note.date}-${note.title}`} className="v2-native-card v2-release-note-card" padding="lg">
              <div className="v2-release-note-header"><span className="v2-tag is-accent">{formatDate(note.date)}</span><h3>{note.title}</h3></div>
              <ul className="v2-release-note-changes">{note.changes.map((change, index) => <li key={index}>{change}</li>)}</ul>
            </Card>
          )) : <div className="v2-empty">Noch keine Release Notes vorhanden.</div>}
        </div>
        <Card className="v2-native-card v2-release-note-info" padding="lg">
          <div className="v2-dashboard-card-title"><ScrollText size={24} /><h3>Hinweis</h3></div>
          <p className="v2-muted">Hier werden neue Funktionen, Korrekturen und Verbesserungen übersichtlich nach Datum aufgelistet. Die neuesten Änderungen stehen immer oben.</p>
        </Card>
      </div>
    </div>
  );
}
