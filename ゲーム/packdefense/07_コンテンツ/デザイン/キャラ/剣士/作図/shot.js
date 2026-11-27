const { chromium } = require('playwright');
const fs = require('fs');
(async () => {
  const [svg, png, scale] = process.argv.slice(2);
  const src = fs.readFileSync(svg, 'utf8');
  const m = src.match(/width="(\d+)" height="(\d+)"/);
  const b = await chromium.launch();
  const p = await b.newPage({ deviceScaleFactor: Number(scale || 1), viewport: { width: +m[1], height: +m[2] } });
  await p.setContent(`<html><body style="margin:0">${src}</body></html>`);
  await p.locator('svg').first().screenshot({ path: png, timeout: 60000 });
  await b.close();
})();
