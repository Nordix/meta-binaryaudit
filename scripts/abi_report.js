document.addEventListener('DOMContentLoaded', () => {
  fetch(jsonsource)
    .then(r => { if (!r.ok) throw new Error('HTTP ' + r.status); return r.json(); })
    .then(data => render(data))
    .catch(err => {
      document.getElementById('loading').textContent = 'Error loading data: ' + err.message;
    });
});

function esc(s) {
  return String(s).replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;');
}

function badge(text, color, dataType) {
  const dt = dataType ? ` data-type="${dataType}"` : '';
  return `<span class="badge" style="background:${color}"${dt}>${esc(text)}</span>`;
}

function binaryStatus(b) {
  if (b.crashed) return badge('TOOL CRASH', '#7f8c8d', 'crashed');
  if (b.soname_changed) return badge('SONAME BREAK', '#8e44ad', 'soname');
  const badges = [];
  if (b.is_incompatible) badges.push(badge('ABI CHANGED', '#c0392b', 'abichanged'));
  if (b.func_removed || b.var_removed || b.fsym_removed || b.vsym_removed) badges.push(badge('SYMBOLS REMOVED', '#c0392b', 'removals'));
  if (b.has_incompat_funcs) badges.push(badge('TYPE CHANGED', '#e67e22', 'subtype'));
  if (badges.length) return badges.join(' ');
  if (b.has_change) return badge('ADDITIONS ONLY', '#d4ac0d', 'compatible');
  return badge('CLEAN', '#27ae60');
}

function funcTable(funcs, rowClass, cols) {
  if (!funcs.length) return '';
  const rows = funcs.map(f =>
    `<tr class="${rowClass}"><td class="mono">${esc(f[0])}</td><td class="mono sym">${esc(f[1])}</td></tr>`
  ).join('');
  return `<table class="ftable"><thead><tr>${cols.map(c => `<th>${c}</th>`).join('')}</tr></thead><tbody>${rows}</tbody></table>`;
}

function symList(syms, rowClass) {
  if (!syms.length) return '';
  const rows = syms.map(s => `<tr class="${rowClass}"><td class="mono">${esc(s)}</td></tr>`).join('');
  return `<table class="ftable"><tbody>${rows}</tbody></table>`;
}

function collapsible(label, contentHtml, open) {
  return `<details${open ? ' open' : ''} class="coll">
<summary class="coll-summary">${esc(label)}</summary>
<div class="coll-body">${contentHtml}</div>
</details>`;
}

// Small inline status pill for a version-transition line.
function transStatusPill(status) {
  const map = {
    'INCOMPATIBLE':      ['ABI CHANGED',   '#c0392b'],
    'HAS_REMOVALS':      ['SYMBOLS REMOVED','#c0392b'],
    'SUBTYPE_RISK':      ['TYPE CHANGED',  '#e67e22'],
    'SONAME_BREAK':      ['SONAME BREAK',  '#8e44ad'],
    'COMPATIBLE_CHANGE': ['ADDITIONS ONLY','#d4ac0d'],
    'CRASHED':           ['TOOL CRASH',    '#7f8c8d'],
    'CLEAN':             ['CLEAN',         '#27ae60'],
  };
  const [label, color] = map[status] || map['CLEAN'];
  return `<span class="ver-status-pill" style="background:${color}">${esc(label)}</span>`;
}

