(function () {
  const treeEl = document.getElementById('tree');
  const contentEl = document.querySelector('.content');
  const docViewerToolbarEl = document.getElementById('doc-viewer-toolbar');

  function getPlaceholderEl(tab) { return document.getElementById('placeholder-' + tab); }
  function getDocEl(tab) { return document.getElementById('doc-' + tab); }
  function getErrorEl(tab) { return document.getElementById('error-' + tab); }
  function getPaneEl(tab) { return document.getElementById('doc-pane-' + tab); }

  var THEME_KEY = 'draft-theme';
  function getTheme() {
    try {
      var t = localStorage.getItem(THEME_KEY);
      return t === 'bright' ? 'bright' : 'night';
    } catch (e) { return 'night'; }
  }
  function setTheme(theme) {
    document.body.setAttribute('data-theme', theme);
    try { localStorage.setItem(THEME_KEY, theme); } catch (e) {}
    var sw = document.getElementById('theme-switch');
    if (sw) sw.setAttribute('aria-checked', theme === 'bright');
  }
  setTheme(getTheme());
  document.getElementById('theme-switch') && document.getElementById('theme-switch').addEventListener('click', function () {
    setTheme(getTheme() === 'bright' ? 'night' : 'bright');
  });

  var DOC_FONT_KEY = 'draft-doc-font';
  var DOC_THEME_KEY = 'draft-doc-theme';
  var DOC_FONT_SIZE_KEY = 'draft-doc-font-size';
  var DOC_DEFAULT_FONT_KEY = 'draft-doc-default-font';
  var DOC_DEFAULT_THEME_KEY = 'draft-doc-default-theme';
  var DOC_FONT_SIZES = [
    { value: 'small', label: 'small' },
    { value: 'medium', label: 'medium' },
    { value: 'large', label: 'large' }
  ];
  var DOC_FONTS = [
    { value: 'default', label: 'Default' },
    { value: 'georgia', label: 'Georgia' },
    { value: 'lora', label: 'Lora' },
    { value: 'source-serif', label: 'Source Serif 4' },
    { value: 'literata', label: 'Literata' },
    { value: 'merriweather', label: 'Merriweather' },
    { value: 'open-sans', label: 'Open Sans' },
    { value: 'crimson-pro', label: 'Crimson Pro' },
    { value: 'ibm-plex-sans', label: 'IBM Plex Sans' },
    { value: 'noto-serif', label: 'Noto Serif' },
    { value: 'inter', label: 'Inter' }
  ];
  var DOC_THEMES = [
    { value: 'default', label: 'Default' },
    { value: 'sepia', label: 'Sepia' },
    { value: 'warm', label: 'Warm' },
    { value: 'cool', label: 'Cool' },
    { value: 'high-contrast', label: 'High contrast' },
    { value: 'soft', label: 'Soft' },
    { value: 'midnight', label: 'Midnight' },
    { value: 'coal', label: 'Coal' },
    { value: 'nord', label: 'Nord' },
    { value: 'dracula', label: 'Dracula' },
    { value: 'forest', label: 'Forest' },
    { value: 'rose', label: 'Rose' },
    { value: 'slate', label: 'Slate' }
  ];
  function getDocFont() {
    try {
      var v = localStorage.getItem(DOC_FONT_KEY);
      if (v && DOC_FONTS.some(function (x) { return x.value === v; })) return v;
    } catch (e) {}
    return 'default';
  }
  function getDefaultDocFont() {
    try {
      var v = localStorage.getItem(DOC_DEFAULT_FONT_KEY);
      if (v && DOC_FONTS.some(function (x) { return x.value === v; })) return v;
    } catch (e) {}
    return 'default';
  }
  function getEffectiveDocFont() {
    var sel = getDocFont();
    return sel === 'default' ? getDefaultDocFont() : sel;
  }
  function setDocFont(value) {
    try { localStorage.setItem(DOC_FONT_KEY, value); } catch (e) {}
    if (contentEl) contentEl.setAttribute('data-doc-font', value === 'default' ? getDefaultDocFont() : value);
  }
  function getDocTheme() {
    try {
      var v = localStorage.getItem(DOC_THEME_KEY);
      if (v && DOC_THEMES.some(function (x) { return x.value === v; })) return v;
    } catch (e) {}
    return 'default';
  }
  function getDefaultDocTheme() {
    try {
      var v = localStorage.getItem(DOC_DEFAULT_THEME_KEY);
      if (v && DOC_THEMES.some(function (x) { return x.value === v; })) return v;
    } catch (e) {}
    return 'default';
  }
  function getEffectiveDocTheme() {
    var sel = getDocTheme();
    return sel === 'default' ? getDefaultDocTheme() : sel;
  }
  function setDocTheme(value) {
    try { localStorage.setItem(DOC_THEME_KEY, value); } catch (e) {}
    if (contentEl) contentEl.setAttribute('data-doc-theme', value === 'default' ? getDefaultDocTheme() : value);
  }
  function getDocFontSize() {
    try {
      var v = localStorage.getItem(DOC_FONT_SIZE_KEY);
      if (v && DOC_FONT_SIZES.some(function (x) { return x.value === v; })) return v;
    } catch (e) {}
    return 'medium';
  }
  function setDocFontSize(value) {
    try { localStorage.setItem(DOC_FONT_SIZE_KEY, value); } catch (e) {}
    if (contentEl) contentEl.setAttribute('data-doc-font-size', value);
  }
  function applyDocViewOptions() {
    if (contentEl) {
      contentEl.setAttribute('data-doc-font', getEffectiveDocFont());
      contentEl.setAttribute('data-doc-theme', getEffectiveDocTheme());
      contentEl.setAttribute('data-doc-font-size', getDocFontSize());
    }
  }
  function setCurrentAsDefault() {
    try {
      localStorage.setItem(DOC_DEFAULT_FONT_KEY, getEffectiveDocFont());
      localStorage.setItem(DOC_DEFAULT_THEME_KEY, getEffectiveDocTheme());
    } catch (e) {}
    applyDocViewOptions();
  }
  applyDocViewOptions();

  var DOC_READER_LINES_KEY = 'draft-doc-reader-lines';
  var DOC_READER_LINES_OPTS = [60, 80, 120, 160, 240];
  function getDocReaderLines() {
    try {
      var v = parseInt(localStorage.getItem(DOC_READER_LINES_KEY), 10);
      if (DOC_READER_LINES_OPTS.indexOf(v) !== -1) return v;
    } catch (e) {}
    return 120;
  }
  function setDocReaderLines(value) {
    var n = parseInt(value, 10);
    if (DOC_READER_LINES_OPTS.indexOf(n) === -1) return;
    try { localStorage.setItem(DOC_READER_LINES_KEY, String(n)); } catch (e) {}
    applyDocReaderLinesToPanes(n);
  }
  var DOC_READER_LINE_HEIGHT_EM = 1.6;
  function applyDocReaderLinesToPanes(n) {
    var lines = n !== undefined ? n : getDocReaderLines();
    var val = String(lines);
    if (contentEl) contentEl.style.setProperty('--doc-reader-lines', val);
    var heightVal = (lines * DOC_READER_LINE_HEIGHT_EM) + 'em';
    [1, 2].forEach(function (tab) {
      var el = document.getElementById('doc-reader-window-' + tab);
      if (el) {
        el.style.setProperty('--doc-reader-lines', val);
        el.style.flex = 'none';
        el.style.height = heightVal;
        el.style.maxHeight = heightVal;
      }
    });
  }
  function applyDocReaderLines() {
    applyDocReaderLinesToPanes(getDocReaderLines());
  }
  applyDocReaderLines();

  (function initDocViewerToolbar() {
    var fontSelect = document.getElementById('doc-font-select');
    var themeSelect = document.getElementById('doc-theme-select');
    if (!fontSelect || !themeSelect) return;
    DOC_FONTS.forEach(function (f) {
      fontSelect.appendChild(document.createElement('option')).value = f.value; fontSelect.lastChild.textContent = f.label;
    });
    DOC_THEMES.forEach(function (t) {
      themeSelect.appendChild(document.createElement('option')).value = t.value; themeSelect.lastChild.textContent = t.label;
    });
    fontSelect.value = getDocFont();
    themeSelect.value = getDocTheme();
    fontSelect.addEventListener('change', function () { setDocFont(fontSelect.value); });
    themeSelect.addEventListener('change', function () { setDocTheme(themeSelect.value); });
    var sizeSelect = document.getElementById('doc-font-size-select');
    if (sizeSelect) {
      sizeSelect.value = getDocFontSize();
      sizeSelect.addEventListener('change', function () { setDocFontSize(sizeSelect.value); });
    }
    var linesSelect = document.getElementById('doc-reader-lines');
    if (linesSelect) {
      linesSelect.value = String(getDocReaderLines());
      linesSelect.addEventListener('change', function () { setDocReaderLines(linesSelect.value); });
    }
    var setDefaultBtn = document.getElementById('doc-set-default-btn');
    if (setDefaultBtn) setDefaultBtn.addEventListener('click', setCurrentAsDefault);
  })();

  var currentDoc = null;
  var activeTab = 1;
  var layoutMode = 'stacked';
  var sideBySideSwapped = false;
  var paneDocs = { 1: null, 2: null };

  var TABS_LAYOUT_KEY = 'draft-tabs-layout';
  var TABS_SWAPPED_KEY = 'draft-tabs-swapped';
  var PANE_1_KEY = 'draft-doc-pane-1';
  var PANE_2_KEY = 'draft-doc-pane-2';
  var ACTIVE_TAB_KEY = 'draft-doc-active-tab';

  function savePanesState() {
    try {
      localStorage.setItem(PANE_1_KEY, paneDocs[1] ? JSON.stringify(paneDocs[1]) : '');
      localStorage.setItem(PANE_2_KEY, paneDocs[2] ? JSON.stringify(paneDocs[2]) : '');
      localStorage.setItem(ACTIVE_TAB_KEY, String(activeTab));
    } catch (e) {}
  }

  function loadDocIntoPane(tab, repo, path) {
    var sourceType = repoSourceTypeMap[repo] || 'local';
    var url = '/api/doc/' + encodeURIComponent(repo) + '/' + path.split('/').map(encodeURIComponent).join('/');
    return fetch(url)
      .then(function (r) {
        if (!r.ok) throw new Error(r.status === 404 ? 'Not found' : 'Failed to load');
        if (isBinaryDoc(path)) return r.blob();
        return r.text();
      })
      .then(function (data) {
        paneDocs[tab] = { repo: repo, path: path };
        if (isBinaryDoc(path)) {
          var blob = data;
          var blobUrl = URL.createObjectURL(blob);
          var ext = path.toLowerCase().slice(path.lastIndexOf('.'));
          if (ext === '.pdf') {
            showDoc('<iframe class="doc-binary-view" src="' + escapeAttr(blobUrl) + '" title="PDF"></iframe>', sourceType, tab);
          } else {
            showDoc('<p class="doc-download">Binary document. <a href="' + escapeAttr(blobUrl) + '" download="' + escapeAttr(path.split('/').pop()) + '">Download</a></p>', sourceType, tab);
          }
          setTimeout(function () { URL.revokeObjectURL(blobUrl); }, 60000);
        } else {
          var text = data;
          if (isPythonDoc(path)) {
            showPythonCodePad(text, path, sourceType, tab);
          } else if (typeof marked !== 'undefined') {
            showDoc(marked.parse(text, { gfm: true }), sourceType, tab);
          } else {
            showDoc('<pre>' + escapeHtml(text) + '</pre>', sourceType, tab);
          }
        }
        addToDocHistory(repo, path, tab);
        renderDocHistory(tab);
      })
      .catch(function () {
        paneDocs[tab] = null;
        var ph = getPlaceholderEl(tab);
        var doc = getDocEl(tab);
        var err = getErrorEl(tab);
        if (ph) ph.classList.remove('hidden');
        if (doc) { doc.classList.add('hidden'); doc.innerHTML = ''; }
        if (err) { err.classList.remove('hidden'); err.textContent = 'Failed to load.'; }
      });
  }

  function loadTabsLayout() {
    try {
      var m = localStorage.getItem(TABS_LAYOUT_KEY);
      if (m === 'side-by-side' || m === 'stacked') layoutMode = m;
      sideBySideSwapped = localStorage.getItem(TABS_SWAPPED_KEY) === '1';
    } catch (e) {}
  }
  function saveTabsLayout() {
    try {
      localStorage.setItem(TABS_LAYOUT_KEY, layoutMode);
      localStorage.setItem(TABS_SWAPPED_KEY, sideBySideSwapped ? '1' : '0');
    } catch (e) {}
  }

  function updateTabBarUI() {
    var stackedBtn = document.getElementById('doc-layout-stacked');
    var sideBtn = document.getElementById('doc-layout-side');
    var swapBtn = document.getElementById('doc-swap-btn');
    var contentWrap = document.getElementById('doc-tabs-content');
    if (getPaneEl(1)) {
      getPaneEl(1).classList.toggle('active', layoutMode === 'stacked' ? activeTab === 1 : true);
      getPaneEl(1).classList.toggle('active-tab', activeTab === 1);
    }
    if (getPaneEl(2)) {
      getPaneEl(2).classList.toggle('active', layoutMode === 'stacked' ? activeTab === 2 : true);
      getPaneEl(2).classList.toggle('active-tab', activeTab === 2);
    }
    if (stackedBtn) stackedBtn.classList.toggle('active', layoutMode === 'stacked');
    if (sideBtn) sideBtn.classList.toggle('active', layoutMode === 'side-by-side');
    if (contentWrap) {
      contentWrap.classList.remove('stacked', 'side-by-side');
      contentWrap.classList.add(layoutMode === 'side-by-side' ? 'side-by-side' : 'stacked');
      contentWrap.classList.toggle('swapped', layoutMode === 'side-by-side' && sideBySideSwapped);
    }
    if (swapBtn) swapBtn.classList.toggle('hidden', layoutMode !== 'side-by-side');
    var num1 = document.getElementById('doc-tab-num-1');
    var num2 = document.getElementById('doc-tab-num-2');
    if (num1) num1.classList.toggle('active', activeTab === 1);
    if (num2) num2.classList.toggle('active', activeTab === 2);
    var vault1 = document.getElementById('btn-save-to-vault-1');
    var vault2 = document.getElementById('btn-save-to-vault-2');
    if (vault1) vault1.classList.toggle('hidden', !paneDocs[1]);
    if (vault2) vault2.classList.toggle('hidden', !paneDocs[2]);
  }

  function updateToolbarVisibility() {
    if (!docViewerToolbarEl) return;
    var hasAny = paneDocs[1] || paneDocs[2];
    if (hasAny) docViewerToolbarEl.classList.remove('hidden');
    else docViewerToolbarEl.classList.add('hidden');
  }

  function clearPane(tabNum) {
    paneDocs[tabNum] = null;
    renderDocHistory(tabNum);
    var ph = getPlaceholderEl(tabNum);
    var doc = getDocEl(tabNum);
    var err = getErrorEl(tabNum);
    if (ph) ph.classList.remove('hidden');
    if (doc) { doc.classList.add('hidden'); doc.innerHTML = ''; }
    if (err) err.classList.add('hidden');
  }

  function afterPanesCleared() {
    currentDoc = paneDocs[activeTab] || paneDocs[activeTab === 1 ? 2 : 1] || null;
    updateTabBarUI();
    updateToolbarVisibility();
    if (currentDoc) setDocHash(currentDoc.repo, currentDoc.path);
    else clearDocHash();
    savePanesState();
  }

  function showPlaceholder(clearStorage) {
    var ph = getPlaceholderEl(activeTab);
    var doc = getDocEl(activeTab);
    var err = getErrorEl(activeTab);
    paneDocs[activeTab] = null;
    renderDocHistory(activeTab);
    currentDoc = paneDocs[activeTab] || paneDocs[activeTab === 1 ? 2 : 1] || null;
    if (clearStorage && !paneDocs[1] && !paneDocs[2]) clearDocHash();
    if (ph) ph.classList.remove('hidden');
    if (doc) { doc.classList.add('hidden'); doc.innerHTML = ''; }
    if (err) err.classList.add('hidden');
    updateTabBarUI();
    updateToolbarVisibility();
    if (currentDoc) setDocHash(currentDoc.repo, currentDoc.path);
    else if (clearStorage) clearDocHash();
    savePanesState();
  }

  function showError(msg) {
    currentDoc = null;
    var ph = getPlaceholderEl(activeTab);
    var doc = getDocEl(activeTab);
    var err = getErrorEl(activeTab);
    if (docViewerToolbarEl) docViewerToolbarEl.classList.add('hidden');
    if (ph) ph.classList.add('hidden');
    if (doc) doc.classList.add('hidden');
    if (err) { err.textContent = msg; err.classList.remove('hidden'); }
  }

  function renderMermaidBlocks(container) {
    if (typeof mermaid === 'undefined') return;
    var blocks = container.querySelectorAll('pre code.language-mermaid');
    if (blocks.length === 0) return;
    blocks.forEach(function (code) {
      var pre = code.parentElement;
      if (!pre || pre.tagName !== 'PRE') return;
      var div = document.createElement('div');
      div.className = 'mermaid';
      div.textContent = code.textContent || '';
      pre.parentNode.replaceChild(div, pre);
    });
    mermaid.initialize({ startOnLoad: false, securityLevel: 'loose' });
    mermaid.run({ nodes: container.querySelectorAll('.mermaid') }).catch(function () {});
  }

  function showDoc(html, sourceType, tab) {
    var t = tab !== undefined ? tab : activeTab;
    var ph = getPlaceholderEl(t);
    var doc = getDocEl(t);
    var err = getErrorEl(t);
    if (ph) ph.classList.add('hidden');
    if (err) err.classList.add('hidden');
    doc.innerHTML = html;
    var emoji = sourceType && SOURCE_EMOJI[sourceType];
    if (emoji) {
      var h1 = doc.querySelector('h1');
      if (h1) {
        var badge = document.createElement('span');
        badge.className = 'doc-source-badge' + (sourceType === 'cloud' ? ' doc-source-cloud' : '');
        badge.setAttribute('aria-hidden', 'true');
        badge.textContent = ' ' + emoji;
        h1.appendChild(badge);
      }
    }
    renderMermaidBlocks(doc);
    doc.classList.remove('hidden');
    updateToolbarVisibility();
  }

  function showPythonCodePad(code, path, sourceType, tab) {
    var t = tab !== undefined ? tab : activeTab;
    var ph = getPlaceholderEl(t);
    var err = getErrorEl(t);
    var doc = getDocEl(t);
    if (ph) ph.classList.add('hidden');
    if (err) err.classList.add('hidden');
    var theme = getCodeTheme();
    var fontSize = getCodeFontSize();
    var fontFamily = getCodeFontFamily();
    var filename = path.split('/').pop();
    var darkOpts = CODE_THEMES.filter(function (t) { return t.dark; }).map(function (t) {
      return '<option value="' + escapeAttr(t.value) + '"' + (t.value === theme ? ' selected' : '') + '>' + escapeHtml(t.label) + '</option>';
    }).join('');
    var lightOpts = CODE_THEMES.filter(function (t) { return !t.dark; }).map(function (t) {
      return '<option value="' + escapeAttr(t.value) + '"' + (t.value === theme ? ' selected' : '') + '>' + escapeHtml(t.label) + '</option>';
    }).join('');
    var sizeOpts = CODE_FONT_SIZES.map(function (s) {
      return '<option value="' + escapeAttr(s.value) + '"' + (s.value === fontSize ? ' selected' : '') + '>' + escapeHtml(s.label) + '</option>';
    }).join('');
    var familyOpts = CODE_FONT_FAMILIES.map(function (f) {
      return '<option value="' + escapeAttr(f.value) + '"' + (f.value === fontFamily ? ' selected' : '') + '>' + escapeHtml(f.label) + '</option>';
    }).join('');
    var html = '<div class="doc-code-pad" data-code-theme="' + escapeAttr(theme) + '" data-code-font-size="' + escapeAttr(fontSize) + '" data-code-font-family="' + escapeAttr(fontFamily) + '">' +
      '<div class="doc-code-pad-toolbar">' +
        '<span class="doc-code-pad-filename" title="' + escapeAttr(path) + '">' + escapeHtml(filename) + '</span>' +
        '<div class="doc-code-pad-controls">' +
          '<label class="doc-code-pad-theme-label">Theme <select class="doc-code-pad-theme" aria-label="Code theme">' +
            '<optgroup label="Dark">' + darkOpts + '</optgroup>' +
            '<optgroup label="Light">' + lightOpts + '</optgroup>' +
          '</select></label>' +
          '<label class="doc-code-pad-font-label">Size <select class="doc-code-pad-font-size" aria-label="Font size">' + sizeOpts + '</select></label>' +
          '<label class="doc-code-pad-font-label">Font <select class="doc-code-pad-font-family" aria-label="Font family">' + familyOpts + '</select></label>' +
        '</div>' +
      '</div>' +
      '<div class="doc-code-pad-window">' +
        '<pre class="line-numbers"><code class="language-python">' + escapeHtml(code) + '</code></pre>' +
      '</div>' +
      '</div>';
    doc.innerHTML = html;
    var codeEl = doc.querySelector('.doc-code-pad code');
    if (typeof Prism !== 'undefined' && codeEl) {
      Prism.highlightElement(codeEl);
    }
    var themeSelect = doc.querySelector('.doc-code-pad-theme');
    if (themeSelect) themeSelect.addEventListener('change', function () { setCodeTheme(themeSelect.value); });
    var sizeSelect = doc.querySelector('.doc-code-pad-font-size');
    if (sizeSelect) sizeSelect.addEventListener('change', function () { setCodeFontSize(sizeSelect.value); });
    var familySelect = doc.querySelector('.doc-code-pad-font-family');
    if (familySelect) familySelect.addEventListener('change', function () { setCodeFontFamily(familySelect.value); });
    doc.classList.remove('hidden');
    updateToolbarVisibility();
  }

  var lastRepos = [];
  var repoSourceTypeMap = {};
  var REPO_ORDER_KEY = 'draft-repo-order';
  var REPO_PINNED_KEY = 'draft-repo-pinned';

  function getSourceType(repo) {
    var name = (repo.name || '').toLowerCase();
    var url = (repo.url || '');
    if (name === 'vault') return 'vault';
    if (name === 'x') return 'x';
    if (url.indexOf('github.com') !== -1) return 'github';
    if (name.indexOf('google') !== -1 || name.indexOf('gdoc') !== -1 || name.indexOf('cloud') !== -1) return 'cloud';
    return 'local';
  }

  var SOURCE_EMOJI = { vault: '🔐', github: '🐙', x: '🐦', cloud: '☁️', local: '💾' };

  function getRepoOrder() {
    try {
      var raw = localStorage.getItem(REPO_ORDER_KEY);
      return raw ? JSON.parse(raw) : [];
    } catch (e) { return []; }
  }
  function setRepoOrder(order) {
    try { localStorage.setItem(REPO_ORDER_KEY, JSON.stringify(order)); } catch (e) {}
  }
  function getPinnedRepos() {
    try {
      var raw = localStorage.getItem(REPO_PINNED_KEY);
      return raw ? JSON.parse(raw) : [];
    } catch (e) { return []; }
  }
  function setPinnedRepos(pinned) {
    try { localStorage.setItem(REPO_PINNED_KEY, JSON.stringify(pinned)); } catch (e) {}
  }

  function applyOrder(repos) {
    if (!repos || repos.length === 0) return repos;
    var order = getRepoOrder();
    if (order.length === 0) {
      order = repos.map(function (r) { return r.name; });
      setRepoOrder(order);
    }
    var pinned = getPinnedRepos();
    var nameToRepo = {};
    repos.forEach(function (r) { nameToRepo[r.name] = r; });
    var ordered = [];
    var seen = {};
    order.forEach(function (name) {
      if (nameToRepo[name] && !seen[name]) {
        seen[name] = true;
        ordered.push(nameToRepo[name]);
      }
    });
    repos.forEach(function (r) {
      if (!seen[r.name]) ordered.push(r);
    });
    var pinnedSet = {};
    pinned.forEach(function (p) { pinnedSet[p] = true; });
    ordered.sort(function (a, b) {
      var aPin = pinnedSet[a.name];
      var bPin = pinnedSet[b.name];
      if (aPin && !bPin) return -1;
      if (!aPin && bPin) return 1;
      var ai = order.indexOf(a.name);
      var bi = order.indexOf(b.name);
      if (ai === -1 && bi === -1) return 0;
      if (ai === -1) return 1;
      if (bi === -1) return -1;
      return ai - bi;
    });
    // Vault always first
    var vaultIdx = ordered.findIndex(function (r) { return r.name === 'vault'; });
    if (vaultIdx > 0) {
      ordered.splice(0, 0, ordered.splice(vaultIdx, 1)[0]);
    }
    return ordered;
  }

  function renderTree(repos) {
    if (!repos || repos.length === 0) {
      treeEl.innerHTML = '<p class="placeholder">No repos in index.</p>';
      return;
    }
    lastRepos = repos;
    var ordered = applyOrder(repos);
    ordered.forEach(function (r) { repoSourceTypeMap[r.name] = getSourceType(r); });
    var pinned = getPinnedRepos();
    var pinnedSet = {};
    pinned.forEach(function (p) { pinnedSet[p] = true; });
    var html = '';
    ordered.forEach(function (repo, idx) {
      var isVault = repo.name === 'vault';
      var isPinned = pinnedSet[repo.name];
      var sourceType = getSourceType(repo);
      var startCollapsed = true;
      html += '<div class="repo-block' + (startCollapsed ? ' collapsed' : '') + (isVault ? ' vault-repo' : '') + '" data-repo="' + escapeAttr(repo.name) + '" data-source-type="' + escapeAttr(sourceType) + '">';
      html += '<div class="repo-header">';
      html += '<button type="button" class="btn-repo-collapse" title="Collapse/expand this repo" aria-expanded="' + (startCollapsed ? 'false' : 'true') + '"><span class="repo-btn-icon" aria-hidden="true">' + (startCollapsed ? '▶' : '▼') + '</span></button>';
      if (isVault) {
        html += '<span class="repo-name vault-name">' + escapeHtml(repo.name) + ' <span class="vault-icon" aria-hidden="true">🔐</span></span>';
      } else {
        html += '<span class="repo-name">' + escapeHtml(repo.name) + '</span>';
      }
      if (!isVault) {
        html += '<button type="button" class="btn-repo-remove" title="Remove source" data-repo="' + escapeAttr(repo.name) + '" aria-label="Remove source"><span class="repo-btn-icon" aria-hidden="true">❎</span></button>';
        html += '<button type="button" class="btn-repo-pin' + (isPinned ? ' pinned' : '') + '" title="' + (isPinned ? 'Unpin' : 'Pin to top') + '" data-repo="' + escapeAttr(repo.name) + '" aria-label="' + (isPinned ? 'Unpin' : 'Pin to top') + '"><span class="repo-btn-icon pin-emoji" aria-hidden="true">📌</span></button>';
        html += '<button type="button" class="btn-repo-down" title="Move to bottom" data-repo="' + escapeAttr(repo.name) + '" aria-label="Move to bottom"><span class="repo-btn-icon" aria-hidden="true">↓</span></button>';
      }
      html += '</div>';
      if (isVault) {
        html += '<div class="vault-drop-zone" id="vault-drop-zone" aria-label="Drop file into vault" role="button" tabindex="0">';
        html += '<input type="file" class="vault-drop-zone-input" id="vault-file-input" multiple aria-hidden="true" tabindex="-1">';
        html += '<span class="vault-drop-zone-text">Drop file here or click to choose → vault</span>';
        html += '</div>';
      }
      html += '<ul class="repo-tree">' + renderChildren(repo.tree, repo.name, '') + '</ul></div>';
      if (isVault) {
        html += '<div class="tree-vault-separator" aria-hidden="true"></div>';
      }
    });
    treeEl.innerHTML = html;

    treeEl.querySelectorAll('a[data-repo][data-path]').forEach(function (a) {
      a.addEventListener('click', function (e) {
        e.preventDefault();
        var block = a.closest('.repo-block');
        var sourceType = block ? block.dataset.sourceType : (repoSourceTypeMap[a.dataset.repo] || 'local');
        loadDoc(a.dataset.repo, a.dataset.path, sourceType);
      });
    });
    treeEl.querySelectorAll('.tree-dir .dir-label').forEach(function (label) {
      label.addEventListener('click', function () {
        var ul = this.parentNode.querySelector('.tree-children');
        if (ul) ul.classList.toggle('collapsed');
      });
    });
    treeEl.querySelectorAll('.btn-repo-collapse').forEach(function (btn) {
      btn.addEventListener('click', function () {
        var block = this.closest('.repo-block');
        var expanded = block.classList.toggle('collapsed');
        var icon = this.querySelector('.repo-btn-icon');
        this.setAttribute('aria-expanded', !expanded);
        if (icon) icon.textContent = expanded ? '▶' : '▼';
      });
    });
    treeEl.querySelectorAll('.btn-repo-down').forEach(function (btn) {
      btn.addEventListener('click', function (e) {
        e.stopPropagation();
        var name = btn.getAttribute('data-repo');
        var order = getRepoOrder();
        if (order.length === 0) lastRepos.forEach(function (r) { order.push(r.name); });
        order = order.filter(function (n) { return n !== name; });
        order.push(name);
        setRepoOrder(order);
        renderTree(lastRepos);
      });
    });
    treeEl.querySelectorAll('.btn-repo-pin').forEach(function (btn) {
      btn.addEventListener('click', function (e) {
        e.stopPropagation();
        var name = btn.getAttribute('data-repo');
        var order = getRepoOrder();
        var pinned = getPinnedRepos();
        if (order.length === 0) lastRepos.forEach(function (r) { order.push(r.name); });
        var isPinned = pinned.indexOf(name) !== -1;
        if (isPinned) {
          pinned = pinned.filter(function (n) { return n !== name; });
          order = order.filter(function (n) { return n !== name; });
          order.splice(pinned.length, 0, name);
        } else {
          /* Only one repo pinned at a time: new pin replaces any previous. */
          pinned = [name];
          order = order.filter(function (n) { return n !== name; });
          order.unshift(name);
        }
        setPinnedRepos(pinned);
        setRepoOrder(order);
        renderTree(lastRepos);
      });
    });
    treeEl.querySelectorAll('.btn-repo-remove').forEach(function (btn) {
      btn.addEventListener('click', function (e) {
        e.stopPropagation();
        var name = btn.getAttribute('data-repo');
        if (!name) return;
        var msg = 'Remove source "' + name + '"?\n\nThis will remove it from sources.yaml, delete its folder under .doc_sources, and rebuild metadata indexes.';
        if (!window.confirm(msg)) return;
        if (typeof appendConsoleLine === 'function') appendConsoleLine('$ remove source ' + name);
        beginExecution();
        fetch('/api/remove_source', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ name: name })
        })
          .then(function (r) { return r.json().then(function (data) { return { ok: r.ok, data: data }; }).catch(function () { return { ok: false, data: {} }; }); })
          .then(function (result) {
            var data = result.data || {};
            if (data.logs && data.logs.length && typeof appendConsoleLines === 'function') appendConsoleLines(data.logs);
            if (result.ok && data.ok) {
              for (var t = 1; t <= 2; t++) { if (paneDocs[t] && paneDocs[t].repo === name) clearPane(t); }
              afterPanesCleared();
              refreshTree();
            } else {
              var err = data.error || data.detail || 'Failed to remove source.';
              if (typeof appendConsoleLine === 'function') appendConsoleLine('Remove failed: ' + err);
            }
          })
          .catch(function (err) {
            if (typeof appendConsoleLine === 'function') appendConsoleLine('Remove failed: ' + (err.message || err));
          })
          .then(function () { endExecution(); });
      });
    });
    treeEl.querySelectorAll('.btn-vault-file-remove').forEach(function (btn) {
      btn.addEventListener('click', function (e) {
        e.preventDefault();
        e.stopPropagation();
        var path = btn.getAttribute('data-path');
        if (!path) return;
        if (!window.confirm('Remove vault file "' + path + '"?')) return;
        if (typeof appendConsoleLine === 'function') appendConsoleLine('$ vault remove ' + path);
        beginExecution();
        fetch('/api/vault/remove', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ path: path })
        })
          .then(function (r) { return r.json().then(function (data) { return { ok: r.ok, data: data }; }).catch(function () { return { ok: false, data: {} }; }); })
          .then(function (result) {
            var data = result.data || {};
            if (data.logs && data.logs.length && typeof appendConsoleLines === 'function') appendConsoleLines(data.logs);
            if (result.ok && data.ok) {
              for (var t = 1; t <= 2; t++) { if (paneDocs[t] && paneDocs[t].repo === 'vault' && paneDocs[t].path === path) clearPane(t); }
              afterPanesCleared();
              refreshTree();
            } else {
              var err = data.error || data.detail || 'Failed to remove vault file.';
              if (typeof appendConsoleLine === 'function') appendConsoleLine('Vault remove failed: ' + err);
            }
          })
          .catch(function (err) {
            if (typeof appendConsoleLine === 'function') appendConsoleLine('Vault remove failed: ' + (err.message || err));
          })
          .then(function () { endExecution(); });
      });
    });
    var dropZone = treeEl.querySelector('#vault-drop-zone');
    if (dropZone) setupVaultDropZone(dropZone);
  }

  function uploadFilesToVault(files) {
    if (!files || files.length === 0) return;
    var form = new FormData();
    for (var i = 0; i < files.length; i++) form.append('files', files[i]);
    if (typeof appendConsoleLine === 'function') appendConsoleLine('$ upload to vault: ' + files.length + ' file(s)');
    beginExecution();
    fetch('/api/vault/upload', { method: 'POST', body: form })
      .then(function (r) {
        return r.json().then(function (data) {
          return { ok: r.ok, status: r.status, data: data };
        }).catch(function () {
          return { ok: false, status: r.status, data: { error: r.statusText || 'Upload failed' } };
        });
      })
      .then(function (result) {
        var data = result.data;
        if (result.ok && data && data.ok && data.saved && data.saved.length) {
          if (typeof appendConsoleLine === 'function') appendConsoleLine('Saved to vault: ' + data.saved.join(', '));
          refreshTree();
        } else {
          var errMsg = (data && data.error) ? data.error : ('HTTP ' + result.status);
          if (typeof appendConsoleLine === 'function') appendConsoleLine('Upload failed: ' + errMsg);
        }
      })
      .catch(function (err) {
        if (typeof appendConsoleLine === 'function') appendConsoleLine('Upload failed: ' + (err.message || err));
        refreshTree();
      })
      .then(function () { endExecution(); });
  }

  function setupVaultDropZone(el) {
    var fileInput = el.querySelector('.vault-drop-zone-input');
    function prevent(e) {
      e.preventDefault();
      e.stopPropagation();
    }
    el.addEventListener('dragover', function (e) {
      prevent(e);
      if (e.dataTransfer) e.dataTransfer.dropEffect = 'copy';
      el.classList.add('drag-over');
    });
    el.addEventListener('dragleave', function (e) {
      prevent(e);
      if (!el.contains(e.relatedTarget)) el.classList.remove('drag-over');
    });
    el.addEventListener('drop', function (e) {
      prevent(e);
      el.classList.remove('drag-over');
      var dt = e.dataTransfer;
      var files = dt && dt.files;
      if (files && files.length > 0) {
        uploadFilesToVault(files);
        return;
      }
      if (dt && dt.items && dt.items.length > 0) {
        var collected = [];
        for (var i = 0; i < dt.items.length; i++) {
          if (dt.items[i].kind === 'file') {
            var f = dt.items[i].getAsFile();
            if (f) collected.push(f);
          }
        }
        if (collected.length > 0) uploadFilesToVault(collected);
      }
    });
    if (fileInput) {
      fileInput.addEventListener('change', function () {
        var files = this.files;
        if (files && files.length > 0) uploadFilesToVault(files);
        this.value = '';
      });
    }
    el.addEventListener('click', function (e) {
      if (e.target === fileInput) return;
      if (fileInput) fileInput.click();
    });
    el.addEventListener('keydown', function (e) {
      if (e.key === 'Enter' || e.key === ' ') {
        prevent(e);
        if (fileInput) fileInput.click();
      }
    });
  }

  function renderChildren(nodes, repo, prefix) {
    if (!nodes || nodes.length === 0) return '';
    var html = '';
    nodes.forEach(function (node) {
      if (node.type === 'dir') {
        html += '<li class="tree-dir"><span class="dir-label">' + escapeHtml(node.name) + '</span>';
        html += '<ul class="tree-children">' + renderChildren(node.children || [], repo, prefix + node.name + '/') + '</ul></li>';
      } else {
        var path = node.path || node.name;
        var displayName = node.name;
        if (repo === 'vault' && node.source) {
          var src = String(node.source).slice(0, 8);
          displayName += ' [' + src + ']';
        }
        if (repo === 'vault') {
          html += '<li class="tree-file-row">';
          html += '<a href="#" data-repo="' + escapeAttr(repo) + '" data-path="' + escapeAttr(path) + '">' + escapeHtml(displayName) + '</a>';
          html += '<button type="button" class="btn-vault-file-remove" data-path="' + escapeAttr(path) + '" title="Remove file from vault" aria-label="Remove file from vault">❎</button>';
          html += '</li>';
        } else {
          html += '<li><a href="#" data-repo="' + escapeAttr(repo) + '" data-path="' + escapeAttr(path) + '">' + escapeHtml(displayName) + '</a></li>';
        }
      }
    });
    return html;
  }

  function collapseAll() {
    treeEl.querySelectorAll('.tree-children').forEach(function (el) { el.classList.add('collapsed'); });
  }

  function expandAll() {
    treeEl.querySelectorAll('.tree-children').forEach(function (el) { el.classList.remove('collapsed'); });
  }

  var consoleContent = document.getElementById('system-console-content');
  var systemConsolePanel = document.getElementById('system-console');
  var MAX_CONSOLE_LINES = 200;
  var activeExecutions = 0;

  function setConsoleRunning(running) {
    if (!systemConsolePanel) return;
    systemConsolePanel.classList.toggle('running', !!running);
  }

  function beginExecution() {
    activeExecutions += 1;
    setConsoleRunning(true);
  }

  function endExecution() {
    activeExecutions = Math.max(0, activeExecutions - 1);
    setConsoleRunning(activeExecutions > 0);
  }

  function appendConsoleLine(text) {
    if (!consoleContent) return;
    var line = document.createElement('div');
    line.className = 'console-line';
    line.textContent = text;
    consoleContent.appendChild(line);
    while (consoleContent.children.length > MAX_CONSOLE_LINES) {
      consoleContent.removeChild(consoleContent.firstChild);
    }
    consoleContent.scrollTop = consoleContent.scrollHeight;
  }

  function appendConsoleLines(lines) {
    if (lines && lines.length) {
      lines.forEach(function (t) { appendConsoleLine(t); });
    }
  }

  function runPull() {
    var statusEl = document.getElementById('pull-status');
    statusEl.textContent = 'Pulling…';
    statusEl.classList.remove('hidden', 'error');
    statusEl.classList.add('pending');
    appendConsoleLine('$ pull');
    beginExecution();
    fetch('/api/pull', { method: 'POST' })
      .then(function (r) { return r.json(); })
      .then(function (data) {
        statusEl.classList.remove('pending');
        if (data.logs && data.logs.length) {
          appendConsoleLines(data.logs);
        }
        if (data.ok) {
          statusEl.textContent = 'Pull done.';
          statusEl.classList.remove('error');
          appendConsoleLine('Pull complete.');
          fetch('/api/tree').then(function (res) { return res.json(); }).then(function (d) { renderTree(d.repos || []); });
        } else {
          statusEl.textContent = 'Pull failed.';
          statusEl.classList.add('error');
          appendConsoleLine('Pull failed: ' + (data.error || ''));
        }
      })
      .catch(function (err) {
        statusEl.classList.remove('pending');
        statusEl.textContent = 'Pull request failed.';
        statusEl.classList.add('error');
        appendConsoleLine('Pull request failed: ' + (err.message || ''));
      })
      .then(function () { endExecution(); });
  }

  (function initSystemConsoleToggle() {
    var toggle = document.getElementById('system-console-toggle');
    var panel = document.getElementById('system-console');
    if (toggle && panel) {
      toggle.addEventListener('click', function () {
        panel.classList.toggle('collapsed');
      });
    }
  })();

  (function initSidebarResize() {
    var layout = document.getElementById('layout');
    var handle = document.getElementById('sidebar-resize');
    var sidebar = document.getElementById('sidebar');
    if (!layout || !handle || !sidebar) return;
    var SIDEBAR_WIDTH_KEY = 'draft-sidebar-width';
    var MIN = 180;
    var MAX = 1200;

    function getWidth() {
      var w = parseFloat(getComputedStyle(layout).getPropertyValue('--sidebar-width')) || 280;
      return isNaN(w) ? 280 : w;
    }
    function setWidth(px) {
      var w = Math.min(MAX, Math.max(MIN, px));
      layout.style.setProperty('--sidebar-width', w + 'px');
      try { localStorage.setItem(SIDEBAR_WIDTH_KEY, String(w)); } catch (e) {}
    }

    var saved = null;
    try { saved = localStorage.getItem(SIDEBAR_WIDTH_KEY); } catch (e) {}
    if (saved != null) {
      var n = parseFloat(saved);
      if (!isNaN(n)) setWidth(n);
    }

    handle.addEventListener('mousedown', function (e) {
      e.preventDefault();
      var startX = e.clientX;
      var startW = getWidth();
      function move(ev) {
        setWidth(startW + (ev.clientX - startX));
      }
      function up() {
        document.removeEventListener('mousemove', move);
        document.removeEventListener('mouseup', up);
      }
      document.addEventListener('mousemove', move);
      document.addEventListener('mouseup', up);
    });
  })();

  function refreshTree() {
    fetch('/api/tree')
      .then(function (r) { return r.json(); })
      .then(function (data) { renderTree(data.repos || []); })
      .catch(function () {});
  }

  (function initAddSource() {
    var input = document.getElementById('add-source-input');
    if (!input) return;
    function submitAddSource() {
      var source = input.value.trim();
      if (!source) return;
      input.disabled = true;
      appendConsoleLine('$ add source ' + source);
      beginExecution();
      fetch('/api/add_source', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ source: source })
      })
        .then(function (r) { return r.json(); })
        .then(function (data) {
          if (data.logs && data.logs.length) appendConsoleLines(data.logs);
          if (data.ok) {
            appendConsoleLine('Source added.');
            input.value = '';
            // Run pull so the new source is fetched and tree updates
            return fetch('/api/pull', { method: 'POST' })
              .then(function (r) { return r.json(); })
              .then(function (pullData) {
                if (pullData.logs && pullData.logs.length) appendConsoleLines(pullData.logs);
                if (pullData.ok) appendConsoleLine('Pull complete.');
                refreshTree();
              })
              .catch(function () { refreshTree(); });
          } else {
            appendConsoleLine('Add failed: ' + (data.error || ''));
          }
        })
        .catch(function (err) {
          appendConsoleLine('Add failed: ' + (err.message || ''));
        })
        .then(function () { input.disabled = false; input.focus(); endExecution(); });
    }
    input.addEventListener('keydown', function (e) {
      if (e.key === 'Enter') {
        e.preventDefault();
        submitAddSource();
      }
    });
  })();

  function escapeHtml(s) {
    const div = document.createElement('div');
    div.textContent = s;
    return div.innerHTML;
  }

  function escapeAttr(s) {
    return escapeHtml(s).replace(/"/g, '&quot;');
  }

  var BINARY_DOC_EXTS = ['.pdf', '.doc', '.docx'];
  function isBinaryDoc(path) {
    var p = (path || '').toLowerCase();
    return BINARY_DOC_EXTS.some(function (ext) { return p.endsWith(ext); });
  }
  function isPythonDoc(path) {
    return (path || '').toLowerCase().endsWith('.py');
  }

  var CODE_THEME_KEY = 'draft-code-theme';
  var CODE_THEMES = [
    { value: 'dark-tomorrow', label: 'Tomorrow Night', dark: true },
    { value: 'dark-dracula', label: 'Dracula', dark: true },
    { value: 'dark-nord', label: 'Nord', dark: true },
    { value: 'dark-onedark', label: 'One Dark', dark: true },
    { value: 'dark-monokai', label: 'Monokai', dark: true },
    { value: 'dark-solarized', label: 'Solarized Dark', dark: true },
    { value: 'dark-gruvbox', label: 'Gruvbox Dark', dark: true },
    { value: 'dark-catppuccin', label: 'Catppuccin Mocha', dark: true },
    { value: 'light-gh', label: 'GitHub', dark: false },
    { value: 'light-coy', label: 'Coy', dark: false },
    { value: 'light-default', label: 'Default Light', dark: false },
    { value: 'light-solarized', label: 'Solarized Light', dark: false },
    { value: 'light-gruvbox', label: 'Gruvbox Light', dark: false },
    { value: 'light-catppuccin', label: 'Catppuccin Latte', dark: false }
  ];
  function getCodeTheme() {
    try {
      var t = localStorage.getItem(CODE_THEME_KEY);
      if (t && CODE_THEMES.some(function (x) { return x.value === t; })) return t;
    } catch (e) {}
    return getTheme() === 'bright' ? 'light-gh' : 'dark-tomorrow';
  }
  function setCodeTheme(value) {
    try { localStorage.setItem(CODE_THEME_KEY, value); } catch (e) {}
    var pad = document.querySelector('.doc-code-pad');
    if (pad) pad.setAttribute('data-code-theme', value);
  }

  var CODE_FONT_SIZE_KEY = 'draft-code-font-size';
  var CODE_FONT_FAMILY_KEY = 'draft-code-font-family';
  var CODE_FONT_SIZES = [
    { value: 'small', label: 'Small', size: '12px' },
    { value: 'medium', label: 'Medium', size: '14px' },
    { value: 'large', label: 'Large', size: '16px' }
  ];
  var CODE_FONT_FAMILIES = [
    { value: 'jetbrains', label: 'JetBrains Mono', family: '"JetBrains Mono", monospace' },
    { value: 'fira', label: 'Fira Code', family: '"Fira Code", monospace' },
    { value: 'system', label: 'System', family: 'ui-monospace, "Cascadia Code", monospace' }
  ];
  function getCodeFontSize() {
    try {
      var v = localStorage.getItem(CODE_FONT_SIZE_KEY);
      if (v && CODE_FONT_SIZES.some(function (x) { return x.value === v; })) return v;
    } catch (e) {}
    return 'medium';
  }
  function setCodeFontSize(value) {
    try { localStorage.setItem(CODE_FONT_SIZE_KEY, value); } catch (e) {}
    var pad = document.querySelector('.doc-code-pad');
    if (pad) pad.setAttribute('data-code-font-size', value);
  }
  function getCodeFontFamily() {
    try {
      var v = localStorage.getItem(CODE_FONT_FAMILY_KEY);
      if (v && CODE_FONT_FAMILIES.some(function (x) { return x.value === v; })) return v;
    } catch (e) {}
    return 'jetbrains';
  }
  function setCodeFontFamily(value) {
    try { localStorage.setItem(CODE_FONT_FAMILY_KEY, value); } catch (e) {}
    var pad = document.querySelector('.doc-code-pad');
    if (pad) pad.setAttribute('data-code-font-family', value);
  }

  var DOC_HASH_PREFIX = 'doc/';
  var DOC_STORAGE_KEY = 'draft-current-doc';
  function getDocFromHash() {
    var h = location.hash.slice(1);
    if (h.indexOf(DOC_HASH_PREFIX) !== 0) return null;
    var parts = h.slice(DOC_HASH_PREFIX.length).split('/');
    if (parts.length < 2) return null;
    try {
      var repo = decodeURIComponent(parts[0]);
      var path = parts.slice(1).map(function (p) { return decodeURIComponent(p); }).join('/');
      return repo && path ? { repo: repo, path: path } : null;
    } catch (e) { return null; }
  }
  function getDocFromStorage() {
    try {
      var raw = sessionStorage.getItem(DOC_STORAGE_KEY) || localStorage.getItem(DOC_STORAGE_KEY);
      if (!raw) return null;
      var o = JSON.parse(raw);
      return (o && o.repo && o.path) ? { repo: o.repo, path: o.path } : null;
    } catch (e) { return null; }
  }
  function setDocHash(repo, path) {
    var value = DOC_HASH_PREFIX + encodeURIComponent(repo) + '/' + path.split('/').map(function (p) { return encodeURIComponent(p); }).join('/');
    if (location.hash !== '#' + value) location.hash = value;
    try { sessionStorage.setItem(DOC_STORAGE_KEY, JSON.stringify({ repo: repo, path: path })); } catch (e) {}
    try { localStorage.setItem(DOC_STORAGE_KEY, JSON.stringify({ repo: repo, path: path })); } catch (e) {}
  }
  function clearDocHash() {
    if (location.hash.indexOf('#' + DOC_HASH_PREFIX) === 0) location.hash = '';
    try { sessionStorage.removeItem(DOC_STORAGE_KEY); } catch (e) {}
    try { localStorage.removeItem(DOC_STORAGE_KEY); } catch (e) {}
  }
  function getCurrentDocToRestore() {
    return getDocFromStorage() || getDocFromHash();
  }

  var DOC_HISTORY_MAX = 10;
  function getDocHistoryKey(tab) { return 'draft-doc-history-' + tab; }

  function getDocHistory(tab) {
    try {
      var raw = localStorage.getItem(getDocHistoryKey(tab));
      var arr = raw ? JSON.parse(raw) : [];
      return Array.isArray(arr) ? arr.slice(0, DOC_HISTORY_MAX) : [];
    } catch (e) { return []; }
  }

  function addToDocHistory(repo, path, tab) {
    if (tab !== 1 && tab !== 2) return;
    var list = getDocHistory(tab);
    var key = repo + '\0' + path;
    list = list.filter(function (item) { return (item.repo + '\0' + item.path) !== key; });
    list.unshift({ repo: repo, path: path });
    list = list.slice(0, DOC_HISTORY_MAX);
    try { localStorage.setItem(getDocHistoryKey(tab), JSON.stringify(list)); } catch (e) {}
  }

  function docHistoryFilename(path) {
    return (path || '').split('/').pop() || path || '';
  }
  function docHistoryLabel(item) {
    return item.repo + ': ' + docHistoryFilename(item.path);
  }

  function renderDocHistory(tab) {
    var trigger = document.getElementById('doc-history-trigger-' + tab);
    var dropdown = document.getElementById('doc-history-dropdown-' + tab);
    if (!trigger || !dropdown) return;
    var current = paneDocs[tab];
    var list = getDocHistory(tab);
    if (current) {
      trigger.textContent = docHistoryFilename(current.path);
      trigger.title = docHistoryLabel(current) + '. Click to show recent.';
    } else {
      trigger.textContent = list.length ? docHistoryFilename(list[0].path) : 'Recent';
      trigger.title = list.length ? 'Last: ' + docHistoryLabel(list[0]) + '. Click to show queue.' : 'Recent documents in this tab';
    }
    dropdown.innerHTML = list.length === 0
      ? '<div class="doc-history-empty">No recent documents.</div>'
      : list.map(function (item) {
          var filename = docHistoryFilename(item.path);
          return '<button type="button" class="doc-history-item" role="menuitem" data-repo="' + escapeAttr(item.repo) + '" data-path="' + escapeAttr(item.path) + '" title="' + escapeAttr(docHistoryLabel(item)) + '">' +
            '<span class="doc-history-item-repo">' + escapeHtml(item.repo) + '</span>: <span class="doc-history-item-path">' + escapeHtml(filename) + '</span></button>';
        }).join('');
    dropdown.querySelectorAll('.doc-history-item').forEach(function (btn) {
      btn.addEventListener('click', function () {
        loadDocIntoPane(tab, btn.dataset.repo, btn.dataset.path);
        dropdown.classList.add('hidden');
        trigger.setAttribute('aria-expanded', 'false');
      });
    });
  }

  function initPaneHistory(tab) {
    var trigger = document.getElementById('doc-history-trigger-' + tab);
    var dropdown = document.getElementById('doc-history-dropdown-' + tab);
    var box = document.getElementById('doc-pane-history-' + tab);
    if (!trigger || !dropdown || !box) return;
    trigger.addEventListener('click', function (e) {
      e.preventDefault();
      e.stopPropagation();
      var open = !dropdown.classList.toggle('hidden');
      trigger.setAttribute('aria-expanded', open);
      if (open) renderDocHistory(tab);
    });
    box.addEventListener('click', function (e) { e.stopPropagation(); });
  }

  (function initDocTabs() {
    loadTabsLayout();
    updateTabBarUI();
    initPaneHistory(1);
    initPaneHistory(2);
    renderDocHistory(1);
    renderDocHistory(2);
    document.addEventListener('click', function () {
      [1, 2].forEach(function (t) {
        var d = document.getElementById('doc-history-dropdown-' + t);
        var tr = document.getElementById('doc-history-trigger-' + t);
        if (d && !d.classList.contains('hidden')) { d.classList.add('hidden'); if (tr) tr.setAttribute('aria-expanded', 'false'); }
      });
    });

    function switchToTab(tabNum) {
      if (tabNum !== 1 && tabNum !== 2) return;
      activeTab = tabNum;
      currentDoc = paneDocs[tabNum] || null;
      if (currentDoc) setDocHash(currentDoc.repo, currentDoc.path); else clearDocHash();
      updateTabBarUI();
      savePanesState();
    }
    document.querySelectorAll('.doc-pane-label').forEach(function (label) {
      label.addEventListener('click', function (e) {
        e.preventDefault();
        var pane = this.closest('.doc-pane');
        if (!pane) return;
        var tab = parseInt(pane.getAttribute('data-pane'), 10);
        switchToTab(tab);
      });
    });

    document.getElementById('doc-layout-stacked') && document.getElementById('doc-layout-stacked').addEventListener('click', function () {
      layoutMode = 'stacked';
      saveTabsLayout();
      updateTabBarUI();
    });
    document.getElementById('doc-layout-side') && document.getElementById('doc-layout-side').addEventListener('click', function () {
      layoutMode = 'side-by-side';
      saveTabsLayout();
      updateTabBarUI();
    });

    document.getElementById('doc-swap-btn') && document.getElementById('doc-swap-btn').addEventListener('click', function () {
      sideBySideSwapped = !sideBySideSwapped;
      saveTabsLayout();
      updateTabBarUI();
    });
    document.querySelectorAll('.doc-tab-num').forEach(function (btn) {
      btn.addEventListener('click', function () {
        var tab = parseInt(btn.getAttribute('data-tab'), 10);
        if (tab === 1 || tab === 2) switchToTab(tab);
      });
    });
    document.querySelectorAll('.doc-pane-save-vault').forEach(function (btn) {
      btn.addEventListener('click', function (e) {
        e.preventDefault();
        e.stopPropagation();
        var tab = parseInt(btn.getAttribute('data-pane'), 10);
        var doc = paneDocs[tab];
        if (!doc) return;
        beginExecution();
        fetch('/api/vault/save-from-doc', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ repo: doc.repo, path: doc.path })
        })
          .then(function (r) { return r.json().then(function (data) { return { ok: r.ok, data: data }; }).catch(function () { return { ok: false, data: {} }; }); })
          .then(function (result) {
            if (result.ok && result.data.saved && result.data.saved.length) {
              if (typeof appendConsoleLine === 'function') appendConsoleLine('Saved to vault: ' + result.data.saved[0]);
              refreshTree();
            } else {
              var err = (result.data && result.data.detail) ? result.data.detail : (result.data.error || 'Failed');
              if (typeof appendConsoleLine === 'function') appendConsoleLine('Save to vault failed: ' + err);
            }
          })
          .then(function () { endExecution(); });
      });
    });
  })();

  var pendingScrollToLine = null;

  function applyPendingScrollToLine() {
    if (!pendingScrollToLine || pendingScrollToLine.line < 1) return;
    var line = pendingScrollToLine.line;
    pendingScrollToLine = null;
    var docEl = getDocEl(activeTab);
    if (!docEl) return;
    var codeWindow = docEl.querySelector('.doc-code-pad-window');
    var container = codeWindow || docEl.closest('.doc-reader-window');
    if (!container) return;
    var pre = docEl.querySelector('.doc-code-pad-window pre, pre');
    var lineHeight = 22;
    if (pre) {
      var style = window.getComputedStyle(pre);
      var fs = parseFloat(style.fontSize) || 14;
      var lh = style.lineHeight;
      if (lh && lh !== 'normal') lineHeight = parseFloat(lh); else lineHeight = fs * 1.5;
    }
    var scrollTop = Math.max(0, (line - 1) * lineHeight - 20);
    requestAnimationFrame(function () {
      if (container) container.scrollTop = scrollTop;
    });
  }

  function loadDoc(repo, path, sourceType) {
    currentDoc = { repo: repo, path: path };
    paneDocs[activeTab] = { repo: repo, path: path };
    setDocHash(repo, path);
    if (sourceType === undefined) sourceType = repoSourceTypeMap[repo] || 'local';
    var url = '/api/doc/' + encodeURIComponent(repo) + '/' + path.split('/').map(encodeURIComponent).join('/');
    fetch(url)
      .then(function (r) {
        if (!r.ok) throw new Error(r.status === 404 ? 'Not found' : 'Failed to load');
        if (isBinaryDoc(path)) return r.blob();
        return r.text();
      })
      .then(function (data) {
        if (isBinaryDoc(path)) {
          var blob = data;
          var blobUrl = URL.createObjectURL(blob);
          var ext = path.toLowerCase().slice(path.lastIndexOf('.'));
          if (ext === '.pdf') {
            showDoc('<iframe class="doc-binary-view" src="' + escapeAttr(blobUrl) + '" title="PDF"></iframe>', sourceType);
          } else {
            showDoc('<p class="doc-download">Binary document. <a href="' + escapeAttr(blobUrl) + '" download="' + escapeAttr(path.split('/').pop()) + '">Download</a></p>', sourceType);
          }
          setTimeout(function () { URL.revokeObjectURL(blobUrl); }, 60000);
        } else {
          var text = data;
          if (isPythonDoc(path)) {
            showPythonCodePad(text, path, sourceType);
          } else if (typeof marked !== 'undefined') {
            showDoc(marked.parse(text, { gfm: true }), sourceType);
          } else {
            showDoc('<pre>' + escapeHtml(text) + '</pre>', sourceType);
          }
        }
        addToDocHistory(repo, path, activeTab);
        renderDocHistory(activeTab);
        savePanesState();
        applyPendingScrollToLine();
      })
      .catch(function (err) {
        showError(err.message || 'Failed to load document.');
        pendingScrollToLine = null;
      });
  }

  function restorePanes() {
    try {
      var raw1 = localStorage.getItem(PANE_1_KEY);
      var raw2 = localStorage.getItem(PANE_2_KEY);
      var rawActive = localStorage.getItem(ACTIVE_TAB_KEY);
      if (raw1) paneDocs[1] = JSON.parse(raw1);
      else paneDocs[1] = null;
      if (raw2) paneDocs[2] = JSON.parse(raw2);
      else paneDocs[2] = null;
      activeTab = (rawActive === '2' ? 2 : 1);
      var currentDocFromUrlOrStorage = getDocFromHash() || getDocFromStorage();
      if (currentDocFromUrlOrStorage) paneDocs[activeTab] = { repo: currentDocFromUrlOrStorage.repo, path: currentDocFromUrlOrStorage.path };
    } catch (e) {}
    var promises = [];
    if (paneDocs[1]) promises.push(loadDocIntoPane(1, paneDocs[1].repo, paneDocs[1].path));
    if (paneDocs[2]) promises.push(loadDocIntoPane(2, paneDocs[2].repo, paneDocs[2].path));
    if (promises.length === 0) {
      var fallback = getCurrentDocToRestore();
      if (fallback) promises.push(loadDocIntoPane(activeTab, fallback.repo, fallback.path));
    }
    Promise.all(promises).then(function () {
      currentDoc = paneDocs[activeTab] || null;
      if (currentDoc) setDocHash(currentDoc.repo, currentDoc.path);
      else clearDocHash();
      updateTabBarUI();
      updateToolbarVisibility();
      renderDocHistory(1);
      renderDocHistory(2);
      savePanesState();
    });
  }

  fetch('/api/tree')
    .then(function (r) { return r.json(); })
    .then(function (data) {
      renderTree(data.repos || []);
      restorePanes();
    })
    .catch(function () {
      treeEl.innerHTML = '<p class="error">Failed to load tree.</p>';
    });

  window.addEventListener('hashchange', function () {
    var doc = getDocFromHash();
    if (doc && (!currentDoc || currentDoc.repo !== doc.repo || currentDoc.path !== doc.path)) loadDoc(doc.repo, doc.path);
    else if (!getDocFromHash() && currentDoc) showPlaceholder(false);
  });

  var SIDEBAR_COLLAPSED_KEY = 'draft-sidebar-collapsed';
  var layoutEl = document.getElementById('layout');
  function getSidebarCollapsed() {
    try { return localStorage.getItem(SIDEBAR_COLLAPSED_KEY) === '1'; } catch (e) { return false; }
  }
  function setSidebarCollapsed(collapsed) {
    try { localStorage.setItem(SIDEBAR_COLLAPSED_KEY, collapsed ? '1' : '0'); } catch (e) {}
    if (layoutEl) layoutEl.classList.toggle('sidebar-collapsed', !!collapsed);
    var btn = document.getElementById('btn-sidebar-toggle');
    if (btn) btn.setAttribute('aria-checked', collapsed ? 'false' : 'true');
  }
  if (layoutEl) layoutEl.classList.toggle('sidebar-collapsed', getSidebarCollapsed());
  var sidebarToggleBtn = document.getElementById('btn-sidebar-toggle');
  if (sidebarToggleBtn) sidebarToggleBtn.setAttribute('aria-checked', getSidebarCollapsed() ? 'false' : 'true');
  document.getElementById('btn-sidebar-toggle') && document.getElementById('btn-sidebar-toggle').addEventListener('click', function () {
    setSidebarCollapsed(!getSidebarCollapsed());
  });

  document.getElementById('btn-collapse').addEventListener('click', collapseAll);
  document.getElementById('btn-expand').addEventListener('click', expandAll);
  document.getElementById('btn-pull').addEventListener('click', runPull);

  (function setupSearch() {
    var btn = document.getElementById('btn-search');
    var input = document.getElementById('search-input');
    var resultsEl = document.getElementById('search-results');
    var searchDebounce = null;

    function renderSearchResults(data) {
      if (!resultsEl) return;
      if (data.error) {
        resultsEl.innerHTML = '<div class="search-result-empty">Search error: ' + escapeHtml(data.error) + '</div>';
        resultsEl.classList.remove('hidden');
        return;
      }
      var results = data.results || [];
      if (results.length === 0) {
        resultsEl.innerHTML = '<div class="search-result-empty">No matches.</div>';
      } else {
        resultsEl.innerHTML = results.map(function (r) {
          return '<button type="button" class="search-result-item" data-repo="' + escapeAttr(r.repo) + '" data-path="' + escapeAttr(r.path) + '">' +
            '<div class="search-result-repo">' + escapeHtml(r.repo) + '</div>' +
            '<div class="search-result-path">' + escapeHtml(r.path) + '</div>' +
            '<div class="search-result-snippet">' + escapeHtml(r.snippet || '') + '</div></button>';
        }).join('');
        resultsEl.querySelectorAll('.search-result-item').forEach(function (btn) {
          btn.addEventListener('click', function () {
            loadDoc(btn.dataset.repo, btn.dataset.path);
            resultsEl.classList.add('hidden');
            resultsEl.innerHTML = '';
            input.value = '';
            filterTreeBySearch('');
          });
        });
      }
      resultsEl.classList.remove('hidden');
    }

    function runFullTextSearch(q) {
      if (!resultsEl) return;
      q = (q || '').trim();
      if (!q) {
        resultsEl.classList.add('hidden');
        resultsEl.innerHTML = '';
        return;
      }
      resultsEl.innerHTML = '<div class="search-result-loading">Searching…</div>';
      resultsEl.classList.remove('hidden');
      fetch('/api/search?q=' + encodeURIComponent(q))
        .then(function (r) { return r.json(); })
        .then(renderSearchResults)
        .catch(function (err) {
          resultsEl.innerHTML = '<div class="search-result-empty">Search failed.</div>';
          resultsEl.classList.remove('hidden');
        });
    }

    btn.addEventListener('click', function () {
      input.classList.toggle('hidden');
      if (!input.classList.contains('hidden')) {
        input.focus();
        var q = input.value.trim();
        filterTreeBySearch(q);
        if (q) runFullTextSearch(q);
      } else {
        filterTreeBySearch('');
        resultsEl.classList.add('hidden');
        resultsEl.innerHTML = '';
      }
    });
    input.addEventListener('input', function () {
      var q = input.value.trim();
      filterTreeBySearch(q);
      clearTimeout(searchDebounce);
      searchDebounce = setTimeout(function () { runFullTextSearch(q); }, 280);
    });
    input.addEventListener('keydown', function (e) {
      if (e.key === 'Escape') {
        input.value = '';
        filterTreeBySearch('');
        resultsEl.classList.add('hidden');
        resultsEl.innerHTML = '';
        input.classList.add('hidden');
        input.blur();
      }
    });
  })();

  (function setupAskAI() {
    var askPanel = document.getElementById('ask-ai');
    var askToggle = document.getElementById('ask-ai-toggle');
    var queryInput = document.getElementById('ask-query-input');
    var answerEl = document.getElementById('ask-answer');
    var citationsEl = document.getElementById('ask-citations');
    var errorEl = document.getElementById('ask-error');
    if (!askPanel || !queryInput) return;
    var askInProgress = false;

    askToggle.addEventListener('click', function () {
      askPanel.classList.toggle('collapsed');
    });

    var reindexBtn = document.getElementById('ask-reindex');
    var reindexDeepBtn = document.getElementById('ask-reindex-deep');
    function runAiReindex(mode) {
      var quickBtn = reindexBtn;
      var deepBtn = reindexDeepBtn;
      if (quickBtn) quickBtn.disabled = true;
      if (deepBtn) deepBtn.disabled = true;
      if (mode === 'quick' && quickBtn) quickBtn.textContent = 'Building…';
      if (mode === 'deep' && deepBtn) deepBtn.textContent = 'Building…';
      appendConsoleLine('$ reindex AI --profile ' + mode);
      beginExecution();
      fetch('/api/reindex_ai', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ mode: mode })
      })
        .then(function (r) { return r.json(); })
        .then(function (d) {
          if (d.logs && d.logs.length) appendConsoleLines(d.logs);
          else if (d.ok) appendConsoleLine('AI index built: ' + (d.indexed || 0) + ' chunks.');
          if (!d.ok && d.error) {
            showAskError(d.error);
            if (!(d.logs && d.logs.length)) appendConsoleLine('AI reindex failed: ' + (d.error || ''));
          }
        })
        .catch(function (err) {
          appendConsoleLine('AI reindex failed: ' + (err.message || ''));
        })
        .then(function () {
          if (quickBtn) {
            quickBtn.disabled = false;
            quickBtn.textContent = 'Quick rebuild';
          }
          if (deepBtn) {
            deepBtn.disabled = false;
            deepBtn.textContent = 'Deep rebuild (nomic)';
          }
          endExecution();
        });
    }
    if (reindexBtn) reindexBtn.addEventListener('click', function () { runAiReindex('quick'); });
    if (reindexDeepBtn) reindexDeepBtn.addEventListener('click', function () { runAiReindex('deep'); });

    function showAskError(msg) {
      errorEl.textContent = msg || '';
      errorEl.classList.toggle('hidden', !msg);
    }

    function appendChunkToBuffer(buf, chunk) {
      var decoder = new TextDecoder();
      return buf + decoder.decode(chunk, { stream: true });
    }
    function parseSSELines(buffer) {
      var events = [];
      var rest = buffer;
      var idx;
      while ((idx = rest.indexOf('\n\n')) !== -1) {
        var block = rest.slice(0, idx);
        rest = rest.slice(idx + 2);
        var line = block.split('\n').find(function (l) { return l.startsWith('data: '); });
        if (line) {
          try {
            events.push(JSON.parse(line.slice(6)));
          } catch (e) {}
        }
      }
      return { events: events, rest: rest };
    }

    function runAsk() {
      var query = (queryInput.value || '').trim();
      if (!query || askInProgress) return;
      askInProgress = true;
      queryInput.disabled = true;
      answerEl.classList.add('hidden');
      answerEl.textContent = '';
      citationsEl.classList.add('hidden');
      citationsEl.innerHTML = '';
      showAskError('');
      answerEl.classList.remove('hidden');
      answerEl.textContent = '…';

      appendConsoleLine('$ ask: ' + query);
      appendConsoleLine('Streaming…');

      function done() {
        askInProgress = false;
        queryInput.disabled = false;
      }

      fetch('/api/ask', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ query: query })
      })
        .then(function (res) {
          if (!res.ok) {
            return res.text().then(function (body) {
              var msg = 'Ask failed (' + res.status + ')';
              try {
                var o = JSON.parse(body);
                if (o.detail) msg += ': ' + o.detail;
              } catch (e) {
                if (body && body.length < 100) msg += ': ' + body;
              }
              throw new Error(msg);
            });
          }
          return res.body.getReader();
        })
        .then(function (reader) {
          var buffer = '';
          var fullText = '';
          function read() {
            return reader.read().then(function (result) {
              if (result.done) {
                var parsed = parseSSELines(buffer);
                parsed.events.forEach(handleEvent);
                finish();
                return;
              }
              buffer = appendChunkToBuffer(buffer, result.value);
              var parsed = parseSSELines(buffer);
              buffer = parsed.rest;
              parsed.events.forEach(handleEvent);
              return read();
            });
          }
          function handleEvent(data) {
            if (data.type === 'text' && data.text) {
              fullText += data.text;
              answerEl.textContent = fullText;
            }
            if (data.type === 'citations' && data.citations) {
              citationsEl.innerHTML = data.citations.map(function (c, i) {
                var num = i + 1;
                var label = c.repo + '/' + c.path + (c.heading ? ' — ' + c.heading : '');
                if (c.start_line != null && c.end_line != null) {
                  label += ' (lines ' + c.start_line + '–' + c.end_line + ')';
                }
                var attrs = 'data-repo="' + escapeAttr(c.repo) + '" data-path="' + escapeAttr(c.path) + '"';
                if (c.start_line != null) attrs += ' data-start-line="' + String(c.start_line) + '"';
                if (c.end_line != null) attrs += ' data-end-line="' + String(c.end_line) + '"';
                var block = '<div class="ask-citation-item">' +
                  num + '. <a href="#" ' + attrs + '>' + escapeHtml(label) + '</a>';
                if (c.snippet) {
                  block += '<pre class="ask-citation-snippet">' + escapeHtml(c.snippet) + '</pre>';
                }
                block += '</div>';
                return block;
              }).join('');
              citationsEl.classList.remove('hidden');
              citationsEl.querySelectorAll('a').forEach(function (a) {
                a.addEventListener('click', function (e) {
                  e.preventDefault();
                  var startLine = a.dataset.startLine;
                  if (startLine) {
                    var n = parseInt(startLine, 10);
                    if (n >= 1) pendingScrollToLine = { line: n };
                  }
                  loadDoc(a.dataset.repo, a.dataset.path);
                });
              });
            }
            if (data.type === 'error') {
              showAskError(data.error || 'Error');
              appendConsoleLine('Ask error: ' + (data.error || ''));
            }
          }
          function finish() {
            if (!answerEl.textContent || answerEl.textContent === '…') answerEl.textContent = '(No answer.)';
            appendConsoleLine('Ask complete.');
            done();
          }
          return read().catch(function (err) {
            showAskError(err.message || 'Request failed.');
            appendConsoleLine('Ask failed: ' + (err.message || ''));
            answerEl.classList.add('hidden');
            done();
          });
        })
        .catch(function (err) {
          showAskError(err.message || 'Request failed.');
          appendConsoleLine('Ask failed: ' + (err.message || ''));
          answerEl.classList.add('hidden');
          done();
        });
    }

    queryInput.addEventListener('keydown', function (e) {
      if (e.key === 'Enter' && !e.shiftKey) {
        e.preventDefault();
        runAsk();
      }
    });
  })();

  function filterTreeBySearch(q) {
    if (!q) {
      treeEl.querySelectorAll('.search-hidden').forEach(function (el) { el.classList.remove('search-hidden'); });
      return;
    }
    q = q.toLowerCase();
    treeEl.querySelectorAll('.repo-block').forEach(function (block) {
      var repoName = ((block.querySelector('.repo-name') || {}).textContent || '').toLowerCase();
      block.querySelectorAll('a[data-repo][data-path]').forEach(function (a) {
        var path = (a.dataset.repo + '/' + (a.dataset.path || '')).toLowerCase();
        var name = (a.textContent || '').toLowerCase();
        var match = path.indexOf(q) !== -1 || name.indexOf(q) !== -1;
        a.closest('li').classList.toggle('search-hidden', !match);
      });
      var dirs = block.querySelectorAll('.tree-dir');
      [].slice.call(dirs).sort(function (a, b) {
        return (b.querySelectorAll('.tree-dir').length) - (a.querySelectorAll('.tree-dir').length);
      }).forEach(function (dirLi) {
        var label = (dirLi.querySelector('.dir-label') || {}).textContent || '';
        var childVisible = dirLi.querySelector('.tree-children li:not(.search-hidden)');
        var dirMatch = label.toLowerCase().indexOf(q) !== -1 || childVisible;
        dirLi.classList.toggle('search-hidden', !dirMatch);
      });
      var anyVisible = repoName.indexOf(q) !== -1 || block.querySelector('li:not(.search-hidden)');
      block.classList.toggle('search-hidden', !anyVisible);
    });
  }

  /* Do not call showPlaceholder here: it runs before restorePanes() and would wipe saved pane state in localStorage. */
})();
