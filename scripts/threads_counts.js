// Reads exact follower counts from public Threads profiles (www.threads.com/@handle).
// Usage: node scripts/threads_counts.js handle1 handle2 ...  -> prints JSON {handle: count|null}
// Threads renders profile data client-side, so this uses the pre-installed headless Chromium.
const { chromium } = require('playwright');

function countFor(html, handle) {
  // Take the follower_count that belongs to this username (pages also embed other profiles).
  const re = /"follower_count":\s*(\d+)/g;
  const uname = `"username":"${handle.toLowerCase()}"`;
  let m;
  while ((m = re.exec(html))) {
    const win = html.slice(Math.max(0, m.index - 4000), m.index + 4000).toLowerCase();
    if (win.includes(uname)) return Number(m[1]);
  }
  return null;
}

(async () => {
  const handles = process.argv.slice(2).map(h => h.replace(/^@/, ''));
  const b = await chromium.launch({ proxy: process.env.HTTPS_PROXY ? { server: process.env.HTTPS_PROXY } : undefined });
  const out = {};
  for (const h of handles) {
    let n = null;
    for (let attempt = 0; attempt < 2 && n === null; attempt++) {
      const p = await b.newPage({ ignoreHTTPSErrors: true, locale: 'en-US' });
      try {
        await p.goto('https://www.threads.com/@' + h, { waitUntil: 'networkidle', timeout: 45000 }).catch(() => {});
        await p.waitForTimeout(2000);
        n = countFor(await p.content(), h);
      } finally { await p.close(); }
    }
    out[h] = n;
    await new Promise(r => setTimeout(r, 1500));  // be gentle
  }
  await b.close();
  console.log(JSON.stringify(out));
})();
