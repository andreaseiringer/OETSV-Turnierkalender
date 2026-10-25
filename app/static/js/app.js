/**
 * pivitLABS ÖTSV Tool - Frontend Logic (https://pivitlabs.com)
 */

// State
let allTournaments = [];
let currentTab = 'aktuell'; // 'aktuell' | 'vergangen'
let selectedBundesland = 'Alle';
let selectedDisziplin = 'Alle';
let selectedAltersklasse = 'Alle';
let searchQuery = '';
let filterOnlyWithResults = false;
let expandedTagsTournaments = new Set();
let currentTeilnehmerData = null;
let selectedTeilnehmerClass = 'Alle';
let teilnehmerSearchQuery = '';
let clubName = 'TSC Musterverein';
let clubShort = 'Musterverein';

// Alias Mapping for Age Categories (FA-5.2)
const AGE_MAPPINGS = {
  'Allgemeine Klasse': ['allg', 'allgemeine klasse', 'allg. klasse', 'allg. kl.'],
  'Senioren': ['sen', 'senioren', 'sen.', 'seniors'],
  'Jugend': ['jug', 'jugend', 'youth'],
  'Junioren': ['jun', 'junioren', 'juniors'],
  'Schüler': ['sch', 'schüler', 'schueler']
};

const BUNDESLAND_MAPPINGS = {
  'NÖ': 'Niederösterreich',
  'OÖ': 'Oberösterreich'
};

document.addEventListener('DOMContentLoaded', async () => {
  initTheme();
  setupEventListeners();
  await loadVersion();
  await loadTournaments();
  loadSyncStatus();
  initOnboardingTour();
});

// 1. Theme Management (FA-5.7)
function initTheme() {
  const saved = localStorage.getItem('adsi-theme');
  if (saved) {
    applyTheme(saved);
  } else {
    const prefersDark = window.matchMedia && window.matchMedia('(prefers-color-scheme: dark)').matches;
    applyTheme(prefersDark ? 'dark' : 'light');
  }

  // System preference change listener
  if (window.matchMedia) {
    window.matchMedia('(prefers-color-scheme: dark)').addEventListener('change', e => {
      if (!localStorage.getItem('adsi-theme')) {
        applyTheme(e.matches ? 'dark' : 'light');
      }
    });
  }
}

function applyTheme(theme) {
  document.documentElement.setAttribute('data-theme', theme);
  const icon = document.getElementById('theme-icon');
  if (icon) {
    icon.innerHTML = theme === 'dark'
      ? '<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="12" r="5"/><path d="M12 1v2M12 21v2M4.2 4.2l1.4 1.4M18.4 18.4l1.4 1.4M1 12h2M21 12h2M4.2 19.8l1.4-1.4M18.4 5.6l1.4-1.4"/></svg>'
      : '<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M21 12.79A9 9 0 1 1 11.21 3 7 7 0 0 0 21 12.79z"/></svg>';
  }
}

function toggleTheme() {
  const current = document.documentElement.getAttribute('data-theme') || 'light';
  const next = current === 'dark' ? 'light' : 'dark';
  localStorage.setItem('adsi-theme', next);
  applyTheme(next);
}

// 2. Event Listeners Setup
function setupEventListeners() {
  document.getElementById('theme-toggle').addEventListener('click', toggleTheme);

  // Search input
  const searchInput = document.getElementById('search-input');
  searchInput.addEventListener('input', (e) => {
    searchQuery = e.target.value.toLowerCase().trim();
    render();
  });

  // Filter chips: Bundesland
  document.querySelectorAll('#filter-bundesland .chip-btn').forEach(btn => {
    btn.addEventListener('click', () => {
      document.querySelectorAll('#filter-bundesland .chip-btn').forEach(b => b.classList.remove('active'));
      btn.classList.add('active');
      selectedBundesland = btn.getAttribute('data-val');
      render();
    });
  });

  // Filter chips: Disziplin
  document.querySelectorAll('#filter-disziplin .chip-btn').forEach(btn => {
    btn.addEventListener('click', () => {
      document.querySelectorAll('#filter-disziplin .chip-btn').forEach(b => b.classList.remove('active'));
      btn.classList.add('active');
      selectedDisziplin = btn.getAttribute('data-val');
      render();
    });
  });

  // Filter chips: Altersklasse
  document.querySelectorAll('#filter-altersklasse .chip-btn').forEach(btn => {
    btn.addEventListener('click', () => {
      document.querySelectorAll('#filter-altersklasse .chip-btn').forEach(b => b.classList.remove('active'));
      btn.classList.add('active');
      selectedAltersklasse = btn.getAttribute('data-val');
      render();
    });
  });

  // Results filter button
  const resFilterBtn = document.getElementById('filter-results-btn');
  if (resFilterBtn) {
    resFilterBtn.addEventListener('click', () => {
      filterOnlyWithResults = !filterOnlyWithResults;
      resFilterBtn.classList.toggle('active', filterOnlyWithResults);
      render();
    });
  }

  // Reset filters
  document.getElementById('btn-reset-filters').addEventListener('click', resetFilters);

  // Tabs
  document.getElementById('tab-aktuell').addEventListener('click', () => {
    currentTab = 'aktuell';
    document.getElementById('tab-aktuell').classList.add('active');
    document.getElementById('tab-vergangen').classList.remove('active');
    render();
  });

  document.getElementById('tab-vergangen').addEventListener('click', () => {
    currentTab = 'vergangen';
    document.getElementById('tab-vergangen').classList.add('active');
    document.getElementById('tab-aktuell').classList.remove('active');
    render();
  });

  // Modal close
  document.getElementById('modal-close-btn').addEventListener('click', closeModal);
  document.getElementById('modal-close-footer').addEventListener('click', closeModal);
  document.getElementById('paare-modal').addEventListener('click', (e) => {
    if (e.target.id === 'paare-modal') closeModal();
  });

  // Teilnehmer Modal listeners
  const tCloseBtn = document.getElementById('teilnehmer-modal-close-btn');
  if (tCloseBtn) tCloseBtn.addEventListener('click', closeTeilnehmerModal);
  const tCloseFooter = document.getElementById('teilnehmer-modal-close-footer');
  if (tCloseFooter) tCloseFooter.addEventListener('click', closeTeilnehmerModal);
  const tModal = document.getElementById('teilnehmer-modal');
  if (tModal) {
    tModal.addEventListener('click', (e) => {
      if (e.target.id === 'teilnehmer-modal') closeTeilnehmerModal();
    });
  }
  const tSearch = document.getElementById('teilnehmer-search-input');
  if (tSearch) {
    tSearch.addEventListener('input', (e) => {
      teilnehmerSearchQuery = e.target.value.toLowerCase().trim();
      renderTeilnehmerContent();
    });
  }
  const tClassSelect = document.getElementById('teilnehmer-class-select');
  if (tClassSelect) {
    tClassSelect.addEventListener('change', (e) => {
      selectTeilnehmerClass(e.target.value);
    });
  }

  document.addEventListener('keydown', (e) => {
    if (e.key === 'Escape') {
      closeModal();
      closeTeilnehmerModal();
    }
  });
}