// Render the version column as paired old→new transitions grouped by arch,
// so it's always clear which version was compared against which — and what
// the ABI verdict is for each arch group.
function versionCell(p) {
  const trans = p.version_transitions || [];
  if (!trans.length) {
    // Fallback to the flat package-level fields.
    return p.version_old === p.version_new
      ? `<span class="ver-same">${esc(p.version_old)}</span>`
      : `<span class="ver-old">${esc(p.version_old)}</span> → <span class="ver-new">${esc(p.version_new)}</span>`;
  }
  // Single transition, no need to list arches.
  if (trans.length === 1) {
    const t = trans[0];
    const ver = t.old === t.new
      ? `<span class="ver-same">${esc(t.old)}</span>`
      : `<span class="ver-old">${esc(t.old)}</span> → <span class="ver-new">${esc(t.new)}</span>`;
    const pill = (t.status && t.status !== 'CLEAN') ? ' ' + transStatusPill(t.status) : '';
    return `${ver}${pill}`;
  }
  // Multiple distinct transitions across architectures: list each on its own
  // line with the arches it applies to and its own ABI status.
  const rows = trans.map(t => {
    const ver = t.old === t.new
      ? `<span class="ver-same">${esc(t.old)}</span>`
      : `<span class="ver-old">${esc(t.old)}</span> → <span class="ver-new">${esc(t.new)}</span>`;
    const arches = (t.arches || []).length ? `<span class="ver-arches">${esc((t.arches || []).join(', '))}</span>` : '';
    const changedCls = t.old !== t.new ? ' ver-line-changed' : '';
    const pill = transStatusPill(t.status || 'CLEAN');
    return `<div class="ver-line${changedCls}">${pill} ${ver} ${arches}</div>`;
  }).join('');
  return `<div class="ver-multi">${rows}</div>`;
}

function renderBinary(b) {
  if (!b.has_change) {
    return `<div class="binary clean">
<span class="bin-name">${esc(b.name)}</span>
${binaryStatus(b)}
<span class="no-change-note">No ABI changes detected</span>
</div>`;
  }

  const rows = [];
  if (b.func_removed || b.func_changed || b.func_added)
    rows.push(['Functions', b.func_removed, b.func_changed, b.func_added]);
  if (b.var_removed || b.var_changed || b.var_added)
    rows.push(['Variables', b.var_removed, b.var_changed, b.var_added]);
  if (b.fsym_removed || b.fsym_added)
    rows.push(['Function Symbols (no debug)', b.fsym_removed, '-', b.fsym_added]);
  if (b.vsym_removed || b.vsym_added)
    rows.push(['Variable Symbols (no debug)', b.vsym_removed, '-', b.vsym_added]);

  const summaryRows = rows.map(r =>
    `<tr><td>${r[0]}</td><td class="num rem">${r[1]}</td><td class="num chg">${r[2]}</td><td class="num add">${r[3]}</td></tr>`
  ).join('');
  let details = rows.length ? `<table class="summary-table">
<thead><tr><th>Category</th><th>Removed</th><th>Changed</th><th>Added</th></tr></thead>
<tbody>${summaryRows}</tbody></table>` : '';

  if (b.soname_changed) {
    const sonameStr = b.new_soname ? `${esc(b.name)} → ${esc(b.new_soname)}` : esc(b.name);
    details += `<div class="soname-note">⚠ SONAME changed: ${sonameStr}</div>`;
  }

  if (b.removed_funcs && b.removed_funcs.length)
    details += collapsible(`Removed Functions (${b.removed_funcs.length})`,
      funcTable(b.removed_funcs.map(f => [f.signature, f.symbol]), 'rem', ['Function Signature', 'ELF Symbol']));
  if (b.added_funcs && b.added_funcs.length)
    details += collapsible(`Added Functions (${b.added_funcs.length})`,
      funcTable(b.added_funcs.map(f => [f.signature, f.symbol]), 'add', ['Function Signature', 'ELF Symbol']));
  if (b.changed_funcs && b.changed_funcs.length) {
    const inner = b.changed_funcs.map(f => {
      const detail = f.detail ? `<pre class="subtype-detail">${esc(f.detail)}</pre>` : '<em>No detail captured</em>';
      return collapsible(`${f.signature}  [${f.location}]`, detail);
    }).join('');
    details += collapsible(`Changed Functions (${b.changed_funcs.length})`, inner);
  }
  if (b.removed_vars && b.removed_vars.length)
    details += collapsible(`Removed Variables (${b.removed_vars.length})`,
      funcTable(b.removed_vars.map(v => [v.declaration, v.symbol]), 'rem', ['Variable Declaration', 'ELF Symbol']));
  if (b.added_vars && b.added_vars.length)
    details += collapsible(`Added Variables (${b.added_vars.length})`,
      funcTable(b.added_vars.map(v => [v.declaration, v.symbol]), 'add', ['Variable Declaration', 'ELF Symbol']));
  if (b.changed_vars && b.changed_vars.length) {
    const inner = b.changed_vars.map(v => {
      const detail = v.detail ? `<pre class="subtype-detail">${esc(v.detail)}</pre>` : '<em>No detail captured</em>';
      return collapsible(`${v.declaration}  [${v.location}]`, detail);
    }).join('');
    details += collapsible(`Changed Variables (${b.changed_vars.length})`, inner);
  }
  if (b.removed_symbols && b.removed_symbols.length)
    details += collapsible(`Removed Symbols not in Debug Info (${b.removed_symbols.length})`,
      symList(b.removed_symbols, 'rem'));
  if (b.added_symbols && b.added_symbols.length)
    details += collapsible(`Added Symbols not in Debug Info (${b.added_symbols.length})`,
      symList(b.added_symbols, 'add'));

  return `<div class="binary changed-bin">
<div class="bin-header"><span class="bin-name">${esc(b.name)}</span>${binaryStatus(b)}</div>
${details}
</div>`;
}

