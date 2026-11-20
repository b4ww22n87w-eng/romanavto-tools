// Сбор объявлений с Авто.ру. Запуск: node collect_autoru.js <url> <файл.json> <макс_страниц>
const { chromium } = require('playwright');
const fs = require('fs');
const [url, outFile, maxArg] = process.argv.slice(2);
const maxPages = parseInt(maxArg || '70', 10);
const CARD = '[data-seo="listing-item"]';
(async () => {
  const browser = await chromium.launch();
  const ctx = await browser.newContext({
    viewport: { width: 1366, height: 1800 }, locale: 'ru-RU', timezoneId: 'Europe/Moscow',
    userAgent: 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0 Safari/537.36',
  });
  await ctx.route('**/*', (r) => (['image', 'media', 'font'].includes(r.request().resourceType()) ? r.abort() : r.continue()));
  const page = await ctx.newPage();
  // Открывает страницу, соглашается с уведомлением о регионе и ждёт карточки объявлений.
  async function load(u) {
    try { await page.goto(u, { waitUntil: 'domcontentloaded', timeout: 45000 }); } catch (e) { return 0; }
    await page.waitForTimeout(2500);
    const consent = page.getByText('Я согласен', { exact: true });
    if (await consent.count().catch(() => 0)) await consent.first().click().catch(() => {});
    for (let i = 0; i < 10; i++) {
      const n = await page.evaluate((s) => document.querySelectorAll(s).length, CARD).catch(() => 0);
      if (n > 0) return n;
      await page.waitForTimeout(2000);
    }
    return 0;
  }
  const out = [];
  let emptyPages = 0;
  for (let n = 1; n <= maxPages; n++) {
    let cards = [];
    for (let attempt = 1; attempt <= 4; attempt++) {
      await load(url + (n > 1 ? '&page=' + n : ''));
      cards = await page.evaluate((s) => [...document.querySelectorAll(s)].map((c) => {
        const a = c.querySelector('a.ListingItemTitle__link, a[class*="ListingItemTitle"]');
        const p = c.querySelector('.MetroListPlace__regionName, [class*="MetroListPlace"]');
        return { title: a ? (a.innerText || '').trim() : '', href: a ? a.href.split('?')[0] : '', place: p ? (p.innerText || '').trim() : '', text: (c.innerText || '').trim() };
      }), CARD).catch(() => []);
      if (cards.length) break;
      console.log('autoru: страница', n, 'попытка', attempt, '— пусто, пауза');
      await page.waitForTimeout(12000 * attempt);
    }
    console.log('autoru: страница', n, 'объявлений', cards.length);
    if (!cards.length) { if (++emptyPages >= 2) break; continue; }
    emptyPages = 0;
    out.push(...cards);
    fs.writeFileSync(outFile, JSON.stringify(out));
    if (cards.length < 20) break;
    await page.waitForTimeout(3000 + Math.floor(Math.random() * 2500));
  }
  console.log('autoru: всего', out.length);
  await browser.close();
})().catch((e) => { console.log('autoru: остановлено —', String(e.message || e).slice(0, 120)); process.exit(0); });