function resetFilters() {
  selectedBundesland = 'Alle';
  selectedDisziplin = 'Alle';
  selectedAltersklasse = 'Alle';
  searchQuery = '';
  filterOnlyWithResults = false;
  document.getElementById('search-input').value = '';

  const resFilterBtn = document.getElementById('filter-results-btn');
  if (resFilterBtn) resFilterBtn.classList.remove('active');

  document.querySelectorAll('.filter-options').forEach(group => {
    group.querySelectorAll('.chip-btn').forEach(btn => {
      if (btn.getAttribute('data-val') === 'Alle') {
        btn.classList.add('active');
      } else {
        btn.classList.remove('active');
      }
    });
  });
  render();
}

// 3. Data Fetching
async function loadTournaments() {
  const container = document.getElementById('table-body');
  container.innerHTML = `
    <tr>
      <td colspan="4" class="loading-state">
        <div class="spinner"></div>
        <p>Lade Turnierdaten...</p>
      </td>
    </tr>
  `;

  try {
    const res = await fetch('/api/turniere?only_current_year=false');
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    allTournaments = await res.json();
    render();
  } catch (err) {
    container.innerHTML = `
      <tr>
        <td colspan="4" class="empty-state">
          <p style="color:#ef4444; font-weight:600;">Fehler beim Laden der Turniere: ${err.message}</p>
        </td>
      </tr>
    `;
  }
}

async function loadSyncStatus() {
  try {
    const res = await fetch('/api/sync-status');
    if (!res.ok) return;
    const data = await res.json();
    const scraper = data.find(s => s.key === 'scraper');
    const fetcher = data.find(s => s.key === 'fetcher');

    const scraperEl = document.getElementById('sync-scraper-status');
    if (scraper && scraperEl) {
      const time = scraper.last_run ? scraper.last_run.split(' ')[0] + ' ' + scraper.last_run.split(' ')[1]?.slice(0,5) : 'Nie';
      scraperEl.textContent = `Scraper: ${time} (+${scraper.added_count}, ~${scraper.updated_count})`;
    }

    const fetcherEl = document.getElementById('sync-fetcher-status');
    if (fetcher && fetcherEl) {
      const time = fetcher.last_run ? fetcher.last_run.split(' ')[0] + ' ' + fetcher.last_run.split(' ')[1]?.slice(0,5) : 'Nie';
      fetcherEl.textContent = `Mail-Import: ${time} (+${fetcher.added_count})`;
    }

    const resultsScraper = data.find(s => s.key === 'results_scraper');
    const resultsEl = document.getElementById('sync-results-status');
    if (resultsScraper && resultsEl) {
      const time = resultsScraper.last_run ? resultsScraper.last_run.split(' ')[0] + ' ' + resultsScraper.last_run.split(' ')[1]?.slice(0,5) : 'Nie';
      resultsEl.textContent = `Ergebnisse: ${time} (+${resultsScraper.added_count})`;
    }

    const teilnehmerScraper = data.find(s => s.key === 'teilnehmer_scraper');
    const teilnehmerEl = document.getElementById('sync-teilnehmer-status');
    if (teilnehmerScraper && teilnehmerEl) {
      const time = teilnehmerScraper.last_run ? teilnehmerScraper.last_run.split(' ')[0] + ' ' + teilnehmerScraper.last_run.split(' ')[1]?.slice(0,5) : 'Nie';
      teilnehmerEl.textContent = `Teilnehmer: ${time} (+${teilnehmerScraper.added_count})`;
    }
  } catch (e) {
    console.error('Error loading sync status', e);
  }
}

async function loadVersion() {
  try {
    const res = await fetch('/api/version');
    if (res.ok) {
      const data = await res.json();
      const el = document.getElementById('app-version-badge');
      if (el) el.textContent = `v${data.app_version}`;
      if (data.club_name) clubName = data.club_name;
      if (data.club_short) clubShort = data.club_short;
      const subEl = document.getElementById('brand-subtitle');
      if (subEl && clubName) {
        subEl.textContent = `${clubName} • Turnierkalender & Nennungen`;
      }
    }
  } catch (_) {}
}

// 4. Filtering & Rendering (FA-5.2, FA-5.3, FA-5.4)
function getCutoffDate() {
  // 7 days grace period: today - 7 days
  const now = new Date();
  now.setDate(now.getDate() - 7);
  const y = now.getFullYear();
  const m = String(now.getMonth() + 1).padStart(2, '0');
  const d = String(now.getDate()).padStart(2, '0');
  return `${y}-${m}-${d}`;
}

function matchesAge(tournamentTags, targetAge) {
  if (targetAge === 'Alle') return true;
  const aliases = AGE_MAPPINGS[targetAge] || [targetAge.toLowerCase()];
  return tournamentTags.some(tag => {
    const t = tag.toLowerCase();
    return aliases.some(alias => t.includes(alias));
  });
}

