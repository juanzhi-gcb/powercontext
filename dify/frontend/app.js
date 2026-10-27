const $ = (id) => document.getElementById(id);

const state = {
  player: null,
  ticket: null,
  conversation: '',
  items: [],
  activeItemId: null,
  activeTicket: '',
  busy: false,
  opening: '',
};

const ACTION_LABEL = {
  appraise: '鉴定完成',
  correct: '鉴定已纠正',
  pawn: '已确认典当',
  revisit: '回访已记录',
  retrieve: '物件已取回',
  shelf: '你的货架',
  chat: '柜台小叙',
};

const STAMP_TEXT = {
  appraise: '草稿',
  correct: '已改',
  pawn: '已收下',
  revisit: '已回访',
  retrieve: '已取回',
};

const FIELD_ORDER = ['外观', '特性', '寓意', '铭文', '小任务'];

const CHIP_MAP = {
  '描述新烦恼': { label: '鉴定一件烦恼', run: () => focusInput('') },
  '查看货架': { label: '查看货架', run: openShelf },
  '纠正鉴定': { label: '纠正鉴定', run: () => focusInput('你鉴定错了，我不是……') },
  '确认典当 / 确认入柜': { label: '确认典当', run: () => send('确认典当') },
  '报告近况，让物件变化': { label: '报告近况', run: () => focusInput('后来……') },
  '取回物件': { label: '取回物件', run: () => send('取回这件藏品') },
};

async function api(path, options = {}) {
  const response = await fetch(path, {
    credentials: 'same-origin',
    headers: { 'Content-Type': 'application/json', ...(options.headers || {}) },
    ...options,
  });
  let data = null;
  try { data = await response.json(); } catch (error) { data = null; }
  if (!response.ok) {
    const message = (data && (data.detail || data.message)) || '柜台那边出了点状况';
    const error = new Error(typeof message === 'string' ? message : '柜台那边出了点状况');
    error.status = response.status;
    throw error;
  }
  return data;
}

