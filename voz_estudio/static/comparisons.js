'use strict';
let selectedComparison=null, comparisonPolling=false;
$('compare-current').onclick=async()=>{
  if(!$('generate-form').reportValidity())return;
  const payload={...generationOptions(),text:$('text').value};
  $('compare-current').disabled=true;
  try{
    const group=await api('/api/comparisons',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(payload)});
    selectedComparison=group.id;location.hash='comparar';await refreshComparisons();
  }catch(error){notice(error.message,true);}
  finally{$('compare-current').disabled=false;}
};
$('comparison-history').onchange=()=>{selectedComparison=$('comparison-history').value;$('comparison-list').replaceChildren();refreshComparisons().catch(error=>notice(error.message,true));};
function ratingField(name,label,value){
  return `<div><label>${label}<select name="${name}"><option value="">Sin evaluar</option>${[1,2,3,4,5].map(v=>`<option value="${v}" ${value===v?'selected':''}>${v} / 5</option>`).join('')}</select></label></div>`;
}
function comparisonCard(record){
  const node=recordCard(record);
  const title=document.createElement('p');title.className='pill';
  title.textContent=`${record.engine} · ${record.trial===1?'carga nueva':'repetición'}`;
  node.prepend(title);
  const metrics=document.createElement('p');metrics.className='comparison-metrics';
  metrics.textContent=`Carga del modelo: ${seconds(record.model_preparation_s)}\nPrimer audio sin carga: ${seconds(record.first_audio_generation_s)} · Con carga: ${seconds(record.first_audio_s)}\nSíntesis: ${seconds(record.inference_s)} · Total: ${seconds(record.processing_s)} · Audio: ${seconds(record.audio_duration_s)}\nRTF: ${record.rtf??'—'} · Pico VRAM PyTorch: ${record.peak_vram_mb??'—'} MB · Semilla: ${record.seed}`;
  node.append(metrics);
  if(record.trial===2 && record.status==='completed'){
    const evaluation=record.evaluation||{};
    const form=document.createElement('form');form.className='evaluation';
    form.innerHTML=`<h3>Tu valoración tras escuchar</h3><div class="settings-grid">${ratingField('naturalness','Naturalidad',evaluation.naturalness)}${ratingField('intelligibility','Claridad y pronunciación',evaluation.intelligibility)}${ratingField('similarity','Parecido / estabilidad de la voz',evaluation.similarity)}</div><label>¿Por qué prefieres este resultado?<textarea name="notes" maxlength="2000" placeholder="Acento, ritmo, errores, timbre…">${escapeHTML(evaluation.notes||'')}</textarea></label><button class="secondary">Guardar valoración</button><p class="footnote" role="status"></p>`;
    form.onsubmit=async event=>{
      event.preventDefault();const values=Object.fromEntries(new FormData(form));
      for(const key of ['naturalness','intelligibility','similarity'])values[key]=values[key]?Number(values[key]):null;
      try{await api(`/api/recordings/${record.id}/evaluation`,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(values)});form.querySelector('[role="status"]').textContent='Valoración guardada en el JSON del audio.';}
      catch(error){notice(error.message,true);}
    };
    node.append(form);
  }
  return node;
}
async function refreshComparisons(){
  if(comparisonPolling)return;comparisonPolling=true;
  try{
    const groups=await api('/api/comparisons');const select=$('comparison-history');
    const signature=JSON.stringify(groups.map(g=>g.id));
    if(select.dataset.signature!==signature){select.replaceChildren(...groups.map(g=>new Option(`${g.kind==='base'?'Clonación':'Voces incluidas'} · ${g.language} · ${new Date(g.created_at).toLocaleString('es-ES')}`,g.id)));select.dataset.signature=signature;}
    if(!selectedComparison&&groups.length)selectedComparison=groups[0].id;
    if(!selectedComparison){$('comparison-summary').textContent='Crea una comparación desde Generar audio.';return;}
    select.value=selectedComparison;
    const group=await api('/api/comparisons/'+selectedComparison);
    const warm=group.items.filter(r=>r.trial===2&&r.status==='completed'&&r.rtf!=null);
    let summary='Comparación en curso: se genera el mismo texto, idioma y semilla con ambos modelos, en frío y en memoria.';
    if(group.items.every(r=>['completed','error','cancelled'].includes(r.status))){
      if(warm.length===2){
        const faster=[...warm].sort((a,b)=>a.rtf-b.rtf)[0];
        summary=`En esta prueba, ${faster.engine} tuvo el menor RTF en memoria (${faster.rtf}). Esto mide velocidad, no calidad. `;
        const scored=warm.filter(r=>['naturalness','intelligibility','similarity'].every(k=>r.evaluation?.[k]));
        if(scored.length===2){const scores=scored.map(r=>({model:r.engine,score:(r.evaluation.naturalness+r.evaluation.intelligibility+r.evaluation.similarity)/3})).sort((a,b)=>b.score-a.score);summary+=Math.abs(scores[0].score-scores[1].score)<.01?'Tus valoraciones de calidad empatan.':`Tu valoración más alta: ${scores[0].model} (${scores[0].score.toFixed(2)}/5).`;}
        else summary+='Escucha las repeticiones y puntúa ambas para comparar calidad.';
      }else summary='Hay pruebas que no han terminado correctamente. Revisa los errores de cada audio.';
    }
    $('comparison-summary').textContent=summary;
    let download=$('comparison-download');
    if(!download){download=document.createElement('a');download.id='comparison-download';download.className='secondary small';download.textContent='Descargar comparación JSON';$('comparison-summary').after(download);}
    download.href=`/api/comparisons/${group.id}/json`;
    const container=$('comparison-list');
    for(const record of group.items){
      const existing=[...container.children].find(n=>n.dataset.id===record.id);
      if(existing&&existing.contains(document.activeElement))continue;
      if(existing?.dataset.signature===JSON.stringify(record))continue;
      const card=comparisonCard(record);if(existing)existing.replaceWith(card);else container.append(card);
    }
    for(const node of [...container.children])if(!group.recordings.includes(node.dataset.id))node.remove();
  }finally{comparisonPolling=false;}
}
if(page==='comparar')refreshComparisons().catch(error=>notice(error.message,true));
