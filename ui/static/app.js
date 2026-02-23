(function () {
  const treeEl = document.getElementById('tree');
  const placeholderEl = document.getElementById('placeholder');
  const docEl = document.getElementById('doc');
  const errorEl = document.getElementById('error');

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

  var currentDoc = null;

  function showPlaceholder(clearStorage) {
    currentDoc = null;
    if (clearStorage) clearDocHash();
    placeholderEl.classList.remove('hidden');
    docEl.classList.add('hidden');
    docEl.innerHTML = '';
    errorEl.classList.add('hidden');
  }

  function showError(msg) {
    currentDoc = null;
    placeholderEl.classList.add('hidden');
    docEl.classList.add('hidden');
    errorEl.textContent = msg;
    errorEl.classList.remove('hidden');
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

  function showDoc(html, sourceType) {
    placeholderEl.classList.add('hidden');
    errorEl.classList.add('hidden');
    docEl.innerHTML = html;
    var emoji = sourceType && SOURCE_EMOJI[sourceType];
    if (emoji) {
      var h1 = docEl.querySelector('h1');
      if (h1) {
        var badge = document.createElement('span');
        badge.className = 'doc-source-badge' + (sourceType === 'cloud' ? ' doc-source-cloud' : '');
        badge.setAttribute('aria-hidden', 'true');
        badge.textContent = ' ' + emoji;
        h1.appendChild(badge);
      }
    }
    renderMermaidBlocks(docEl);
    docEl.classList.remove('hidden');
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
        html += '<button type="button" class="btn-repo-bookmark" id="btn-save-to-vault" title="Save current document to vault" aria-label="Save current document to vault"><span class="repo-btn-icon" aria-hidden="true">🔖</span></button>';
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
              if (currentDoc && currentDoc.repo === name) showPlaceholder(true);
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
              if (currentDoc && currentDoc.repo === 'vault' && currentDoc.path === path) showPlaceholder(true);
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
    var btnSaveToVault = treeEl.querySelector('#btn-save-to-vault');
    if (btnSaveToVault) {
      btnSaveToVault.addEventListener('click', function (e) {
        e.stopPropagation();
        if (!currentDoc) return;
        beginExecution();
        fetch('/api/vault/save-from-doc', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ repo: currentDoc.repo, path: currentDoc.path })
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
    }
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

  function loadDoc(repo, path, sourceType) {
    currentDoc = { repo: repo, path: path };
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
          var md = data;
          if (typeof marked !== 'undefined') {
            showDoc(marked.parse(md, { gfm: true }), sourceType);
          } else {
            showDoc('<pre>' + escapeHtml(md) + '</pre>', sourceType);
          }
        }
      })
      .catch(function (err) {
        showError(err.message || 'Failed to load document.');
      });
  }

  function restoreCurrentDoc() {
    var doc = getCurrentDocToRestore();
    if (doc) loadDoc(doc.repo, doc.path);
  }

  restoreCurrentDoc();

  fetch('/api/tree')
    .then(function (r) { return r.json(); })
    .then(function (data) {
      renderTree(data.repos || []);
      var doc = getCurrentDocToRestore();
      if (doc && (!currentDoc || currentDoc.repo !== doc.repo || currentDoc.path !== doc.path)) loadDoc(doc.repo, doc.path);
    })
    .catch(function () {
      treeEl.innerHTML = '<p class="error">Failed to load tree.</p>';
    });

  window.addEventListener('hashchange', function () {
    var doc = getDocFromHash();
    if (doc && (!currentDoc || currentDoc.repo !== doc.repo || currentDoc.path !== doc.path)) loadDoc(doc.repo, doc.path);
    else if (!getDocFromHash() && currentDoc) showPlaceholder(false);
  });

  document.getElementById('btn-home').addEventListener('click', function () {
    showPlaceholder(true);
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
                return num + '. <a href="#" data-repo="' + escapeAttr(c.repo) + '" data-path="' + escapeAttr(c.path) + '">' + escapeHtml(label) + '</a>';
              }).join('');
              citationsEl.classList.remove('hidden');
              citationsEl.querySelectorAll('a').forEach(function (a) {
                a.addEventListener('click', function (e) {
                  e.preventDefault();
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

  if (!currentDoc) showPlaceholder(false);
})();
