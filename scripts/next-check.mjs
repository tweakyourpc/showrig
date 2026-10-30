// Requires an isolated library. All created films and packs are explicitly synthetic QA fixtures.
import {createRequire} from 'node:module';
import {execFileSync} from 'node:child_process';
import {mkdirSync} from 'node:fs';
import {join} from 'node:path';
import assert from 'node:assert/strict';
const base=process.env.SHOWRIG_TEST_URL.replace(/\/+$/,'');
if(!base)throw new Error('Set SHOWRIG_TEST_URL to an isolated QA library.');
const {chromium}=createRequire(import.meta.url)(join(execFileSync('npm',['root','-g'],{encoding:'utf8'}).trim(),'playwright'));
const out=process.env.SHOWRIG_TEST_OUTPUT||'/tmp/showrig-next-check';mkdirSync(out,{recursive:true});
const browser=await chromium.launch({headless:true}),page=await browser.newPage({viewport:{width:1440,height:960}}),errors=[],outside=[],created=[];
page.on('pageerror',e=>errors.push(e.message));
await page.route('**/*',route=>{if(new URL(route.request().url()).origin!==new URL(base).origin){outside.push(route.request().url());return route.abort();}return route.continue();});
const api=async(path,method='GET',data)=>{const r=await page.request.fetch(base+'/api'+path,{method,headers:{'X-Showrig-Request':'1'},data});assert.ok(r.ok(),await r.text());return r.json();};
let packId='';
const shot=async name=>page.screenshot({path:join(out,name+'.png'),fullPage:true});
try{
 await page.goto(base);await page.locator('.library-grid').waitFor();
 await page.locator('[data-nav="production"]').click();await page.getByRole('heading',{name:'You choose who directs.'}).waitFor();await shot('workbench');
 await page.locator('[data-nav="extensions"]').click();await page.getByRole('heading',{name:'A studio with room to grow.'}).waitFor();
 const pack={schema:1,id:'qa-'+Date.now(),name:'Synthetic QA pack',author:'Showrig tests',license:'MIT',templates:[{id:'story',name:'QA Story',description:'Synthetic test template',prompts:['Introduce the idea','Show the evidence']}],themes:[{id:'moss',name:'QA Moss',accent:'#A3CEB7',background:'#182B28'}]};
 packId=pack.id;
 await page.locator('#pack-file').setInputFiles({name:'qa.json',mimeType:'application/json',buffer:Buffer.from(JSON.stringify(pack))});await page.getByText('Pack installed. Its templates and looks are ready to use.').waitFor();await shot('packs');
 await page.locator('[data-action="new"]').first().click();await page.locator('#new-title').fill('Synthetic UX verification');
 await page.locator(`input[name=template][value="pack.${pack.id}.story"]`).check();
 for(const input of await page.locator('input[name=sceneIndex]').all())await input.uncheck();await page.getByRole('button',{name:/Create film/}).click();await page.locator('#creation-error:not([hidden])').waitFor();assert.ok(await page.locator('#new-dialog').isVisible());
 for(const input of await page.locator('input[name=sceneIndex]').all())await input.check();
 const response=page.waitForResponse(r=>r.url().endsWith('/api/projects')&&r.request().method()==='POST'&&r.status()===201);
 await page.getByRole('button',{name:/Create film/}).click();const project=await (await response).json();created.push(project.id);
 await page.locator('#scene-heading').waitFor();await shot('workspace');
 await page.locator('[data-action="guided-review"]').first().click();await page.locator('.readiness-list').waitFor();assert.ok(await page.getByRole('button',{name:/Fix scene 2/}).isVisible());
 await page.getByRole('button',{name:/Fix scene 2/}).click();await page.locator('#scene-heading').fill('Evidence makes the story');
 await page.locator('[data-action="move-scene"][data-direction="-1"]').click();assert.match(await page.locator('.scene-guidance').innerText(),/Show the evidence/);
 assert.ok(await page.getByRole('button',{name:'Back to review'}).isVisible());
 await page.getByRole('button',{name:'Back to review'}).click();await page.getByText('Everything is ready to render.',{exact:true}).first().waitFor();await shot('review');
 await page.locator('[data-action="guided-scene"]').first().click();
 for(const width of [390,320]){await page.setViewportSize({width,height:844});assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth>innerWidth),false);await page.locator('#scene-picker').selectOption(project.board.scenes[0].id);assert.ok(await page.locator('#scene-heading').isVisible());await shot('mobile-'+width);}
 await page.setViewportSize({width:1440,height:960});
 const backdrop=await page.screenshot();await page.locator('#scene-image-input').setInputFiles({name:'synthetic-backdrop.png',mimeType:'image/png',buffer:backdrop});await page.getByText(/synthetic-backdrop[^<]*\.png/).waitFor();
 await page.getByRole('button',{name:'Film audio settings →'}).click();assert.equal(await page.locator('.guided-form select[data-field="voice.source"]').count(),0);assert.ok(await page.locator('#film-settings select[data-field="voice.source"]').isVisible());await page.getByRole('button',{name:'Done',exact:true}).click();
 await page.locator('[data-action="guided-settings"][data-tab="look"]').first().click();await page.locator(`[data-action="look"][data-id="pack.${pack.id}.moss"]`).click();await page.getByRole('button',{name:'Done',exact:true}).click();
 const saved=await api('/projects/'+project.id);assert.equal(saved.board.style.accent,'#A3CEB7');
 if(process.env.SHOWRIG_RENDER_TEST==='1'){
  saved.board.format={width:480,height:270,fps:30};saved.board.music.source='none';await api('/projects/'+project.id,'PUT',saved.board);
  const job=await api('/projects/'+project.id+'/render','POST',{mode:'final'});let status;
  const deadline=Date.now()+180000;do{status=await api('/jobs/'+job.id);if(!['starting','running','cancelling'].includes(status.status))break;await page.waitForTimeout(500);}while(Date.now()<deadline);
  assert.equal(status.status,'succeeded',status.error);const pkg=await page.request.get(base+'/api/projects/'+project.id+'/package');assert.equal(pkg.status(),200);const bytes=await pkg.body();assert.ok(bytes.length>500);
  const imported=await page.request.post(base+'/api/library/import',{headers:{'X-Showrig-Request':'1'},multipart:{file:{name:'qa-editable.zip',mimeType:'application/zip',buffer:bytes}}});assert.equal(imported.status(),201,await imported.text());created.push((await imported.json()).id);
 }
 assert.deepEqual(errors,[]);assert.deepEqual(outside,[]);console.log('Creation recovery, packs, guidance reorder, review return, audio scope, mobile reflow and offline-origin checks passed. '+out);
}catch(error){await shot('failure');throw error;}finally{
 for(const id of created){await api('/library/actions','POST',{action:'trash',ids:[id]});await api('/trash/'+id,'DELETE',{confirm:id});}
 if(packId)await api('/extensions/'+packId,'DELETE');
 const afterClean=await api('/catalog');
 const leftClean=await api('/projects');
 assert.ok(!afterClean.templates.some(t=>t.id.startsWith('pack.')),'QA pack uninstall left entries in the catalog.');
 assert.ok(!leftClean.some(f=>f.id.startsWith('qa-')||/synthetic/i.test(f.title)),'QA library still contains synthetic films.');
 await browser.close();
}
