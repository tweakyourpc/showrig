// Records the promo's app clips from locally running servers into ../media/*.mp4.
// Uses Showrig's capture technique: CDP screencast frames with their timestamps,
// re-timed to a constant frame rate. Run through record-apps.sh, which starts the servers.
//
//   node record-apps.mjs <scenario> --url URL --out FILE [--extension DIR] [--repo DIR --words FILE]
import {createRequire} from 'node:module';
import {execFileSync} from 'node:child_process';
import {createHash} from 'node:crypto';
import {existsSync, mkdirSync, mkdtempSync, readFileSync, rmSync, writeFileSync} from 'node:fs';
import {homedir, tmpdir} from 'node:os';
import {join} from 'node:path';

const require = createRequire(import.meta.url);
const playwright = process.env.SHOWRIG_PLAYWRIGHT || join(execFileSync('npm', ['root', '-g'], {encoding: 'utf8'}).trim(), 'playwright');
const {chromium} = require(playwright);
const sleep = ms => new Promise(r => setTimeout(r, ms));

const [scenarioName, ...rest] = process.argv.slice(2);
const opt = {};
for (let i = 0; i < rest.length; i += 2) opt[rest[i].replace(/^--/, '')] = rest[i + 1];
const WIDTH = 1920, HEIGHT = 1080, FPS = 30;

// act(hold) runs the scenario; hold(fn) runs fn off the clock, so a still screen while the script
// thinks is cut from the clip.
async function record(page, out, act) {
  const dir = mkdtempSync(join(tmpdir(), 'promo-frames-'));
  const cdp = await page.context().newCDPSession(page);
  const frames = [];
  let writing = Promise.resolve(), stopped = false, held = 0, holding = false, resumed = 0;
  cdp.on('Page.screencastFrame', ({data, metadata, sessionId}) => {
    cdp.send('Page.screencastFrameAck', {sessionId}).catch(() => {});
    if (stopped || holding || metadata.timestamp < resumed) return;
    const f = join(dir, `f${String(frames.length).padStart(6, '0')}.jpg`);
    frames.push({f, t: metadata.timestamp - held});
    writing = writing.then(() => writeFileSync(f, Buffer.from(data, 'base64')));
  });
  const hold = async fn => {
    const from = Date.now() / 1000;
    holding = true;
    try { return await fn(); } finally {
      resumed = Date.now() / 1000;
      held += resumed - from;
      holding = false;
    }
  };
  await cdp.send('Page.startScreencast', {format: 'jpeg', quality: 95, maxWidth: WIDTH, maxHeight: HEIGHT});
  const t0 = Date.now() / 1000;
  try {
    await act(hold);
    await sleep(500);
  } finally {
    stopped = true;
    await cdp.send('Page.stopScreencast');
    await writing;
  }
  const t1 = Date.now() / 1000 - held;
  if (!frames.length) throw Error('no frames captured');
  frames[0].t = Math.min(frames[0].t, t0);
  const list = frames.map((fr, i) => `file '${fr.f}'\nduration ${((frames[i + 1]?.t ?? t1) - fr.t).toFixed(6)}`);
  writeFileSync(join(dir, 'frames.ffconcat'), 'ffconcat version 1.0\n' + list.join('\n') + `\nfile '${frames.at(-1).f}'\n`);
  execFileSync('ffmpeg', ['-v', 'error', '-y', '-f', 'concat', '-safe', '0', '-i', join(dir, 'frames.ffconcat'),
    '-vf', `scale=${WIDTH}:${HEIGHT}:flags=lanczos,fps=${FPS},tpad=stop_mode=clone:stop_duration=1,format=yuv420p`,
    '-c:v', 'libx264', '-preset', 'slow', '-crf', '16', '-movflags', '+faststart', '-an', out]);
  rmSync(dir, {recursive: true, force: true});
  console.log(JSON.stringify({clip: out, frames: frames.length, seconds: +(t1 - t0).toFixed(1),
    capturedFps: +(frames.length / (t1 - t0)).toFixed(1)}));
}