function matchesDiscipline(tournamentTags, targetDiscipline) {
  if (targetDiscipline === 'Alle') return true;
  const target = targetDiscipline.toLowerCase();
  return tournamentTags.some(tag => tag.toLowerCase().includes(target));
}

function matchesBundesland(bundesland, target) {
  if (target === 'Alle') return true;
  if (!bundesland) return false;
  const targetFullName = BUNDESLAND_MAPPINGS[target] || target;
  return bundesland.toLowerCase().includes(targetFullName.toLowerCase());
}

function render() {
  const cutoff = getCutoffDate();

  // Active filters badge
  const hasActiveFilters = selectedBundesland !== 'Alle' || selectedDisziplin !== 'Alle' || selectedAltersklasse !== 'Alle' || searchQuery.length > 0 || filterOnlyWithResults;
  const badge = document.getElementById('active-filters-indicator');
  if (badge) {
    badge.style.display = hasActiveFilters ? 'inline-flex' : 'none';
  }

  // Split tournaments into Aktuell and Vergangen
  let aktuellList = [];
  let vergangenList = [];

  allTournaments.forEach(t => {
    if (t.datum_sort >= cutoff) {
      aktuellList.push(t);
    } else {
      vergangenList.push(t);
    }
  });

  // Sorting
  aktuellList.sort((a, b) => a.datum_sort.localeCompare(b.datum_sort)); // Ascending
  vergangenList.sort((a, b) => b.datum_sort.localeCompare(a.datum_sort)); // Descending

  // Update tab counts
  document.getElementById('count-aktuell').textContent = aktuellList.length;
  document.getElementById('count-vergangen').textContent = vergangenList.length;

  const currentList = currentTab === 'aktuell' ? aktuellList : vergangenList;

  // Apply filters
  const filtered = currentList.filter(t => {
    // Only with results filter
    if (filterOnlyWithResults && (!t.ergebnisse_anzahl || t.ergebnisse_anzahl === 0)) {
      return false;
    }

    // Full text search (FA-5.2)
    if (searchQuery) {
      const matchTitle = t.titel.toLowerCase().includes(searchQuery);
      const matchKlub = t.klub ? t.klub.toLowerCase().includes(searchQuery) : false;
      const matchBundesland = t.bundesland ? t.bundesland.toLowerCase().includes(searchQuery) : false;
      if (!matchTitle && !matchKlub && !matchBundesland) return false;
    }

    // Bundesland filter
    if (!matchesBundesland(t.bundesland, selectedBundesland)) return false;

    // Disziplin filter
    if (!matchesDiscipline(t.tags, selectedDisziplin)) return false;

    // Altersklasse filter
    if (!matchesAge(t.tags, selectedAltersklasse)) return false;

    return true;
  });

  // Render Table
  const tbody = document.getElementById('table-body');
  if (filtered.length === 0) {
    tbody.innerHTML = `
      <tr>
        <td colspan="4" class="empty-state">
          <p>Keine Turniere für die ausgewählten Kriterien gefunden.</p>
        </td>
      </tr>
    `;
    return;
  }

  tbody.innerHTML = filtered.map(t => renderTournamentRow(t)).join('');
}