function pkgBadge(libs) {
  const incompat = libs.filter(b => b.is_incompatible).length;
  const removals = libs.filter(b => b.func_removed || b.var_removed || b.fsym_removed || b.vsym_removed).length;
  const subtype  = libs.filter(b => b.has_incompat_funcs).length;
  const soname   = libs.filter(b => b.soname_changed).length;
  const crashed  = libs.filter(b => b.crashed).length;
  const changed  = libs.filter(b => b.has_change).length;
  if (crashed)   return badge('TOOL CRASH', '#7f8c8d', 'crashed');
  if (incompat)  return badge('ABI CHANGED', '#c0392b', 'abichanged');
  if (removals)  return badge('SYMBOLS REMOVED', '#c0392b', 'removals');
  if (subtype)   return badge('TYPE CHANGED', '#e67e22', 'subtype');
  if (soname)    return badge('SONAME BREAK', '#8e44ad', 'soname');
  if (changed)   return badge('ADDITIONS ONLY', '#d4ac0d', 'compatible');
  return badge('CLEAN', '#27ae60');
}

function pkgStatusCell(libs) {
  const incompat  = libs.filter(b => b.is_incompatible).length;
  const soname    = libs.filter(b => b.soname_changed).length;
  const changed   = libs.filter(b => b.has_change).length;
  const removals  = libs.filter(b => b.func_removed || b.var_removed || b.fsym_removed || b.vsym_removed).length;
  const subtype   = libs.filter(b => b.has_incompat_funcs).length;
  const crashed   = libs.filter(b => b.crashed).length;

  const badges = [];
  if (crashed)   badges.push(badge('TOOL CRASH', '#7f8c8d', 'crashed'));
  if (incompat)  badges.push(badge('ABI CHANGED', '#c0392b', 'abichanged'));
  if (removals)  badges.push(badge('SYMBOLS REMOVED', '#c0392b', 'removals'));
  if (subtype)   badges.push(badge('TYPE CHANGED', '#e67e22', 'subtype'));
  if (soname)    badges.push(badge('SONAME BREAK', '#8e44ad', 'soname'));
  if (changed && !incompat && !removals && !subtype && !soname && !crashed) badges.push(badge('ADDITIONS ONLY', '#d4ac0d', 'compatible'));
  if (!changed && !soname && !crashed) badges.push(badge('CLEAN', '#27ae60'));
  return badges.join(' ');
}

