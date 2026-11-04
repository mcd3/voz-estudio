'use strict';
let selectedDesign = null, designSubmitting = false;
const designStates = {queued:'En cola',designing:'Creando la muestra con el modelo seleccionado…',ready:'Muestra preparada. Escúchala antes de guardar.',error:'No se ha podido crear la muestra.'};
async function refreshDesigns() {
  const designs = await api('/api/designs');
  const select = $('design-history');
  const signature = JSON.stringify(designs.map(d=>[d.id,d.status,d.voice_id]));
  if (select.dataset.signature !== signature) {
    select.replaceChildren(...designs.map(d=>new Option(`${d.name} · ${new Date(d.created_at).toLocaleString('es-ES')}`,d.id)));
    select.dataset.signature = signature;
  }
  if (!selectedDesign && designs.length) selectedDesign = designs[0].id;
  if (selectedDesign) select.value = selectedDesign;
  const design = designs.find(d=>d.id === selectedDesign);
  const busy = design && ['queued','designing'].includes(design.status);
  $('design-submit').disabled = designSubmitting || !!busy;
  $('design-result').hidden = !design;
  if (!design) return;
  $('design-state').textContent = design.error || (design.voice_id?'Guardada en Mis voces. Ya puedes usarla para generar otros textos.':designStates[design.status]);
  $('design-state').classList.toggle('error', design.status==='error');
  $('design-description-preview').textContent = design.description;
  $('design-text-preview').textContent = `${design.model_repo || 'VoiceDesign 1.7B'} · ${design.language || 'Spanish'}\n${design.text}`;
  $('design-audio').hidden = design.status!=='ready';
  if (design.status==='ready' && $('design-audio').dataset.id !== design.id) {
    $('design-audio').src = `/api/designs/${design.id}/audio`;
    $('design-audio').dataset.id = design.id;
  }
  $('design-save').disabled = design.status!=='ready' || !!design.voice_id;
  $('design-save').textContent = design.voice_id?'Voz guardada':'Guardar como voz clonable';
}
$('design-history').onchange = () => { selectedDesign=$('design-history').value;refreshDesigns().catch(error=>notice(error.message,true)); };
$('design-form').onsubmit = async event => {
  event.preventDefault(); if (designSubmitting) return;
  designSubmitting=true; $('design-submit').disabled=true; notice('');
  try {
    const design = await api('/api/designs',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({...designOptions(),name:$('design-name').value,description:$('design-description').disabled?'':$('design-description').value,text:$('design-text').value})});
    selectedDesign=design.id;
    await refreshDesigns();
  } catch(error) { notice(error.message,true); }
  finally { designSubmitting=false;refreshDesigns().catch(()=>{}); }
};
$('design-save').onclick = async () => {
  if (!selectedDesign) return;
  $('design-save').disabled=true;
  try {
    const voice=await api(`/api/designs/${selectedDesign}/save`,{method:'POST'});
    localStorage.setItem('voz-estudio-selected',voice.id);
    autoSelect=voice.id;
    await refreshVoices();
    $('voice').value=voice.id;
    // A saved sample is a reference voice: generate with Base, not CustomVoice.
    if(usesCustomVoice())$('gen-model').value=$('gen-model').value==='custom17'?'base17':'base06';
    updateGenerationControls();

    await refreshDesigns();
    notice('Voz guardada. Ya puedes seleccionarla en Generar audio.');
  } catch(error) { notice(error.message,true);await refreshDesigns(); }
};
if (page==='crear') refreshDesigns().catch(error=>notice(error.message,true));
