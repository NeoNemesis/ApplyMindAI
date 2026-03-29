/* ApplyMind AI — Frontend JS */

/* ============================================================
   SIDEBAR TOGGLE
   ============================================================ */
function toggleSidebar() {
  document.body.classList.toggle('sidebar-collapsed');
}

/* ============================================================
   DYNAMIC FORM LISTS (experience / education / languages)
   ============================================================ */
function addItem(containerId, templateId) {
  const container = document.getElementById(containerId);
  const template  = document.getElementById(templateId);
  if (!container || !template) return;

  const clone = template.content.cloneNode(true);
  const idx   = container.querySelectorAll('.dynamic-item').length;

  // Update input names to include index
  clone.querySelectorAll('[data-name]').forEach(el => {
    el.name = el.dataset.name;
  });

  container.appendChild(clone);
  updateRemoveButtons(containerId);
}

function removeItem(btn) {
  const item = btn.closest('.dynamic-item');
  if (item) {
    const container = item.parentElement;
    item.remove();
    updateRemoveButtons(container.id);
  }
}

function updateRemoveButtons(containerId) {
  const container = document.getElementById(containerId);
  if (!container) return;
  const items = container.querySelectorAll('.dynamic-item');
  items.forEach((item, i) => {
    const btn = item.querySelector('.remove-btn');
    if (btn) btn.style.display = items.length > 1 ? 'block' : 'none';
  });
}

/* ============================================================
   PLATFORM CARD SELECTION
   ============================================================ */
document.addEventListener('DOMContentLoaded', () => {
  document.querySelectorAll('.platform-card').forEach(card => {
    const cb = card.querySelector('input[type="checkbox"]');
    if (!cb) return;

    // Sync visual state on load
    if (cb.checked) card.classList.add('selected');

    card.addEventListener('click', (e) => {
      if (e.target === cb) return; // let checkbox handle itself
      cb.checked = !cb.checked;
      card.classList.toggle('selected', cb.checked);
    });

    cb.addEventListener('change', () => {
      card.classList.toggle('selected', cb.checked);
    });
  });

  // Init remove buttons
  ['exp-list', 'edu-list', 'lang-list'].forEach(id => {
    if (document.getElementById(id)) updateRemoveButtons(id);
  });
});

/* ============================================================
   JOB SEARCH — SSE STREAM
   ============================================================ */
function startSearch(formId) {
  const form    = document.getElementById(formId);
  const btn     = document.getElementById('start-btn');
  const terminal = document.getElementById('terminal');

  if (!form || !btn || !terminal) return;

  btn.disabled = true;
  btn.innerHTML = '<span class="spinner-border spinner-border-sm me-2"></span>Söker...';
  terminal.innerHTML = '';

  const data = new FormData(form);

  fetch('/search/run', {
    method: 'POST',
    body: data,
  })
  .then(r => r.json())
  .then(res => {
    if (res.error) {
      appendTerminal('❌ ' + res.error + '\n', 'err');
      resetBtn(btn);
      return;
    }

    // Start SSE stream
    const evtSource = new EventSource('/search/stream');

    evtSource.onmessage = (e) => {
      const msg = JSON.parse(e.data);

      if (msg.type === 'output') {
        appendTerminal(msg.text);
      } else if (msg.type === 'progress') {
        // Update per-job document generation progress bar
        const parts = msg.value.split('/');
        const done  = parseInt(parts[0], 10);
        const total = parseInt(parts[1], 10);
        const pct   = total > 0 ? Math.round(done / total * 100) : 0;
        const progressEl  = document.getElementById('job-progress');
        const progressBar = document.getElementById('job-progress-bar');
        const progressTxt = document.getElementById('job-progress-text');
        if (progressEl)  progressEl.style.display  = 'block';
        if (progressBar) progressBar.style.width    = pct + '%';
        if (progressTxt) progressTxt.textContent    = msg.value + ' jobb klara';
      } else if (msg.type === 'error') {
        appendTerminal(msg.text, 'err');
        evtSource.close();
        resetBtn(btn);
      } else if (msg.type === 'done') {
        appendTerminal('\n✅ Sökning klar!\n', 'ok');
        evtSource.close();
        resetBtn(btn);
        // Reload job count badge after 1s
        setTimeout(updateJobCount, 1000);
      }
    };

    evtSource.onerror = () => {
      evtSource.close();
      resetBtn(btn);
    };
  })
  .catch(err => {
    appendTerminal('❌ Nätverksfel: ' + err + '\n', 'err');
    resetBtn(btn);
  });
}

function appendTerminal(text, cls) {
  const terminal = document.getElementById('terminal');
  if (!terminal) return;
  const span = document.createElement('span');
  if (cls) span.className = cls;
  span.textContent = text;
  terminal.appendChild(span);
  terminal.scrollTop = terminal.scrollHeight;
}

function resetBtn(btn) {
  btn.disabled = false;
  btn.innerHTML = '<i class="bi bi-search me-2"></i>Starta Sökning';
}

function updateJobCount() {
  fetch('/api/stats')
    .then(r => r.json())
    .then(stats => {
      const el = document.getElementById('job-count-badge');
      if (el) el.textContent = stats.total_folders;
    });
}

/* ============================================================
   PDF PREVIEW MODAL
   ============================================================ */
function previewPdf(folder, filename) {
  const url = `/view/${encodeURIComponent(folder)}/${encodeURIComponent(filename)}`;
  const modal = document.getElementById('pdf-modal');
  const iframe = document.getElementById('pdf-iframe');
  if (iframe) iframe.src = url;
  if (modal) new bootstrap.Modal(modal).show();
}
