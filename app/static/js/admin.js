/**
 * pivitLABS ÖTSV Tool - Admin Control Center Logic (https://pivitlabs.com)
 */

let currentLogTarget = 'system';
let logAutoRefreshInterval = null;

document.addEventListener('DOMContentLoaded', () => {
  initAdminTheme();
  setupAdminListeners();
  refreshAll();

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


