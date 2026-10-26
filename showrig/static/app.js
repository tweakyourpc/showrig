const $ = selector => document.querySelector(selector);
const escapeHtml = value => String(value ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const e = escapeHtml;
const steps = ['Purpose', 'Look', 'Story', 'Sound', 'Review'];
const symbols = ['▣', '◈', '↗', '≡'];
const sceneId = () => `s-${Array.from(crypto.getRandomValues(new Uint8Array(8)), n=>n.toString(16).padStart(2,'0')).join('')}`;
const state = {catalog:null, projects:[], capabilities:null, id:null, board:null, step:0, scene:0, estimate:null, outputs:{}, job:null, mode:'preview', dirty:false, saving:Promise.resolve(), saveTimer:null, poll:null, busy:false};

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
async function refreshLibrary() {
  state.projects=await api('/projects');
  $('#library').innerHTML=state.projects.map(p=>`<button class="library-item${p.id===state.id?' active':''}" data-action="open" data-id="${e(p.id)}" title="${e(p.title)}"><span class="film-icon" aria-hidden="true">▤</span>${e(p.title)}</button>`).join('') || '<p class="hint">Your films will live here.</p>';
}
async function openProject(id, step=0) {
  await save();
  clearInterval(state.poll);
  const project=await api(`/projects/${id}`);
  Object.assign(state,{id,board:project.board,estimate:project.estimate,outputs:project.outputs,job:project.job,step,scene:0,dirty:false,mode:project.outputs.final?'final':'preview'});
  notify(project.missing.length ? 'Some media has moved. Replace the missing files in Story or Sound before rendering.' : '');
  $('#save-status').textContent='SAVED ON THIS COMPUTER';
  await refreshLibrary(); render();
  if(activeJob()) beginPolling();
}
function route() { if(state.id) history.replaceState(null,'',`#${state.id}/${state.step}`); }
function renderHome() {
  $('#breadcrumb').textContent='Studio / Your films';
  $('#app').innerHTML=`<section class="welcome"><span class="eyebrow">SMALL FILMS. ALL YOURS.</span><h1>You have the story.<br>Let’s give it a little motion.</h1><p class="muted">A few words, a considered look, and whatever pictures you have. Turn them into a finished short film, right here on your computer.</p><button class="primary" data-action="new">Make a film <span aria-hidden="true">→</span></button><div class="welcome-art" aria-hidden="true"><div class="mini-frame"><i></i><strong>Show something<br>worth sharing.</strong><span>A small introduction. A lasting impression.</span></div><div class="mini-frame"><i></i><strong>One idea.<br>Beautifully told.</strong><span>Good stories start with something simple.</span></div><div class="mini-frame"><i></i><strong>Made here.<br>Ready to go.</strong><span>Your words, your pictures, your film.</span></div></div></section><div class="library-heading"><span>YOUR FILM LIBRARY</span></div><div class="library-grid">${state.projects.map(p=>`<button class="film-card" data-action="open" data-id="${e(p.id)}"><span class="template-symbol" aria-hidden="true">▤</span><strong>${e(p.title)}</strong><small>${e(p.kind)} · ${p.scenes} scenes</small></button>`).join('')}</div>`;
}
function previewMarkup() {
  return `<aside class="preview-panel"><div class="panel-heading"><span>YOUR FILM, TAKING SHAPE</span><span id="preview-scene-number"></span></div><div id="preview-content"></div><div class="preview-tip"><span class="tip-symbol" aria-hidden="true">i</span><p id="preview-tip-text">A layout sketch of your scene. Render a preview in Review to see the finished motion, timing, and sound.</p></div></aside>`;
}
function updatePreview() {
  if(!state.board || !$('#preview-content')) return;
  if(state.step===4 && state.outputs[state.mode]) {
    const manifest=state.outputs[state.mode];
    const url=`/api/projects/${state.id}/outputs/${state.mode}/mp4`;
    $('#preview-content').innerHTML=`<div class="output-toggle">${['preview','final'].filter(m=>state.outputs[m]).map(m=>`<button class="${m===state.mode?'active':''}" data-action="output-mode" data-mode="${m}">${m==='final'?'Final export':'Rendered preview'}</button>`).join('')}</div><div class="video-card"><video class="finished-video" src="${url}?v=${manifest.created||0}" controls preload="metadata" playsinline></video><div class="preview-caption"><span>${state.mode==='final'?'Final export':'Half-size preview'}</span><span>${manifest.duration ? seconds(manifest.duration) : 'Existing export'}</span></div></div><div class="output-links">${Object.keys(manifest.files).map(ext=>`<a href="/api/projects/${state.id}/outputs/${state.mode}/${ext}?download=true">${{mp4:'Download video',fcproj:'Editable project',srt:'Captions (SRT)'}[ext]}</a>`).join('')}</div><p class="hint">This is your last successful ${state.mode==='final'?'export':'preview'}. Render again to include new edits.</p>`;
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
  return `<h3>Start with the story.</h3><p class="muted">Choose a starting point. Your words and pictures make it yours.</p><label>Film title<input data-field="title" value="${e(state.board.title)}" maxlength="120"></label><label>What kind of film?</label><div class="template-grid">${state.catalog.templates.map((t,i)=>`<button class="template-card${selected(t.id,state.board.kind)}" data-action="template" data-id="${t.id}" aria-pressed="${t.id===state.board.kind}"><span class="template-symbol" aria-hidden="true">${symbols[i]}</span><strong>${e(t.name)}</strong><small>${e(t.description)}</small></button>`).join('')}</div>`;
}
function look() {
  const style=state.board.style, fmt=state.board.format;
  const design=state.catalog.looks.find(l=>l.id===style.design)||state.catalog.looks[0];
  const format=fmt.height>fmt.width?'vertical':fmt.width===fmt.height?'square':'landscape';
  return `<h3>Give it a point of view.</h3><p class="muted">A complete look, with room for your own colour.</p><label>Visual style</label><div class="look-grid">${state.catalog.looks.map(l=>`<button class="look-card ${l.id}${selected(l.id,style.design)}" data-action="look" data-id="${l.id}" aria-pressed="${l.id===style.design}"><span class="look-sample" style="--look-bg:${l.background};--look-accent:${l.accent}"><i></i><b>${l.id==='terminal'?'hello, world_':'A little<br>perspective.'}</b><small>YOUR STORY IN MOTION</small></span><span class="look-name">${l.name}</span></button>`).join('')}</div><p class="look-note">${e(design.description)}</p><label>Where will it be watched?</label><div class="choice-row">${[['landscape','Landscape','16:9'],['vertical','Portrait','9:16'],['square','Square','1:1']].map(([id,name,ratio])=>`<button class="choice${selected(id,format)}" data-action="format" data-id="${id}" aria-pressed="${id===format}"><span class="shape ${id}" aria-hidden="true"></span>${name} <span class="muted">${ratio}</span></button>`).join('')}</div><div class="two-col"><label>Accent colour<input type="color" data-field="style.accent" value="${e(style.accent)}"></label><label>Background<input type="color" data-field="style.background" value="${e(style.background)}"></label></div><details><summary>A few more choices</summary><label>Transitions<select data-field="style.transitions"><option value="simple"${selected('simple',style.transitions)}>Soft dissolves</option><option value="cinematic"${selected('cinematic',style.transitions)}>Cinematic</option><option value="cuts"${selected('cuts',style.transitions)}>Clean cuts</option></select></label><label>Gentle camera push (%)<input type="number" data-field="style.pushIn" min="0" max="15" value="${style.pushIn}"></label><label class="check-label"><input type="checkbox" data-field="style.showcase3d"${checked(style.showcase3d)}${format!=='landscape'||!state.capabilities?.blender?' disabled':''}>3D floating screens</label><p class="hint">Optional Blender scenes for landscape films with media. These take longer to render.</p></details>`;
}
function story() {
  const scene=currentScene();
  const template=state.catalog.templates.find(t=>t.id===state.board.kind)||state.catalog.templates[0];
  const prompt=template.prompts[Math.min(state.scene,2)];
  return `<h3>A few scenes. One clear story.</h3><p class="muted">${e(prompt)}. Text is enough; pictures are optional.</p><div class="scene-list" aria-label="Scenes">${state.board.scenes.map((s,i)=>`<button class="scene-tab${i===state.scene?' active':''}" data-action="scene" data-index="${i}" aria-pressed="${i===state.scene}"><small>SCENE ${String(i+1).padStart(2,'0')}</small><b>${e(s.title||'Untitled scene')}</b></button>`).join('')}<button class="scene-tab" data-action="add-scene" aria-label="Add scene">＋<b>Add scene</b></button></div><div class="scene-tools"><span class="scene-counter">${String(state.scene+1).padStart(2,'0')} / ${String(state.board.scenes.length).padStart(2,'0')}</span><div><button data-action="move-scene" data-direction="-1"${state.scene===0?' disabled':''} aria-label="Move scene earlier">←</button> <button data-action="move-scene" data-direction="1"${state.scene===state.board.scenes.length-1?' disabled':''} aria-label="Move scene later">→</button> <button data-action="duplicate">Duplicate</button> <button class="delete" data-action="delete-scene"${state.board.scenes.length===1?' disabled':''}>Remove</button></div></div><label>Heading<input data-field="scene.title" value="${e(scene.title)}" maxlength="160" placeholder="${e(prompt)}"></label><label>On-screen text<textarea data-field="scene.tagline" maxlength="600" placeholder="One useful thought, in your own words.">${e(scene.tagline)}</textarea></label><p class="hint">Keep it concise. The scene gets enough time to read naturally.</p><div class="dropzone" id="dropzone"><div class="upload-icon" aria-hidden="true">↥</div><label for="media-input">Bring your pictures<p>Drop images or video clips here</p><input class="file-input" id="media-input" type="file" accept="image/png,image/jpeg,image/webp,video/mp4,video/quicktime,video/webm,.mkv" multiple><span class="upload-button">Choose files</span></label></div>${(scene.shots||[]).map((shot,i)=>`<div class="media-row"><span class="media-name">${e((shot.file||shot.capture?.url||'Media').split('/').pop())}</span><label>Start (sec)<input type="number" min="0" step="0.1" data-shot="${i}" value="${shot.in||0}" aria-label="Clip ${i+1} start time"></label><button data-action="replace-media" data-index="${i}" aria-label="Replace clip ${i+1}">↻</button><button data-action="remove-media" data-index="${i}" aria-label="Remove clip ${i+1}">×</button></div>`).join('')}<p class="hint">Clips supply the pictures. Add voice recordings and music in Sound.</p><input type="file" class="file-input" id="replace-input" accept="image/png,image/jpeg,image/webp,video/*"><details><summary>Timing and small print</summary><label>Small line or website<input data-field="scene.subtitle" value="${e(scene.subtitle)}" maxlength="600" placeholder="Optional"></label><label>Minimum scene length (seconds)<input type="number" data-field="scene.duration" min="1" max="180" step="0.5" value="${scene.duration??''}" placeholder="Automatic"></label><p class="hint">Leave blank for automatic timing. Narration and reading time always have room to finish.</p></details>`;
}
function sound() {
  const board=state.board, voice=board.voice, music=board.music;
  const speech=state.capabilities?.speech?.[voice.voice];
  return `<h3>Set the tone.</h3><p class="muted">Music and narration are optional. A quiet film can say plenty.</p><label>Narration</label><div class="sound-options">${[['none','Aa','Text only','Let the pictures and words do the talking.'],['files','♫','My recordings','Attach an audio file for each narration line.'],['tts','◌','Offline voice','Uses an installed voice model on this computer.']].map(([id,symbol,name,note])=>`<button class="sound-option${selected(id,voice.source)}" data-action="voice-source" data-id="${id}" aria-pressed="${id===voice.source}"><span class="sound-symbol" aria-hidden="true">${symbol}</span><span><b>${name}</b><small>${note}</small></span></button>`).join('')}</div>${voice.source==='tts'?`<label>Voice<select data-field="voice.voice">${[['af_heart','Warm American · female'],['af_bella','Bright American · female'],['am_michael','Calm American · male'],['bf_emma','Clear British · female'],['bm_george','Rich British · male']].map(([id,name])=>`<option value="${id}"${selected(id,voice.voice)}>${name}</option>`).join('')}</select></label><button data-action="check-speech" id="speech-check">Check this offline voice</button><p class="hint" id="speech-status">${e(speech?.reason||'Run a local synthesis check before using this voice. Nothing is downloaded.')}</p>`:''}<div class="two-col"><label>Music<select data-field="music.source"><option value="procedural"${selected('procedural',music.source)}>Made to fit your film</option><option value="file"${selected('file',music.source)}>My own track</option><option value="none"${selected('none',music.source)}>No music</option></select></label>${music.source==='procedural'?`<label>Mood<select data-field="music.mood">${[['calm','Calm & spacious'],['bright','Bright & uplifting'],['drive','Energetic']].map(([id,name])=>`<option value="${id}"${selected(id,music.mood)}>${name}</option>`).join('')}</select></label>`:''}</div>${music.source==='file'?`<label>Music file<input type="file" id="music-input" accept="audio/*,.wav,.mp3,.m4a,.flac,.ogg"></label><p class="hint">${e(music.file?.split('/').pop()||'Choose your music track.')}</p>`:''}<details${voice.source!=='none'?' open':''}><summary>${voice.source==='none'?'Optional captions and audio settings':'Narration lines and captions'}</summary><label>Captions<select data-field="captions.mode"><option value="burn"${selected('burn',board.captions.mode)}>In the video + SRT file</option><option value="srt"${selected('srt',board.captions.mode)}>SRT file only</option><option value="none"${selected('none',board.captions.mode)}>None</option></select></label><label>Music level (dB)<input type="number" min="-60" max="0" data-field="music.volumeDb" value="${music.volumeDb}"></label><p class="hint">One sentence per line. With no voice, these become timed captions.</p>${board.scenes.map((s,i)=>`<div class="narration-card"><h3>${i+1}. ${e(s.title||'Untitled scene')}</h3><label>Narration / captions<textarea data-lines="${i}" placeholder="Optional: what should be said or captioned?">${e(s.lines.join('\n'))}</textarea></label>${voice.source==='files'?s.lines.map((line,j)=>`<label class="recording">${j+1}. ${e(line)}<input type="file" data-recording-scene="${i}" data-recording-line="${j}" accept="audio/*"><span class="hint">${e(s.voice?.[j]?.split('/').pop()||'No recording attached')}</span></label>`).join(''):''}</div>`).join('')}</details>`;
}
function review() {
  return `<h3>A final look at your story.</h3><p class="muted">Watch a quick render, adjust anything, then export the finished film.</p><ol class="review-list">${state.board.scenes.map((s,i)=>`<li><span class="review-number">${String(i+1).padStart(2,'0')}</span><div class="review-text"><strong>${e(s.title||'Untitled scene')}</strong><p>${e(s.tagline|| (s.shots?.length?`${s.shots.length} media item${s.shots.length>1?'s':''}`:'Add your scene text'))}</p><span class="hint">${s.lines.length} narration / caption line${s.lines.length!==1?'s':''}</span></div><button data-action="edit-scene" data-index="${i}">Edit</button></li>`).join('')}</ol><a class="hint" href="/api/projects/${state.id}/storyboard">Download storyboard</a><div class="render-buttons"><button data-action="render" data-mode="preview"${activeJob()?' disabled':''}>▷ Render preview</button><button class="primary" data-action="render" data-mode="final"${activeJob()?' disabled':''}>Export video <span aria-hidden="true">↗</span></button></div><p class="hint">Preview renders at half size. Final export uses ${state.board.format.width} × ${state.board.format.height}. Both run entirely here.</p><div id="job-status"></div>`;
}
function updateJob() {
  const container=$('#job-status'); if(!container || !state.job) return;
  const job=state.job, running=activeJob(), failed=['failed','interrupted'].includes(job.status);
  container.innerHTML=`<div class="job-card${failed?' error':''}"><strong>${e(failed?'The render needs attention':job.stage)}</strong>${running?`<progress max="${job.totalStages}" value="${job.completedStages}" aria-label="Completed render stages"></progress><div class="job-meta"><span>${job.completedStages} of ${job.totalStages} stages complete</span><span>${seconds(job.elapsed||0)} elapsed</span></div><p>Rendering continues if you close this tab.</p><button data-action="cancel"${job.status==='cancelling'?' disabled':''}>${job.status==='cancelling'?'Stopping…':'Cancel render'}</button>`:`<p>${job.status==='succeeded'?'Your film is ready. Watch it and download it on the right.':job.status==='cancelled'?'Your previous export is safe. You can edit and render again.':e(job.error||'Try rendering again.')}</p>`}<p><a href="/api/jobs/${job.id}/log" target="_blank" rel="noopener">Open render log</a></p></div>`;
  document.querySelectorAll('[data-action="render"]').forEach(b=>b.disabled=running);
}
function render() {
  if(!state.board) return renderHome();
  route();
  $('#breadcrumb').textContent=`Studio / ${state.board.title}`;
  const headings=['A small film starts here.','Find your film’s feeling.','Make room for your story.','Give it a little atmosphere.','Ready for the first showing?'];
  $('#app').innerHTML=`<div class="page-heading"><div><span class="eyebrow">${e(state.catalog.templates.find(t=>t.id===state.board.kind)?.name.toUpperCase()||'YOUR FILM')}</span><h1>${headings[state.step]}</h1><p class="muted">${e(state.board.title)}</p></div><span class="duration-pill" id="duration">~ ${seconds(state.estimate?.seconds||0)}</span></div><nav class="steps" aria-label="Film creation steps">${steps.map((s,i)=>`<button class="step${state.step===i?' active':''}" data-action="step" data-index="${i}"${activeJob()&&i!==4?' disabled':''} aria-current="${state.step===i?'step':'false'}"><span class="step-number">${i+1}</span>${s}</button>`).join('')}</nav>${activeJob()?'<p class="locked-note">Your film is rendering. Editing is paused until it finishes or you cancel.</p>':''}<div class="workspace"><section class="form-panel">${[purpose,look,story,sound,review][state.step]()}</section>${previewMarkup()}</div><footer class="actions"><button class="secondary" data-action="${state.step?'back':'library'}">← ${state.step?'Back':'Your films'}</button><span class="muted">Your work is saved as you go.</span>${state.step<4?'<button class="primary" data-action="next">Continue <span aria-hidden="true">→</span></button>':'<button class="secondary" data-action="save">Save changes</button>'}</footer>`;
  updatePreview();updateJob();
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

document.addEventListener('input',event=>{
  const target=event.target;
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
  try {
    const target=event.target;
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
    if(['music.source','voice.voice'].includes(target.dataset.field) || (target.dataset.lines!==undefined && state.board.voice.source==='files')) {await save();render();}
  } catch(error) {notify(error.message);}
});
document.addEventListener('dragover',event=>{if(event.target.closest('#dropzone')) {event.preventDefault();$('#dropzone').classList.add('dragover');}});
document.addEventListener('dragleave',event=>{if(event.target.closest('#dropzone')) $('#dropzone').classList.remove('dragover');});
document.addEventListener('drop',event=>{if(event.target.closest('#dropzone')) {event.preventDefault();addMedia(event.dataTransfer.files).catch(error=>notify(error.message));}});
document.addEventListener('click',async event=>{
  const target=event.target.closest('[data-action]');if(!target || target.disabled) return;
  const action=target.dataset.action;
  try {
    if(action==='new') {
      await save();$('#new-templates').innerHTML=state.catalog.templates.map((t,i)=>`<label class="template-card"><input type="radio" name="template" value="${t.id}"${i===0?' checked':''}><span class="template-symbol">${symbols[i]}</span><strong>${e(t.name)}</strong><small>${e(t.description)}</small></label>`).join('');$('#new-dialog').showModal();$('#new-title').focus();return;
    }
    if(action==='close-dialog') {$('#new-dialog').close();return;}
    if(action==='close-setup') {$('#setup-dialog').close();return;}
    if(action==='setup') {
      $('#setup-dialog').showModal();$('#setup-content').textContent='Checking installed video tools…';state.capabilities=await api('/capabilities');
      $('#setup-content').innerHTML=`<div class="setup-row"><span>Video production</span><strong>${state.capabilities.ready?'Ready':'Needs setup'}</strong></div>${state.capabilities.missing.length?`<p class="error">Missing or unusable: ${e(state.capabilities.missing.join(', '))}</p>`:''}<div class="setup-row"><span>Optional 3D showcase</span><strong>${state.capabilities.blender?'Blender installed':'Unavailable'}</strong></div><div class="setup-row"><span>Offline narration</span><span>Check a voice in Sound</span></div><p class="hint">The regular workflow uses local video tools and procedural music. Speech models are optional and are never downloaded while making a film.</p>`;return;
    }
    if(action==='open') {await openProject(target.dataset.id);return;}
    if(action==='library') {await save();clearInterval(state.poll);state.id=null;state.board=null;history.replaceState(null,'',location.pathname);await refreshLibrary();renderHome();return;}
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
    if(action==='format') {
      const dimensions={landscape:[1920,1080],vertical:[1080,1920],square:[1080,1080]}[target.dataset.id];
      state.board.format={width:dimensions[0],height:dimensions[1],fps:30};
      if(target.dataset.id!=='landscape') state.board.style.showcase3d=false;dirty();render();
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
    [state.catalog,state.capabilities]=await Promise.all([api('/catalog'),api('/capabilities')]);await refreshLibrary();
    const [id,step]=location.hash.slice(1).split('/');
    if(id) await openProject(id,Math.max(0,Math.min(4,Number(step)||0)));else renderHome();
    if(!state.capabilities.ready) notify(`Some video tools need setup: ${state.capabilities.missing.join(', ')}. You can still work on your storyboard.`);
  } catch(error) {notify(error.message);if(state.catalog) renderHome();else $('#app').innerHTML='<p class="muted">The studio could not connect. Reload the page after starting Showrig.</p>';}
}
start();