function renderTournamentRow(t) {
  const isExpanded = expandedTagsTournaments.has(t.id);

  // Separate primary tags vs secondary tags (FA-5.4)
  const primaryDisciplines = ['standard', 'latein', 'kombination', 'formationen'];
  const primaryTags = [];
  const secondaryTags = [];

  t.tags.forEach(tag => {
    const tLower = tag.toLowerCase();
    if (primaryDisciplines.some(p => tLower.includes(p))) {
      primaryTags.push(tag);
    } else {
      secondaryTags.push(tag);
    }
  });

  const visibleSecondary = isExpanded ? secondaryTags : [];
  const hasMoreTags = secondaryTags.length > 0;

  // Tag HTML generator
  const renderTagChip = (tag) => {
    const tl = tag.toLowerCase();
    let modifier = '';
    if (tl.includes('standard')) modifier = 'tag-standard';
    else if (tl.includes('latein')) modifier = 'tag-latein';
    else if (tl.includes('kombination') || tl.includes('kombi')) modifier = 'tag-kombi';
    return `<span class="tag-badge ${modifier}">${escapeHtml(tag)}</span>`;
  };

  // Links (FA-5.5)
  const linkKeys = Object.keys(t.links || {});
  let linksHtml = '<div class="link-buttons">';
  if (linkKeys.length > 0) {
    linkKeys.forEach(k => {
      const url = t.links[k];
      let label = k.charAt(0).toUpperCase() + k.slice(1);
      let btnClass = 'link-btn';
      if (k === 'ausschreibung') {
        label = 'Ausschreibung';
        btnClass += ' btn-ausschreibung';
      } else if (k === 'homepage') {
        label = 'Homepage';
      } else if (k === 'anmeldung') {
        label = 'Anmeldung';
      } else if (k === 'information') {
        label = 'Information';
      }
      linksHtml += `
        <a href="${safeUrl(url)}" target="_blank" rel="noopener noreferrer" class="${btnClass}">
          ${escapeHtml(label)} ↗
        </a>
      `;
    });
  }

  // Teilnehmerliste Button
  if (t.turnier_id) {
    let teilnehmerBadge = '';
    if (t.teilnehmer_anzahl > 0) {
      const utscSnippet = t.teilnehmer_utsc_anzahl > 0 ? ` • ${t.teilnehmer_utsc_anzahl} ${escapeHtml(clubShort)}` : '';
      teilnehmerBadge = `(${t.teilnehmer_anzahl}${utscSnippet})`;
    }
    linksHtml += `
      <button class="link-btn btn-teilnehmer" onclick="openTeilnehmerModal(${t.id})" title="Teilnehmerliste öffnen">
        👥 Teilnehmerliste ${teilnehmerBadge}
      </button>
    `;
  } else if (linkKeys.length === 0) {
    linksHtml += '<span style="color:var(--text-muted); font-size:0.75rem;">—</span>';
  }

  if (t.ergebnisse && t.ergebnisse.length > 0) {
    linksHtml += `
      <button class="btn-copy-html" onclick="copyResultsHtml(${t.id}, this)" title="HTML für Newsblog in Zwischenablage kopieren" style="margin-top:0.35rem;">
        📋 HTML kopieren
      </button>
    `;
  }
  linksHtml += '</div>';

  // Couples Button (FA-5.1)
  let paareHtml = '<span class="no-paare">—</span>';
  if (t.utsc_paare_anzahl > 0) {
    const label = t.utsc_paare_anzahl === 1 ? '1 Paar' : `${t.utsc_paare_anzahl} Paare`;
    paareHtml = `
      <button class="btn-paare" onclick="openPaareModal(${t.id})">
        <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5">
          <path d="M17 21v-2a4 4 0 0 0-4-4H5a4 4 0 0 0-4 4v2"/>
          <circle cx="9" cy="7" r="4"/>
          <path d="M23 21v-2a4 4 0 0 0-3-3.87"/>
          <path d="M16 3.13a4 4 0 0 1 0 7.75"/>
        </svg>
        ${label}
      </button>
    `;
  }

  // Results Box (TopTurnier)
  let ergebnisseHtml = '';
  if (t.ergebnisse && t.ergebnisse.length > 0) {
    const reportUrl = t.turnier_id ? `https://www.tanzsportverband.at/upload/turnierberichte/${String(t.turnier_id).padStart(5, '0')}/index.htm` : null;
    ergebnisseHtml = `
      <div class="tournament-results-box">
        <div class="results-header">
          <span class="results-badge">🏆 ${t.ergebnisse.length} Ergebnis${t.ergebnisse.length > 1 ? 'se' : ''}</span>
          <div class="results-header-actions">
            <button class="btn-copy-html" onclick="copyResultsHtml(${t.id}, this)" title="HTML für Newsblog in Zwischenablage kopieren">
              📋 HTML kopieren
            </button>
            ${reportUrl ? `<a href="${reportUrl}" target="_blank" rel="noopener noreferrer" class="report-link">Offizieller ÖTSV-Bericht ↗</a>` : ''}
          </div>
        </div>
        <div class="results-list">
          ${t.ergebnisse.map(res => {
            let medal = '🎖️';
            let medalClass = 'medal-other';
            if (res.platz_sort === 1) { medal = '🥇'; medalClass = 'medal-gold'; }
            else if (res.platz_sort === 2) { medal = '🥈'; medalClass = 'medal-silver'; }
            else if (res.platz_sort === 3) { medal = '🥉'; medalClass = 'medal-bronze'; }
            const totalStr = res.total_paare > 0 ? ` von ${res.total_paare}` : '';
            return `
              <div class="result-row ${medalClass}">
                <span class="result-medal">${medal}</span>
                <span class="result-platz"><strong>Platz ${escapeHtml(res.platz)}</strong>${totalStr}</span>
                <span class="result-paar">${escapeHtml(res.paar_name)}</span>
                <span class="result-klasse">${escapeHtml(res.klasse_name)}</span>
                ${res.bericht_url ? `<a href="${escapeHtml(res.bericht_url)}" target="_blank" rel="noopener noreferrer" class="result-single-link" title="Ergebnis aufrufen">↗</a>` : ''}
              </div>
            `;
          }).join('')}
        </div>
      </div>
    `;
  }

  return `
    <tr data-id="${t.id}">
      <td class="col-date">
        <div class="date-badge">${escapeHtml(t.datum)}</div>
      </td>
      <td class="col-content">
        <div class="tournament-title">
          ${escapeHtml(t.titel)}
          ${t.ergebnisse_anzahl > 0 ? `<span class="badge-count" style="background:#fef3c7; color:#92400e; border:1px solid #fde68a; margin-left:0.5rem; font-size:0.75rem;">🏆 Ergebnisse</span>` : ''}
        </div>
        <div class="tournament-sub">
          ${t.klub ? `<span class="sub-item"><strong>Klub:</strong> ${escapeHtml(t.klub)}</span>` : ''}
          ${t.bundesland ? `<span class="sub-item"><strong>BL:</strong> ${escapeHtml(t.bundesland)}</span>` : ''}
          ${t.turnier_id ? `<span class="sub-item" style="opacity:0.75;">(TKNr: ${t.turnier_id})</span>` : ''}
        </div>
        <div class="tournament-tags">
          ${primaryTags.map(renderTagChip).join('')}
          ${visibleSecondary.map(renderTagChip).join('')}
          ${hasMoreTags ? `
            <button class="tag-expand-btn" onclick="toggleTags(${t.id})">
              ${isExpanded ? '− Weniger' : `+ ${secondaryTags.length} weitere...`}
            </button>
          ` : ''}
        </div>
        ${ergebnisseHtml}
      </td>
      <td class="col-links">
        ${linksHtml}
      </td>
      <td class="col-paare">
        ${paareHtml}
      </td>
    </tr>
  `;
}

function toggleTags(tournamentId) {
  if (expandedTagsTournaments.has(tournamentId)) {
    expandedTagsTournaments.delete(tournamentId);
  } else {
    expandedTagsTournaments.add(tournamentId);
  }
  render();
}

