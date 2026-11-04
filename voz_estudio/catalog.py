"""Capabilities are explicit: 0.6B CustomVoice does not support instructions."""
from pathlib import Path

LANGUAGES={'Auto':'Automático','Spanish':'Español','English':'Inglés','French':'Francés',
           'German':'Alemán','Italian':'Italiano','Portuguese':'Portugués','Chinese':'Chino',
           'Japanese':'Japonés','Korean':'Coreano','Russian':'Ruso'}
LANGUAGE_CODES=dict(zip(LANGUAGES,(None,'es','en','fr','de','it','pt','zh','ja','ko','ru')))
SPEAKERS=[{'id':name,'native_language':language} for name,language in
          [('Vivian','Chinese'),('Serena','Chinese'),('Uncle_Fu','Chinese'),('Dylan','Chinese'),
           ('Eric','Chinese'),('Ryan','English'),('Aiden','English'),('Ono_Anna','Japanese'),('Sohee','Korean')]]
MODELS={
 'base06':dict(suffix='0.6B-Base',label='Base 0.6B · clonar',kind='base',instructions=False),
 'base17':dict(suffix='1.7B-Base',label='Base 1.7B · clonar',kind='base',instructions=False),
 'custom06':dict(suffix='0.6B-CustomVoice',label='CustomVoice 0.6B · voces incluidas',kind='custom',instructions=False),
 'custom17':dict(suffix='1.7B-CustomVoice',label='CustomVoice 1.7B · voces y estilo',kind='custom',instructions=True),
 'design17':dict(suffix='1.7B-VoiceDesign',label='VoiceDesign 1.7B · describir una voz',kind='design',instructions=True),
}
for model in MODELS.values():model['repo']='Qwen/Qwen3-TTS-12Hz-'+model['suffix']
REVISIONS={'base06':'5d83992436eae1d760afd27aff78a71d676296fc',
           'base17':'fd4b254389122332181a7c3db7f27e918eec64e3',
           'custom17':'0c0e3051f131929182e2c023b9537f8b1c68adfe',
           'custom06':'85e237c12c027371202489a0ec509ded67b5e4b5',
           'design17':'5ecdb67327fd37bb2e042aab12ff7391903235d3'}
for key,model in MODELS.items():model['revision']=REVISIONS[key]


def model_path(cache,key):
    model=MODELS[key]
    snapshots=Path(cache)/'hub'/('models--'+model['repo'].replace('/','--'))/'snapshots'
    preferred=snapshots/model['revision']
    if (preferred/'model.safetensors').is_file():return preferred
    return next((p for p in sorted(snapshots.glob('*')) if (p/'model.safetensors').is_file()),None)


def validate(key,language,speaker='',instruct='',kinds=('base','custom')):
    if key not in MODELS or MODELS[key]['kind'] not in kinds:raise ValueError('Modelo no válido para esta operación.')
    if language not in LANGUAGES:raise ValueError('Idioma no compatible.')
    model=MODELS[key]
    if model['kind']=='custom' and speaker not in [s['id'] for s in SPEAKERS]:raise ValueError('Selecciona una de las nueve voces incluidas.')
    if instruct.strip() and not model['instructions']:raise ValueError('Este modelo no admite instrucciones de estilo.')
    return model
