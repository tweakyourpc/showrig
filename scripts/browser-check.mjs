// Runs against an already-started Showrig QA library. All traffic stays on its origin.
import {createRequire} from 'node:module';
import {execFileSync} from 'node:child_process';
import {mkdirSync} from 'node:fs';
import {join} from 'node:path';
import assert from 'node:assert/strict';

const require = createRequire(import.meta.url);
const playwright = process.env.SHOWRIG_PLAYWRIGHT || join(execFileSync('npm', ['root', '-g'], {encoding:'utf8'}).trim(), 'playwright');
const {chromium} = require(playwright);
if (!process.env.SHOWRIG_TEST_URL) throw new Error('Set SHOWRIG_TEST_URL to an isolated QA library, not your real films.');
const base = process.env.SHOWRIG_TEST_URL;
const out = process.env.SHOWRIG_TEST_OUTPUT || '/tmp/showrig-browser-check';
mkdirSync(out, {recursive:true});
const browser = await chromium.launch({headless:true});
const page = await browser.newPage({viewport:{width:1440,height:1000}});
try {
  const errors=[];
  page.on('pageerror', error=>errors.push(error.message));
  await page.route('**/*', route => new URL(route.request().url()).origin === new URL(base).origin ? route.continue() : route.abort());
  await page.goto(base);
  await page.locator('.welcome, .library-grid').first().waitFor();
  await page.getByRole('button', {name:'New film', exact:true}).click();
  await page.getByLabel('Film title', {exact:true}).fill('Browser verification');
  await page.getByRole('button', {name:'Create film'}).click();
  await page.getByRole('button', {name:'Continue'}).click();
  await page.getByRole('button', {name:'Cinematic', exact:false}).first().click();
  await page.screenshot({path:join(out,'look.png'),fullPage:true});
  await page.getByRole('button', {name:'Continue'}).click();
  await page.getByLabel('Heading', {exact:true}).fill('A small film, made here.');
  await page.getByLabel('On-screen text').fill('An offline browser workflow, from your words to a real video.');
  await page.getByRole('button', {name:'Add scene',exact:true}).click();
  await page.getByLabel('Heading',{exact:true}).fill('A useful detail');
  await page.getByRole('button',{name:'Duplicate',exact:true}).click();
  await page.getByRole('button',{name:'Move scene earlier'}).click();
  await page.getByRole('button',{name:'Remove',exact:true}).click();
  await page.screenshot({path:join(out,'story.png'),fullPage:true});
  await page.setViewportSize({width:390,height:844});
  await page.screenshot({path:join(out,'mobile.png'),fullPage:true});
  assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth>innerWidth),false,'Mobile layout overflows');
  await page.getByRole('button',{name:'Continue'}).click();
  await page.getByRole('combobox',{name:/^Music\b/}).selectOption('none');
  await page.getByRole('button',{name:'Continue'}).click();
  await page.getByRole('button',{name:'Save changes',exact:true}).click();
  await page.reload();
  await page.getByRole('heading',{name:'Ready for the first showing?'}).waitFor();
  assert.deepEqual(errors,[]);
  console.log(`Browser workflow passed. Screenshots: ${out}`);
} catch (error) {
  await page.screenshot({path:join(out,'failure.png'),fullPage:true}).catch(()=>{});
  throw error;
} finally { await browser.close(); }