// 5. Nennungs-Modal (FA-5.6)
function openPaareModal(tournamentId) {
  const t = allTournaments.find(item => item.id === tournamentId);
  if (!t) return;

  document.getElementById('modal-tournament-title').textContent = t.titel;
  document.getElementById('modal-tournament-sub').textContent = `${t.datum} • ${t.klub || 'Verein'} (${t.bundesland || 'Österreich'})`;

  const body = document.getElementById('modal-couples-list');

  let resultsModalHtml = '';
  if (t.ergebnisse && t.ergebnisse.length > 0) {
    resultsModalHtml = `
      <div style="margin-bottom:1.5rem; padding:1rem; border-radius:8px; background:var(--card-bg, #f8fafc); border:1px solid #fbbf24;">
        <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:0.75rem; flex-wrap:wrap; gap:0.5rem;">
          <h4 style="margin:0; color:#b45309; display:flex; align-items:center; gap:0.5rem;">
            🏆 Erzielte Ergebnisse
          </h4>
          <button class="btn-copy-html" onclick="copyResultsHtml(${t.id}, this)" title="HTML für Newsblog in Zwischenablage kopieren">
            📋 HTML kopieren
          </button>
        </div>
        <div style="display:flex; flex-direction:column; gap:0.5rem;">
          ${t.ergebnisse.map(r => `
            <div style="font-size:0.875rem; display:flex; align-items:center; justify-content:space-between; flex-wrap:wrap; gap:0.5rem; padding:0.4rem 0.6rem; border-radius:4px; background:var(--bg-main, #ffffff);">
              <div>
                <strong>${r.platz_sort === 1 ? '🥇' : r.platz_sort === 2 ? '🥈' : r.platz_sort === 3 ? '🥉' : '🎖️'} Platz ${escapeHtml(r.platz)}</strong>
                ${r.total_paare > 0 ? `(von ${r.total_paare})` : ''}: 
                <strong>${escapeHtml(r.paar_name)}</strong> &ndash; <em>${escapeHtml(r.klasse_name)}</em>
              </div>
              ${r.bericht_url ? `<a href="${escapeHtml(r.bericht_url)}" target="_blank" rel="noopener noreferrer" style="color:#2563eb; font-size:0.8rem;">Detail ↗</a>` : ''}
            </div>
          `).join('')}
        </div>
      </div>
    `;
  }

  if (!t.utsc_paare || t.utsc_paare.length === 0) {
    body.innerHTML = resultsModalHtml + '<p class="empty-state">Keine gemeldeten Vereinspaare hinterlegt.</p>';
  } else {
    body.innerHTML = resultsModalHtml + t.utsc_paare.map(p => `
      <div class="couple-entry">
        <div class="couple-header">
          <div class="couple-name">${escapeHtml(p.paar_name)}</div>
          <div class="couple-club">${escapeHtml(p.klub || '')}</div>
        </div>
        <div class="couple-meta">
          ${p.min_partner_1 ? `MIN 1: <strong>${escapeHtml(p.min_partner_1)}</strong>` : ''}
          ${p.min_partner_2 ? ` • MIN 2: <strong>${escapeHtml(p.min_partner_2)}</strong>` : ''}
          ${p.nennungs_id ? ` • Nennungs-ID: <code>${escapeHtml(p.nennungs_id)}</code>` : ''}
        </div>
        <div class="couple-classes">
          ${p.klassen.map(k => `
            <span class="class-chip">
              ${escapeHtml(k.datum)}: ${escapeHtml(k.klasse)}
            </span>
          `).join('')}
        </div>
      </div>
    `).join('');
  }

  const modal = document.getElementById('paare-modal');
  modal.classList.add('open');
}