function render(data) {
  const packages = data.packages;
  const ref      = data.comparison.ref;
  const current  = data.comparison.current;
  const fps      = data.suppressed_false_positives || [];

  const totalPkgs     = packages.length;
  const totalBinaries = packages.reduce((s, p) => s + p.libraries.length, 0);
  const cleanPkgs     = packages.filter(p => p.libraries.every(b => b.status === 'CLEAN')).length;
  const changedPkgs   = packages.filter(p => p.libraries.some(b => b.status !== 'CLEAN' && b.status !== 'SONAME_BREAK' && b.status !== 'CRASHED')).length;
  const abiChanged    = packages.filter(p => p.libraries.some(b => b.status === 'INCOMPATIBLE')).length;
  const sonameChanged = packages.filter(p => p.libraries.some(b => b.status === 'SONAME_BREAK')).length;
  const crashed       = packages.filter(p => p.libraries.some(b => b.status === 'CRASHED')).length;

  document.title = `ABI Compatibility Report — ${ref} vs ${current}`;

  // Map JSON library fields back to the shape renderBinary() expects
  function mapLib(lib) {
    const c = lib.changes || {};
    const fn = c.functions || {};
    const vr = c.variables || {};
    const snd = c.symbols_no_debug || {};
    const sndf = snd.functions || {};
    const sndv = snd.variables || {};
    return {
      name:             lib.library,
      crashed:          lib.status === 'CRASHED',
      has_change:       lib.status !== 'CLEAN' && lib.status !== 'CRASHED',
      is_incompatible:  lib.status === 'INCOMPATIBLE',
      soname_changed:   lib.status === 'SONAME_BREAK',
      has_incompat_funcs: (lib.status_flags || []).includes('SUBTYPE_RISK'),
      func_removed:  fn.removed  || 0,
      func_changed:  fn.changed  || 0,
      func_added:    fn.added    || 0,
      var_removed:   vr.removed  || 0,
      var_changed:   vr.changed  || 0,
      var_added:     vr.added    || 0,
      fsym_removed:  sndf.removed || 0,
      fsym_added:    sndf.added   || 0,
      vsym_removed:  sndv.removed || 0,
      vsym_added:    sndv.added   || 0,
      removed_funcs:   lib.removed_functions  || [],
      added_funcs:     lib.added_functions    || [],
      changed_funcs:   (lib.changed_functions || []).map(f => ({
        signature: f.signature, location: f.location, detail: f.detail
      })),
      removed_vars:    lib.removed_variables  || [],
      added_vars:      lib.added_variables    || [],
      changed_vars:    (lib.changed_variables || []).map(v => ({
        declaration: v.declaration, location: v.location, detail: v.detail
      })),
      removed_symbols: lib.removed_symbols || [],
      added_symbols:   lib.added_symbols   || [],
      new_soname:      lib.new_soname || null,
    };
  }

  // Overview table rows
  const pkgRows = packages.map(p => {
    const libs    = p.libraries.map(mapLib);
    const verCell = versionCell(p);
    return `<tr>
<td><a href="#${esc(p.package)}" class="pkg-link">${esc(p.package)}</a></td>
<td>${verCell}</td>
<td class="num">${libs.length}</td>
<td>${pkgStatusCell(libs)}</td>
</tr>`;
  }).join('');

  // Package detail sections
  const pkgSections = packages.map(p => {
    const libs = p.libraries.map(mapLib);
    const trans = p.version_transitions || [];
    const multiVer = trans.length > 1;
    const verInline = multiVer
      ? `${trans.length} version transitions`
      : 'v' + (trans.length === 1
          ? (trans[0].old === trans[0].new ? trans[0].old : `${trans[0].old} → ${trans[0].new}`)
          : (p.version_old === p.version_new ? p.version_old : `${p.version_old} → ${p.version_new}`));
    const verBlock = multiVer
      ? `<div class="pkg-ver-detail">${versionCell(p)}</div>`
      : '';
    const binariesHtml = libs.map(b => renderBinary(b)).join('');
    return `<div class="pkg-section" id="${esc(p.package)}">
<details class="pkg-coll">
<summary class="pkg-summary">
<span class="pkg-name">${esc(p.package)}</span>
<span class="pkg-meta">${esc(verInline)}</span>
<span class="pkg-meta">${libs.length} ${libs.length === 1 ? 'binary' : 'binaries'}</span>
${pkgBadge(libs)}
</summary>
<div class="pkg-body">${verBlock}${binariesHtml}</div>
</details>
</div>`;
  }).join('');

  const fpNote = fps.length
    ? `<div class="fp-note"><strong>Suppressed false positives:</strong><ul>${fps.map(f => `<li>${esc(f)}</li>`).join('')}</ul></div>`
    : '';

  document.getElementById('report-title').textContent = 'ABI Compatibility Report';
  document.getElementById('report-subtitle').innerHTML =
    `Comparison: <strong>${esc(ref)}</strong> vs <strong>${esc(current)}</strong>`;

  document.getElementById('stats').innerHTML = `
  <div class="stat-card blue"><div class="num">${totalPkgs}</div><div class="label">Packages</div></div>
  <div class="stat-card blue"><div class="num">${totalBinaries}</div><div class="label">Total Binaries</div></div>
  <div class="stat-card green"><div class="num">${cleanPkgs}</div><div class="label">No Changes</div></div>
  <div class="stat-card orange"><div class="num">${changedPkgs}</div><div class="label">With Changes</div></div>
  <div class="stat-card red"><div class="num">${abiChanged}</div><div class="label">ABI Changed</div></div>
  <div class="stat-card purple"><div class="num">${sonameChanged}</div><div class="label">SONAME Break</div></div>
  ${crashed ? `<div class="stat-card grey"><div class="num">${crashed}</div><div class="label">Tool Crash</div></div>` : ''}`;

  document.getElementById('overview-tbody').innerHTML = pkgRows;
  document.getElementById('pkg-sections').innerHTML   = pkgSections;
  document.getElementById('fp-note').innerHTML        = fpNote;
  document.getElementById('loading').style.display    = 'none';
  document.getElementById('report-content').style.display = '';
}

