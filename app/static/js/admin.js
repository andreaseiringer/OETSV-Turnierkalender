/**
 * pivitLABS ÖTSV Tool - Admin Control Center Logic (https://pivitlabs.com)
 */

let currentLogTarget = 'system';
let logAutoRefreshInterval = null;

document.addEventListener('DOMContentLoaded', () => {
  initAdminTheme();
  setupAdminListeners();
  refreshAll();
  initAdminOnboardingTour();

  // Auto refresh status every 10 seconds
  setInterval(loadAdminStatus, 10000);
});

function initAdminTheme() {
  const saved = localStorage.getItem('adsi-theme');
  if (saved) {
    document.documentElement.setAttribute('data-theme', saved);
  }
}

function setupAdminListeners() {
  // Triggers
  document.getElementById('btn-trigger-scraper').addEventListener('click', () => triggerJob('scraper'));
  document.getElementById('btn-trigger-fetcher').addEventListener('click', () => triggerJob('fetcher'));
  const resBtn = document.getElementById('btn-trigger-results-scraper');
  if (resBtn) resBtn.addEventListener('click', () => triggerJob('results-scraper'));
  const teilnehmerBtn = document.getElementById('btn-trigger-teilnehmer-scraper');
  if (teilnehmerBtn) teilnehmerBtn.addEventListener('click', () => triggerJob('teilnehmer-scraper'));

  // Log target switcher
  document.querySelectorAll('#log-target-tabs .tab-btn').forEach(btn => {
    btn.addEventListener('click', () => {
      document.querySelectorAll('#log-target-tabs .tab-btn').forEach(b => b.classList.remove('active'));
      btn.classList.add('active');
      currentLogTarget = btn.getAttribute('data-target');
      loadLogs();
    });
  });

  // Log Auto Refresh
  const autoRefreshCheckbox = document.getElementById('log-auto-refresh');
  autoRefreshCheckbox.addEventListener('change', (e) => {
    if (e.target.checked) {
      logAutoRefreshInterval = setInterval(loadLogs, 3000);
    } else if (logAutoRefreshInterval) {
      clearInterval(logAutoRefreshInterval);
      logAutoRefreshInterval = null;
    }
  });

  document.getElementById('btn-refresh-logs').addEventListener('click', loadLogs);
  document.getElementById('btn-refresh-data').addEventListener('click', loadDataInspector);

  // Storage & Cloud Config buttons
  const reloadStorageBtn = document.getElementById('btn-reload-storage-config');
  if (reloadStorageBtn) reloadStorageBtn.addEventListener('click', loadStorageConfig);
  const saveStorageBtn = document.getElementById('btn-save-storage-cfg');
  if (saveStorageBtn) saveStorageBtn.addEventListener('click', saveStorageConfig);
  const manualSyncBtn = document.getElementById('btn-manual-cloud-sync');
  if (manualSyncBtn) manualSyncBtn.addEventListener('click', triggerManualCloudSync);
  const browseAdminBtn = document.getElementById('btn-admin-browse-folder');
  if (browseAdminBtn) browseAdminBtn.addEventListener('click', browseAdminCloudFolder);

  document.querySelectorAll('input[name="admin-storage-mode"]').forEach(r => {
    r.addEventListener('change', () => {
      const isCloud = r.value === 'cloud' && r.checked;
      updateAdminStorageModeUI(isCloud);
    });
  });

  // Club Config ("Verein einstellen") buttons
  const reloadClubBtn = document.getElementById('btn-reload-club-config');
  if (reloadClubBtn) reloadClubBtn.addEventListener('click', loadClubConfig);
  const saveClubBtn = document.getElementById('btn-save-club-cfg');
  if (saveClubBtn) saveClubBtn.addEventListener('click', saveClubConfig);

  // IMAP Config buttons
  document.getElementById('btn-reload-imap-config').addEventListener('click', loadImapConfig);
  document.getElementById('btn-save-imap-cfg').addEventListener('click', saveImapConfig);
  document.getElementById('btn-test-imap-conn').addEventListener('click', testImapConnection);
}

async function refreshAll() {
  await Promise.all([
    loadAdminStatus(),
    loadStorageConfig(),
    loadClubConfig(),
    loadImapConfig(),
    loadLogs(),
    loadDataInspector(),
    loadChangelog()
  ]);
}

