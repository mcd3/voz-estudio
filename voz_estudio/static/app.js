'use strict';
const $ = id => document.getElementById(id);
const escapeHTML = value => String(value ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const seconds = value => value == null ? '—' : Number(value).toFixed(2) + ' s';
const states = {queued:'En cola',processing:'Preparando voz',ready:'Preparada',loading:'Cargando modelo',generating:'Generando',completed:'Completado',cancelled:'Cancelado',error:'Error'};
let voices = [], voiceSignature = '', page = 'generar', activeId = null, polling = false, historyLimit = 50;
let playerAbort, mediaURL, mediaSource, sourceBuffer, streamQueue = [], streamFinished = false, livePlayback = false;
let lastRecord = null, registering = false, autoSelect = null;
let engineAvailable = false;
const engineMessage = document.createElement('p');
engineMessage.className = 'footnote';
engineMessage.setAttribute('role', 'status');
engineMessage.setAttribute('aria-live', 'polite');
$('generate-button').parentElement.before(engineMessage);
$('generate-button').disabled = true;

// Advanced controls can be collapsed. Surface native validation failures.
for (const form of document.querySelectorAll('form')) {
  form.addEventListener('invalid', event => {
    const field=event.target;
    const details=field.closest('details');
    if(details)details.open=true;
    const label=field.labels?.[0]?.textContent.trim() || field.name || 'un campo';
    notice(`Revisa ${label}: ${field.validationMessage}`,true);
  },true);
}


function notice(text, error = false) { $('notice').textContent = text; $('notice').hidden = !text; $('notice').classList.toggle('error', error); }
async function api(url, options = {}) {
  const response = await fetch(url, options);
  if (!response.ok) {
    const data = await response.json().catch(() => ({}));
    throw new Error(typeof data.detail === 'string' ? data.detail : 'No se ha podido completar la operación.');
  }
  return response.json();
}
function navigate(next) {
  page = ['generar','voces','crear','comparar','biblioteca'].includes(next) ? next : 'generar';
  document.querySelectorAll('.page').forEach(node => node.hidden = node.id !== page);
  document.querySelectorAll('.nav').forEach(node => node.classList.toggle('active', node.dataset.page === page));
  $('page-label').textContent = {generar:'Generar audio',voces:'Mis voces',crear:'Crear una voz',comparar:'Comparar modelos',biblioteca:'Biblioteca'}[page];
  if (page === 'biblioteca') loadHistory().catch(error => notice(error.message, true));
  if (page === 'crear' && typeof refreshDesigns === 'function') refreshDesigns().catch(error => notice(error.message,true));
  if (page === 'comparar' && typeof refreshComparisons === 'function') refreshComparisons().catch(error=>notice(error.message,true));
}
document.querySelectorAll('.nav[data-page]').forEach(node => node.onclick = () => { location.hash = node.dataset.page; });
window.addEventListener('hashchange', () => navigate(location.hash.slice(1)));
$('add-voice').onclick = () => { location.hash = 'voces'; $('name').focus(); };
$('text').oninput = () => { $('characters').textContent = $('text').value.length.toLocaleString('es-ES') + ' / 50.000 caracteres'; };
$('example').onclick = () => { $('text').value = 'Hola. Esta es una prueba de Voz Estudio. Podemos convertir cualquier texto en una grabación y conservarla junto a su fecha y su transcripción.'; $('text').oninput(); };
$('voice').onchange = () => localStorage.setItem('voz-estudio-selected', $('voice').value);

function updateOptions(select, allLabel = null) {
  const selected = select.value || localStorage.getItem('voz-estudio-selected');
  select.replaceChildren();
  if (allLabel) select.add(new Option(allLabel, ''));
  for (const voice of voices.filter(v => v.status === 'ready')) select.add(new Option(voice.name, voice.id));
  if (!select.options.length) select.add(new Option('Registra tu primera voz', ''));
  if ([...select.options].some(option => option.value === selected)) select.value = selected;
}
async function refreshVoices() {
  const data = await api('/api/voices');
  const signature = JSON.stringify(data);
  voices = data;
  if (signature === voiceSignature) return;
  voiceSignature = signature;
  updateOptions($('voice'));
  const filterValue = $('filter-voice').value;
  updateOptions($('filter-voice'), 'Todas las personas');
  $('filter-voice').value = filterValue;
  if (autoSelect && voices.some(v => v.id === autoSelect && v.status === 'ready')) {
    $('voice').value = autoSelect; localStorage.setItem('voz-estudio-selected', autoSelect); autoSelect = null;
    $('upload-status').textContent = 'Voz preparada. Ya puedes seleccionarla para generar audio.';
  }
  $('voice-count').textContent = voices.length;
  $('ready-count').textContent = voices.filter(v => v.status === 'ready').length + ' PREPARADAS';
  $('voices-list').innerHTML = voices.length ? voices.map(voice => `<article class="voice-card"><div class="top"><span class="avatar">${escapeHTML(voice.name.slice(0,2).toUpperCase())}</span><div><h3>${escapeHTML(voice.name)}</h3><small>${voice.duration_s ? voice.duration_s.toFixed(1) + ' s de referencia' : 'Registro de voz'}</small></div><span class="pill">${states[voice.status] || voice.status}</span></div>${voice.status === 'ready' ? `<audio controls preload="none" aria-label="Referencia de ${escapeHTML(voice.name)}" src="/api/voices/${voice.id}/reference"></audio><details><summary>Texto de referencia</summary><pre>${escapeHTML(voice.transcript)}</pre></details><button class="text-button use-voice" data-id="${voice.id}">Usar esta voz ↗</button>` : voice.status === 'error' ? `<p class="error">${escapeHTML(voice.error)}</p><button class="secondary retry" data-id="${voice.id}">Reintentar</button>` : '<p class="footnote">Preparando el audio y reconociendo el texto. Puedes seguir usando la aplicación.</p>'}</article>`).join('') : '<div class="empty">Tu estudio está listo.<br>Registra una voz para empezar.</div>';
  document.querySelectorAll('.use-voice').forEach(button => button.onclick = () => { $('voice').value = button.dataset.id; $('voice').onchange(); location.hash = 'generar'; });
  document.querySelectorAll('.retry').forEach(button => button.onclick = async () => { try { await api(`/api/voices/${button.dataset.id}/retry`, {method:'POST'}); await refreshVoices(); } catch (error) { notice(error.message, true); } });
}
$('audio-file').onchange = () => { $('file-label').textContent = $('audio-file').files[0]?.name || 'Selecciona un archivo de audio'; };
$('voice-form').onsubmit = async event => {
  event.preventDefault(); if (registering) return;
  const file = $('audio-file').files[0];
  if (!file || !$('name').value.trim()) return;
  if (file.size > 50 * 1024 * 1024) return notice('La muestra no puede superar los 50 MB.', true);
  registering = true; $('register').disabled = true; $('upload-status').textContent = 'Subiendo la muestra…'; notice('');
  const data = new FormData(); data.append('name', $('name').value.trim()); data.append('audio', file);
  try {
    data.append('language',$('reference-language').value);
    const voice = await api('/api/voices', {method:'POST', body:data}); autoSelect = voice.id;
    $('upload-status').textContent = 'Muestra recibida. Preparando la voz y su transcripción…';
    $('voice-form').reset(); $('audio-file').onchange(); await refreshVoices();
  } catch (error) { $('upload-status').textContent = error.message; notice(error.message, true); }
  finally { registering = false; $('register').disabled = false; }
};

function resetPlayer() {
  playerAbort?.abort(); $('player').pause(); $('player').removeAttribute('src'); $('player').load();
  if (mediaURL) URL.revokeObjectURL(mediaURL);
  mediaURL = null; sourceBuffer = null; mediaSource = null; streamQueue = []; streamFinished = false; livePlayback = false;
}
function pump() {
  if (!sourceBuffer || sourceBuffer.updating || mediaSource?.readyState !== 'open') return;
  try { if (streamQueue.length) sourceBuffer.appendBuffer(streamQueue.shift()); else if (streamFinished) mediaSource.endOfStream(); }
  catch (_) { livePlayback = false; notice('La escucha en directo no está disponible. Podrás reproducir el MP3 cuando termine.'); }
}
async function startPlayback(id) {
  if (!$('autoplay').checked || !window.MediaSource || !MediaSource.isTypeSupported('audio/mpeg')) return;
  livePlayback = true; playerAbort = new AbortController();
  mediaSource = new MediaSource(); mediaURL = URL.createObjectURL(mediaSource); $('player').src = mediaURL;
  mediaSource.addEventListener('sourceopen', () => { try { sourceBuffer = mediaSource.addSourceBuffer('audio/mpeg'); sourceBuffer.addEventListener('updateend', pump); pump(); } catch (_) { livePlayback = false; } }, {once:true});
  try {
    const response = await fetch(`/api/recordings/${id}/stream`, {signal:playerAbort.signal});
    if (!response.ok) throw Error('No se ha podido abrir el audio en directo.');
    const reader = response.body.getReader(); let playRequested = false;
    while (true) {
      const {value, done} = await reader.read(); if (done) break;
      streamQueue.push(value); pump();
      if (!playRequested) { playRequested = true; $('player').play().catch(() => notice('Pulsa reproducir si el navegador no inicia el audio automáticamente.')); }
    }
    streamFinished = true; pump();
  } catch (error) { if (error.name !== 'AbortError') { livePlayback = false; notice(error.message); } }
}
function showRecord(record) {
  lastRecord = record;
  const busy = ['queued','loading','generating'].includes(record.status);
  $('job-state').textContent = states[record.status];
  $('elapsed').textContent = seconds(record.processing_s ?? record.elapsed_s);
  $('first').textContent = seconds(record.first_audio_s);
  $('duration').textContent = seconds(record.audio_duration_s);
  $('generate-button').disabled = busy || !engineAvailable; $('cancel').hidden = !busy;
  document.body.classList.toggle('busy', busy);
  $('progress').textContent = record.error || ({queued:'En cola. El audio se guardará aunque cambies de apartado.',loading:'Preparando el modelo en este ordenador. La primera carga puede tardar.',generating:`Generando con ${record.voice_name}…`,completed:`Guardado: ${record.filename}`,cancelled:'Generación cancelada. El audio parcial se conserva si se ha producido.'}[record.status] || '');
  $('downloads').hidden = busy || !record.audio_bytes;
  $('download-audio').href = `/api/recordings/${record.id}/audio?download=true`;
  $('download-json').href = `/api/recordings/${record.id}/json`;
  if (!busy) {
    activeId = null;
    if (record.audio_bytes && !livePlayback) { $('player').src = `/api/recordings/${record.id}/audio`; if ($('autoplay').checked) $('player').play().catch(() => {}); }
  }
}
$('generate-form').onsubmit = async event => {
  event.preventDefault(); if (activeId || !engineAvailable) return;
  if (!$('voice').value && !usesCustomVoice()) { location.hash = 'voces'; return notice('Registra primero una voz.'); }
  $('generate-button').disabled = true; notice(''); resetPlayer(); $('downloads').hidden = true;
  try {
    const record = await api('/api/recordings', {method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({...generationOptions(),text:$('text').value})});
    activeId = record.id; showRecord(record); startPlayback(record.id); await refreshStatus();
  } catch (error) { $('generate-button').disabled = !engineAvailable; notice(error.message, true); }
};
$('cancel').onclick = async () => { if (!activeId) return; try { await api(`/api/recordings/${activeId}/cancel`, {method:'POST'}); $('progress').textContent = 'Cancelando al terminar el fragmento en curso…'; } catch (error) { notice(error.message, true); } };

function recordCard(record) {
  const node = document.createElement('article'); node.className = 'record'; node.dataset.id = record.id;
  node.dataset.signature = JSON.stringify(record);
  const complete = ['completed','cancelled','error'].includes(record.status), hasAudio = complete && record.audio_bytes > 0;
  const date = new Date(record.created_at).toLocaleString('es-ES', {dateStyle:'medium',timeStyle:'short'});
  node.innerHTML = `<div class="record-head"><div><h3>${escapeHTML(record.voice_name)}</h3><small>${escapeHTML(date)} · ${record.characters.toLocaleString('es-ES')} caracteres</small></div><span class="pill">${states[record.status]}</span></div><p class="preview">${escapeHTML(record.text.slice(0,180))}${record.text.length>180?'…':''}</p>${record.error?`<p class="error">${escapeHTML(record.error)}</p>`:''}${hasAudio?`<audio controls preload="none" src="/api/recordings/${record.id}/audio" aria-label="Audio de ${escapeHTML(record.voice_name)}"></audio>`:''}<details><summary>Ver texto completo</summary><pre>${escapeHTML(record.text)}</pre></details><div class="meta">Audio: ${seconds(record.audio_duration_s)} · Procesamiento: ${seconds(record.processing_s)} · Primer fragmento: ${seconds(record.first_audio_s)}</div><div class="actions">${hasAudio?`<a class="primary small" href="/api/recordings/${record.id}/audio?download=true">Descargar MP3 ↓</a>`:''}<a class="secondary small" href="/api/recordings/${record.id}/json">Texto y JSON ↓</a><button class="text-button reuse">Reutilizar texto ↗</button></div>`;
  node.querySelector('.reuse').onclick = () => { $('text').value = record.text; $('text').oninput(); if (voices.some(v=>v.id===record.voice_id && v.status==='ready')) $('voice').value=record.voice_id; location.hash='generar'; };
  const identity=document.createElement('p');identity.className='footnote';
  identity.textContent=`${record.engine || 'Base 0.6B'} · ${record.language || 'Spanish'} · Carga: ${seconds(record.model_preparation_s)} · Síntesis: ${seconds(record.inference_s)} · RTF: ${record.rtf ?? '—'}`;
  node.querySelector('.meta').before(identity);
  const reuse=node.querySelector('.reuse').onclick;
  node.querySelector('.reuse').onclick=()=>{reuse();$('gen-model').value=record.model||'base06';$('gen-language').value=record.language||'Spanish';$('gen-speaker').value=record.speaker||'Ryan';$('gen-style').value=record.instruct||'';updateGenerationControls();};
  return node;
}
async function loadHistory(reset = false) {
  const data = {items:[],total:0};
  do {
    const query = new URLSearchParams({q:$('search').value,voice_id:$('filter-voice').value,limit:Math.min(100,historyLimit-data.items.length),offset:data.items.length});
    const part = await api('/api/recordings?' + query);
    data.total=part.total;data.items.push(...part.items);
    if(!part.items.length) break;
  } while(data.items.length<historyLimit && data.items.length<data.total);
  if (reset) $('history').replaceChildren();
  $('record-count').textContent = data.total;
  $('more').hidden = data.items.length >= data.total;
  if (!data.items.length) { $('history').innerHTML = '<div class="empty">Todavía no hay grabaciones que coincidan.<br>Crea un audio o cambia la búsqueda.</div>'; return; }
  $('history').querySelector('.empty')?.remove();
  const ids = new Set(data.items.map(item => item.id));
  [...$('history').children].forEach(node => { if (!ids.has(node.dataset.id)) node.remove(); });
  data.items.forEach((record,index) => {
    let node = [...$('history').children].find(n=>n.dataset.id===record.id);
    if (!node || node.dataset.signature !== JSON.stringify(record)) { const fresh=recordCard(record); if(node) node.replaceWith(fresh); node=fresh; }
    if ($('history').children[index] !== node) $('history').insertBefore(node,$('history').children[index]||null);
  });
}
let searchTimer;
$('search').oninput = () => { clearTimeout(searchTimer); searchTimer=setTimeout(()=>{historyLimit=50;loadHistory(true).catch(error=>notice(error.message,true));},250); };
$('filter-voice').onchange = () => { historyLimit=50;loadHistory(true).catch(error=>notice(error.message,true)); };
$('refresh').onclick = () => loadHistory().catch(error=>notice(error.message,true));
$('more').onclick = () => { historyLimit+=50;loadHistory().catch(error=>notice(error.message,true)); };
async function refreshStatus() {
  const status = await api('/api/status');
  $('record-count').textContent = status.recordings;
  $('engine').textContent = status.engine==='designing'?'Creando una voz':status.engine==='loading'?'Preparando motor':status.engine==='ready'?`${status.device==='cuda'?'GPU':'CPU'} · ${status.loaded_model || 'motor preparado'}`:status.engine==='error'?'Motor pendiente de revisar':'Motor en espera';
  engineAvailable = status.engine === 'ready' || status.engine === 'error';
  $('generate-button').disabled = !!activeId || !engineAvailable;
  $('generate-button').innerHTML = engineAvailable ? 'Generar audio <span>↗</span>' : 'Preparando voz…';
  engineMessage.textContent = status.engine === 'designing' ? 'Creando una muestra con VoiceDesign. El motor de clonación se preparará al terminar.' : status.engine === 'ready' ? 'Motor preparado. Ya puedes generar audio.' : status.engine === 'error' ? `No se ha podido preparar el motor: ${status.error || 'error desconocido'}. Puedes reintentarlo al generar.` : 'Preparando voz… Estamos cargando el modelo y la aceleración. Puedes escribir el texto mientras esperas.';
  $('design-install').hidden = status.design_model_available;
}
async function poll() {
  if (polling) return; polling=true;
  try {
    if (activeId) { const id=activeId; const record=await api('/api/recordings/'+id); if(activeId===id) { showRecord(record); if(!activeId) { await refreshStatus(); if(page==='biblioteca') await loadHistory(); } } }
    await refreshVoices();
    if (page === 'crear') await refreshDesigns();
    if (page === 'comparar') await refreshComparisons();
    if ($('notice').textContent === 'No se ha podido conectar con la aplicación. Comprueba que sigue abierta.') notice('');
    if (page==='biblioteca' && activeId) await loadHistory();
  } catch (error) { notice('No se ha podido conectar con la aplicación. Comprueba que sigue abierta.',true); }
  finally { polling=false; }
}
navigate(location.hash.slice(1));
Promise.all([refreshVoices(),refreshStatus()]).catch(error=>notice(error.message,true));
setInterval(poll,1200);
setInterval(()=>refreshStatus().catch(()=>{}),6000);