// Frame-stepped recording for WebGL pages that render slowly without a GPU: the page runs on a
// virtual clock that advances exactly one frame per capture, so motion is smooth at any render speed.
const VIRTUAL_CLOCK = () => {
  let now = 0, queue = [];
  const epoch = Date.now();
  window.requestAnimationFrame = callback => { const id = Math.random(); queue.push([id, callback]); return id; };
  window.cancelAnimationFrame = id => { queue = queue.filter(([queued]) => queued !== id); };
  performance.now = () => now;
  Date.now = () => epoch + now;
  window.__virtualClock = {step(ms) {
    now += ms;
    const due = queue;
    queue = [];
    for (const [, callback] of due) callback(now);
    return due.length;
  }};
};

async function recordStepped(page, out, seconds, timeline) {
  const dir = mkdtempSync(join(tmpdir(), 'promo-steps-'));
  const total = Math.round(seconds * FPS);
  const events = [...timeline].sort((a, b) => a.at - b.at);
  for (let i = 0; i < total; i++) {
    while (events.length && events[0].at <= i / FPS) await events.shift().run();
    await page.evaluate(ms => window.__virtualClock.step(ms), 1000 / FPS);
    await page.screenshot({path: join(dir, `f${String(i).padStart(6, '0')}.jpg`), type: 'jpeg', quality: 95});
    if (i % FPS === 0) process.stdout.write(`\r  ${(i / FPS).toFixed(0)}s of ${seconds}s`);
  }
  process.stdout.write('\n');
  execFileSync('ffmpeg', ['-v', 'error', '-y', '-framerate', String(FPS), '-i', join(dir, 'f%06d.jpg'),
    '-vf', `scale=${WIDTH}:${HEIGHT}:flags=lanczos,tpad=stop_mode=clone:stop_duration=1,format=yuv420p`,
    '-c:v', 'libx264', '-preset', 'slow', '-crf', '16', '-movflags', '+faststart', '-an', out]);
  rmSync(dir, {recursive: true, force: true});
  console.log(JSON.stringify({clip: out, frames: total, seconds}));
}

async function browserPage(scale = 1) {
  const browser = await chromium.launch({headless: true});
  const context = await browser.newContext({viewport: {width: Math.round(WIDTH / scale), height: Math.round(HEIGHT / scale)},
    deviceScaleFactor: scale});
  return {browser, context, page: await context.newPage()};
}

// OpenStreetMap through Overpass: answer from ~/.cache/showrig-promo/osm, asking a public mirror only
// on a miss. The mirrors are often busy (504s, minute-long queries), and a cached city is the same city.
const OVERPASS = ['https://overpass.private.coffee/api/interpreter', 'https://overpass.kumi.systems/api/interpreter',
  'https://overpass-api.de/api/interpreter'];
async function cacheOverpass(page) {
  const dir = join(process.env.PROMO_CACHE || join(homedir(), '.cache', 'showrig-promo'), 'osm');
  mkdirSync(dir, {recursive: true});
  await page.route(/\/api\/interpreter/, async route => {
    const body = route.request().postData() || route.request().url();
    const file = join(dir, createHash('sha256').update(body).digest('hex').slice(0, 20) + '.json');
    for (const mirror of existsSync(file) ? [] : OVERPASS) {
      const res = await fetch(mirror, {method: 'POST', body, headers: {
        'Content-Type': route.request().headers()['content-type'] || 'application/x-www-form-urlencoded',
        'User-Agent': 'vertex-city/3.0 (+https://github.com/tweakyourpc/vertex-city)'}}).catch(() => null);
      if (res?.ok) { writeFileSync(file, Buffer.from(await res.arrayBuffer())); break; }
    }
    if (!existsSync(file)) return route.abort();
    await route.fulfill({status: 200, contentType: 'application/json', headers: {'Access-Control-Allow-Origin': '*'},
      body: readFileSync(file)});
  });
}

const at = (t, run) => ({at: t, run});
const set = (page, id, value) => page.evaluate(([id, value]) => {
  const el = document.getElementById(id);
  el.value = value;
  el.dispatchEvent(new Event('input', {bubbles: true}));
  el.dispatchEvent(new Event('change', {bubbles: true}));
}, [id, value]);