async function loadAdminStatus() {
  try {
    const res = await fetch('/adsi-admin/api/status');
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    const data = await res.json();

    document.getElementById('kpi-turniere').textContent = data.turniere_gesamt;
    document.getElementById('kpi-nennungen').textContent = data.nennungen_gesamt;
    document.getElementById('kpi-klassen').textContent = data.klassen_gesamt;
    const ergebnisseEl = document.getElementById('kpi-ergebnisse');
    if (ergebnisseEl) ergebnisseEl.textContent = data.ergebnisse_gesamt || 0;
    const teilnehmerEl = document.getElementById('kpi-teilnehmer');
    if (teilnehmerEl) teilnehmerEl.textContent = data.teilnehmer_gesamt || 0;
    document.getElementById('kpi-server-time').textContent = data.server_time;

    // Running jobs & Next runs
    const nextScraper = data.next_runs.scraper || 'Kein Zeitplan';
    const nextFetcher = data.next_runs.fetcher || 'Kein Zeitplan';
    const nextResults = data.next_runs.results_scraper || 'Kein Zeitplan';
    const nextTeilnehmer = data.next_runs.teilnehmer_scraper || 'Kein Zeitplan';
    document.getElementById('next-run-scraper').textContent = nextScraper;
    document.getElementById('next-run-fetcher').textContent = nextFetcher;
    const nextResEl = document.getElementById('next-run-results-scraper');
    if (nextResEl) nextResEl.textContent = nextResults;
    const nextTEl = document.getElementById('next-run-teilnehmer-scraper');
    if (nextTEl) nextTEl.textContent = nextTeilnehmer;

    const scraperRunning = data.running_jobs.includes('scraper');
    const fetcherRunning = data.running_jobs.includes('fetcher');
    const resultsRunning = data.running_jobs.includes('results_scraper');
    const teilnehmerRunning = data.running_jobs.includes('teilnehmer_scraper');

    const scraperBtn = document.getElementById('btn-trigger-scraper');
    scraperBtn.disabled = scraperRunning;
    scraperBtn.textContent = scraperRunning ? 'Scraper läuft...' : 'Kalender jetzt scrapen';

    const fetcherBtn = document.getElementById('btn-trigger-fetcher');
    fetcherBtn.disabled = fetcherRunning;
    fetcherBtn.textContent = fetcherRunning ? 'Mail-Abruf läuft...' : 'Mail-Abruf jetzt starten';

    const resultsBtn = document.getElementById('btn-trigger-results-scraper');
    if (resultsBtn) {
      resultsBtn.disabled = resultsRunning;
      resultsBtn.textContent = resultsRunning ? 'Ergebnisse laufen...' : 'Ergebnisse jetzt abrufen';
    }

    const tBtn = document.getElementById('btn-trigger-teilnehmer-scraper');
    if (tBtn) {
      tBtn.disabled = teilnehmerRunning;
      tBtn.textContent = teilnehmerRunning ? 'Import läuft...' : 'Teilnehmerlisten jetzt abrufen';
    }

    // Sync status details
    const ss = data.sync_status;
    if (ss.scraper) {
      document.getElementById('status-msg-scraper').textContent = `${ss.scraper.message || ''} (${ss.scraper.last_run || 'Nie'})`;
    }
    if (ss.fetcher) {
      document.getElementById('status-msg-fetcher').textContent = `${ss.fetcher.message || ''} (${ss.fetcher.last_run || 'Nie'})`;
    }
    if (ss.results_scraper) {
      const msgEl = document.getElementById('status-msg-results-scraper');
      if (msgEl) msgEl.textContent = `${ss.results_scraper.message || ''} (${ss.results_scraper.last_run || 'Nie'})`;
    }
    if (ss.teilnehmer_scraper) {
      const msgEl = document.getElementById('status-msg-teilnehmer-scraper');
      if (msgEl) msgEl.textContent = `${ss.teilnehmer_scraper.message || ''} (${ss.teilnehmer_scraper.last_run || 'Nie'})`;
    }
  } catch (err) {
    console.error('Failed to load admin status', err);
  }
}

