import {libraryScreen, templateScreen, setupScreen, templateCard, visibleFilms} from './screens.js';

const $ = selector => document.querySelector(selector);
const escapeHtml = value => String(value ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const e = escapeHtml;
const steps = ['Purpose', 'Look', 'Story', 'Sound', 'Export'];
const sceneId = () => `s-${Array.from(crypto.getRandomValues(new Uint8Array(8)), n=>n.toString(16).padStart(2,'0')).join('')}`;
const recentKey = 'showrig.recent-films.v1';
function readRecentFilms() {
  try {
    const stored=localStorage.getItem(recentKey);
    if(stored===null) return null;
    const ids=JSON.parse(stored);
    return Array.isArray(ids)?ids.filter(id=>typeof id==='string').slice(0,12):null;
  } catch {return null;}
}
const state = {catalog:null, projects:[], capabilities:null, id:null, board:null, step:0, scene:0, estimate:null, outputs:{}, job:null, mode:'preview', dirty:false, saving:Promise.resolve(), saveTimer:null, poll:null, busy:false, proof:null, proofPoll:null, view:'library', filter:'active', search:'', sort:'recent', selection:new Set(), trash:[], setup:null, setupPlatform:null, templateCategory:'All', pendingDelete:[], recent:readRecentFilms()};

async function api(path, method='GET', body) {
  const headers = {'X-Showrig-Request':'1'};
  if (body && !(body instanceof FormData)) headers['Content-Type'] = 'application/json';
  const response = await fetch(`/api${path}`, {method, headers, body:body instanceof FormData ? body : body ? JSON.stringify(body) : undefined});
  const result = await response.json();
  if (!response.ok) throw new Error(typeof result.detail === 'string' ? result.detail : 'Please check the information you entered.');
  return result;
}
function notify(message='') { $('#notice').textContent=message; $('#notice').hidden=!message; }
function activeJob() { return state.job && ['starting','running','cancelling'].includes(state.job.status); }
function seconds(value) { return value < 60 ? `${Math.round(value)} sec` : `${Math.floor(value/60)}:${String(Math.round(value%60)).padStart(2,'0')}`; }
function currentScene() { return state.board?.scenes[state.scene]; }
function selected(value, current) { return value === current ? ' selected' : ''; }
function checked(value) { return value ? ' checked' : ''; }
function setPath(object, path, value) { const parts=path.split('.'); const key=parts.pop(); const parent=parts.reduce((o,p)=>o[p]??= {},object); parent[key]=value; }
function dirty() {
  state.dirty=true;
  $('#save-status').textContent='UNSAVED CHANGES';
  clearTimeout(state.saveTimer);
  state.saveTimer=setTimeout(()=>save().catch(err=>notify(err.message)),800);
  updatePreview();
}
async function save() {
  clearTimeout(state.saveTimer);
  if (!state.id || !state.dirty) return state.saving;
  const id=state.id, snapshot=structuredClone(state.board);
  state.dirty=false;
  $('#save-status').textContent='SAVING…';
  const task=state.saving.catch(()=>{}).then(()=>api(`/projects/${id}`,'PUT',snapshot));
  state.saving=task;
  try {
    const response=await task;
    if (id===state.id) {
      state.estimate=response.estimate;
      $('#save-status').textContent=state.dirty ? 'UNSAVED CHANGES' : 'SAVED ON THIS COMPUTER';
      const badge=$('#duration'); if(badge) badge.textContent=`~ ${seconds(response.estimate.seconds)}`;
    }
    return response;
  } catch(error) {
    if(id===state.id) {state.dirty=true; $('#save-status').textContent='NOT SAVED';}
    throw error;
  }
}
function updateNavigation() {
  document.querySelectorAll('[data-nav]').forEach(button=>{
    const active=button.dataset.nav===state.view;
    button.classList.toggle('active',active);
    if(active) button.setAttribute('aria-current','page'); else button.removeAttribute('aria-current');
  });
  $('#film-count').textContent=state.projects.filter(p=>!p.archived).length;
  $('#nav-editor').hidden=!state.board;
  $('#nav-editor').classList.toggle('active',state.view==='editor');
  $('#setup-dot').classList.toggle('needs-setup',!state.capabilities?.ready);
}
async function refreshLibrary() {
  [state.projects,state.trash]=await Promise.all([api('/projects'),api('/trash')]);
  if(state.recent===null) {
    state.recent=state.projects.filter(p=>!p.archived).slice(0,6).map(p=>p.id);
    storeRecentFilms();
  }
  renderRecentFilms();
  updateNavigation();
}
function storeRecentFilms() {
  try {localStorage.setItem(recentKey,JSON.stringify(state.recent));return true;}
  catch {return false;}
}
function renderRecentFilms() {
  const films=(state.recent||[]).map(id=>state.projects.find(p=>p.id===id&&!p.archived)).filter(Boolean).slice(0,6);
  $('#library').innerHTML=films.map(p=>`<button class="library-item${p.id===state.id?' active':''}" data-action="open" data-id="${e(p.id)}" title="${e(p.title)}"><span class="film-icon" aria-hidden="true">▤</span>${e(p.title)}</button>`).join('') || '<p class="hint">No recent films. Open a film from the library to add it here.</p>';
  $('#clear-recent').disabled=!(state.recent||[]).length;
}
function rememberFilm(id) {
  state.recent=[id,...(state.recent||[]).filter(value=>value!==id)].slice(0,12);
  storeRecentFilms();
}
async function navigate(view) {
  await save();
  clearInterval(state.poll);clearInterval(state.proofPoll);
  state.view=view;
  history.replaceState(null,'',`#${view}`);
  notify();renderHome();
}
async function showNew(template='demo') {
  await save();
  $('#new-templates').innerHTML=state.catalog.templates.map(t=>templateCard(t,true,t.id===template)).join('');
  $('#new-dialog').showModal();$('#new-title').focus();
}
async function importProject(file) {
  if(!file) return;
  const form=new FormData();form.append('file',file);
  notify('Importing project and media…');
  const project=await api('/library/import','POST',form);
  await refreshLibrary();
  await openProject(project.id);
  notify(`Imported “${project.title}”. It is now in your Film library.`);
}
async function changeLibrary(action,ids) {
  if(!ids.length) return;
  await save();
  const result=await api('/library/actions','POST',{action,ids});
  if(action==='trash'&&result.changed.includes(state.id)) {state.id=null;state.board=null;}
  state.selection=new Set(result.errors.map(item=>item.id));
  await refreshLibrary();renderHome();
  notify(result.errors.length ? result.errors.map(item=>item.detail).join('\n') : `${result.changed.length} film${result.changed.length===1?'':'s'} ${action==='trash'?'moved to Trash. You can restore them there.':action==='restore'?'restored to the library.':action==='archive'?'archived. Files and exports are kept.':'returned to the active library.'}`);
}
function confirmDeletion(ids) {
  state.pendingDelete=ids;
  const film=[...state.projects,...state.trash].find(p=>p.id===ids[0]);
  $('#confirm-description').textContent=ids.length===1 ? `Permanently delete “${film?.title||'this film'}” and all files inside its film folder?` : `Permanently delete all ${ids.length} selected film folders and their files?`;
  $('#confirm-dialog').showModal();
}
async function copyCommand(text) {
  if(navigator.clipboard?.writeText) await navigator.clipboard.writeText(text);
  else {
    const field=document.createElement('textarea');field.value=text;document.body.append(field);field.select();
    const copied=document.execCommand('copy');field.remove();
    if(!copied) throw new Error('Select the command shown and copy it from the page.');
  }
  notify('Command copied. Run it in a terminal on the Showrig host.');
}
async function openProject(id, step=0, recordRecent=true) {
  await save();
  clearInterval(state.poll);
  clearInterval(state.proofPoll);
  const project=await api(`/projects/${id}`);
  if(recordRecent) rememberFilm(id);
  Object.assign(state,{view:'editor',id,board:project.board,estimate:project.estimate,outputs:project.outputs,job:project.job,step,scene:0,dirty:false,mode:project.outputs.final?'final':'preview',proof:null});
  notify(project.missing.length ? 'Some media has moved. Replace the missing files in Story or Sound before rendering.' : '');
  $('#save-status').textContent='SAVED ON THIS COMPUTER';
  await refreshLibrary(); render();
  if(activeJob()) beginPolling();
}
function route() { updateNavigation(); if(state.id) history.replaceState(null,'',`#${state.id}/${state.step}`); }
function renderHome() {
  updateNavigation();
  $('#breadcrumb').textContent=`Studio / ${state.view==='templates'?'Templates':state.view==='setup'?'Setup & extras':'Film library'}`;
  $('#save-status').textContent='SAVED ON THIS COMPUTER';
  $('#app').innerHTML=state.view==='templates'?templateScreen(state):state.view==='setup'?setupScreen(state):libraryScreen(state);
}
function previewMarkup() {
  return `<aside class="preview-panel"><div class="panel-heading"><span>YOUR FILM, TAKING SHAPE</span><span id="preview-scene-number"></span></div><div id="preview-content"></div><div class="preview-tip"><span class="tip-symbol" aria-hidden="true">i</span><p id="preview-tip-text">A layout sketch of your scene. Render a preview in Export to see the finished motion, timing, and sound.</p></div></aside>`;
}
function updatePreview() {
  if(!state.board || !$('#preview-content')) return;
  if(state.step===4 && state.outputs[state.mode]) {
    const manifest=state.outputs[state.mode];
    const url=`/api/projects/${state.id}/outputs/${state.mode}/mp4`;
    $('#preview-content').innerHTML=`<div class="output-toggle">${['preview','final'].filter(m=>state.outputs[m]).map(m=>`<button class="${m===state.mode?'active':''}" data-action="output-mode" data-mode="${m}">${m==='final'?'Final export':'Rendered preview'}</button>`).join('')}</div><div class="video-card"><video class="finished-video" src="${url}?v=${manifest.created||0}" controls preload="metadata" playsinline></video><div class="preview-caption"><span>${state.mode==='final'?'Final export':'Half-size preview'}</span><span>${manifest.duration ? seconds(manifest.duration) : 'Existing export'}</span></div></div><div class="output-links">${Object.keys(manifest.files).map(ext=>`<a href="/api/projects/${state.id}/outputs/${state.mode}/${ext}?download=true">${{mp4:'Download video',fcproj:'FilmCraft timeline (.fcproj)',srt:'Captions (SRT)'}[ext]}</a>`).join('')}<a class="package-link" href="/api/projects/${state.id}/package">Editable package + media (.zip)</a></div><p class="hint">Keep the ZIP for a portable edit: extract it, run its PREPARE-EDIT.py helper, then open the printed project in FilmCraft. The package includes media and may be large. This is your last successful ${state.mode==='final'?'export':'preview'}. Render again to include new edits.</p>`;
    $('#preview-tip-text').textContent='The video above is a real render. Your last successful export stays available while you make changes.';
    return;
  }
  const scene=currentScene(), style=state.board.style, fmt=state.board.format;
  if(!scene) return;
  const shape=fmt.height>fmt.width?'portrait':fmt.width===fmt.height?'square':'';
  const shot=scene.shots?.[0];
  const file=shot?.file;
  let media='';
  if(file?.startsWith('assets/')) {
    const url=`/api/projects/${state.id}/media?path=${encodeURIComponent(file)}`;
    media=/\.(png|jpe?g|webp)$/i.test(file)?`<img class="stage-media" src="${url}" alt="Scene media">`:`<video class="stage-media" src="${url}#t=${shot.in||0}" muted preload="metadata" playsinline></video>`;
  }
  $('#preview-scene-number').textContent=`SCENE ${String(state.scene+1).padStart(2,'0')}`;
  $('#preview-content').innerHTML=`<div class="preview-shell"><div class="stage ${shape} ${e(style.design||'clean')} ${media?'has-media':''}" style="--scene-accent:${e(scene.color||style.accent)};--scene-bg:${e(style.background)}">${media}<div class="stage-content"><div class="stage-rule"></div><div class="stage-title">${e(scene.title||'Your story starts here.')}</div><div class="stage-body">${e(scene.tagline||'Add a few words. Make them yours.')}</div>${scene.subtitle?`<div class="stage-subtitle">${e(scene.subtitle)}</div>`:''}</div></div><div class="preview-caption"><span>◌ Layout preview</span><span>${fmt.width} × ${fmt.height} · ${fmt.fps} fps</span></div></div>`;
}
function purpose() {
  const template=state.catalog.templates.find(t=>t.id===state.board.kind)||state.catalog.templates[0];
  return `<h3>Your story starts here.</h3><p class="muted">Set the title and direction, then move through Look, Story, Sound, and Export. Your changes are saved automatically.</p><label>Film title<input data-field="title" value="${e(state.board.title)}" maxlength="120"></label><label>Story template<select data-field="kind">${state.catalog.templates.map(t=>`<option value="${e(t.id)}"${selected(t.id,state.board.kind)}>${e(t.name)}</option>`).join('')}</select></label><p class="hint">Changing the guidance keeps your existing scenes. Start a new film from Templates for a fresh structure.</p><div class="story-outline"><span class="eyebrow">${e(template.name.toUpperCase())}</span><p>${e(template.description)}</p><ol>${template.prompts.map(prompt=>`<li>${e(prompt)}</li>`).join('')}</ol></div><div class="info-strip"><span aria-hidden="true">◈</span><div><strong>Procedural, from start to finish.</strong><p>Your content drives the scenes, title motion, timing, and music. No generated stock footage or cloud processing. Keep the editable FilmCraft project alongside your finished video.</p></div></div>`;
}
function stageName(id) {
  const stage=(state.catalog.stages||[]).find(s=>s.id===id);
  return stage?stage.name:id;
}
function activeStage() {
  const style=state.board.style, stage=style.stage||'auto';
  return stage==='auto'?(style.showcase3d?'screens':'fullbleed'):stage;
}
function stageCards() {
  const current=activeStage(), landscape=state.board.format.width>state.board.format.height;
  return (state.catalog.stages||[]).map(s=>{
    const blocked=!!s.needsBlender&&(!landscape||!state.capabilities?.blender);
    const chosen=s.id===current, own=chosen&&state.proof?.video;
    const sample=s.sample?`/samples/${s.id}.mp4`:'';
    return `<button class="stage-card${chosen?' selected':''}" data-action="stage" data-id="${s.id}" aria-pressed="${chosen}"${blocked?' disabled title="This stage needs landscape footage and Blender"':''}>
      <span class="stage-media">${own?`<video src="${state.proof.video}" muted loop autoplay playsinline></video>`:sample?`<video src="${sample}#t=0.1" muted loop playsinline preload="metadata"></video><span class="stage-play" aria-hidden="true">▶</span>`:`<span class="stage-blank" aria-hidden="true">▧</span>`}</span>
      <span class="stage-name">${e(s.name)}</span>
      <small>${e(s.description)}</small>
    </button>`;
  }).join('');
}
function proofPanel() {
  const shot=state.board.scenes.map((s,i)=>({s,i})).filter(x=>x.s.kind==='segment'&&x.s.shots?.length);
  if(!shot.length) return `<div class="proof"><p class="hint">Add a clip in Story and a short proof of this look can be rendered here.</p></div>`;
  const index=shot.some(x=>x.i===state.scene)?state.scene:shot[0].i;
  return `<div class="proof"><div class="proof-head"><strong>See it in motion</strong><span class="hint">A short draft of scene ${index+1} in “${e(stageName(activeStage()))}”, rendered on this computer.</span></div><div class="proof-body" id="proof-status"></div><button data-action="proof" data-index="${index}">▷ Render a proof of this look</button></div>`;
}
function updateProof() {
  const box=$('#proof-status'), button=$('[data-action="proof"]');
  const p=state.proof, running=!!p&&!!p.job&&['starting','running'].includes(p.job.status);
  if(button) button.disabled=running;
  if(!box) return;
  if(!p) { box.innerHTML=''; return; }
  if(running) { box.innerHTML=`<progress max="${p.job.totalStages||8}" value="${p.job.completedStages||0}"></progress><p class="hint">${e(p.job.stage||'Rendering your proof')} · ${seconds(p.job.elapsed||0)}. Keep editing; this is a draft.</p>`; return; }
  if(p.video) {
    if(box.dataset.video===p.video) return;
    box.dataset.video=p.video;
    box.innerHTML=`<video class="proof-video" src="${p.video}" controls playsinline></video><p class="hint">Scene ${p.scene+1}, ${e(stageName(p.stage))}. Only the stage changed.</p>`;
    return;
  }
  box.innerHTML=p.error?`<p class="error">${e(p.error)}</p>`:'';
}
function look() {
  const style=state.board.style, fmt=state.board.format;
  const design=state.catalog.looks.find(l=>l.id===style.design)||state.catalog.looks[0];
  const format=fmt.height>fmt.width?'vertical':fmt.width===fmt.height?'square':'landscape';
  return `<h3>Give it a point of view.</h3><p class="muted">A complete look, with room for your own colour.</p><label>Visual style</label><div class="look-grid">${state.catalog.looks.map(l=>`<button class="look-card ${l.id}${selected(l.id,style.design)}" data-action="look" data-id="${l.id}" aria-pressed="${l.id===style.design}"><span class="look-sample" style="--look-bg:${l.background};--look-accent:${l.accent}"><i></i><b>${l.id==='terminal'?'hello, world_':'A little<br>perspective.'}</b><small>YOUR STORY IN MOTION</small></span><span class="look-name">${l.name}</span></button>`).join('')}</div><p class="look-note">${e(design.description)}</p><label>How it is staged</label><div class="stage-grid">${stageCards()}</div>${proofPanel()}<label>Where will it be watched?</label><div class="choice-row">${[['landscape','Landscape','16:9'],['vertical','Portrait','9:16'],['square','Square','1:1']].map(([id,name,ratio])=>`<button class="choice${selected(id,format)}" data-action="format" data-id="${id}" aria-pressed="${id===format}"><span class="shape ${id}" aria-hidden="true"></span>${name} <span class="muted">${ratio}</span></button>`).join('')}</div><div class="two-col"><label>Accent colour<input type="color" data-field="style.accent" value="${e(style.accent)}"></label><label>Background<input type="color" data-field="style.background" value="${e(style.background)}"></label></div><details><summary>A few more choices</summary><label>Transitions<select data-field="style.transitions"><option value="simple"${selected('simple',style.transitions)}>Soft dissolves</option><option value="cinematic"${selected('cinematic',style.transitions)}>Cinematic</option><option value="cuts"${selected('cuts',style.transitions)}>Clean cuts</option></select></label><label>Gentle camera push (%)<input type="number" data-field="style.pushIn" min="0" max="15" value="${style.pushIn}"></label><p class="hint">The stage is the big decision. Pick one and render a proof to see it with your own footage.</p></details>`;
}
function story() {
  const scene=currentScene();
  const template=state.catalog.templates.find(t=>t.id===state.board.kind)||state.catalog.templates[0];
  const prompt=template.prompts[Math.min(state.scene,template.prompts.length-1)];
  return `<h3>A few scenes. One clear story.</h3><p class="muted">${e(prompt)}. Text is enough; pictures are optional.</p><div class="scene-list" aria-label="Scenes">${state.board.scenes.map((s,i)=>`<button class="scene-tab${i===state.scene?' active':''}" data-action="scene" data-index="${i}" aria-pressed="${i===state.scene}"><small>SCENE ${String(i+1).padStart(2,'0')}</small><b>${e(s.title||'Untitled scene')}</b></button>`).join('')}<button class="scene-tab" data-action="add-scene" aria-label="Add scene">＋<b>Add scene</b></button></div><div class="scene-tools"><span class="scene-counter">${String(state.scene+1).padStart(2,'0')} / ${String(state.board.scenes.length).padStart(2,'0')}</span><div><button data-action="move-scene" data-direction="-1"${state.scene===0?' disabled':''} aria-label="Move scene earlier">←</button> <button data-action="move-scene" data-direction="1"${state.scene===state.board.scenes.length-1?' disabled':''} aria-label="Move scene later">→</button> <button data-action="duplicate">Duplicate</button> <button class="delete" data-action="delete-scene"${state.board.scenes.length===1?' disabled':''}>Remove</button></div></div><label>Heading<input data-field="scene.title" value="${e(scene.title)}" maxlength="160" placeholder="${e(prompt)}"></label><label>On-screen text<textarea data-field="scene.tagline" maxlength="600" placeholder="One useful thought, in your own words.">${e(scene.tagline)}</textarea></label><p class="hint">Keep it concise. The scene gets enough time to read naturally.</p><div class="dropzone" id="dropzone"><div class="upload-icon" aria-hidden="true">↥</div><label for="media-input">Bring your pictures<p>Drop images or video clips here</p><input class="file-input" id="media-input" type="file" accept="image/png,image/jpeg,image/webp,video/mp4,video/quicktime,video/webm,.mkv" multiple><span class="upload-button">Choose files</span></label></div>${(scene.shots||[]).map((shot,i)=>`<div class="media-row"><span class="media-name">${e((shot.file||shot.capture?.url||'Media').split('/').pop())}</span><label>Start (sec)<input type="number" min="0" step="0.1" data-shot="${i}" value="${shot.in||0}" aria-label="Clip ${i+1} start time"></label><button data-action="replace-media" data-index="${i}" aria-label="Replace clip ${i+1}">↻</button><button data-action="remove-media" data-index="${i}" aria-label="Remove clip ${i+1}">×</button></div>`).join('')}<p class="hint">Clips supply the pictures. Add voice recordings and music in Sound.</p><input type="file" class="file-input" id="replace-input" accept="image/png,image/jpeg,image/webp,video/*"><details><summary>Timing and small print</summary><label>Small line or website<input data-field="scene.subtitle" value="${e(scene.subtitle)}" maxlength="600" placeholder="Optional"></label><label>Minimum scene length (seconds)<input type="number" data-field="scene.duration" min="1" max="180" step="0.5" value="${scene.duration??''}" placeholder="Automatic"></label><p class="hint">Leave blank for automatic timing. Narration and reading time always have room to finish.</p></details>`;
}
function sound() {
  const board=state.board, voice=board.voice, music=board.music;
  const speech=state.capabilities?.speech?.[voice.voice];
  return `<h3>Set the tone.</h3><p class="muted">Music and narration are optional. A quiet film can say plenty.</p><label>Narration</label><div class="sound-options">${[['none','Aa','Text only','Let the pictures and words do the talking.'],['files','♫','My recordings','Attach an audio file for each narration line.'],['tts','◌','Offline voice','Uses an installed voice model on this computer.']].map(([id,symbol,name,note])=>`<button class="sound-option${selected(id,voice.source)}" data-action="voice-source" data-id="${id}" aria-pressed="${id===voice.source}"><span class="sound-symbol" aria-hidden="true">${symbol}</span><span><b>${name}</b><small>${note}</small></span></button>`).join('')}</div>${voice.source==='tts'?`<label>Voice<select data-field="voice.voice">${[['af_heart','Warm American · female'],['af_bella','Bright American · female'],['am_michael','Calm American · male'],['bf_emma','Clear British · female'],['bm_george','Rich British · male']].map(([id,name])=>`<option value="${id}"${selected(id,voice.voice)}>${name}</option>`).join('')}</select></label><button data-action="check-speech" id="speech-check">Check this offline voice</button><p class="hint" id="speech-status">${e(speech?.reason||'Run a local synthesis check before using this voice. Nothing is downloaded.')}</p><button class="text-button" data-action="setup">Set up optional voices ↗</button>`:''}<div class="two-col"><label>Music<select data-field="music.source"><option value="procedural"${selected('procedural',music.source)}>Made to fit your film</option><option value="file"${selected('file',music.source)}>My own track</option><option value="none"${selected('none',music.source)}>No music</option></select></label>${music.source==='procedural'?`<label>Mood<select data-field="music.mood">${[['calm','Calm & spacious'],['bright','Bright & uplifting'],['drive','Energetic']].map(([id,name])=>`<option value="${id}"${selected(id,music.mood)}>${name}</option>`).join('')}</select></label>`:''}</div>${music.source==='file'?`<label>Music file<input type="file" id="music-input" accept="audio/*,.wav,.mp3,.m4a,.flac,.ogg"></label><p class="hint">${e(music.file?.split('/').pop()||'Choose your music track.')}</p>`:''}<details${voice.source!=='none'?' open':''}><summary>${voice.source==='none'?'Optional captions and audio settings':'Narration lines and captions'}</summary><label>Captions<select data-field="captions.mode"><option value="burn"${selected('burn',board.captions.mode)}>In the video + SRT file</option><option value="srt"${selected('srt',board.captions.mode)}>SRT file only</option><option value="none"${selected('none',board.captions.mode)}>None</option></select></label><label>Music level (dB)<input type="number" min="-60" max="0" data-field="music.volumeDb" value="${music.volumeDb}"></label><p class="hint">One sentence per line. With no voice, these become timed captions.</p>${board.scenes.map((s,i)=>`<div class="narration-card"><h3>${i+1}. ${e(s.title||'Untitled scene')}</h3><label>Narration / captions<textarea data-lines="${i}" placeholder="Optional: what should be said or captioned?">${e(s.lines.join('\n'))}</textarea></label>${voice.source==='files'?s.lines.map((line,j)=>`<label class="recording">${j+1}. ${e(line)}<input type="file" data-recording-scene="${i}" data-recording-line="${j}" accept="audio/*"><span class="hint">${e(s.voice?.[j]?.split('/').pop()||'No recording attached')}</span></label>`).join(''):''}</div>`).join('')}</details>`;
}
function review() {
  return `<h3>One film. Two ways to keep it.</h3><p class="muted">Export a finished MP4 here in your browser. Your FilmCraft timeline stays editable, with individual clips, titles, and audio.</p><div class="export-explainer"><div><strong>MP4 video</strong><span>Play, share, and publish.</span></div><div><strong>FilmCraft project + media</strong><span>Keep editing later. Download the ZIP after a render.</span></div></div><ol class="review-list">${state.board.scenes.map((s,i)=>`<li><span class="review-number">${String(i+1).padStart(2,'0')}</span><div class="review-text"><strong>${e(s.title||'Untitled scene')}</strong><p>${e(s.tagline|| (s.shots?.length?`${s.shots.length} media item${s.shots.length>1?'s':''}`:'Add your scene text'))}</p><span class="hint">${s.lines.length} narration / caption line${s.lines.length!==1?'s':''}</span></div><button data-action="edit-scene" data-index="${i}">Edit</button></li>`).join('')}</ol><a class="hint" href="/api/projects/${state.id}/storyboard">Download storyboard</a><div class="render-buttons"><button data-action="render" data-mode="preview"${activeJob()?' disabled':''}>▷ Render preview</button><button class="primary" data-action="render" data-mode="final"${activeJob()?' disabled':''}>Export video <span aria-hidden="true">↗</span></button></div><p class="hint">Preview renders at half size. Final export uses ${state.board.format.width} × ${state.board.format.height}. The browser starts the render; native tools do the work on this computer. No uploads or hosted processing.</p><div id="job-status"></div>`;
}
function updateJob() {
  const container=$('#job-status'); if(!container || !state.job) return;
  const job=state.job, running=activeJob(), failed=['failed','interrupted'].includes(job.status);
  container.innerHTML=`<div class="job-card${failed?' error':''}"><strong>${e(failed?'The render needs attention':job.stage)}</strong>${running?`<progress max="${job.totalStages}" value="${job.completedStages}" aria-label="Completed render stages"></progress><div class="job-meta"><span>${job.completedStages} of ${job.totalStages} stages complete</span><span>${seconds(job.elapsed||0)} elapsed</span></div><p>Rendering continues if you close this tab.</p><button data-action="cancel"${job.status==='cancelling'?' disabled':''}>${job.status==='cancelling'?'Stopping…':'Cancel render'}</button>`:`<p>${job.status==='succeeded'?'Your film is ready. Watch it and download it on the right.':job.status==='cancelled'?'Your previous export is safe. You can edit and render again.':e(job.error||'Try rendering again.')}</p>`}<p><a href="/api/jobs/${job.id}/log" target="_blank" rel="noopener">Open render log</a></p></div>`;
  document.querySelectorAll('[data-action="render"]').forEach(b=>b.disabled=running);
}
function render() {
  if(state.view!=='editor'||!state.board) return renderHome();
  route();
  $('#breadcrumb').textContent=`Studio / ${state.board.title}`;
  const headings=['A small film starts here.','Find your film’s feeling.','Make room for your story.','Give it a little atmosphere.','Ready for the first showing?'];
  $('#app').innerHTML=`<div class="page-heading"><div><span class="eyebrow">${e(state.catalog.templates.find(t=>t.id===state.board.kind)?.name.toUpperCase()||'YOUR FILM')}</span><h1>${headings[state.step]}</h1><p class="muted">${e(state.board.title)}</p></div><span class="duration-pill" id="duration">~ ${seconds(state.estimate?.seconds||0)}</span></div><nav class="steps" aria-label="Film creation steps">${steps.map((s,i)=>`<button class="step${state.step===i?' active':''}" data-action="step" data-index="${i}"${activeJob()&&i!==4?' disabled':''} aria-current="${state.step===i?'step':'false'}"><span class="step-number">${i+1}</span>${s}</button>`).join('')}</nav>${activeJob()?'<p class="locked-note">Your film is rendering. Editing is paused until it finishes or you cancel.</p>':''}<div class="workspace"><section class="form-panel">${[purpose,look,story,sound,review][state.step]()}</section>${previewMarkup()}</div><footer class="actions"><button class="secondary" data-action="${state.step?'back':'library'}">← ${state.step?'Back':'Your films'}</button><span class="muted">Your work is saved as you go.</span>${state.step<4?'<button class="primary" data-action="next">Continue <span aria-hidden="true">→</span></button>':'<button class="secondary" data-action="save">Save changes</button>'}</footer>`;
  updatePreview();updateJob();updateProof();
  if(activeJob() && state.step!==4) {state.step=4;render();}
}
async function uploadFile(file) {
  const data=new FormData();data.append('file',file);
  return api(`/projects/${state.id}/assets`,'POST',data);
}
async function addMedia(files, replacement=null) {
  if(state.busy) return;
  state.busy=true;notify('Adding your media…');
  try {
    const scene=currentScene();
    for(const file of files) {
      const asset=await uploadFile(file);
      if(!asset.info.width) throw new Error('This is an audio file. Add it in the Sound step.');
      const shot={file:asset.path,in:0,weight:1,fit:'fit'};
      scene.shots??=[];
      if(replacement!==null) {scene.shots[replacement]=shot;break;} else scene.shots.push(shot);
    }
    if(scene.shots?.length) {scene.kind='segment';scene.color??=state.board.style.accent;}
    dirty();await save();notify();render();
  } finally {state.busy=false;}
}
function beginPolling() {
  clearInterval(state.poll);
  state.poll=setInterval(async()=>{
    try {
      state.job=await api(`/jobs/${state.job.id}`);updateJob();
      if(!activeJob()) {
        clearInterval(state.poll);
        const fresh=await api(`/projects/${state.id}`);state.outputs=fresh.outputs;
        if(state.job.status==='succeeded') state.mode=state.job.mode;
        render();
      }
    } catch(error) {notify(`Could not check render progress: ${error.message}`);}
  },1200);
}

async function startProof(index) {
  await save();
  notify('Starting a proof render…');
  const result=await api(`/projects/${state.id}/proof`,'POST',{scene:index});
  state.proof={proof:result.proof,scene:result.scene,stage:result.stage,job:result.job,video:null,error:null};
  notify('');render();beginProofPolling();
}
function beginProofPolling() {
  clearInterval(state.proofPoll);
  state.proofPoll=setInterval(async()=>{
    if(!state.proof) {clearInterval(state.proofPoll);return;}
    try {
      const job=await api(`/jobs/${state.proof.job.id}`);state.proof.job=job;
      if(['starting','running'].includes(job.status)) {updateProof();return;}
      clearInterval(state.proofPoll);
      if(job.status==='succeeded') state.proof.video=`/api/proofs/${state.proof.proof}/video?t=${Date.now()}`;
      else state.proof.error=job.error||'The proof did not finish. Open the render log for details.';
      updateProof();
    } catch(error) {clearInterval(state.proofPoll);notify(error.message);}
  },1500);
}

document.addEventListener('input',event=>{
  const target=event.target;
  if(target.id==='film-search') {state.search=target.value;const pos=target.selectionStart;renderHome();$('#film-search').focus();$('#film-search').setSelectionRange(pos,pos);return;}
  if(!state.board || activeJob()) return;
  if(target.dataset.field) {
    let value=target.type==='checkbox'?target.checked:target.type==='number'?(target.value===''?null:Number(target.value)):target.value;
    const field=target.dataset.field;
    if(field.startsWith('scene.')) setPath(currentScene(),field.slice(6),value);
    else setPath(state.board,field,value);
    if(field==='style.accent') state.board.scenes.forEach(s=>{if(s.color)s.color=value;});
    dirty();
  }
  if(target.dataset.lines!==undefined) {
    const scene=state.board.scenes[Number(target.dataset.lines)];
    scene.lines=target.value.split('\n').map(x=>x.trim()).filter(Boolean);
    scene.voice=(scene.voice||[]).slice(0,scene.lines.length);
    dirty();
  }
  if(target.dataset.shot!==undefined) {currentScene().shots[Number(target.dataset.shot)].in=Number(target.value);dirty();}
});
document.addEventListener('change',async event=>{
  const field=event.target;
  if(field.dataset.select) {if(field.checked) state.selection.add(field.dataset.select);else state.selection.delete(field.dataset.select);renderHome();return;}
  if(field.id==='select-all') {visibleFilms(state).forEach(p=>field.checked?state.selection.add(p.id):state.selection.delete(p.id));renderHome();return;}
  if(field.id==='film-sort') {state.sort=field.value;renderHome();return;}
  if(field.id==='setup-platform') {state.setupPlatform=field.value;renderHome();return;}

  try {
    const target=event.target;
    if(target.id==='import-input' && target.files[0]) {await importProject(target.files[0]);target.value='';}
    if(target.id==='media-input') await addMedia(target.files);
    if(target.id==='replace-input') await addMedia(target.files,Number(target.dataset.index));
    if(target.id==='music-input' && target.files[0]) {
      notify('Adding your music…');const asset=await uploadFile(target.files[0]);
      if(!asset.info.audio) throw new Error('Choose a file with audio for the music track.');
      state.board.music.file=asset.path;dirty();await save();notify();render();
    }
    if(target.dataset.recordingScene!==undefined && target.files[0]) {
      notify('Adding your recording…');const asset=await uploadFile(target.files[0]);
      if(!asset.info.audio) throw new Error('Choose an audio recording.');
      const scene=state.board.scenes[Number(target.dataset.recordingScene)];scene.voice??=[];
      while(scene.voice.length<scene.lines.length) scene.voice.push('');
      scene.voice[Number(target.dataset.recordingLine)]=asset.path;dirty();await save();notify();render();
    }
    if(['music.source','voice.voice','kind'].includes(target.dataset.field) || (target.dataset.lines!==undefined && state.board.voice.source==='files')) {await save();render();}
  } catch(error) {notify(error.message);}
});
document.addEventListener('dragover',event=>{if(event.target.closest('#dropzone')) {event.preventDefault();$('#dropzone').classList.add('dragover');}});
document.addEventListener('dragleave',event=>{if(event.target.closest('#dropzone')) $('#dropzone').classList.remove('dragover');});
document.addEventListener('drop',event=>{if(event.target.closest('#dropzone')) {event.preventDefault();addMedia(event.dataTransfer.files).catch(error=>notify(error.message));}});
document.addEventListener('mouseover',event=>{const card=event.target.closest?.('.stage-card');const video=card?.querySelector('video');if(video&&video.paused)video.play().catch(()=>{});});
document.addEventListener('mouseout',event=>{const card=event.target.closest?.('.stage-card');if(!card||card.contains(event.relatedTarget))return;const video=card.querySelector('video');if(video)video.pause();});
document.addEventListener('click',async event=>{
  const target=event.target.closest('[data-action]');if(!target || target.disabled) return;
  const action=target.dataset.action;
  try {
    if(action==='new') {await showNew();return;}
    if(action==='import') {$('#import-input').click();return;}
    if(action==='clear-recent') {
      state.recent=[];
      const persisted=storeRecentFilms();renderRecentFilms();
      notify(persisted?'Recent films cleared. Your films are still in Film library.':'Recent films cleared for this session. This browser could not save the history setting.');return;
    }
    if(action==='new-template') {await showNew(target.dataset.template);return;}
    if(action==='templates') {await navigate('templates');return;}
    if(action==='template-category') {state.templateCategory=target.dataset.category;renderHome();return;}
    if(action==='close-dialog') {$('#new-dialog').close();return;}
    if(action==='close-confirm') {$('#confirm-dialog').close();return;}
    if(action==='setup') {await navigate('setup');return;}
    if(action==='recheck-setup') {
      target.disabled=true;target.textContent='Checking…';
      try {[state.capabilities,state.setup]=await Promise.all([api('/capabilities'),api('/setup')]);renderHome();notify('Tool availability refreshed. Use a voice synthesis check in Sound before narration.');}
      finally {target.disabled=false;}return;
    }
    if(action==='copy-command') {await copyCommand(decodeURIComponent(target.dataset.command));const label=target.textContent;target.textContent='Copied ✓';setTimeout(()=>target.textContent=label,1800);return;}
    if(action==='return-editor') {if(state.id) await openProject(state.id,state.step);return;}
    if(action==='library-filter') {state.filter=target.dataset.filter;state.selection.clear();state.search='';await navigate('library');return;}
    if(action==='library-action') {await changeLibrary(target.dataset.operation,target.dataset.id?[target.dataset.id]:[...state.selection]);return;}
    if(action==='restore-film') {await changeLibrary('restore',[target.dataset.id]);return;}
    if(action==='delete-film') {confirmDeletion([target.dataset.id]);return;}
    if(action==='delete-selected') {confirmDeletion([...state.selection]);return;}
    if(action==='empty-trash') {confirmDeletion(state.trash.map(p=>p.id));return;}
    if(action==='confirm-delete') {
      target.disabled=true;
      try {
        const errors=[];
        for(const id of state.pendingDelete) {try {await api(`/trash/${id}`,'DELETE',{confirm:id});} catch(error) {errors.push(error.message);}}
        $('#confirm-dialog').close();state.selection.clear();await refreshLibrary();renderHome();
        notify(errors.length?errors.join('\n'):'Selected films permanently removed from Trash.');
      } finally {target.disabled=false;state.pendingDelete=[];}return;
    }
    if(action==='open') {await openProject(target.dataset.id);return;}
    if(action==='library') {await navigate('library');return;}
    if(action==='save') {await save();notify();return;}
    if(action==='step'||action==='next'||action==='back') {
      await save();state.step=action==='step'?Number(target.dataset.index):state.step+(action==='next'?1:-1);notify();render();return;
    }
    if(action==='template') {state.board.kind=target.dataset.id;dirty();render();}
    if(action==='look') {
      const look=state.catalog.looks.find(l=>l.id===target.dataset.id);
      Object.assign(state.board.style,Object.fromEntries(['accent','background','titles','transitions','pushIn'].map(k=>[k,look[k]])),{design:look.id});
      state.board.scenes.forEach(s=>{if(s.color)s.color=look.accent;});dirty();render();
    }
    if(action==='stage') {
      const id=target.dataset.id, stage=state.catalog.stages.find(s=>s.id===id);
      if(stage?.needsBlender && (state.board.format.width<=state.board.format.height || !state.capabilities?.blender))
        throw new Error('That stage needs a landscape film and Blender on this computer.');
      state.board.style.stage=id;
      state.board.style.showcase3d=id!=='fullbleed';
      state.proof=null;clearInterval(state.proofPoll);
      dirty();render();
    }
    if(action==='proof') {await startProof(Number(target.dataset.index));return;}
    if(action==='format') {
      const dimensions={landscape:[1920,1080],vertical:[1080,1920],square:[1080,1080]}[target.dataset.id];
      state.board.format={width:dimensions[0],height:dimensions[1],fps:30};
      if(target.dataset.id!=='landscape') {state.board.style.showcase3d=false;state.board.style.stage='fullbleed';state.proof=null;}
      dirty();render();
    }
    if(action==='scene') {await save();state.scene=Number(target.dataset.index);render();}
    if(action==='edit-scene') {state.scene=Number(target.dataset.index);state.step=2;render();}
    if(action==='add-scene') {if(state.board.scenes.length>=40) throw new Error('Use up to 40 scenes in one film.');state.board.scenes.push({id:sceneId(),kind:'card',title:'',tagline:'',lines:[]});state.scene=state.board.scenes.length-1;dirty();render();}
    if(action==='duplicate') {if(state.board.scenes.length>=40) throw new Error('Use up to 40 scenes in one film.');const scene=structuredClone(currentScene());scene.id=sceneId();state.board.scenes.splice(state.scene+1,0,scene);state.scene++;dirty();render();}
    if(action==='delete-scene') {state.board.scenes.splice(state.scene,1);state.scene=Math.min(state.scene,state.board.scenes.length-1);dirty();render();}
    if(action==='move-scene') {const index=state.scene+Number(target.dataset.direction);const [scene]=state.board.scenes.splice(state.scene,1);state.board.scenes.splice(index,0,scene);state.scene=index;dirty();render();}
    if(action==='remove-media') {const scene=currentScene();scene.shots.splice(Number(target.dataset.index),1);if(!scene.shots.length) scene.kind='card';dirty();render();}
    if(action==='replace-media') {$('#replace-input').dataset.index=target.dataset.index;$('#replace-input').click();}
    if(action==='voice-source') {state.board.voice.source=target.dataset.id;dirty();render();}
    if(action==='check-speech') {
      target.disabled=true;target.textContent='Checking local speech…';const voice=state.board.voice.voice;
      try {const result=await api('/speech/check','POST',{voice});state.capabilities.speech[voice]=result;render();}
      finally {target.disabled=false;}return;
    }
    if(action==='render') {
      target.disabled=true;
      try {await save();state.job=await api(`/projects/${state.id}/render`,'POST',{mode:target.dataset.mode});notify();render();beginPolling();}
      finally {target.disabled=false;}
    }
    if(action==='cancel') {state.job=await api(`/jobs/${state.job.id}/cancel`,'POST',{});updateJob();}
    if(action==='output-mode') {state.mode=target.dataset.mode;updatePreview();}
  } catch(error) {notify(error.message);}
});
$('#new-form').addEventListener('submit',async event=>{
  event.preventDefault();const button=event.target.querySelector('[type=submit]');button.disabled=true;
  try {const data=new FormData(event.target);const project=await api('/projects','POST',{title:data.get('title'),template:data.get('template')});$('#new-dialog').close();event.target.reset();await openProject(project.id);}
  catch(error){notify(error.message);$('#new-dialog').close();}finally{button.disabled=false;}
});
window.addEventListener('beforeunload',event=>{if(state.dirty){event.preventDefault();event.returnValue='';}});
async function start() {
  try {
    [state.catalog,state.capabilities,state.setup]=await Promise.all([api('/catalog'),api('/capabilities'),api('/setup')]);state.setupPlatform=state.setup.systems[state.setup.platform]?state.setup.platform:'linux';await refreshLibrary();
    const [id,step]=location.hash.slice(1).split('/');
    if(['library','templates','setup'].includes(id)) {state.view=id;renderHome();} else if(id) await openProject(id,Math.max(0,Math.min(4,Number(step)||0)),false);else renderHome();
    if(!state.capabilities.ready) notify(`Some video tools need setup: ${state.capabilities.missing.join(', ')}. You can still work on your storyboard.`);
  } catch(error) {notify(error.message);if(state.catalog) renderHome();else $('#app').innerHTML='<p class="muted">The studio could not connect. Reload the page after starting Showrig.</p>';}
}
start();
