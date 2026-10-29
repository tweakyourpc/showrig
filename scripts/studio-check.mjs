// Uses an explicitly selected QA library; synthetic films created here are cleaned up.
import {createRequire} from 'node:module';
import {execFileSync} from 'node:child_process';
import {mkdirSync} from 'node:fs';
import {join} from 'node:path';
import assert from 'node:assert/strict';

if (!process.env.SHOWRIG_TEST_URL) throw new Error('Set SHOWRIG_TEST_URL to an isolated test library, never your real films.');
const base = process.env.SHOWRIG_TEST_URL;
const require = createRequire(import.meta.url);
const playwright = process.env.SHOWRIG_PLAYWRIGHT || join(execFileSync('npm',['root','-g'],{encoding:'utf8'}).trim(),'playwright');
const {chromium} = require(playwright);
const out = process.env.SHOWRIG_TEST_OUTPUT || '/tmp/showrig-studio-check';
mkdirSync(out,{recursive:true});
const browser = await chromium.launch({headless:true});
const page = await browser.newPage({viewport:{width:1440,height:1000}});
const created = [], errors = [], outside = [];
async function api(path,method='GET',body) {
  const r = await page.request.fetch(base+'/api'+path,{method,headers:{'X-Showrig-Request':'1'},data:body});
  assert.ok(r.ok(),await r.text());
  return r.json();
}
async function screenshot(name) {
  await page.evaluate(()=>scrollTo(0,0));
  await page.screenshot({path:join(out,name+'.png'),fullPage:true});
}
try {
  page.on('pageerror',error=>errors.push(error.message));
  await page.route('**/*',route=>{
    if (new URL(route.request().url()).origin !== new URL(base).origin) {
      outside.push(route.request().url());return route.abort();
    }
    return route.continue();
  });
  await page.goto(base);
  await page.getByRole('heading',{name:'Make a film. Keep the edit.'}).waitFor();
  await screenshot('library');
  await page.locator('[data-nav="templates"]').click();
  assert.equal(await page.locator('.template-gallery .template-card').count(),14);
  await screenshot('templates');
  await page.getByRole('button',{name:'Teach',exact:true}).click();
  assert.equal(await page.locator('.template-gallery .template-card').count(),3);
  await page.getByRole('button',{name:'All',exact:true}).click();
  await page.locator('[data-template="social"]').click();
  assert.equal(await page.locator('input[name="template"]:checked').inputValue(),'social');
  await page.locator('#new-title').fill('QA history lifecycle');
  const creation = page.waitForResponse(r=>r.url().endsWith('/api/projects') && r.request().method()==='POST');
  await page.getByRole('button',{name:'Create film',exact:false}).click();
  const film = await (await creation).json();created.push(film.id);
  assert.equal(film.board.format.height,1920);
  await page.locator('.steps').waitFor();
  await page.getByRole('button',{name:'Clear recent films',exact:true}).click();
  assert.equal(await page.locator('#library .library-item').count(),0);
  assert.ok((await api('/projects')).some(p=>p.id===film.id),'Clear Recent removed a library film');
  await page.reload();
  await page.locator('.steps').waitFor();
  assert.equal(await page.locator('#library .library-item').count(),0,'Reload repopulated cleared history');
  await page.locator('[data-nav="library"]').click();
  await page.getByRole('searchbox',{name:'Search films'}).fill('QA history lifecycle');
  assert.equal(await page.locator('.film-card').count(),1);
  await page.locator('.film-card .film-open').click();
  await page.locator('.steps').waitFor();
  assert.equal(await page.locator('#library .library-item').count(),1,'Opening a film did not update Recent');
  await page.locator('[data-nav="library"]').click();
  await page.locator('.film-card').getByRole('button',{name:'Archive',exact:true}).click();
  await page.locator('.library-tabs [data-filter="archive"]').click();
  await page.locator('.film-card').filter({hasText:'QA history lifecycle'}).waitFor();
  await page.locator('.film-card').filter({hasText:'QA history lifecycle'}).getByRole('button',{name:'Move to Trash'}).click();
  await page.locator('.library-tabs [data-filter="trash"]').click();
  await screenshot('trash');
  await page.locator('.film-card').filter({hasText:'QA history lifecycle'}).getByRole('button',{name:'Restore',exact:true}).click();
  await page.locator('.library-tabs [data-filter="active"]').click();
  await page.getByRole('searchbox',{name:'Search films'}).fill('QA history lifecycle');
  await page.getByLabel('Select QA history lifecycle',{exact:true}).check();
  await page.getByRole('button',{name:'Move selected to Trash'}).click();
  await page.locator('.library-tabs [data-filter="trash"]').click();
  await page.locator('.film-card').filter({hasText:'QA history lifecycle'}).getByRole('button',{name:'Delete permanently',exact:true}).click();
  await page.getByRole('dialog').getByRole('button',{name:'Keep in Trash'}).click();
  assert.ok((await api('/trash')).some(p=>p.id===film.id));
  await page.locator('[data-nav="setup"]').click();
  await page.getByRole('heading',{name:'Ready on this computer.'}).waitFor();
  await page.getByLabel('Installation instructions').selectOption('win32');
  assert.ok(await page.locator('#app').innerText().then(t=>t.includes('winget')));
  await screenshot('setup-windows');
  await page.getByLabel('Installation instructions').selectOption('darwin');
  assert.ok(await page.locator('#app').innerText().then(t=>t.includes('brew install')));
  await screenshot('setup-macos');
  await page.setViewportSize({width:390,height:844});
  await screenshot('setup-mobile');
  assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth>innerWidth),false,'Setup overflows on mobile');
  await page.locator('[data-nav="templates"]').click();
  await screenshot('templates-mobile');
  assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth>innerWidth),false,'Templates overflow on mobile');
  await page.locator('[data-nav="library"]').click();
  await screenshot('library-mobile');
  assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth>innerWidth),false,'Library overflows on mobile');
  await page.reload();
  await page.locator('.library-grid').waitFor();
  const exported = await api('/projects','POST',{title:'QA browser export','template':'blank'});
  created.push(exported.id);
  const board = exported.board;
  board.format={width:480,height:270,fps:30};board.music.source='none';
  board.scenes[0].title='Keep the edit';board.scenes[0].tagline='An offline browser export verification.';
  await api(`/projects/${exported.id}`,'PUT',board);
  await page.setViewportSize({width:1440,height:1000});
  await page.goto(`${base}/#${exported.id}/4`);await page.reload();
  await page.getByRole('heading',{name:'Ready for the first showing?'}).waitFor();
  const rendering = page.waitForResponse(r=>r.url().endsWith(`/api/projects/${exported.id}/render`) && r.request().method()==='POST');
  await page.getByRole('button',{name:/^Export video/}).click();
  const job = await (await rendering).json();
  const deadline=Date.now()+180000;
  let status;
  do {
    status=await api(`/jobs/${job.id}`);
    if(!['starting','running','cancelling'].includes(status.status)) break;
    await page.waitForTimeout(600);
  } while(Date.now()<deadline);
  assert.equal(status.status,'succeeded',status.error);
  await page.getByRole('link',{name:'Download video',exact:true}).waitFor();
  await screenshot('export');
  const videoDownload=page.waitForEvent('download');
  await page.getByRole('link',{name:'Download video',exact:true}).click();
  const video=await videoDownload;await video.saveAs(join(out,'browser-export.mp4'));
  assert.equal(await video.failure(),null);
  const packageDownload=page.waitForEvent('download');
  await page.getByRole('link',{name:'Editable package + media (.zip)',exact:true}).click();
  const editable=await packageDownload;await editable.saveAs(join(out,'editable-package.zip'));
  assert.equal(await editable.failure(),null);
  assert.deepEqual(errors,[]);
  assert.deepEqual(outside,[],'The application requested a resource outside its local origin');
  console.log(`Studio navigation, templates, cleanup, platform setup, mobile, real browser MP4/ZIP downloads and offline-origin checks passed. Artifacts: ${out}`);
} catch (error) {
  await screenshot('failure').catch(()=>{});
  throw error;
} finally {
  for(const id of created) {
    await api('/library/actions','POST',{action:'trash',ids:[id]}).catch(()=>{});
    await api(`/trash/${id}`,'DELETE',{confirm:id}).catch(()=>{});
  }
  await browser.close();
}
