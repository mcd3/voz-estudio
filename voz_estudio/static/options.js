'use strict';
let qwenCatalog={models:[],languages:{},speakers:[]};
function usesCustomVoice(){return $('gen-model').value.startsWith('custom');}
function updateGenerationControls(){
  const model=qwenCatalog.models.find(m=>m.id===$('gen-model').value);
  const custom=usesCustomVoice();
  $('gen-source').value=custom?'included':'clone';
  $('clone-choice').hidden=custom;$('custom-choice').hidden=!custom;
  $('voice').required=!custom;
  $('gen-style').disabled=!model?.instructions;
  $('gen-style-box').hidden=!model?.instructions;
  $('gen-style-help').textContent=model?.instructions?'Puedes indicar el estilo: tranquilo, alegre, pausado…':'Este modelo no admite instrucciones de estilo. El acento depende de la voz de referencia o de la voz incluida.';
  if(!model?.instructions)$('gen-style').value='';
}
function updateDesignControls(){
  const model=qwenCatalog.models.find(m=>m.id===$('design-model').value);
  $('design-source').value=model?.kind==='custom'?'included':'description';
  $('design-model-badge').textContent=model?.suffix||'Qwen3-TTS';
  $('design-custom-choice').hidden=model?.kind!=='custom';
  $('design-description').disabled=!model?.instructions;
  $('design-description').required=model?.kind==='design';
  $('design-description').minLength=model?.kind==='design'?10:0;
  if(!model?.instructions)$('design-description').value='';
  $('design-model-help').textContent=model?.kind==='design'?'Crea una voz a partir de tu descripción.':model?.instructions?'Usa una voz incluida y describe su estilo. Puedes guardar la muestra para clonarla después.':'Usa una de las nueve voces incluidas. La versión 0.6B no admite instrucciones de estilo.';
}
function generationOptions(){
  return {model:$('gen-model').value,language:$('gen-language').value,voice_id:usesCustomVoice()?null:$('voice').value,
          speaker:$('gen-speaker').value,instruct:$('gen-style').disabled?'':$('gen-style').value,
          seed:Number($('gen-seed').value),temperature:Number($('gen-temperature').value),
          top_p:Number($('gen-top-p').value),top_k:Number($('gen-top-k').value),
          repetition_penalty:Number($('gen-penalty').value),do_sample:$('gen-sampling').checked,
          max_new_tokens:Number($('gen-max-tokens').value),force_reload:$('gen-cold').checked};
}
function designOptions(){
  return {model:$('design-model').value,language:$('design-language').value,speaker:$('design-speaker').value,
          seed:Number($('design-seed').value),temperature:Number($('design-temperature').value),
          top_p:Number($('design-top-p').value),top_k:Number($('design-top-k').value),
          repetition_penalty:Number($('design-penalty').value),do_sample:$('design-sampling').checked,
          max_new_tokens:Number($('design-max-tokens').value)};
}
async function initializeOptions(){
  qwenCatalog=await api('/api/catalog');
  for(const [id,kinds] of [['gen-model',['base','custom']],['design-model',['design','custom']]]){
    $(id).replaceChildren(...qwenCatalog.models.filter(m=>kinds.includes(m.kind)).map(m=>new Option(m.label+(m.available?'':' · no instalado'),m.id)));
  }
  $('design-model').value='design17';
  for(const id of ['gen-language','design-language','reference-language']){
    $(id).replaceChildren(...Object.entries(qwenCatalog.languages).map(([key,label])=>new Option(label,key)));
    $(id).value=id==='reference-language'?'Auto':'Spanish';
  }
  for(const id of ['gen-speaker','design-speaker']){
    $(id).replaceChildren(...qwenCatalog.speakers.map(s=>new Option(`${s.id} · lengua nativa: ${qwenCatalog.languages[s.native_language]}`,s.id)));
    $(id).value='Ryan';
  }
  $('gen-source').onchange=()=>{
    const size=$('gen-model').value.endsWith('17')?'17':'06';
    $('gen-model').value=($('gen-source').value==='included'?'custom':'base')+size;
    updateGenerationControls();
  };
  $('design-source').onchange=()=>{
    $('design-model').value=$('design-source').value==='description'?'design17':'custom17';
    updateDesignControls();
  };
  $('gen-model').onchange=updateGenerationControls;
  $('design-model').onchange=updateDesignControls;
  updateGenerationControls();updateDesignControls();
}
initializeOptions().catch(error=>notice(error.message,true));