function escapeHtml(value) {
  return String(value).replace(/[&<>"']/g, (char) => (
    { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[char]
  ));
}

function unescapeMarkdown(value) {
  return String(value).replace(/\\([\\`*_{}\[\]()#+.!|>~-])/g, '$1');
}

function convKey() {
  return `pawnshop.conv.${state.player || 'unknown'}`;
}

function toast(message) {
  const el = $('toast');
  el.textContent = message;
  el.classList.add('show');
  clearTimeout(toast.timer);
  toast.timer = setTimeout(() => el.classList.remove('show'), 3200);
}

function setBusy(busy) {
  state.busy = busy;
  $('send').disabled = busy;
  $('send').textContent = busy ? '翻账本…' : '推过去';
}

function focusInput(placeholder) {
  const input = $('query');
  if (placeholder) input.placeholder = placeholder;
  input.focus();
}

function updateTicketUI() {
  $('ticketMini').textContent = state.ticket || '—';
  $('ticketCode').textContent = state.ticket || '—';
}

function typeInto(el, text, speed = 22) {
  el.textContent = '';
  el.classList.add('typing');
  let index = 0;
  return new Promise((resolve) => {
    const timer = setInterval(() => {
      index = Math.min(text.length, index + 2);
      el.textContent = text.slice(0, index);
      if (index >= text.length) {
        clearInterval(timer);
        el.classList.remove('typing');
        resolve();
      }
    }, speed);
  });
}

function parseDisplay(markdown) {
  const result = { reply: '', action: '', ticket: '', status: '', name: '', fields: {}, memory: '', options: [], raw: markdown };
  const lines = String(markdown || '').split(/\r?\n/);
  let mode = '';
  for (const raw of lines) {
    const line = raw.trimEnd();
    if (line.trim() === '老余：') { mode = 'reply'; continue; }
    if (mode === 'reply') {
      if (line.startsWith('>')) {
        result.reply += (result.reply ? '\n' : '') + unescapeMarkdown(line.replace(/^>\s?/, ''));
        continue;
      }
      // The rendered display puts one blank line between "老余：" and the
      // quoted reply, and another blank line after it. Blank lines inside the
      // quote block must not end the reply.
      if (line.trim() === '') continue;
      mode = '';
    }
    const action = line.match(/^\*\*(.+?)\*\*$/);
    if (action && !result.action) { result.action = action[1]; continue; }
    const ticket = line.match(/^当票 `([0-9a-f]+)` · (.+)$/);
    if (ticket) { result.ticket = ticket[1]; result.status = ticket[2]; continue; }
    const name = line.match(/^\*\*(.+?)\*\*（奇幻藏品）$/);
    if (name) { result.name = unescapeMarkdown(name[1]); continue; }
    const field = line.match(/^- (外观|特性|寓意|铭文|小任务)：(.*)$/);
    if (field) { result.fields[field[1]] = unescapeMarkdown(field[2]); continue; }
    if (/^(老余已记下|交易已保存|长期记忆)/.test(line.trim())) { result.memory = line.trim(); continue; }
    if (line.startsWith('可以输入：')) {
      result.options = line.replace('可以输入：', '').replace(/。$/, '')
        .split('；').map((item) => item.trim()).filter(Boolean);
    }
  }
  return result;
}

function renderCard(parsed) {
  const card = $('itemCard');
  if (!parsed.name) return;
  $('itemName').textContent = parsed.name;
  $('itemTicket').textContent = parsed.ticket ? `当票 ${parsed.ticket} · ${parsed.status}` : parsed.status;
  $('itemStatus').textContent = parsed.action || '';
  if (parsed.ticket) state.activeTicket = parsed.ticket;
  const dl = $('itemFields');
  dl.innerHTML = '';
  for (const key of FIELD_ORDER) {
    if (!parsed.fields[key]) continue;
    const dt = document.createElement('dt');
    dt.textContent = key;
    const dd = document.createElement('dd');
    dd.textContent = parsed.fields[key];
    dl.append(dt, dd);
  }
  card.hidden = false;
  const stamp = $('stamp');
  const action = parsed.action === '鉴定完成' ? 'appraise'
    : parsed.action === '鉴定已纠正' ? 'correct'
    : parsed.action === '已确认典当' ? 'pawn'
    : parsed.action === '回访已记录' ? 'revisit'
    : parsed.action === '物件已取回' ? 'retrieve' : '';
  stamp.textContent = STAMP_TEXT[action] || '已收下';
  stamp.classList.remove('show');
  void stamp.offsetWidth;
  stamp.classList.add('show');
  card.dataset.itemName = parsed.name;
}

function renderChips(options) {
  const holder = $('chips');
  holder.innerHTML = '';
  const labels = (options && options.length) ? options : ['描述新烦恼', '查看货架'];
  const seen = new Set();
  for (const option of labels) {
    const mapped = CHIP_MAP[option];
    const label = mapped ? mapped.label : option;
    if (seen.has(label)) continue;
    seen.add(label);
    const button = document.createElement('button');
    button.type = 'button';
    button.className = 'chip';
    button.textContent = label;
    button.addEventListener('click', () => {
      if (mapped) mapped.run();
      else focusInput(option);
    });
    holder.append(button);
  }
}

async function renderAnswer(markdown) {
  const parsed = parseDisplay(markdown);
  const receipt = $('receipt');
  receipt.classList.remove('fresh');
  void receipt.offsetWidth;
  receipt.classList.add('fresh');
  const speech = $('speech');
  const text = parsed.reply || markdown || '老余没有说话，只是把账本翻了一页。';
  await typeInto(speech, text, 18);
  const meta = [];
  if (parsed.ticket) meta.push(`当票 ${parsed.ticket}`);
  if (parsed.status) meta.push(parsed.status);
  if (parsed.memory) meta.push(parsed.memory);
  $('speechMeta').textContent = meta.join(' · ');
  $('footStamp').textContent = parsed.action || '柜台小叙';
  renderCard(parsed);
  renderChips(parsed.options);
  if (parsed.action === '已确认典当' || parsed.action === '回访已记录' || parsed.action === '物件已取回' || parsed.action === '鉴定已纠正') {
    refreshShelf().catch(() => {});
  }
}

async function ensureSession() {
  const data = await api('/api/session', { method: 'POST' });
  state.player = data.player;
  state.ticket = data.ticket;
  updateTicketUI();
  renderUserLine('');
  if (data.new) {
    await typeInto($('speech'), state.opening || '进来坐。我是老余。', 16);
    $('speechMeta').textContent = '新客登记 · 当票 ' + state.ticket;
  } else {
    state.conversation = localStorage.getItem(convKey()) || '';
    await typeInto($('speech'), '又见面了。旧账本我都收着，慢慢说。', 16);
    $('speechMeta').textContent = '旧客回访 · 当票 ' + state.ticket;
  }
}

function renderUserLine(text) {
  const line = $('userLine');
  if (!text) {
    line.hidden = true;
    line.textContent = '';
    return;
  }
  line.hidden = false;
  line.textContent = '你：' + text;
}

function flySlip(text, origin) {
  if (!origin || window.matchMedia('(prefers-reduced-motion: reduce)').matches) return;
  const rect = origin.getBoundingClientRect();
  const slip = document.createElement('div');
  slip.className = 'flying-slip';
  slip.textContent = text.length > 46 ? text.slice(0, 46) + '…' : text;
  slip.style.left = rect.left + rect.width / 2 + 'px';
  slip.style.top = rect.top + rect.height / 2 + 'px';
  document.body.append(slip);
  requestAnimationFrame(() => {
    const dx = window.innerWidth * 0.5 - (rect.left + rect.width / 2);
    const dy = window.innerHeight * 0.44 - (rect.top + rect.height / 2);
    slip.style.transform = `translate(-50%, -50%) translate(${dx}px, ${dy}px) rotate(7deg) scale(.45)`;
    slip.classList.add('go');
  });
  setTimeout(() => slip.remove(), 820);
}

function startParallax() {
  if (window.matchMedia('(prefers-reduced-motion: reduce)').matches) return;
  let frame = null;
  const set = (x, y) => {
    document.body.style.setProperty('--px', x.toFixed(3));
    document.body.style.setProperty('--py', y.toFixed(3));
  };
  document.addEventListener('pointermove', (event) => {
    if (frame) return;
    frame = requestAnimationFrame(() => {
      set((event.clientX / window.innerWidth - 0.5) * 2, (event.clientY / window.innerHeight - 0.5) * 2);
      frame = null;
    });
  }, { passive: true });
  document.addEventListener('pointerleave', () => set(0, 0));
}

async function send(text) {
  if (state.busy) return;
  const input = $('query');
  const query = (text !== undefined ? text : input.value).trim();
  if (!query) { input.focus(); return; }
  if (!state.player) await ensureSession();
  renderUserLine(query);
  flySlip(query, input);
  input.value = '';
  autosize(input);
  setBusy(true);
  $('shop').classList.add('thinking');
  $('footStamp').textContent = '正在翻账本';
  $('speech').classList.add('typing');
  $('speech').textContent = '沙沙……老余把你要说的话抄到一张新纸上。';
  try {
    const data = await api('/api/chat', {
      method: 'POST',
      body: JSON.stringify({ query, conversation_id: state.conversation }),
    });
    if (data.conversation_id) {
      state.conversation = data.conversation_id;
      localStorage.setItem(convKey(), state.conversation);
    }
    await renderAnswer(data.answer);
  } catch (error) {
    $('speech').classList.remove('typing');
    $('speech').textContent = error.message || '柜台那边没有回应。';
    $('footStamp').textContent = '未盖章';
    toast(error.message || '柜台那边没有回应');
  } finally {
    $('shop').classList.remove('thinking');
    setBusy(false);
  }
}

async function refreshShelf() {
  const data = await api('/api/shelf');
  state.items = (data && data.items) || [];
  state.activeItemId = (state.activeTicket
    && state.items.find((item) => item.id.startsWith(state.activeTicket))?.id)
    || state.items[0]?.id || null;
  $('shelfCount').textContent = state.items.length;
  renderShelfList();
}

function renderShelfList() {
  const holder = $('shelfList');
  holder.innerHTML = '';
  if (!state.items.length) {
    holder.innerHTML = '<p class="shelf-empty">货架还空着。说说最近硌着你的那件事，老余先给你出一张草稿。</p>';
    return;
  }
  for (const item of state.items) {
    const button = document.createElement('button');
    button.type = 'button';
    button.className = 'shelf-item';
    button.innerHTML = `<h3>${escapeHtml(item.card.name)}</h3>
      <p>当票 ${escapeHtml(item.id.slice(0, 8))} · ${escapeHtml(statusText(item.status))} · 第 ${item.version} 版</p>`;
    button.addEventListener('click', () => openProvenance(item.id));
    holder.append(button);
  }
}

function statusText(status) {
  return {
    draft: '鉴定草稿', pawned: '已入柜', transformed: '回访后有了新变化',
    retrieved: '已取回', merged: '已合成', forgotten: '已遗忘',
  }[status] || status;
}

function openShelf() {
  refreshShelf().catch(() => {});
  $('shelfDrawer').classList.add('open');
  $('shelfDrawer').setAttribute('aria-hidden', 'false');
}

async function openProvenance(itemId) {
  $('shelfDrawer').classList.remove('open');
  $('shelfDrawer').setAttribute('aria-hidden', 'true');
  $('provenanceDrawer').classList.add('open');
  $('provenanceDrawer').setAttribute('aria-hidden', 'false');
  const holder = $('provenanceList');
  holder.innerHTML = '<p class="shelf-empty">正在翻旧账……</p>';
  try {
    const item = await api('/api/items/' + encodeURIComponent(itemId));
    holder.innerHTML = '';
    const head = document.createElement('div');
    head.className = 'event';
    head.innerHTML = `<h4>${escapeHtml(item.card.name)}</h4>
      <p>${escapeHtml(statusText(item.status))} · 第 ${item.version} 版</p>
      <p>寓意：${escapeHtml(item.card.meaning)}</p>`;
    holder.append(head);
    if (!item.events || !item.events.length) {
      holder.insertAdjacentHTML('beforeend', '<p class="shelf-empty">还没有可追溯的记录。</p>');
      return;
    }
    for (const event of item.events) {
      const block = document.createElement('div');
      block.className = 'event';
      const refs = (event.memory_refs || []).map((ref) => escapeHtml(ref.artifact_id)).join('、');
      const source = event.source_receipt && event.source_receipt.source
        ? escapeHtml(event.source_receipt.source.source_id) : '';
      const sync = event.memory_status === 'synced'
        ? '<span class="ok">已写入长期记忆</span>'
        : event.memory_status === 'not_required'
          ? '<span>草稿不写长期记忆</span>'
          : `<span class="warn">${escapeHtml(event.memory_status)}</span>`;
      block.innerHTML = `<h4>${escapeHtml(ACTION_LABEL[event.action] || event.action)} · 第 ${event.version} 版</h4>
        <p>${sync}</p>
        ${refs ? `<p>记忆编号：${refs}</p>` : ''}
        ${source ? `<p>来源：${source}</p>` : ''}`;
      holder.append(block);
    }
  } catch (error) {
    holder.innerHTML = `<p class="shelf-empty">${escapeHtml(error.message)}</p>`;
  }
}

function autosize(textarea) {
  textarea.style.height = 'auto';
  textarea.style.height = Math.min(textarea.scrollHeight, 120) + 'px';
}

/* ---------- 当票 ---------- */
function openTicket() {
  $('ticketModal').classList.add('open');
  $('ticketModal').setAttribute('aria-hidden', 'false');
}

async function copyTicket() {
  const code = state.ticket || '';
  try {
    await navigator.clipboard.writeText(code);
    toast('当票号已抄好');
  } catch (error) {
    $('claimInput').value = code;
    $('claimInput').select();
    toast('请手动复制选中的当票号');
  }
}

async function claimTicket(event) {
  event.preventDefault();
  const value = $('claimInput').value.trim();
  $('claimError').textContent = '';
  if (!value) return;
  try {
    const data = await api('/api/session/claim', { method: 'POST', body: JSON.stringify({ ticket: value }) });
    state.player = data.player;
    state.ticket = data.ticket;
    state.conversation = localStorage.getItem(convKey()) || '';
    state.activeTicket = '';
    state.activeItemId = null;
    $('itemCard').hidden = true;
    renderUserLine('');
    updateTicketUI();
    $('ticketModal').classList.remove('open');
    $('ticketModal').setAttribute('aria-hidden', 'true');
    $('claimInput').value = '';
    await refreshShelf();
    await typeInto($('speech'), '当票对上了。旧账本在这儿，慢慢看。', 18);
    $('speechMeta').textContent = '当票认领 · ' + state.ticket;
    toast('已认领当票 ' + state.ticket);
  } catch (error) {
    $('claimError').textContent = error.message;
  }
}

/* ---------- 雨 ---------- */
function startRain() {
  if (window.matchMedia && window.matchMedia('(prefers-reduced-motion: reduce)').matches) return;
  const canvas = $('rain');
  const ctx = canvas.getContext('2d');
  let width = 0;
  let height = 0;
  let drops = [];
  const resize = () => {
    width = canvas.width = window.innerWidth * devicePixelRatio;
    height = canvas.height = window.innerHeight * devicePixelRatio;
    canvas.style.width = window.innerWidth + 'px';
    canvas.style.height = window.innerHeight + 'px';
    const count = Math.round(window.innerWidth / 16);
    drops = Array.from({ length: count }, () => ({
      x: Math.random() * width,
      y: Math.random() * height,
      len: (8 + Math.random() * 22) * devicePixelRatio,
      speed: (6 + Math.random() * 10) * devicePixelRatio,
      alpha: 0.06 + Math.random() * 0.14,
    }));
  };
  const frame = () => {
    ctx.clearRect(0, 0, width, height);
    ctx.lineWidth = 1 * devicePixelRatio;
    for (const drop of drops) {
      ctx.strokeStyle = `rgba(150, 230, 225, ${drop.alpha})`;
      ctx.beginPath();
      ctx.moveTo(drop.x, drop.y);
      ctx.lineTo(drop.x - drop.len * 0.18, drop.y + drop.len);
      ctx.stroke();
      drop.y += drop.speed;
      if (drop.y > height) {
        drop.y = -drop.len;
        drop.x = Math.random() * width;
      }
    }
    requestAnimationFrame(frame);
  };
  resize();
  window.addEventListener('resize', resize);
  requestAnimationFrame(frame);
}

/* ---------- 事件 ---------- */
function bind() {
  $('form').addEventListener('submit', (event) => {
    event.preventDefault();
    send();
  });
  $('query').addEventListener('keydown', (event) => {
    if (event.key === 'Enter' && !event.shiftKey && !event.isComposing) {
      event.preventDefault();
      send();
    }
  });
  $('query').addEventListener('input', (event) => autosize(event.target));
  $('shelfBtn').addEventListener('click', openShelf);
  $('lookupBtn').addEventListener('click', () => {
    if (state.activeItemId) openProvenance(state.activeItemId);
  });
  $('itemCard').addEventListener('click', (event) => {
    if (event.target.closest('button')) return;
    if (state.activeItemId) openProvenance(state.activeItemId);
  });
  $('ticketBtn').addEventListener('click', openTicket);
  $('copyTicket').addEventListener('click', copyTicket);
  $('claimForm').addEventListener('submit', claimTicket);
  $('newSessionBtn').addEventListener('click', () => {
    state.conversation = '';
    localStorage.removeItem(convKey());
    $('itemCard').hidden = true;
    renderUserLine('');
    typeInto($('speech'), '好，重新开一段。柜台还是这张柜台，旧事都还在架上。', 18);
    $('speechMeta').textContent = '新会话';
    toast('已重开一段对话；旧记忆仍会按当票召回');
  });
  for (const button of document.querySelectorAll('[data-close]')) {
    button.addEventListener('click', () => {
      const target = $(button.dataset.close);
      target.classList.remove('open');
      target.setAttribute('aria-hidden', 'true');
    });
  }
  $('ticketModal').addEventListener('click', (event) => {
    if (event.target === $('ticketModal')) {
      $('ticketModal').classList.remove('open');
      $('ticketModal').setAttribute('aria-hidden', 'true');
    }
  });
  document.addEventListener('keydown', (event) => {
    if (event.key === 'Escape') {
      for (const id of ['ticketModal', 'shelfDrawer', 'provenanceDrawer']) {
        $(id).classList.remove('open');
        $(id).setAttribute('aria-hidden', 'true');
      }
    }
  });
}

async function init() {
  bind();
  startRain();
  startParallax();
  try {
    const config = await api('/api/config');
    state.opening = config.opening;
    renderChips([]);
  } catch (error) { /* 静态打开时也能看到界面 */ }
  try {
    await ensureSession();
    await refreshShelf();
  } catch (error) {
    $('speech').textContent = '柜台还没通电。确认后端和 Dify 都启动后再推门。';
    toast(error.message);
  }
}

init();