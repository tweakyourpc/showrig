// Scripted browser capture: headless Chromium on the GPU, CDP screencast frames with their
// timestamps, re-timed to a constant frame rate and encoded with the codec Showrig picked.
// node capture.mjs <job.json>
//   job: {url, out, width, height, fps, scale, actions, playwright, codec: [...ffmpeg args]}
import {createRequire} from 'node:module';
import {mkdirSync, writeFileSync, rmSync, readFileSync} from 'node:fs';
import {join} from 'node:path';
import {execFileSync} from 'node:child_process';

const job = JSON.parse(readFileSync(process.argv[2], 'utf8'));
const {chromium} = createRequire(import.meta.url)(job.playwright);
const sleep = ms => new Promise(r => setTimeout(r, ms));

const GPU_ARGS = ['--enable-gpu', '--ignore-gpu-blocklist', '--use-angle=vulkan',
  '--enable-features=Vulkan,VulkanFromANGLE,DefaultANGLEVulkan', '--disable-vulkan-surface',
  '--enable-gpu-rasterization', '--enable-zero-copy', '--disable-background-timer-throttling',
  '--disable-renderer-backgrounding', '--autoplay-policy=no-user-gesture-required', '--hide-scrollbars'];

// Eased scroll driven by requestAnimationFrame, so every captured frame moves smoothly.
async function glide(page, px, secs) {
  await page.evaluate(([px, ms]) => new Promise(done => {
    const el = document.scrollingElement, from = el.scrollTop, t0 = performance.now();
    const ease = t => t < 0.5 ? 4 * t * t * t : 1 - (-2 * t + 2) ** 3 / 2;
    const step = now => {
      const t = Math.min(1, (now - t0) / ms);
      el.scrollTop = from + px * ease(t);
      t < 1 ? requestAnimationFrame(step) : done();
    };
    requestAnimationFrame(step);
  }), [px, secs * 1000]);
}

async function act(page, line) {
  const [verb, ...rest] = line.trim().split(/\s+/);
  const arg = rest.join(' ');
  switch (verb) {
    case 'wait': return sleep(parseFloat(arg || '1') * 1000);
    case 'scroll': return glide(page, parseFloat(rest[0] || '800'), parseFloat(rest[1] || '3'));
    case 'type': {
      const [sel, ...words] = rest;
      await page.click(sel);
      return page.keyboard.type(words.join(' '), {delay: 85});
    }
    case 'click': return page.click(arg);
    case 'press': return page.keyboard.press(arg);
    case 'goto': return page.goto(arg, {waitUntil: 'networkidle'});
    default: throw Error(`unknown action: ${line}`);
  }
}

const scale = job.scale || 1;
const browser = await chromium.launch({headless: true, args: GPU_ARGS});
const page = await (await browser.newContext({
  viewport: {width: Math.round(job.width / scale), height: Math.round(job.height / scale)},
  deviceScaleFactor: scale, colorScheme: 'dark'})).newPage();
if (job.offline) {
  await page.context().route('**/*', route => {
    const protocol = new URL(route.request().url()).protocol;
    return ['file:', 'data:', 'blob:', 'about:'].includes(protocol) ? route.continue() : route.abort();
  });
  if (page.context().routeWebSocket) await page.context().routeWebSocket('**/*', ws => ws.close());
}
await page.goto(job.url, {waitUntil: 'networkidle'});
await sleep(600);

const dir = job.out.replace(/\.mp4$/, '.frames');
rmSync(dir, {recursive: true, force: true});
mkdirSync(dir, {recursive: true});
const cdp = await page.context().newCDPSession(page);
const frames = [];
let writing = Promise.resolve();
cdp.on('Page.screencastFrame', ({data, metadata, sessionId}) => {
  const f = join(dir, `f${String(frames.length).padStart(6, '0')}.jpg`);
  frames.push({f, t: metadata.timestamp});
  writing = writing.then(() => writeFileSync(f, Buffer.from(data, 'base64')));
  cdp.send('Page.screencastFrameAck', {sessionId}).catch(() => {});
});
await cdp.send('Page.startScreencast', {format: 'jpeg', quality: 92, maxWidth: job.width, maxHeight: job.height});
const t0 = Date.now() / 1000;
try {
  for (const a of job.actions) await act(page, a);
  await sleep(400);
} finally {
  await cdp.send('Page.stopScreencast');
  await writing;
}
const t1 = Date.now() / 1000;
await browser.close();
if (!frames.length) throw Error('no frames captured');
frames[0].t = Math.min(frames[0].t, t0);
const list = frames.map((fr, i) => `file '${fr.f}'\nduration ${((frames[i + 1]?.t ?? t1) - fr.t).toFixed(6)}`);
writeFileSync(join(dir, 'frames.ffconcat'), 'ffconcat version 1.0\n' + list.join('\n') + `\nfile '${frames.at(-1).f}'\n`);
execFileSync('ffmpeg', ['-v', 'error', '-y', '-f', 'concat', '-safe', '0', '-i', join(dir, 'frames.ffconcat'),
  '-vf', `scale=${job.width}:${job.height}:flags=lanczos,fps=${job.fps},tpad=stop_mode=clone:stop_duration=${job.hold || 0},format=yuv420p`, ...job.codec,
  '-movflags', '+faststart', job.out]);
rmSync(dir, {recursive: true, force: true});
console.log(JSON.stringify({frames: frames.length, seconds: +(t1 - t0).toFixed(2),
  capturedFps: +(frames.length / (t1 - t0)).toFixed(1)}));