function closeModal() {
  document.getElementById('paare-modal').classList.remove('open');
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

function safeUrl(url) {
  if (!url) return '#';
  const trimmed = String(url).trim();
  if (/^https?:\/\//i.test(trimmed)) {
    return escapeHtml(trimmed);
  }
  return '#';
}

// 6. Newsblog HTML Generator & Clipboard Copy
function generateNewsblogHtml(t) {
  const reportUrl = t.turnier_id ? `https://www.tanzsportverband.at/upload/turnierberichte/${String(t.turnier_id).padStart(5, '0')}/index.htm` : '';
  
  const rows = (t.ergebnisse || []).map(res => {
    let medal = '🎖️';
    let borderColor = '#cbd5e1';
    let bgTint = '#ffffff';
    if (res.platz_sort === 1) { medal = '🥇'; borderColor = '#eab308'; bgTint = '#fefce8'; }
    else if (res.platz_sort === 2) { medal = '🥈'; borderColor = '#94a3b8'; bgTint = '#f8fafc'; }
    else if (res.platz_sort === 3) { medal = '🥉'; borderColor = '#d97706'; bgTint = '#fffbeb'; }
    const totalStr = res.total_paare > 0 ? ` von ${res.total_paare}` : '';
    const linkStr = res.bericht_url ? ` <a href="${escapeHtml(res.bericht_url)}" target="_blank" rel="noopener" style="color:#2563eb; text-decoration:none; font-weight:bold;">&nearr;</a>` : '';

    return `    <li style="margin-bottom:8px; padding:10px 14px; background-color:${bgTint}; border:1px solid #e2e8f0; border-left:4px solid ${borderColor}; border-radius:6px; display:flex; align-items:center; justify-content:space-between; flex-wrap:wrap; gap:8px;">
      <div>
        <span style="font-size:1.15rem; margin-right:6px;">${medal}</span>
        <strong style="color:#0f172a;">Platz ${escapeHtml(res.platz)}${totalStr}:</strong>
        <strong style="color:#1e293b; margin-left:4px;">${escapeHtml(res.paar_name)}</strong>
        <span style="color:#64748b; font-style:italic; margin-left:6px;">&ndash; ${escapeHtml(res.klasse_name)}</span>
      </div>
      ${linkStr ? `<div>${linkStr}</div>` : ''}
    </li>`;
  }).join('\n');

  return `<div class="turnier-ergebnisse-box" style="font-family:-apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Helvetica, Arial, sans-serif; max-width:760px; margin:20px 0; padding:18px 20px; background-color:#f8fafc; border:1px solid #e2e8f0; border-radius:10px; box-shadow:0 1px 3px rgba(0,0,0,0.05);">
  <div style="margin-bottom:14px; display:flex; justify-content:space-between; align-items:flex-start; flex-wrap:wrap; gap:10px; border-bottom:1px solid #e2e8f0; padding-bottom:10px;">
    <div>
      <h3 style="margin:0 0 4px 0; font-size:1.2rem; font-weight:700; color:#0f172a;">🏆 ${escapeHtml(t.titel)}</h3>
      <div style="font-size:0.875rem; color:#64748b;">
        <span>📅 ${escapeHtml(t.datum)}</span>
        ${t.klub ? `<span style="margin-left:10px;">📍 ${escapeHtml(t.klub)}${t.bundesland ? ' (' + escapeHtml(t.bundesland) + ')' : ''}</span>` : ''}
      </div>
    </div>
    ${reportUrl ? `<a href="${escapeHtml(reportUrl)}" target="_blank" rel="noopener" style="display:inline-block; padding:5px 10px; background-color:#eff6ff; color:#1d4ed8; border:1px solid #bfdbfe; border-radius:6px; font-size:0.8125rem; font-weight:600; text-decoration:none;">Offizieller ÖTSV-Bericht &nearr;</a>` : ''}
  </div>
  <ul style="list-style:none; margin:0; padding:0;">
${rows}
  </ul>
  <div style="margin-top:12px; font-size:0.75rem; color:#94a3b8; text-align:right;">
    ${escapeHtml(clubName)} Turnierergebnisse
  </div>
</div>`;
}

async function copyResultsHtml(tournamentId, btnElement) {
  const t = allTournaments.find(item => item.id === tournamentId);
  if (!t || !t.ergebnisse || t.ergebnisse.length === 0) return;

  const htmlCode = generateNewsblogHtml(t);

  try {
    if (navigator.clipboard && window.isSecureContext) {
      await navigator.clipboard.writeText(htmlCode);
    } else {
      const ta = document.createElement('textarea');
      ta.value = htmlCode;
      ta.style.position = 'fixed';
      ta.style.left = '-9999px';
      document.body.appendChild(ta);
      ta.focus();
      ta.select();
      document.execCommand('copy');
      document.body.removeChild(ta);
    }

    if (btnElement) {
      const origText = btnElement.innerHTML;
      btnElement.innerHTML = '✅ Kopiert!';
      btnElement.classList.add('copied');
      setTimeout(() => {
        btnElement.innerHTML = origText;
        btnElement.classList.remove('copied');
      }, 2000);
    }
  } catch (err) {
    console.error('Failed to copy HTML', err);
    alert('Kopieren fehlgeschlagen: ' + err.message);
  }
}

// 7. Teilnehmerliste Modal Logic
async function openTeilnehmerModal(tournamentId) {
  const t = allTournaments.find(item => item.id === tournamentId);
  if (!t) return;

  const modal = document.getElementById('teilnehmer-modal');
  const titleEl = document.getElementById('teilnehmer-modal-title');
  const subEl = document.getElementById('teilnehmer-modal-sub');
  const origLink = document.getElementById('teilnehmer-original-link');
  const statsEl = document.getElementById('teilnehmer-summary-badge');
  const chipsEl = document.getElementById('teilnehmer-class-chips');
  const contentEl = document.getElementById('teilnehmer-modal-content');
  const updatedEl = document.getElementById('teilnehmer-modal-updated');
  const searchInput = document.getElementById('teilnehmer-search-input');
  const selectEl = document.getElementById('teilnehmer-class-select');

  titleEl.textContent = `Teilnehmerliste: ${t.titel}`;
  subEl.textContent = `${t.datum} • ${t.klub || 'Verein'}${t.bundesland ? ' (' + t.bundesland + ')' : ''} • TKNr: ${t.turnier_id || '—'}`;

  const defaultUrl = t.turnier_id
    ? `https://www.tanzsportverband.at/portal/nennungen/nennungen_liste_002.php?lang=DE&TASNr=${t.turnier_id}&sort=KLASSE&aktion=list`
    : '#';
  origLink.href = defaultUrl;

  selectedTeilnehmerClass = 'Alle';
  teilnehmerSearchQuery = '';
  if (searchInput) searchInput.value = '';
  if (selectEl) selectEl.innerHTML = '<option value="Alle">Alle Klassen</option>';

  chipsEl.innerHTML = '';
  statsEl.innerHTML = '';
  updatedEl.textContent = '';

  contentEl.innerHTML = `
    <div class="loading-state" style="padding: 3rem 1rem;">
      <div class="spinner"></div>
      <p style="margin-top:0.75rem;">Lade Teilnehmerliste...</p>
    </div>
  `;

  modal.classList.add('open');

  try {
    const res = await fetch(`/api/turniere/${t.id}/teilnehmer`);
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    const data = await res.json();
    currentTeilnehmerData = data;

    if (data.original_url) {
      origLink.href = data.original_url;
    }

    if (data.last_updated && updatedEl) {
      updatedEl.textContent = `Zuletzt aktualisiert: ${data.last_updated}`;
    }

    renderTeilnehmerChips();
    renderTeilnehmerContent();
  } catch (err) {
    contentEl.innerHTML = `
      <div class="empty-state">
        <p style="color:#ef4444; font-weight:600;">Fehler beim Laden der Teilnehmerliste: ${escapeHtml(err.message)}</p>
        <p style="margin-top:0.5rem; font-size:0.875rem;">Sie können die offizielle ÖTSV-Liste direkt über den Link oben öffnen.</p>
      </div>
    `;
  }
}

function renderTeilnehmerChips() {
  if (!currentTeilnehmerData) return;
  const chipsEl = document.getElementById('teilnehmer-class-chips');
  const statsEl = document.getElementById('teilnehmer-summary-badge');
  const selectEl = document.getElementById('teilnehmer-class-select');

  const { total_anmeldungen, total_paare, utsc_paare_anzahl, klassen } = currentTeilnehmerData;

  const utscBadge = utsc_paare_anzahl > 0
    ? `<span class="utsc-stat-pill">★ ${utsc_paare_anzahl} ${escapeHtml(clubName)} ${utsc_paare_anzahl === 1 ? 'Paar' : 'Paare'}</span>`
    : '';

  statsEl.innerHTML = `
    <span><strong>${total_anmeldungen}</strong> Nennung${total_anmeldungen === 1 ? '' : 'en'} (${total_paare} Paare) in <strong>${klassen.length}</strong> Klassen</span>
    ${utscBadge}
  `;

  if (selectEl) {
    let selectHtml = `<option value="Alle">Alle Klassen (${total_anmeldungen} Nennungen)</option>`;
    klassen.forEach(k => {
      const star = k.utsc_anzahl > 0 ? '★ ' : '';
      const utscTag = k.utsc_anzahl > 0 ? ` [${k.utsc_anzahl} ${escapeHtml(clubShort)}]` : '';
      selectHtml += `<option value="${escapeHtml(k.klasse)}" ${selectedTeilnehmerClass === k.klasse ? 'selected' : ''}>${star}${escapeHtml(k.klasse)} (${k.paare_anzahl})${utscTag}</option>`;
    });
    selectEl.innerHTML = selectHtml;
    selectEl.value = selectedTeilnehmerClass;
  }

  let chipsHtml = `
    <button class="chip-btn ${selectedTeilnehmerClass === 'Alle' ? 'active' : ''}" data-class="Alle" onclick="selectTeilnehmerClass('Alle')">
      Alle Klassen (${total_anmeldungen})
    </button>
  `;

  klassen.forEach(k => {
    const isActive = selectedTeilnehmerClass === k.klasse;
    const utscIndicator = k.utsc_anzahl > 0 ? ` <span class="chip-utsc-dot" title="${k.utsc_anzahl} ${escapeHtml(clubName)} Paar(e)">★</span>` : '';
    chipsHtml += `
      <button class="chip-btn ${isActive ? 'active' : ''} ${k.utsc_anzahl > 0 ? 'chip-has-utsc' : ''}" data-class="${escapeHtml(k.klasse)}" onclick="selectTeilnehmerClass('${escapeHtml(k.klasse)}')">
        ${escapeHtml(k.klasse)} (${k.paare_anzahl})${utscIndicator}
      </button>
    `;
  });

  chipsEl.innerHTML = chipsHtml;
}

function selectTeilnehmerClass(className) {
  selectedTeilnehmerClass = className;

  const selectEl = document.getElementById('teilnehmer-class-select');
  if (selectEl && selectEl.value !== className) {
    selectEl.value = className;
  }

  const chipsEl = document.getElementById('teilnehmer-class-chips');
  if (chipsEl) {
    chipsEl.querySelectorAll('.chip-btn').forEach(btn => {
      const match = btn.getAttribute('data-class') === className;
      btn.classList.toggle('active', match);
      if (match) {
        btn.scrollIntoView({ behavior: 'smooth', block: 'nearest', inline: 'center' });
      }
    });
  }

  const contentEl = document.getElementById('teilnehmer-modal-content');
  if (contentEl) contentEl.scrollTop = 0;

  renderTeilnehmerContent();
}

function renderTeilnehmerContent() {
  if (!currentTeilnehmerData) return;
  const contentEl = document.getElementById('teilnehmer-modal-content');

  const { klassen } = currentTeilnehmerData;
  if (!klassen || klassen.length === 0) {
    contentEl.innerHTML = `
      <div class="empty-state">
        <p>Noch keine Nennungen eingelangt oder importiert.</p>
        <p style="margin-top:0.5rem; font-size:0.875rem;">
          Prüfen Sie auch die <a href="${escapeHtml(currentTeilnehmerData.original_url)}" target="_blank" rel="noopener" style="color:var(--primary); font-weight:600;">originale ÖTSV-Teilnehmerliste ↗</a>.
        </p>
      </div>
    `;
    return;
  }

  // Filter classes
  let filteredKlassen = klassen;
  if (selectedTeilnehmerClass !== 'Alle') {
    filteredKlassen = klassen.filter(k => k.klasse === selectedTeilnehmerClass);
  }

  // Filter couples within classes if search query is present
  const htmlParts = [];

  filteredKlassen.forEach(k => {
    let paare = k.paare;
    if (teilnehmerSearchQuery) {
      const q = teilnehmerSearchQuery.toLowerCase();
      const classMatches = k.klasse.toLowerCase().includes(q);
      if (!classMatches) {
        paare = paare.filter(p =>
          p.paar_name.toLowerCase().includes(q) ||
          (p.klub && p.klub.toLowerCase().includes(q))
        );
      }
    }

    if (paare.length === 0 && teilnehmerSearchQuery) {
      return;
    }

    const classUtscCount = paare.filter(p => p.is_utsc).length;

    htmlParts.push(`
      <div class="teilnehmer-class-card ${classUtscCount > 0 ? 'card-has-utsc' : ''}">
        <div class="teilnehmer-class-header">
          <div class="class-title-group">
            <span class="class-badge">Klasse</span>
            <strong class="class-name">${escapeHtml(k.klasse)}</strong>
            <span class="class-count">(${paare.length} ${paare.length === 1 ? 'Paar/Person' : 'Paare/Personen'})</span>
          </div>
          ${classUtscCount > 0 ? `
            <span class="utsc-class-badge">
              ★ ${classUtscCount} ${escapeHtml(clubName)}
            </span>
          ` : ''}
        </div>
        <div class="teilnehmer-couples-grid">
          ${paare.map((p, idx) => {
            const isUtsc = p.is_utsc;
            return `
              <div class="teilnehmer-couple-card ${isUtsc ? 'utsc-highlight' : ''}">
                <div class="couple-index">${idx + 1}</div>
                <div class="couple-info">
                  <div class="couple-name">
                    ${escapeHtml(p.paar_name)}
                    ${isUtsc ? `<span class="utsc-club-tag">${escapeHtml(clubName)}</span>` : ''}
                  </div>
                  <div class="couple-club-text">
                    ${escapeHtml(p.klub || 'Keine Klubangabe')}
                  </div>
                </div>
              </div>
            `;
          }).join('')}
        </div>
      </div>
    `);
  });

  if (htmlParts.length === 0) {
    contentEl.innerHTML = `
      <div class="empty-state">
        <p>Keine Paare für "${escapeHtml(teilnehmerSearchQuery)}" gefunden.</p>
      </div>
    `;
    return;
  }

  contentEl.innerHTML = htmlParts.join('');
}

function closeTeilnehmerModal() {
  const modal = document.getElementById('teilnehmer-modal');
  if (modal) modal.classList.remove('open');
}

// ==========================================================================
// 11. Interactive First-Start Onboarding Tour
// ==========================================================================
const TOUR_STORAGE_KEY = 'oetsv_portal_tour_v1';
let currentTourStepIndex = 0;

function getPortalTourSteps() {
  return [
    {
      selector: '#tour-target-brand',
      title: 'Willkommen im pivitLABS ÖTSV Tool!',
      description: `Dein lokales Tanzsport-Informationssystem für ${clubName}. Diese kurze Tour zeigt dir in 6 Schritten die wichtigsten Funktionen.`
    },
    {
      selector: '.filter-card',
      title: 'Suche & Schnellfilter',
      description: 'Durchsuche alle ÖTSV-Turniere in Echtzeit oder filtere mit einem Klick nach Bundesland, Disziplin (Standard, Latein, Kombination), Altersklasse oder über „🏆 Nur mit Ergebnissen“.'
    },
    {
      selector: '.sub-nav',
      title: 'Aktuelle Turniere, Archiv & Live-Sync',
      description: 'Wechsle zwischen kommenden Turnieren (inkl. 7-Tage-Rückblick aufs letzte Wochenende) und vergangenen Turnieren. Rechts siehst du den Status der automatischen Hintergrund-Jobs.'
    },
    {
      selector: '.table-wrapper',
      title: 'Turnierliste, Teilnehmer & Ergebnisse',
      description: `Klicke bei einem Turnier auf „👥 Teilnehmer“, um alle Starter nach Klassen gruppiert zu sehen (${clubShort}-Paare werden gelb markiert!). Ein Klick auf das grüne Paar-Badge rechts öffnet eure Vereins-Nennungen und Medaillen/Platzierungen.`
    },
    {
      selector: '#tour-target-admin-btn',
      title: 'Admin Control Center & Verein einstellen',
      description: 'Im Admin-Bereich (/adsi-admin) kannst du unter „Verein einstellen“ jederzeit deinen eigenen Vereinsnamen speichern, dein IMAP-Postfach verbinden und Scraper manuell anstoßen.'
    },
    {
      selector: '#btn-start-tour',
      title: 'Tour & Dark/Light Mode',
      description: 'Über das Mond/Sonnen-Symbol wechselst du zwischen hellem und dunklem Design. Mit dem Button „Tour“ kannst du diese Einführung jederzeit erneut starten!'
    }
  ];
}

function clearTourTargetHighlight() {
  document.querySelectorAll('.tour-active-target').forEach(el => {
    el.classList.remove('tour-active-target');
  });
}

function renderTourStep(index) {
  const steps = getPortalTourSteps();
  const popover = document.getElementById('app-tour-popover');
  if (!popover || index < 0 || index >= steps.length) return;

  currentTourStepIndex = index;
  const step = steps[index];

  clearTourTargetHighlight();
  const targetEl = document.querySelector(step.selector);
  if (targetEl) {
    targetEl.classList.add('tour-active-target');
    targetEl.scrollIntoView({ behavior: 'smooth', block: 'center' });
  }

  document.getElementById('tour-step-badge').textContent = `Schritt ${index + 1} von ${steps.length}`;
  document.getElementById('tour-title').textContent = step.title;
  document.getElementById('tour-description').textContent = step.description;

  const dotsContainer = document.getElementById('tour-dots');
  if (dotsContainer) {
    dotsContainer.innerHTML = steps
      .map((_, i) => `<span class="tour-dot ${i === index ? 'active' : ''}"></span>`)
      .join('');
  }

  const prevBtn = document.getElementById('tour-prev-btn');
  const nextBtn = document.getElementById('tour-next-btn');
  if (prevBtn) {
    prevBtn.style.display = index === 0 ? 'none' : 'inline-flex';
  }
  if (nextBtn) {
    nextBtn.innerHTML = index === steps.length - 1 ? 'Fertig &#10003;' : 'Weiter &rarr;';
  }

  if (typeof popover.showPopover === 'function') {
    try {
      if (!popover.matches(':popover-open')) {
        popover.showPopover();
      }
    } catch (_) {}
  }

  // MANDATORY: Programmatically route focus into the non-modal popover
  if (nextBtn) {
    nextBtn.focus();
  }
}

function finishOnboardingTour() {
  clearTourTargetHighlight();
  localStorage.setItem(TOUR_STORAGE_KEY, 'completed');
  const popover = document.getElementById('app-tour-popover');
  if (popover && typeof popover.hidePopover === 'function') {
    try {
      if (popover.matches(':popover-open')) {
        popover.hidePopover();
      }
    } catch (_) {}
  }
}

function startOnboardingTour() {
  renderTourStep(0);
}

function initOnboardingTour() {
  const popover = document.getElementById('app-tour-popover');
  if (!popover) return;

  const startBtn = document.getElementById('btn-start-tour');
  if (startBtn) {
    startBtn.addEventListener('click', () => startOnboardingTour());
  }

  const prevBtn = document.getElementById('tour-prev-btn');
  if (prevBtn) {
    prevBtn.addEventListener('click', () => {
      if (currentTourStepIndex > 0) {
        renderTourStep(currentTourStepIndex - 1);
      }
    });
  }

  const nextBtn = document.getElementById('tour-next-btn');
  if (nextBtn) {
    nextBtn.addEventListener('click', () => {
      const steps = getPortalTourSteps();
      if (currentTourStepIndex < steps.length - 1) {
        renderTourStep(currentTourStepIndex + 1);
      } else {
        finishOnboardingTour();
      }
    });
  }

  // Clean up highlight and persist completion when closed via popovertargetaction="hide"
  popover.addEventListener('beforetoggle', (e) => {
    if (e.newState === 'closed') {
      clearTourTargetHighlight();
      localStorage.setItem(TOUR_STORAGE_KEY, 'completed');
    }
  });

  // Automatically start on first visit
  if (!localStorage.getItem(TOUR_STORAGE_KEY)) {
    setTimeout(() => startOnboardingTour(), 350);
  }
}

