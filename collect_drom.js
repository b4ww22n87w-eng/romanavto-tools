const {chromium}=require('playwright');
const fs=require('fs');
(async()=>{
 const b=await chromium.launch();
 const ctx=await b.newContext({viewport:{width:1366,height:1200},locale:'ru-RU',timezoneId:'Europe/Moscow',userAgent:'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0 Safari/537.36'});
 await ctx.route('**/*',r=>{const t=r.request().resourceType(); if(t==='image'||t==='media'||t==='font') return r.abort(); return r.continue();});
 const p=await ctx.newPage();
 const out=[]; const maxPages=parseInt(process.argv[2]||'60');
 for(let n=1;n<=maxPages;n++){
   const url='https://yaroslavl.drom.ru/auto/do-750000/all/'+(n>1?('page'+n+'/'):'')+'?distance=50&unsold=1';
   let status=0;
   try{ const r=await p.goto(url,{waitUntil:'domcontentloaded',timeout:45000}); status=r?r.status():0; }catch(e){ console.log('err',n,e.message.slice(0,80)); }
   const cards=await p.evaluate(()=>[...document.querySelectorAll('[data-ftid="bulls-list_bull"]')].map(c=>{
     const o={}; c.querySelectorAll('[data-ftid]').forEach(e=>{const k=e.getAttribute('data-ftid'); const v=(e.innerText||'').trim(); if(!o[k]) o[k]=v; else o[k]+=' | '+v;});
     const a=c.querySelector('a[data-ftid="bull_title"]'); o.href=a?a.href:''; o.text=(c.innerText||'').trim(); return o;}));
   console.log('page',n,'status',status,'cards',cards.length);
   if(status===429||cards.length===0){ break; }
   cards.forEach(c=>{c.page=n; out.push(c);});
   fs.writeFileSync('drom_raw.json',JSON.stringify(out));
   if(cards.length<20) break;
   await p.waitForTimeout(2200+Math.floor(Math.random()*1500));
 }
 console.log('TOTAL',out.length);
 await b.close();
})();