// Vertex City in Midtown at a given instant, recorded frame-stepped for `seconds` with timeline(page).
async function midtown(instant, seconds, timeline) {
  const {browser, page} = await browserPage(1);
  await cacheOverpass(page);
  await page.route(/\/src\/main\.js$/, async route => {  // let the recorder read the sky marks (read-only)
    const res = await route.fetch();
    const code = (await res.text()).replace('const skyMarks = new SkyMarks();',
      'const skyMarks = new SkyMarks();\nwindow.__vertexCity = {screen, skyMarks};');
    await route.fulfill({response: res, body: code});
  });
  await page.addInitScript(VIRTUAL_CLOCK);
  await page.goto(`${opt.url}#city=manhattan&x=316&y=326&z=0.7&a=-0.55&p=0&t=${instant}`, {waitUntil: 'load'});
  const step = () => page.evaluate(() => window.__virtualClock.step(1000 / 30));
  for (let i = 0; i < 600 && !(await page.evaluate(() => /ways/.test(document.getElementById('attrib').textContent))); i++) {
    await step();
    await sleep(200);
  }
  await set(page, 'lighting', 'live');
  await set(page, 'traffic-mode', '2');
  for (let i = 0; i < 90; i++) await step();
  for (let i = 0; i < 40 && !/READY/.test(await page.innerText('#radio')); i++) await sleep(500);
  await recordStepped(page, opt.out, seconds, timeline(page));
  await browser.close();
}

// The brightest catalogued star or planet in view, from the app's own sky marks: the cell where the
// sky renderer drew it, as a page position. midtown() exposes the marks to the page for this.
async function brightestStar(page) {
  const star = await page.evaluate(() => {
    const {screen, skyMarks: m} = window.__vertexCity, r = document.getElementById('c').getBoundingClientRect();
    let best = null;
    for (let i = 0; i < m.n; i++) {
      const o = m.obj[i], x = r.left + (m.x[i] + 0.5) * screen.cw, y = r.top + (m.y[i] + 0.5) * screen.ch;
      if (o.kind !== 'sun' && x > 380 && x < 1540 && y > 120 && y < 700 && (!best || o.mag < best.mag)) best = {x, y, name: o.name, mag: o.mag};
    }
    return best;
  });
  if (!star) throw Error('no catalogued star or planet in view');
  console.log(`  clicking ${star.name} (magnitude ${star.mag.toFixed(1)}) at ${Math.round(star.x)},${Math.round(star.y)}`);
  return [star.x, star.y];
}

async function signIn(page, url, name = 'Ann', pin = '1234') {
  await page.goto(url, {waitUntil: 'networkidle'});
  await page.fill('#gn-code', 'maple owl');
  await page.click('text=Continue');
  await page.click(`.gn-name >> text=${name}`);
  await page.fill('#gn-pin', pin);
  await page.click('text=Sign in');
  await page.waitForSelector('text=Start a table');
}

async function glide(page, px, seconds) {
  await page.evaluate(([px, ms]) => new Promise(done => {
    const el = document.scrollingElement, from = el.scrollTop, t0 = performance.now();
    const ease = t => t < .5 ? 4 * t * t * t : 1 - (-2 * t + 2) ** 3 / 2;
    const step = now => {
      const t = Math.min(1, (now - t0) / ms);
      el.scrollTop = from + px * ease(t);
      t < 1 ? requestAnimationFrame(step) : done();
    };
    requestAnimationFrame(step);
  }), [px, seconds * 1000]);
}