async function triggerJob(jobName) {
  const statusBanner = document.getElementById('trigger-status-banner');
  statusBanner.style.display = 'block';
  statusBanner.textContent = `Starte Job '${jobName}'...`;

  try {
    const res = await fetch(`/adsi-admin/api/trigger/${jobName}`, { method: 'POST' });
    const result = await res.json();

    statusBanner.textContent = result.message;
    setTimeout(() => {
      loadAdminStatus();
      loadLogs();
    }, 1000);
  } catch (err) {
    statusBanner.textContent = `Fehler: ${err.message}`;
  }
}

async function loadLogs() {
  const terminal = document.getElementById('log-terminal');
  try {
    const res = await fetch(`/adsi-admin/api/logs?target=${currentLogTarget}&limit=150`);
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    const data = await res.json();
    if (data.logs.length === 0) {
      terminal.textContent = 'Keine Log-Einträge vorhanden.';
    } else {
      terminal.textContent = data.logs.join('\n');
      terminal.scrollTop = terminal.scrollHeight;
    }
  } catch (err) {
    terminal.textContent = `Fehler beim Abrufen der Logs: ${err.message}`;
  }
}

async function loadDataInspector() {
  const tContainer = document.getElementById('inspector-turniere-body');
  const nContainer = document.getElementById('inspector-nennungen-body');

  try {
    const res = await fetch('/adsi-admin/api/data?limit=50');
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    const data = await res.json();

    // Turniere table
    tContainer.innerHTML = data.turniere.map(t => `
      <tr>
        <td><code>${t.id}</code></td>
        <td><strong>${escapeHtml(t.datum)}</strong></td>
        <td>${escapeHtml(t.titel)}</td>
        <td>${escapeHtml(t.klub || '—')}</td>
        <td>${escapeHtml(t.bundesland || '—')}</td>
        <td><small>${(t.tags || []).join(', ')}</small></td>
      </tr>
    `).join('');

    // Nennungen table
    nContainer.innerHTML = data.nennungen.map(n => `
      <tr>
        <td><code>${n.id}</code></td>
        <td><code>${escapeHtml(n.nennungs_id)}</code></td>
        <td><strong>${escapeHtml(n.paar_name)}</strong></td>
        <td>${escapeHtml(n.klub || '—')}</td>
        <td>Turnier-ID: <strong>${n.turnier_id}</strong> ${n.turnier_db_id ? `(DB: #${n.turnier_db_id})` : '<span style="color:#ef4444;">(nicht verknüpft)</span>'}</td>
        <td>
          ${n.klassen.map(k => `<span class="class-chip">${escapeHtml(k.datum)}: ${escapeHtml(k.klasse)}</span>`).join(' ')}
        </td>
      </tr>
    `).join('');

  } catch (err) {
    console.error('Failed to load inspector data', err);
  }
}

async function loadChangelog() {
  const container = document.getElementById('changelog-container');
  try {
    const res = await fetch('/adsi-admin/api/changelog');
    if (!res.ok) return;
    const list = await res.json();
    container.innerHTML = list.map(entry => `
      <div style="margin-bottom: 1.5rem; padding-left: 1rem; border-left: 3px solid var(--primary);">
        <div style="display:flex; justify-content:space-between; align-items:center;">
          <h4 style="font-weight:700; color:var(--text-main);">Version ${escapeHtml(entry.version)}</h4>
          <span style="font-size:0.8125rem; color:var(--text-muted);">${escapeHtml(entry.date)}</span>
        </div>
        <ul style="margin-top:0.5rem; padding-left:1.25rem; font-size:0.875rem; color:var(--text-muted);">
          ${entry.changes.map(c => `<li>${escapeHtml(c)}</li>`).join('')}
        </ul>
      </div>
    `).join('');
  } catch (e) {
    console.error('Failed to load changelog', e);
  }
}

function escapeHtml(str) {
  if (!str) return '';
  return String(str)
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#039;');
}

/* IMAP Configuration Functions */
async function loadImapConfig() {
  try {
    const res = await fetch('/adsi-admin/api/config/imap');
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    const data = await res.json();

    document.getElementById('cfg-imap-enabled').checked = data.imap_enabled;
    document.getElementById('cfg-imap-mock').checked = data.imap_mock;
    document.getElementById('cfg-imap-server').value = data.imap_server || '';
    document.getElementById('cfg-imap-port').value = data.imap_port || 993;
    document.getElementById('cfg-imap-mailbox').value = data.imap_mailbox || 'INBOX';
    document.getElementById('cfg-imap-interval').value = data.imap_fetch_interval_minutes || 15;
    document.getElementById('cfg-imap-user').value = data.imap_user || '';
    document.getElementById('cfg-imap-password').value = '';
    document.getElementById('cfg-imap-senders').value = data.imap_allowed_senders || '';

    const pwdStatus = document.getElementById('cfg-imap-password-status');
    if (pwdStatus) {
      if (data.has_password) {
        pwdStatus.textContent = '(Passwort hinterlegt)';
        pwdStatus.style.color = 'var(--accent-green)';
      } else {
        pwdStatus.textContent = '(Kein Passwort hinterlegt)';
        pwdStatus.style.color = 'var(--text-muted)';
      }
    }
  } catch (err) {
    showImapAlert('error', `Fehler beim Laden der IMAP-Konfiguration: ${err.message}`);
  }
}

function showImapAlert(type, message) {
  const box = document.getElementById('imap-config-alert');
  if (!box) return;
  box.className = `alert-box ${type}`;
  box.textContent = message;
  box.style.display = 'block';
}

async function saveImapConfig() {
  const saveBtn = document.getElementById('btn-save-imap-cfg');
  saveBtn.disabled = true;
  saveBtn.textContent = 'Speichere...';

  const payload = {
    imap_enabled: document.getElementById('cfg-imap-enabled').checked,
    imap_mock: document.getElementById('cfg-imap-mock').checked,
    imap_server: document.getElementById('cfg-imap-server').value.trim(),
    imap_port: parseInt(document.getElementById('cfg-imap-port').value) || 993,
    imap_mailbox: document.getElementById('cfg-imap-mailbox').value.trim() || 'INBOX',
    imap_fetch_interval_minutes: parseInt(document.getElementById('cfg-imap-interval').value) || 15,
    imap_user: document.getElementById('cfg-imap-user').value.trim(),
    imap_password: document.getElementById('cfg-imap-password').value,
    imap_allowed_senders: document.getElementById('cfg-imap-senders').value.trim()
  };

  try {
    const res = await fetch('/adsi-admin/api/config/imap', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload)
    });
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    await res.json();
    showImapAlert('success', 'IMAP-Konfiguration erfolgreich in .env gespeichert und live angewendet!');
    await loadImapConfig();
    await loadAdminStatus();
  } catch (err) {
    showImapAlert('error', `Fehler beim Speichern: ${err.message}`);
  } finally {
    saveBtn.disabled = false;
    saveBtn.innerHTML = `
      <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
        <path d="M19 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h11l5 5v11a2 2 0 0 1-2 2z"/>
        <polyline points="17 21 17 13 7 13 7 21"/>
        <polyline points="7 3 7 8 15 8"/>
      </svg>
      Konfiguration speichern
    `;
  }
}

async function testImapConnection() {
  const testBtn = document.getElementById('btn-test-imap-conn');
  testBtn.disabled = true;
  testBtn.textContent = 'Teste Verbindung...';
  showImapAlert('info', 'Prüfe IMAP-Verbindung...');

  const payload = {
    imap_enabled: document.getElementById('cfg-imap-enabled').checked,
    imap_mock: document.getElementById('cfg-imap-mock').checked,
    imap_server: document.getElementById('cfg-imap-server').value.trim(),
    imap_port: parseInt(document.getElementById('cfg-imap-port').value) || 993,
    imap_mailbox: document.getElementById('cfg-imap-mailbox').value.trim() || 'INBOX',
    imap_fetch_interval_minutes: parseInt(document.getElementById('cfg-imap-interval').value) || 15,
    imap_user: document.getElementById('cfg-imap-user').value.trim(),
    imap_password: document.getElementById('cfg-imap-password').value,
    imap_allowed_senders: document.getElementById('cfg-imap-senders').value.trim()
  };

  try {
    const res = await fetch('/adsi-admin/api/config/imap/test', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload)
    });
    const result = await res.json();
    if (result.success) {
      showImapAlert('success', result.message);
    } else {
      showImapAlert('error', result.message);
    }
  } catch (err) {
    showImapAlert('error', `Verbindungstest fehlgeschlagen: ${err.message}`);
  } finally {
    testBtn.disabled = false;
    testBtn.innerHTML = `
      <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
        <path d="M22 11.08V12a10 10 0 1 1-5.93-9.14"/>
        <polyline points="22 4 12 14.01 9 11.01"/>
      </svg>
      Verbindung testen
    `;
  }
}

/* Club Configuration Functions ("Verein einstellen") */
async function loadClubConfig() {
  const nameInput = document.getElementById('cfg-club-name');
  if (!nameInput) return;

  try {
    const res = await fetch('/adsi-admin/api/config/club');
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    const data = await res.json();

    nameInput.value = data.club_name || '';
    document.getElementById('cfg-club-short').value = data.club_short || '';
    document.getElementById('cfg-club-keywords').value = data.club_keywords || '';

    const tokensEl = document.getElementById('cfg-club-effective-tokens');
    if (tokensEl) {
      tokensEl.textContent = (data.effective_tokens && data.effective_tokens.length > 0)
        ? data.effective_tokens.join(' + ')
        : '—';
    }
  } catch (err) {
    showClubAlert('error', `Fehler beim Laden der Vereinseinstellung: ${err.message}`);
  }
}

function showClubAlert(type, message) {
  const box = document.getElementById('club-config-alert');
  if (!box) return;
  box.className = `alert-box ${type}`;
  box.textContent = message;
  box.style.display = 'block';
}

async function saveClubConfig() {
  const saveBtn = document.getElementById('btn-save-club-cfg');
  if (!saveBtn) return;

  const clubNameVal = document.getElementById('cfg-club-name').value.trim();
  if (!clubNameVal) {
    showClubAlert('error', 'Bitte einen Vereinsnamen eingeben.');
    return;
  }

  saveBtn.disabled = true;
  saveBtn.textContent = 'Speichere...';

  const payload = {
    club_name: clubNameVal,
    club_short: document.getElementById('cfg-club-short').value.trim(),
    club_keywords: document.getElementById('cfg-club-keywords').value.trim()
  };

  try {
    const res = await fetch('/adsi-admin/api/config/club', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload)
    });
    if (!res.ok) {
      const errData = await res.json().catch(() => ({}));
      throw new Error(errData.detail || `HTTP ${res.status}`);
    }
    const updated = await res.json();
    showClubAlert('success', `Verein "${updated.club_name}" (${updated.club_short}) erfolgreich gespeichert und Teilnehmerlisten aktualisiert!`);
    await loadClubConfig();
    await loadAdminStatus();
  } catch (err) {
    showClubAlert('error', `Fehler beim Speichern des Vereins: ${err.message}`);
  } finally {
    saveBtn.disabled = false;
    saveBtn.innerHTML = `
      <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
        <path d="M19 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h11l5 5v11a2 2 0 0 1-2 2z"/>
        <polyline points="17 21 17 13 7 13 7 21"/>
        <polyline points="7 3 7 8 15 8"/>
      </svg>
      Verein speichern
    `;
  }
}

// ==========================================================================
// Storage & Cloud Synchronization Configuration
// ==========================================================================
function updateAdminStorageModeUI(isCloud) {
  const localCard = document.getElementById('admin-card-local');
  const cloudCard = document.getElementById('admin-card-cloud');
  const cloudPanel = document.getElementById('admin-cloud-details');
  const syncBtn = document.getElementById('btn-manual-cloud-sync');

  if (localCard) localCard.classList.toggle('active', !isCloud);
  if (cloudCard) cloudCard.classList.toggle('active', isCloud);
  if (cloudPanel) cloudPanel.style.display = isCloud ? 'block' : 'none';
  if (syncBtn) syncBtn.style.display = isCloud ? 'inline-flex' : 'none';
}

function showStorageAlert(type, message) {
  const box = document.getElementById('storage-config-alert');
  if (!box) return;
  box.className = `alert-box ${type}`;
  box.textContent = message;
  box.style.display = 'block';
}

async function loadStorageConfig() {
  try {
    const res = await fetch('/adsi-admin/api/config/storage');
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    const data = await res.json();

    const isCloud = data.storage_mode === 'cloud';
    const radios = document.querySelectorAll('input[name="admin-storage-mode"]');
    radios.forEach(r => {
      r.checked = (r.value === data.storage_mode);
    });
    updateAdminStorageModeUI(isCloud);

    const pill = document.getElementById('cfg-storage-status-pill');
    if (pill) {
      if (isCloud) {
        pill.textContent = data.read_only_cloud ? '☁️ Cloud (Nur-Lesen)' : '☁️ Cloud aktiv';
      } else {
        pill.textContent = '💻 Lokal';
      }
    }

    const dirInput = document.getElementById('cfg-cloud-dir');
    if (dirInput) dirInput.value = data.cloud_dir || '';

    const imapToggle = document.getElementById('cfg-storage-sync-imap');
    if (imapToggle) imapToggle.checked = Boolean(data.sync_imap);

    const localDbEl = document.getElementById('cfg-local-db-path');
    if (localDbEl) localDbEl.textContent = data.local_db_path || 'data/adsi.db';

    const lastSyncEl = document.getElementById('cfg-cloud-last-sync');
    if (lastSyncEl) lastSyncEl.textContent = data.last_sync || 'Noch nie';

    const providersWrap = document.getElementById('admin-detected-providers');
    if (providersWrap) {
      if (data.detected_providers && data.detected_providers.length > 0) {
        providersWrap.innerHTML = data.detected_providers.map(p => `
          <button type="button" class="provider-chip-btn" data-path="${escapeHtml(p.suggested_path)}">
            ☁️ ${escapeHtml(p.name)}${p.existing_db ? ' (DB vorhanden ✓)' : ''}
          </button>
        `).join('');
        providersWrap.querySelectorAll('.provider-chip-btn').forEach(btn => {
          btn.addEventListener('click', () => {
            document.getElementById('cfg-cloud-dir').value = btn.getAttribute('data-path');
          });
        });
      } else {
        providersWrap.innerHTML = '<span style="font-size:0.78rem; color:var(--text-muted);">Keine Standard-Cloud-Ordner automatisch erkannt – bitte über „Ordner auswählen…“ wählen.</span>';
      }
    }

    if (data.last_error) {
      showStorageAlert('error', data.last_error);
    }
  } catch (err) {
    showStorageAlert('error', `Fehler beim Laden des Speicherorts: ${err.message}`);
  }
}

async function browseAdminCloudFolder() {
  const btn = document.getElementById('btn-admin-browse-folder');
  if (!btn) return;
  btn.disabled = true;
  btn.textContent = 'Öffne Dialog…';
  try {
    const res = await fetch('/adsi-admin/api/config/storage/browse', { method: 'POST' });
    if (res.ok) {
      const data = await res.json();
      if (data.selected_path) {
        document.getElementById('cfg-cloud-dir').value = data.selected_path;
      }
    }
  } catch (err) {
    showStorageAlert('error', `Ordner-Dialog konnte nicht geöffnet werden: ${err.message}`);
  } finally {
    btn.disabled = false;
    btn.textContent = '📂 Ordner auswählen…';
  }
}

async function saveStorageConfig() {
  const saveBtn = document.getElementById('btn-save-storage-cfg');
  const selectedRadio = document.querySelector('input[name="admin-storage-mode"]:checked');
  const mode = selectedRadio ? selectedRadio.value : 'local';
  const cloudDir = (document.getElementById('cfg-cloud-dir')?.value || '').trim();
  const syncImap = Boolean(document.getElementById('cfg-storage-sync-imap')?.checked);

  if (mode === 'cloud' && !cloudDir) {
    showStorageAlert('error', 'Bitte gib einen gültigen Cloud-Ordnerpfad an oder wähle einen Ordner aus.');
    return;
  }

  if (saveBtn) {
    saveBtn.disabled = true;
    saveBtn.textContent = 'Speichere…';
  }

  try {
    const res = await fetch('/adsi-admin/api/config/storage', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        storage_mode: mode,
        cloud_dir: cloudDir,
        sync_imap: syncImap,
        force_lock: false
      })
    });
    if (!res.ok) {
      const errData = await res.json().catch(() => ({}));
      throw new Error(errData.detail || `HTTP ${res.status}`);
    }
    const updated = await res.json();
    if (updated.storage_mode === 'cloud') {
      showStorageAlert('success', `Cloud-Speicherort aktiviert (${updated.cloud_dir}). Datenbank & Vereinsdaten sind synchronisiert!`);
    } else {
      showStorageAlert('success', 'Lokaler Speichermodus aktiviert.');
    }
    await refreshAll();
  } catch (err) {
    showStorageAlert('error', `Fehler beim Speichern des Speicherorts: ${err.message}`);
  } finally {
    if (saveBtn) {
      saveBtn.disabled = false;
      saveBtn.textContent = 'Speicherort speichern';
    }
  }
}

async function triggerManualCloudSync() {
  const btn = document.getElementById('btn-manual-cloud-sync');
  if (btn) {
    btn.disabled = true;
    btn.textContent = 'Synchronisiere…';
  }
  try {
    const res = await fetch('/adsi-admin/api/config/storage/sync', { method: 'POST' });
    const data = await res.json();
    if (data.status === 'ok') {
      showStorageAlert('success', data.message || 'Cloud-Synchronisation erfolgreich.');
    } else {
      showStorageAlert('error', data.message || 'Synchronisation fehlgeschlagen.');
    }
    await loadStorageConfig();
  } catch (err) {
    showStorageAlert('error', `Fehler bei der Cloud-Synchronisation: ${err.message}`);
  } finally {
    if (btn) {
      btn.disabled = false;
      btn.textContent = '🔄 Jetzt mit Cloud synchronisieren';
    }
  }
}

// ==========================================================================
// Admin Onboarding Tour
// ==========================================================================
const ADMIN_TOUR_STORAGE_KEY = 'oetsv_admin_tour_v1';
let currentAdminTourStep = 0;

const ADMIN_TOUR_STEPS = [
  {
    selector: '.admin-grid',
    title: 'System-KPIs & Überblick',
    description: 'Hier siehst du auf einen Blick die aktuelle Anzahl gespeicherter Turniere, gemeldeter Vereinspaare, Startklassen, Ergebnisse und importierter Teilnehmer.'
  },
  {
    selector: '#btn-trigger-scraper',
    title: 'Manuelle Job-Steuerung',
    description: 'Alle Scraper laufen automatisch im Hintergrund. Über diese Buttons kannst du den Turnierkalender, Teilnehmerlisten, Ergebnisse oder den Mail-Import jederzeit sofort manuell starten.'
  },
  {
    selector: '#storage-config-card',
    title: 'Datenspeicher & Cloud-Sync',
    description: 'Wähle hier, ob die Datenbank lokal oder in einem Cloud-Ordner (iCloud Drive, Google Drive, OneDrive) liegt. Vereinsdaten werden immer mitgespeichert, IMAP-Daten optional per Schalter.'
  },
  {
    selector: '#club-config-form',
    title: 'Verein einstellen',
    description: 'Trage hier deinen Vereinsnamen (z. B. „TSC Musterverein“) und das Kurz-Badge ein. Alle Teilnehmerlisten und Hervorhebungen im Portal passen sich beim Speichern sofort automatisch an!'
  },
  {
    selector: '#imap-config-form',
    title: 'IMAP E-Mail-Postfach & Mock-Modus',
    description: 'Hinterlege hier optional das E-Mail-Postfach, an das ÖTSV-Nennungsbestätigungen gesendet werden – oder nutze den Mock-Modus zum sofortigen Testen mit Beispieldaten.'
  }
];

function clearAdminTourHighlight() {
  document.querySelectorAll('.tour-active-target').forEach(el => {
    el.classList.remove('tour-active-target');
  });
}

function scrollAndPositionAdminTourPopover(popover, targetEl) {
  if (!targetEl) return;

  const rectBefore = targetEl.getBoundingClientRect();
  const headerOffset = 95;
  if (rectBefore.top < headerOffset || rectBefore.top > window.innerHeight * 0.55) {
    const targetScrollY = Math.max(0, window.scrollY + rectBefore.top - headerOffset);
    window.scrollTo({ top: targetScrollY, behavior: 'smooth' });
  }

  const updateCoords = () => {
    if (!popover.matches(':popover-open')) return;
    const rect = targetEl.getBoundingClientRect();
    const popRect = popover.getBoundingClientRect();
    const popW = popRect.width || 400;
    const popH = popRect.height || 210;
    const margin = 16;

    let left = rect.left + (rect.width / 2) - (popW / 2);
    left = Math.max(margin, Math.min(left, window.innerWidth - popW - margin));

    let top;
    if (rect.height > window.innerHeight * 0.45) {
      top = Math.max(headerOffset + 12, rect.top + 56);
    } else if (rect.bottom + popH + margin <= window.innerHeight) {
      top = rect.bottom + 14;
    } else if (rect.top - popH - margin >= headerOffset) {
      top = rect.top - popH - 14;
    } else {
      top = window.innerHeight - popH - margin;
    }

    top = Math.max(margin, Math.min(top, window.innerHeight - popH - margin));
    popover.style.left = `${Math.round(left)}px`;
    popover.style.top = `${Math.round(top)}px`;
  };

  requestAnimationFrame(updateCoords);
  setTimeout(updateCoords, 260);
}

function renderAdminTourStep(index) {
  const popover = document.getElementById('app-tour-popover');
  if (!popover || index < 0 || index >= ADMIN_TOUR_STEPS.length) return;

  currentAdminTourStep = index;
  const step = ADMIN_TOUR_STEPS[index];

  clearAdminTourHighlight();
  const targetEl = document.querySelector(step.selector);
  if (targetEl) {
    targetEl.classList.add('tour-active-target');
  }

  document.getElementById('tour-step-badge').textContent = `Schritt ${index + 1} von ${ADMIN_TOUR_STEPS.length}`;
  document.getElementById('tour-title').textContent = step.title;
  document.getElementById('tour-description').textContent = step.description;

  const dotsContainer = document.getElementById('tour-dots');
  if (dotsContainer) {
    dotsContainer.innerHTML = ADMIN_TOUR_STEPS
      .map((_, i) => `<span class="tour-dot ${i === index ? 'active' : ''}"></span>`)
      .join('');
  }

  const prevBtn = document.getElementById('tour-prev-btn');
  const nextBtn = document.getElementById('tour-next-btn');
  if (prevBtn) {
    prevBtn.style.display = index === 0 ? 'none' : 'inline-flex';
  }
  if (nextBtn) {
    nextBtn.innerHTML = index === ADMIN_TOUR_STEPS.length - 1 ? 'Fertig &#10003;' : 'Weiter &rarr;';
  }

  if (typeof popover.showPopover === 'function') {
    try {
      if (!popover.matches(':popover-open')) {
        popover.showPopover();
      }
    } catch (_) {}
  }

  if (targetEl) {
    scrollAndPositionAdminTourPopover(popover, targetEl);
  }

  if (nextBtn) {
    nextBtn.focus({ preventScroll: true });
  }
}

function finishAdminOnboardingTour() {
  clearAdminTourHighlight();
  localStorage.setItem(ADMIN_TOUR_STORAGE_KEY, 'completed');
  const popover = document.getElementById('app-tour-popover');
  if (popover && typeof popover.hidePopover === 'function') {
    try {
      if (popover.matches(':popover-open')) {
        popover.hidePopover();
      }
    } catch (_) {}
  }
}

function initAdminOnboardingTour() {
  const popover = document.getElementById('app-tour-popover');
  if (!popover) return;

  const startBtn = document.getElementById('btn-start-admin-tour');
  if (startBtn) {
    startBtn.addEventListener('click', () => renderAdminTourStep(0));
  }

  const prevBtn = document.getElementById('tour-prev-btn');
  if (prevBtn) {
    prevBtn.addEventListener('click', () => {
      if (currentAdminTourStep > 0) {
        renderAdminTourStep(currentAdminTourStep - 1);
      }
    });
  }

  const nextBtn = document.getElementById('tour-next-btn');
  if (nextBtn) {
    nextBtn.addEventListener('click', () => {
      if (currentAdminTourStep < ADMIN_TOUR_STEPS.length - 1) {
        renderAdminTourStep(currentAdminTourStep + 1);
      } else {
        finishAdminOnboardingTour();
      }
    });
  }

  popover.addEventListener('beforetoggle', (e) => {
    if (e.newState === 'closed') {
      clearAdminTourHighlight();
      localStorage.setItem(ADMIN_TOUR_STORAGE_KEY, 'completed');
    }
  });

  if (!localStorage.getItem(ADMIN_TOUR_STORAGE_KEY)) {
    setTimeout(() => renderAdminTourStep(0), 350);
  }
}



