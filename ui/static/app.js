(function () {
  const treeEl = document.getElementById('tree');
  const placeholderEl = document.getElementById('placeholder');
  const docEl = document.getElementById('doc');
  const errorEl = document.getElementById('error');

  function showPlaceholder() {
    placeholderEl.classList.remove('hidden');
    docEl.classList.add('hidden');
    docEl.innerHTML = '';
    errorEl.classList.add('hidden');
  }

  function showError(msg) {
    placeholderEl.classList.add('hidden');
    docEl.classList.add('hidden');
    errorEl.textContent = msg;
    errorEl.classList.remove('hidden');
  }

  function showDoc(html) {
    placeholderEl.classList.add('hidden');
    errorEl.classList.add('hidden');
    docEl.innerHTML = html;
    docEl.classList.remove('hidden');
  }

  var lastRepos = [];
  var REPO_ORDER_KEY = 'draft-repo-order';
  var REPO_PINNED_KEY = 'draft-repo-pinned';

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
    return ordered;
  }

  function renderTree(repos) {
    if (!repos || repos.length === 0) {
      treeEl.innerHTML = '<p class="placeholder">No repos in index.</p>';
      return;
    }
    lastRepos = repos;
    var ordered = applyOrder(repos);
    var pinned = getPinnedRepos();
    var pinnedSet = {};
    pinned.forEach(function (p) { pinnedSet[p] = true; });
    var html = '';
    ordered.forEach(function (repo) {
      var isPinned = pinnedSet[repo.name];
      html += '<div class="repo-block collapsed" data-repo="' + escapeAttr(repo.name) + '">';
      html += '<div class="repo-header">';
      html += '<button type="button" class="btn-repo-collapse" title="Collapse/expand this repo" aria-expanded="false"><span class="repo-btn-icon" aria-hidden="true">▶</span></button>';
      html += '<span class="repo-name">' + escapeHtml(repo.name) + '</span>';
      html += '<button type="button" class="btn-repo-pin' + (isPinned ? ' pinned' : '') + '" title="' + (isPinned ? 'Unpin' : 'Pin to top') + '" data-repo="' + escapeAttr(repo.name) + '" aria-label="' + (isPinned ? 'Unpin' : 'Pin to top') + '"><span class="pin-icon-wrap"><span class="repo-btn-icon" aria-hidden="true">📌</span><span class="pin-toggle" aria-hidden="true">✓</span></span></button>';
      html += '<button type="button" class="btn-repo-down" title="Move to bottom" data-repo="' + escapeAttr(repo.name) + '" aria-label="Move to bottom"><span class="repo-btn-icon" aria-hidden="true">↓</span></button>';
      html += '</div>';
      html += '<ul class="repo-tree">' + renderChildren(repo.tree, repo.name, '') + '</ul></div>';
    });
    treeEl.innerHTML = html;

    treeEl.querySelectorAll('a[data-repo][data-path]').forEach(function (a) {
      a.addEventListener('click', function (e) {
        e.preventDefault();
        loadDoc(a.dataset.repo, a.dataset.path);
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
          pinned = pinned.concat([name]);
          order = order.filter(function (n) { return n !== name; });
          order.unshift(name);
        }
        setPinnedRepos(pinned);
        setRepoOrder(order);
        renderTree(lastRepos);
      });
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
        html += '<li><a href="#" data-repo="' + escapeAttr(repo) + '" data-path="' + escapeAttr(path) + '">' + escapeHtml(node.name) + '</a></li>';
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
  var MAX_CONSOLE_LINES = 200;

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
      });
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
            fetch('/api/pull', { method: 'POST' })
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
        .then(function () { input.disabled = false; input.focus(); });
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

  function loadDoc(repo, path) {
    fetch('/api/doc/' + encodeURIComponent(repo) + '/' + path.split('/').map(encodeURIComponent).join('/'))
      .then(function (r) {
        if (!r.ok) throw new Error(r.status === 404 ? 'Not found' : 'Failed to load');
        return r.text();
      })
      .then(function (md) {
        if (typeof marked !== 'undefined') {
          showDoc(marked.parse(md, { gfm: true }));
        } else {
          showDoc('<pre>' + escapeHtml(md) + '</pre>');
        }
      })
      .catch(function (err) {
        showError(err.message || 'Failed to load document.');
      });
  }

  fetch('/api/tree')
    .then(function (r) { return r.json(); })
    .then(function (data) {
      renderTree(data.repos || []);
    })
    .catch(function () {
      treeEl.innerHTML = '<p class="error">Failed to load tree.</p>';
    });

  document.getElementById('btn-home').addEventListener('click', function () {
    showPlaceholder();
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
    var askSubmit = document.getElementById('ask-submit');
    var answerEl = document.getElementById('ask-answer');
    var citationsEl = document.getElementById('ask-citations');
    var errorEl = document.getElementById('ask-error');
    if (!askPanel || !askSubmit || !queryInput) return;

    askToggle.addEventListener('click', function () {
      askPanel.classList.toggle('collapsed');
    });

    var reindexBtn = document.getElementById('ask-reindex');
    if (reindexBtn) {
      reindexBtn.addEventListener('click', function () {
        reindexBtn.disabled = true;
        reindexBtn.textContent = 'Building…';
        appendConsoleLine('$ reindex AI');
        fetch('/api/reindex_ai', { method: 'POST' })
          .then(function (r) { return r.json(); })
          .then(function (d) {
            reindexBtn.textContent = d.ok ? 'Rebuild AI index (' + (d.indexed || 0) + ' chunks)' : 'Rebuild AI index';
            if (d.ok) appendConsoleLine('AI index built: ' + (d.indexed || 0) + ' chunks.');
            if (!d.ok && d.error) {
              showAskError(d.error);
              appendConsoleLine('AI reindex failed: ' + (d.error || ''));
            }
          })
          .catch(function (err) {
            reindexBtn.textContent = 'Rebuild AI index';
            appendConsoleLine('AI reindex failed: ' + (err.message || ''));
          })
          .then(function () { reindexBtn.disabled = false; });
      });
    }

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

    askSubmit.addEventListener('click', function () {
      var query = (queryInput.value || '').trim();
      if (!query) return;
      answerEl.classList.add('hidden');
      answerEl.textContent = '';
      citationsEl.classList.add('hidden');
      citationsEl.innerHTML = '';
      showAskError('');
      answerEl.classList.remove('hidden');
      answerEl.textContent = '…';
      askSubmit.disabled = true;

      appendConsoleLine('$ ask: ' + query);
      appendConsoleLine('Streaming…');

      fetch('/api/ask', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ query: query })
      })
        .then(function (res) {
          if (!res.ok) throw new Error('Ask failed');
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
            askSubmit.disabled = false;
          }
          return read().catch(function (err) {
            showAskError(err.message || 'Request failed.');
            appendConsoleLine('Ask failed: ' + (err.message || ''));
            answerEl.classList.add('hidden');
            askSubmit.disabled = false;
          });
        })
        .catch(function (err) {
          showAskError(err.message || 'Request failed.');
          appendConsoleLine('Ask failed: ' + (err.message || ''));
          answerEl.classList.add('hidden');
          askSubmit.disabled = false;
        });
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

  showPlaceholder();
})();