const scenarios = {
  // Two players at one table: Ann (recorded, via localhost) and Sam (off camera, via 127.0.0.1).
  async 'game-night'() {
    const {browser, page: ann} = await browserPage(1.25);
    const sam = await (await browser.newContext({viewport: {width: 1536, height: 864}})).newPage();
    const host = new URL(opt.url);
    const annUrl = `${host.protocol}//localhost:${host.port}/`, samHost = `127.0.0.1:${host.port}`;
    await ann.goto(annUrl, {waitUntil: 'networkidle'});
    await ann.fill('#gn-code', 'maple owl');
    await ann.click('text=Continue');
    await ann.click('.gn-name >> text=Ann');
    await ann.fill('#gn-pin', '1234');
    await ann.click('text=Sign in');
    await sam.goto(`http://${samHost}/`, {waitUntil: 'networkidle'});
    await sam.fill('#gn-code', 'maple owl');
    await sam.click('text=Continue');
    await sam.click("text=I'm new here");
    await sam.fill('#gn-newname', 'Sam');
    await sam.click('button:has-text("Join")');
    await ann.waitForSelector('text=Sam');
    await sleep(800);
    // Free spaces on the board, from column labels like "Column 4, 6 spaces free". Before move n the
    // mover's board must show n discs and their turn; after it, n + 1. Polling updates can lag, so
    // counting discs (not comparing with a before-click snapshot) keeps a stale board from passing.
    const FREE = `[...document.querySelectorAll('.f4-col')].reduce((sum, col) =>
      sum + Number((col.getAttribute('aria-label').match(/(\\d+) spaces? free/) || [0, 0])[1]), 0)`;
    const drop = async (player, column, n) => {
      await player.waitForFunction(`${FREE} === ${42 - n} && document.body.innerText.includes('Your turn.')`, null, {timeout: 15000});
      for (let attempt = 0; attempt < 4; attempt++) {
        await player.click(`.f4-col[data-c="${column}"]`);
        try {
          await player.waitForFunction(`${FREE} === ${41 - n}`, null, {timeout: 3000});
          break;
        } catch {
          if (attempt === 3) throw Error(`move ${n + 1} (column ${column + 1}) did not register`);
        }
      }
      await sleep(900);
    };
    await record(ann, opt.out, async () => {
      const started = Date.now();
      const mark = label => console.log(`  ${label} at ${((Date.now() - started) / 1000).toFixed(1)}s`);
      await sleep(1600);
      await ann.locator('button.gn-btn', {hasText: 'New table'}).nth(3).click();
      await sleep(1300);
      await ann.click('button:has-text("Create table")');
      mark('table created');
      await sleep(1500);
      const link = (await ann.inputValue('.gn-linkbox')).replace(/\/\/[^/]+/, `//${samHost}`);
      await sam.goto(link, {waitUntil: 'networkidle'});
      await sam.click('button:has-text("Take a seat")');
      await sam.click('button:has-text("I\'m ready")');
      await sleep(1400);
      await ann.click('button:has-text("I\'m ready")');
      await ann.waitForSelector('button:has-text("Start game"):enabled', {timeout: 15000});
      await sleep(500);
      await ann.click('button:has-text("Start game")');
      mark('game started');
      await sleep(1200);
      const moves = [[ann, 3], [sam, 3], [ann, 2], [sam, 2], [ann, 4], [sam, 6], [ann, 5]];  // Ann wins along the bottom
      for (const [n, [player, column]] of moves.entries()) await drop(player, column, n);
      await ann.waitForSelector('text=/wins|won|winner/i', {timeout: 15000}).catch(() => {});
      mark('game over');
      await sleep(2600);
    });
    await browser.close();
  },

  // Ann against the computer at Wordwright, with the real word list. Ann's words come from the game's
  // own move search run on her rack (blanks left out, so no letter prompt); she places them by tapping.
  async wordwright() {
    const {loadServer} = require(join(opt.repo, 'test', 'support', 'load.js'));
    const GN = loadServer();
    const words = new Set(readFileSync(opt.words, 'utf8').toUpperCase().split(/\r?\n/).filter(Boolean));
    const byLength = {};
    for (const w of words) (byLength[w.length] ||= []).push(w);
    // The bot's search is bounded, so give each word length its own search and keep the best score.
    const best = (board, rack, bag) => {
      let top = null;
      for (let n = 8; n >= 2; n--) {
        const dict = {has: w => words.has(w), forEach: f => (byLength[n] || []).forEach(f)};
        const move = GN.bots.wordwright.choose({board, racks: {ann: rack}, bag: new Array(bag)}, 'ann', {services: {dict: () => dict}});
        if (move.type !== 'play') continue;
        const score = GN.wordwright.evaluateMove(board, rack, move.placements, words).score;
        if (!top || score > top.score) top = {score, placements: move.placements};
      }
      return top;
    };
    const {browser, page} = await browserPage(1);
    // Game Night race (ui.js reconcile): the board update for Ann's own play can land before the play
    // response clears her draft, which shows a stray "board changed" toast. Hidden here, not fixed.
    await page.addInitScript(() => new MutationObserver(() => {
      for (const el of document.querySelectorAll('body *')) {
        if (!el.children.length && el.textContent.startsWith('The board changed, so your tiles')) el.style.display = 'none';
      }
    }).observe(document, {childList: true, subtree: true}));
    await signIn(page, opt.url);
    const view = () => page.evaluate(() => {
      const m = GNC.app.match;
      return {rev: m.rev, mine: document.body.innerText.includes('Your turn'), board: m.view.board, rack: m.view.myRack,
              bag: m.view.bagCount, status: m.view.status};
    });
    const turn = async hold => {
      const v = await view();
      const move = await hold(async () => best(v.board, v.rack.filter(l => l !== '?'), v.bag));
      if (!move) throw Error('Ann has no word to play: ' + JSON.stringify(v.rack));
      for (const {r, c, l} of move.placements) {
        const tiles = page.locator('.ww-rack .ww-rtile');  // the rack on screen drops placed tiles and keeps its own order
        await tiles.nth((await tiles.allInnerTexts()).findIndex(t => t.trim()[0] === l)).click();
        await sleep(260);
        await page.click(`.ww-cell[data-r="${r}"][data-c="${c}"]`);
        await sleep(420);
      }
      await sleep(700);
      await page.locator('.gn-btn.gn-go:enabled').waitFor({timeout: 6000}).catch(async () => {  // enabled once the word checks out
        throw Error(`the game refused ${JSON.stringify(move.placements)}: ${await page.locator('.ww-status').allInnerTexts()}`);
      });
      await page.click('.gn-btn.gn-go');
      return v.rev;
    };
    await record(page, opt.out, async hold => {
      const started = Date.now();
      const mark = label => console.log(`  ${label} at ${((Date.now() - started) / 1000).toFixed(1)}s`);
      await sleep(1400);
      await page.click('button:has-text("Play vs Computer")');
      await page.waitForSelector('.ww-board');
      await page.evaluate(() => window.scrollTo({top: 66}));
      mark('game open');
      for (let n = 0; n < 4; n++) {
        await page.waitForFunction(() => document.body.innerText.includes('Your turn'), null, {timeout: 20000});
        await sleep(n ? 300 : 1400);
        const rev = await turn(hold);
        mark(`Ann played move ${n + 1}`);
        await page.waitForFunction(r => GNC.app.match.rev >= r + 2, rev, {timeout: 20000});
        mark('computer replied');
        // Placing tiles while a board update is still arriving sends them back to the rack, so wait for quiet.
        const revision = () => page.evaluate(() => GNC.app.match.rev);
        let seen;
        do { seen = await revision(); await sleep(1200); } while (seen !== await revision());
      }
      await sleep(2500);
    });
    await browser.close();
  },

  // A throwaway workspace built from TextStrata's own seed docs: browse, search, open, follow a link.
  async textstrata() {
    const {browser, page} = await browserPage(1.25);
    await page.goto(opt.url, {waitUntil: 'networkidle'});
    await record(page, opt.out, async () => {
      await sleep(1500);
      await glide(page, 420, 2.2);
      await sleep(600);
      await page.click('#query');
      await page.keyboard.type('deterministic', {delay: 90});
      await sleep(400);
      await page.keyboard.press('Enter');
      await page.waitForLoadState('networkidle');
      await sleep(1800);
      await page.click('text=Deterministic acquisition >> nth=0');
      await page.waitForLoadState('networkidle');
      await sleep(2400);
      await page.locator('a', {hasText: 'Wiki links, aliases, and safe renames'}).last().click();
      await page.waitForLoadState('networkidle');
      await sleep(2600);
    });
    await browser.close();
  },

  // The offline procedural city on a virtual clock: rise, fly forward, and change the visual style
  // every few seconds. Rendering is software WebGL here, so this takes a few minutes to record.
  async 'vertex-city'() {
    const {browser, page} = await browserPage(1);
    await page.addInitScript(VIRTUAL_CLOCK);
    await page.goto(opt.url, {waitUntil: 'networkidle'});
    const set = (id, value) => page.evaluate(([id, value]) => {
      const el = document.getElementById(id);
      el.value = value;
      el.dispatchEvent(new Event('input', {bubbles: true}));
      el.dispatchEvent(new Event('change', {bubbles: true}));
    }, [id, value]);
    await set('lighting', 'golden');
    for (let i = 0; i < 90; i++) await page.evaluate(() => window.__virtualClock.step(1000 / 30));
    await page.mouse.move(WIDTH / 2, HEIGHT / 2);
    const key = (at, action, name) => ({at, run: () => page.keyboard[action](name)});
    const look = (at, appearance, lighting) => ({at, run: async () => { await set('lighting', lighting); await set('appearance', appearance); }});
    await recordStepped(page, opt.out, 15, [
      key(0.3, 'down', 'e'), key(4.2, 'up', 'e'), key(1.6, 'down', 'w'),
      look(4.5, 'wireframe', 'night'),
      look(8, 'ascii', 'day'),
      look(11.5, 'cinematic', 'golden'),
      key(14.6, 'up', 'w'),
    ]);
    await browser.close();
  },

  // Real Midtown Manhattan from OpenStreetMap at 42nd Street and Fifth Avenue, on a virtual clock.
  // vertex-city-live: local radio, then a time-lapse from late afternoon into night.
  // vertex-city-stars: the same corner after dark; up over the roofs, look up, and name a star.
  // Overpass answers come from a local cache (filled once from a public mirror), so every run is the
  // same city; radio stations come live from Radio Browser.
  async 'vertex-city-live'() { await midtown(Date.UTC(2026, 9, 25, 21, 10), 15, page => [  // 17:10 EDT
    at(2.4, () => page.click('#open-layers')),
    at(3.4, () => page.click('#radio-next')),
    at(6.2, () => page.click('#close-panel')),
    at(6.8, () => page.click('#open-view')),
    at(7.4, () => set(page, 'warp', '80')),
    at(8.6, () => page.click('#close-panel')),
  ]); },
  async 'vertex-city-stars'() { await midtown(Date.UTC(2026, 9, 26, 0, 5), 11, page => [  // 20:05 EDT
    at(0.8, () => page.keyboard.down('e')),
    at(4.2, () => page.keyboard.up('e')),
    ...Array.from({length: 37}, (_, i) => at(4.5 + i / 30, async () => {  // dragging down tilts the view up
      if (i === 0) { await page.mouse.move(960, 400); await page.mouse.down(); }
      await page.mouse.move(960, 400 + 300 * i / 36);
      if (i === 36) await page.mouse.up();
    })),
    at(6.4, async () => { const [x, y] = await brightestStar(page); await page.mouse.click(x, y); }),
  ]); },

  // The real unpacked extension, annotating a chat thread as messages arrive.
  async 'temporal-lens'() {
    const profile = mkdtempSync(join(tmpdir(), 'promo-temporal-lens-'));
    const context = await chromium.launchPersistentContext(profile, {
      channel: 'chromium', headless: true, viewport: {width: 960, height: 540}, deviceScaleFactor: 2, colorScheme: 'dark',
      args: [`--disable-extensions-except=${opt.extension}`, `--load-extension=${opt.extension}`]});
    const page = context.pages()[0] || await context.newPage();
    await page.goto(`${opt.url}?manual=1`, {waitUntil: 'networkidle'});
    await sleep(1500);
    await record(page, opt.out, async () => {
      await sleep(600);
      await page.evaluate(() => window.playThread(1500));
      await sleep(10000);
    });
    await context.close();
    rmSync(profile, {recursive: true, force: true});
  },
};

if (!scenarios[scenarioName] || !opt.url || !opt.out) {
  console.error(`usage: node record-apps.mjs <${Object.keys(scenarios).join('|')}> --url URL --out FILE [--extension DIR]`);
  process.exit(2);
}
await scenarios[scenarioName]();
