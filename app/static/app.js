const $ = (id) => document.getElementById(id);
const state = { catalog: null, campaigns: [], detail: null, streamId: null, draft: [], prefix: 'test_frolov_' };

function toast(message, error = false) {
  const node = $('toast'); node.textContent = message; node.className = `show${error ? ' error' : ''}`;
  clearTimeout(toast.timer); toast.timer = setTimeout(() => { node.className = ''; }, 4000);
}
async function api(path, options = {}) {
  const response = await fetch(path, { ...options, headers: { 'Content-Type': 'application/json', ...(options.headers || {}) } });
  let payload; try { payload = await response.json(); } catch { payload = {}; }
  if (!response.ok) throw new Error(typeof payload.detail === 'string' ? payload.detail : `Ошибка HTTP ${response.status}`);
  return payload;
}
function option(value, label) { const node = document.createElement('option'); node.value = value; node.textContent = label; return node; }
function fillSelect(node, items, placeholder, label = (x) => `${x.name} · #${x.id}`) {
  const previous = node.value; node.replaceChildren(option('', placeholder));
  items.forEach((item) => node.append(option(item.id, label(item))));
  if (items.some((item) => String(item.id) === previous)) node.value = previous;
}
function showPanel(panel) {
  $('create-panel').classList.toggle('hidden', panel !== 'create');
  $('editor-panel').classList.toggle('hidden', panel !== 'editor');
  document.querySelectorAll('.nav').forEach((node) => node.classList.toggle('active', node.dataset.panel === panel));
}
function setConnected(ok, label) {
  $('status-dot').className = `status-dot ${ok ? 'ok' : 'error'}`;
  $('connection-status').textContent = label;
}
async function loadCatalog() {
  state.catalog = await api('/api/catalog');
  fillSelect($('domain-select'), state.catalog.domains, 'Выберите домен');
  fillSelect($('group-select'), state.catalog.groups, 'Выберите группу');
  fillSelect($('source-select'), state.catalog.sources, 'Выберите источник');
  fillOfferSelect();
}
function fillOfferSelect() {
  const used = new Set(state.draft.map((x) => Number(x.offer_id)));
  fillSelect($('offer-select'), (state.catalog?.offers || []).filter((x) => !used.has(Number(x.id))), 'Выберите оффер');
}
async function loadCampaigns() {
  state.campaigns = await api('/api/campaigns');
  fillSelect($('campaign-select'), state.campaigns, 'Выберите кампанию', (x) => `${x.name} · #${x.id}`);
}
async function loadDetail(id) {
  if (!id) { state.detail = null; state.streamId = null; state.draft = []; renderStreams(); return; }
  state.detail = await api(`/api/campaigns/${id}`);
  fillSelect($('stream-select'), state.detail.streams.filter((s) => s.schema === 'landings'), 'Выберите поток', (s) => `${s.name} · #${s.id}`);
  if (!state.detail.streams.some((s) => String(s.id) === String(state.streamId) && s.schema === 'landings')) {
    state.streamId = state.detail.streams.find((s) => s.schema === 'landings')?.id || null;
  }
  $('stream-select').value = state.streamId || '';
  loadDraft();
}
function currentStream() { return state.detail?.streams.find((s) => String(s.id) === String(state.streamId)); }
function loadDraft() {
  const stream = currentStream();
  state.draft = stream ? stream.offers.map((x) => ({ offer_id: Number(x.offer_id), share: Number(x.share), state: x.state || 'active', name: x.name })) : [];
  renderStreams();
}
function renderStreams() {
  const stream = currentStream();
  $('stream-description').textContent = stream ? `${stream.name} · поток #${stream.id}` : 'Выберите кампанию и поток';
  const list = $('offers-list'); list.replaceChildren();
  if (!stream) { const empty = document.createElement('div'); empty.className = 'empty-state'; empty.textContent = 'Здесь появятся офферы выбранного потока'; list.append(empty); }
  state.draft.forEach((item, index) => {
    const row = document.createElement('div'); row.className = 'offer-row';
    const info = document.createElement('div'); const name = document.createElement('div'); name.className = 'offer-name'; name.textContent = item.name; const id = document.createElement('div'); id.className = 'offer-id'; id.textContent = `Оффер #${item.offer_id}${item.state === 'disabled' ? ' · выключен' : ''}`; info.append(name, id);
    const share = document.createElement('div'); share.className = 'share-input'; const input = document.createElement('input'); input.type = 'number'; input.min = '1'; input.max = '100'; input.value = item.share; input.disabled = item.state === 'disabled'; input.setAttribute('aria-label', `Доля ${item.name}`); input.addEventListener('input', () => { state.draft[index].share = Number(input.value) || 0; renderTotal(); }); share.append(input, document.createTextNode('%'));
    const remove = document.createElement('button'); remove.type = 'button'; remove.className = 'remove-button'; remove.textContent = '×'; remove.setAttribute('aria-label', `Удалить ${item.name}`); remove.addEventListener('click', () => { state.draft.splice(index, 1); rebalance(); renderStreams(); });
    row.append(info, share, remove); list.append(row);
  });
  fillOfferSelect(); renderTotal();
}
function renderTotal() {
  const active = state.draft.filter((x) => x.state === 'active');
  const total = active.reduce((sum, x) => sum + Number(x.share), 0);
  $('share-total').textContent = `Итого: ${total}%`;
  const valid = !!currentStream() && active.length > 0 && state.draft.length <= 100 && total === 100 && active.every((x) => Number.isInteger(x.share) && x.share >= 1 && x.share <= 100);
  $('share-total').classList.toggle('invalid', !!currentStream() && !valid);
  $('save-button').disabled = !valid;
  $('share-hint').textContent = valid ? 'Можно сохранить изменения' : 'Сумма активных долей должна быть 100%';
}
function rebalance() {
  const active = state.draft.filter((x) => x.state === 'active');
  const n = active.length; if (!n || n > 100) return;
  const weights = active.map((x) => Math.max(1, Number(x.share) || 1));
  const sum = weights.reduce((a, b) => a + b, 0);
  const extra = 100 - n; const exact = weights.map((w) => extra * w / sum);
  const shares = exact.map((x) => Math.floor(x) + 1);
  let remainder = 100 - shares.reduce((a, b) => a + b, 0);
  exact.map((x, i) => ({ i, rem: x - Math.floor(x) })).sort((a, b) => b.rem - a.rem).slice(0, remainder).forEach((x) => shares[x.i]++);
  active.forEach((x, i) => { x.share = shares[i]; });
}
async function loadHistory() {
  const rows = await api('/api/history'); const node = $('history-list'); node.replaceChildren();
  if (!rows.length) { const p = document.createElement('p'); p.className = 'muted'; p.textContent = 'Пока нет действий'; node.append(p); return; }
  rows.slice(0, 5).forEach((row) => { const div = document.createElement('div'); div.className = 'history-row'; const text = document.createElement('strong'); text.textContent = row.action === 'create_campaign' ? `Создана кампания #${row.campaign_id}` : `Изменён поток #${row.stream_id}`; const date = document.createElement('span'); date.textContent = new Date(row.created_at).toLocaleDateString('ru-RU'); div.append(text, date); node.append(div); });
}

