const {chromium}=require('playwright');
const fs=require('fs');
(async()=>{
 const b=await chromium.launch();
 const ctx=await b.newContext({viewport:{width:1366,height:1800},locale:'ru-RU',timezoneId:'Europe/Moscow',userAgent:'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0 Safari/537.36'});
 await ctx.route('**/*',r=>{const t=r.request().resourceType(); if(t==='image'||t==='media'||t==='font') return r.abort(); return r.continue();});
 const p=await ctx.newPage();
 const base='https://auto.ru/yaroslavl/cars/used/?price_to=750000&geo_radius=50&sort=cr_date-desc';
 const maxPages=parseInt(process.argv[2]||'2'); const out=[];
 async function load(url){
   try{ await p.goto(url,{waitUntil:'domcontentloaded',timeout:45000}); }catch(e){ console.log('ERR',e.message.slice(0,80)); }
   await p.waitForTimeout(2500);
   const btn=p.getByText('Я согласен',{exact:true});
   if(await btn.count()){ await btn.first().click().catch(()=>{}); }
   for(let i=0;i<10;i++){ const n=await p.evaluate(()=>document.querySelectorAll('[data-seo="listing-item"]').length).catch(()=>0); if(n>0) return n; await p.waitForTimeout(2000); }
   return 0;
 }
 let fails=0;
 for(let n=1;n<=maxPages;n++){
   let cards=[];
   for(let attempt=1;attempt<=5;attempt++){
     await load(base+(n>1?'&page='+n:''));
     cards=await p.evaluate(()=>[...document.querySelectorAll('[data-seo="listing-item"]')].map(c=>{
       const a=c.querySelector('a.ListingItemTitle__link, a[class*="ListingItemTitle"]');
       const q=s=>{const e=c.querySelector(s); return e?(e.innerText||'').trim():'';};
       return {title:a?(a.innerText||'').trim():'', href:a?a.href.split('?')[0]:'', cond:q('[class*="ListingItemUniversalCondition"]'), place:q('.MetroListPlace__regionName, [class*="MetroListPlace"]'), text:(c.innerText||'').trim()};
     })).catch(()=>[]);
     if(cards.length) break;
     const t=(await p.evaluate(()=>document.body.innerText).catch(()=>'')).slice(0,80).replace(/\s+/g,' ');
     console.log('page',n,'attempt',attempt,'empty:',t);
     if(/Ничего не найдено|нет объявлений/i.test(t)) break;
     await p.waitForTimeout(12000*attempt);
   }
   console.log('page',n,'cards',cards.length);
   if(!cards.length){ fails++; if(fails>=2) break; continue; }
   fails=0;
   cards.forEach(c=>{c.page=n; out.push(c);});
   fs.writeFileSync('autoru_raw.json',JSON.stringify(out));
   if(cards.length<20) break;
   await p.waitForTimeout(3000+Math.floor(Math.random()*2500));
 }
 console.log('TOTAL',out.length);
 await b.close();
})();