function filterPackages() {
  const q    = document.getElementById('search').value.toLowerCase();
  const mode = document.querySelector('.filter-btn.active').dataset.mode;
  let visible = 0;

  // Build a map of package id -> overview row for synced hiding
  const overviewRows = {};
  document.querySelectorAll('#overview-tbody tr').forEach(row => {
    const link = row.querySelector('a.pkg-link');
    if (link) overviewRows[link.getAttribute('href').slice(1)] = row;
  });

  document.querySelectorAll('.pkg-section').forEach(sec => {
    const name        = sec.id.toLowerCase();
    const hasIncompat = !!sec.querySelector('.badge[data-type="abichanged"]');
    const hasRemovals = !!sec.querySelector('.badge[data-type="removals"]');
    const hasSubtype  = !!sec.querySelector('.badge[data-type="subtype"]');
    const hasSoname   = !!sec.querySelector('.badge[data-type="soname"]');
    const hasCrashed  = !!sec.querySelector('.badge[data-type="crashed"]');
    const hasChanged  = !!sec.querySelector('.binary.changed-bin');

    let show = name.includes(q);
    if (mode === 'changed')  show = show && hasChanged && !hasSoname && !hasCrashed;
    if (mode === 'subtype')  show = show && hasSubtype;
    if (mode === 'removals') show = show && hasRemovals;
    if (mode === 'incompat') show = show && hasIncompat;
    if (mode === 'soname')   show = show && hasSoname;
    sec.style.display = show ? '' : 'none';
    if (overviewRows[sec.id]) overviewRows[sec.id].style.display = show ? '' : 'none';
    if (show) visible++;

    sec.querySelectorAll('.binary').forEach(bin => {
      if (mode === 'incompat')
        bin.style.display = bin.querySelector('.badge[data-type="abichanged"]') ? '' : 'none';
      else if (mode === 'removals')
        bin.style.display = bin.querySelector('.badge[data-type="removals"]') ? '' : 'none';
      else if (mode === 'subtype')
        bin.style.display = bin.querySelector('.badge[data-type="subtype"]') ? '' : 'none';
      else if (mode === 'soname')
        bin.style.display = bin.querySelector('.badge[data-type="soname"]') ? '' : 'none';
      else if (mode === 'changed')
        bin.style.display = (bin.classList.contains('clean') || bin.querySelector('.badge[data-type="soname"]') || bin.querySelector('.badge[data-type="crashed"]')) ? 'none' : '';
      else
        bin.style.display = '';
    });
  });
  const noResults = document.getElementById('no-results');
  noResults.style.display = visible === 0 ? '' : 'none';
}

function setFilter(btn, mode) {
  document.querySelectorAll('.filter-btn').forEach(b => b.classList.remove('active'));
  btn.classList.add('active');
  const toggleBtn = document.querySelector('.filter-btn[data-state]');
  toggleBtn.dataset.state = 'collapsed';
  toggleBtn.textContent = 'Expand All';
  document.querySelectorAll('.pkg-coll, .coll').forEach(d => { d.open = false; });
  filterPackages();
}

function toggleAll(btn) {
  const expand = btn.dataset.state !== 'expanded';
  document.querySelectorAll('.pkg-coll, .coll').forEach(d => { d.open = expand; });
  btn.dataset.state = expand ? 'expanded' : 'collapsed';
  btn.textContent   = expand ? 'Collapse All' : 'Expand All';
}
