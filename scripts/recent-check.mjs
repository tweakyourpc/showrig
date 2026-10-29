// Read-only browser regression check. Recent history belongs to this isolated browser context.
import assert from 'node:assert/strict';
import {createRequire} from 'node:module';
import {execFileSync} from 'node:child_process';
import {mkdirSync} from 'node:fs';
import {join} from 'node:path';

const base=process.env.SHOWRIG_TEST_URL;
if(!base) throw new Error('Set SHOWRIG_TEST_URL to the Showrig instance to check. No film files are changed.');
const require=createRequire(import.meta.url);
const modulePath=process.env.SHOWRIG_PLAYWRIGHT || join(execFileSync('npm',['root','-g'],{encoding:'utf8'}).trim(),'playwright');
const {chromium}=require(modulePath);
const browser=await chromium.launch({headless:true});
const page=await browser.newPage({viewport:{width:1440,height:1000}});
const errors=[], writes=[];
const out=process.env.SHOWRIG_TEST_OUTPUT || '/tmp/showrig-recent-check';
mkdirSync(out,{recursive:true});
try {
  page.on('pageerror',error=>errors.push(error.message));
  await page.route('**/*',route=>{
    const request=route.request();
    if(!['GET','HEAD'].includes(request.method())) {writes.push(request.url());return route.abort();}
    return new URL(request.url()).origin===new URL(base).origin ? route.continue() : route.abort();
  });
  const initial=await (await page.request.get(base+'/api/projects')).json();
  const film=initial.find(item=>!item.archived);
  assert.ok(film,'At least one active film is needed for this read-only check.');
  await page.goto(`${base}/#${film.id}/0`);
  await page.locator('.steps').waitFor();
  await page.getByRole('button',{name:'Clear recent films',exact:true}).click();
  assert.equal(await page.locator('#library .library-item').count(),0);
  assert.equal(await page.evaluate(()=>localStorage.getItem('showrig.recent-films.v1')),'[]');
  await page.reload();
  await page.locator('.steps').waitFor();
  assert.equal(await page.locator('#library .library-item').count(),0,'Editor reload repopulated a cleared list');
  await page.locator('[data-nav="library"]').click();
  assert.ok(await page.locator(`.film-open[data-id="${film.id}"]`).isVisible(),'Film disappeared from the library');
  await page.locator(`.film-open[data-id="${film.id}"]`).click();
  await page.locator('.steps').waitFor();
  assert.equal(await page.locator('#library .library-item').count(),1);
  assert.equal(await page.locator('#library .library-item').first().getAttribute('data-id'),film.id);
  await page.getByRole('button',{name:'Clear recent films',exact:true}).click();
  await page.locator('[data-nav="library"]').click();
  await page.reload();
  await page.locator('.library-grid').waitFor();
  assert.equal(await page.locator('#library .library-item').count(),0,'Library reload repopulated a cleared list');
  assert.ok(await page.locator(`.film-open[data-id="${film.id}"]`).isVisible());
  await page.screenshot({path:join(out,'cleared-recents.png'),fullPage:true});
  const after=await (await page.request.get(base+'/api/projects')).json();
  assert.ok(initial.every(item=>after.some(p=>p.id===item.id)),'A film was removed');
  assert.deepEqual(writes,[],'History clearing wrote to the film API');
  assert.deepEqual(errors,[]);
  console.log('Clear Recent, persistence across editor/library reloads, explicit reopen, and preservation of films passed. No API writes.');
} finally {await browser.close();}