document.querySelectorAll('.nav').forEach((node) => node.addEventListener('click', () => showPanel(node.dataset.panel)));
$('create-form').addEventListener('submit', async (event) => {
  event.preventDefault(); const button = $('create-button'); button.disabled = true;
  const raw = Object.fromEntries(new FormData(event.currentTarget).entries());
  const data = { name: raw.name.trim(), country: raw.country.trim().toUpperCase(), offer_id: Number(raw.offer_id), domain_id: Number(raw.domain_id), group_id: Number(raw.group_id), traffic_source_id: Number(raw.traffic_source_id) };
  try { const campaign = await api('/api/campaigns', { method: 'POST', body: JSON.stringify(data) }); const result = $('create-result'); result.replaceChildren(); const cap = document.createElement('div'); cap.className = 'mini-label'; cap.textContent = 'КАМПАНИЯ СОЗДАНА'; const h = document.createElement('h3'); h.textContent = campaign.name; const p = document.createElement('p'); p.textContent = `ID ${campaign.id} · идентификатор ${campaign.alias}`; const link = document.createElement('a'); link.href = '#editor'; link.textContent = 'Перейти к редактору →'; link.addEventListener('click', async (e) => { e.preventDefault(); showPanel('editor'); await loadCampaigns(); $('campaign-select').value = campaign.id; await loadDetail(campaign.id); }); result.append(cap, h, p, link); toast(`Кампания #${campaign.id} создана`); await loadCampaigns(); await loadHistory(); }
  catch (error) { toast(error.message, true); } finally { button.disabled = false; }
});
$('campaign-select').addEventListener('change', async (e) => { try { await loadDetail(e.target.value); } catch (error) { toast(error.message, true); } });
$('stream-select').addEventListener('change', (e) => { state.streamId = e.target.value; loadDraft(); });
$('add-button').addEventListener('click', () => { const id = Number($('offer-select').value); const offer = state.catalog?.offers.find((x) => Number(x.id) === id); if (!offer) { toast('Выберите оффер', true); return; } if (state.draft.length >= 100) { toast('Можно добавить не более 100 офферов', true); return; } state.draft.push({ offer_id: id, share: Math.max(1, Math.round(100 / (state.draft.length + 1))), state: 'active', name: offer.name }); rebalance(); renderStreams(); });
$('balance-button').addEventListener('click', () => { rebalance(); renderStreams(); });
$('refresh-button').addEventListener('click', async () => { try { await Promise.all([loadCatalog(), loadCampaigns()]); await loadDetail($('campaign-select').value); await loadHistory(); toast('Данные обновлены из Keitaro'); } catch (error) { toast(error.message, true); } });
$('save-button').addEventListener('click', async () => { const stream = currentStream(); if (!stream) return; const button = $('save-button'); button.disabled = true; try { await api(`/api/campaigns/${state.detail.campaign.id}/streams/${stream.id}/offers`, { method: 'PUT', body: JSON.stringify({ expected_version: stream.version, offers: state.draft.map(({ offer_id, share, state }) => ({ offer_id, share, state })) }) }); await loadDetail(state.detail.campaign.id); await loadHistory(); toast('Офферы сохранены в Keitaro'); } catch (error) { toast(error.message, true); if (error.message.includes('изменился')) await loadDetail(state.detail.campaign.id); } finally { renderTotal(); } });

async function init() { try { const status = await api('/api/status'); state.prefix = status.prefix; $('prefix-label').textContent = status.prefix; if (!status.configured) { $('setup-banner').classList.remove('hidden'); setConnected(false, 'Нет подключения'); return; } await Promise.all([loadCatalog(), loadCampaigns(), loadHistory()]); setConnected(true, 'Keitaro подключён'); } catch (error) { setConnected(false, 'Ошибка подключения'); toast(error.message, true); } }
init();
