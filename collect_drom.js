// Сбор объявлений с Дрома. Запуск: node collect_drom.js <url> <файл.json> <макс_страниц>
const { chromium } = require('playwright');
const fs = require('fs');
const [url, outFile, maxArg] = process.argv.slice(2);
const maxPages = parseInt(maxArg || '70', 10);
const pageUrl = (n) => {
  if (n === 1) return url;
  const [path, query] = url.split('?');
  return path.replace(/\/?$/, '/') + 'page' + n + '/' + (query ? '?' + query : '');
};
(async () => {
  const browser = await chromium.launch();
  const ctx = await browser.newContext({
    viewport: { width: 1366, height: 1200 }, locale: 'ru-RU', timezoneId: 'Europe/Moscow',
    userAgent: 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0 Safari/537.36',
  });
  await ctx.route('**/*', (r) => (['image', 'media', 'font'].includes(r.request().resourceType()) ? r.abort() : r.continue()));
  const page = await ctx.newPage();
  const out = [];
  for (let n = 1; n <= maxPages; n++) {
    let cards = [], status = 0;
    for (let attempt = 1; attempt <= 3; attempt++) {
      try { const r = await page.goto(pageUrl(n), { waitUntil: 'domcontentloaded', timeout: 45000 }); status = r ? r.status() : 0; }
      catch (e) { status = 0; }
      if (status === 429) { console.log('drom: страница', n, '— сайт просит подождать, пауза'); await page.waitForTimeout(60000 * attempt); continue; }
      cards = await page.evaluate(() => [...document.querySelectorAll('[data-ftid="bulls-list_bull"]')].map((c) => {
        const o = {};
        c.querySelectorAll('[data-ftid]').forEach((e) => { const k = e.getAttribute('data-ftid'); const v = (e.innerText || '').trim(); o[k] = o[k] ? o[k] + ' | ' + v : v; });
        const a = c.querySelector('a[data-ftid="bull_title"]');
        o.href = a ? a.href : ''; o.text = (c.innerText || '').trim();
        return o;
      })).catch(() => []);
      break;
    }
    console.log('drom: страница', n, 'объявлений', cards.length);
    if (!cards.length) break;
    out.push(...cards);
    fs.writeFileSync(outFile, JSON.stringify(out));
    await page.waitForTimeout(2200 + Math.floor(Math.random() * 1500));
  }
  console.log('drom: всего', out.length);
  await browser.close();
})();
