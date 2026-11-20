import json,re,collections,statistics as st
RAT=['отличная цена','хорошая цена','нормальная цена','высокая цена','без оценки']
# ---------- DROM
rows=[]; seen=set()
for x in json.load(open('drom_raw.json')):
    if x['href'] in seen: continue
    seen.add(x['href'])
    t=x['bull_title']; m=re.match(r'(.+),\s*(\d{4})$',t)
    name=m.group(1) if m else t; year=int(m.group(2)) if m else None
    desc=x.get('component_inline-bull-description','')
    km=re.search(r'([\d\s]+)\s*км',desc); km=int(re.sub(r'\D','',km.group(1))) if km else None
    vol=re.search(r'(\d\.\d)\s*л',desc); hp=re.search(r'\((\d+)\s*л\.с\.\)',desc)
    tr=next((k for k in ['АКПП','механика','вариатор','робот'] if k in desc),'')
    fuel=next((k for k in ['бензин','дизель','гибрид','электро'] if k in desc),'')
    drive=next((k for k in ['4WD','передний','задний'] if k in desc),'')
    price=int(re.sub(r'\D','',x['bull_price']) or 0)
    L=[l.strip() for l in x['text'].split('\n') if l.strip()]
    rating=next((r for r in RAT if r in L),'')
    std={x.get('bull_title'),x.get('bull_subtitle'),desc,x.get('bull_location'),x.get('bull_date'),'только на Дроме','от собственника',*RAT}
    extra=[l for l in L if l not in std and not re.fullmatch(r'[\d\s]+₽',l)]
    dealer=extra[0] if extra else ''
    slug='/'.join(x['href'].split('/')[-3:-1])
    if not price or not year: continue
    rows.append(dict(src='Дром',name=name,slug='d:'+slug,year=year,vol=vol.group(1) if vol else '',hp=int(hp.group(1)) if hp else None,fuel=fuel,tr=tr,drive=drive,km=km,price=price,rating=rating,owner='bull_label_owner' in x,private=not dealer,dealer=dealer,broken='bull_label_broken' in x,nodocs='bull_label_nodocs' in x,loc=x.get('bull_location',''),href=x['href']))
nd=len(rows)
# ---------- AUTO.RU
TR={'Механика':'механика','Автомат':'АКПП','Вариатор':'вариатор','Робот':'робот'}
DR={'Передний привод':'передний','Полный привод':'4WD','Задний привод':'задний'}
LADA={'Granta':'Гранта','Kalina':'Калина','Priora':'Приора','Vesta':'Веста','Largus':'Ларгус','XRAY':'Х-рей','Niva':'Нива'}
def clean(title):
    t=re.sub(r'\s+Рестайлинг.*$','',title)
    t=re.sub(r'\s+\([^)]*\)$','',t) if not t.startswith('Lada') else t
    t=re.sub(r'\s+[IVX]+$','',t).strip()
    t=re.sub(r'\s+\([^)]*\)$','',t).strip() if not re.search(r'\(4x4\)$',t) else t
    t=re.sub(r'\s+[IVX]+$','',t).strip()
    if t.startswith('Lada (ВАЗ)'):
        m=t.replace('Lada (ВАЗ)','').strip()
        for k,v in LADA.items(): m=re.sub(r'\b'+k+r'\b',v,m)
        t='Лада '+m
    return t
u={}
for x in json.load(open('autoru_raw.json')):
    if x['href'] and x['href'] not in u: u[x['href']]=x
OUT_TOWNS={'Кострома','Иваново','Рыбинск','Москва','Приволжск','Меленки','Коляново'}
na=0
for x in u.values():
    txt=x['text'].replace('\xa0',' ')
    L=[l.strip() for l in txt.split('\n') if l.strip()]
    place=x['place'].replace('\xa0',' ').strip() or (L[-1] if L else '')
    town=place.split(',')[0].strip()
    if town in OUT_TOWNS: continue
    eng=next((l for l in L if re.match(r'\d\.\d л',l)),'')
    m=re.match(r'(\d\.\d) л(?:, (\d+) л\.с\.)?(?:, (.+))?',eng)
    vol=m.group(1) if m else ''; hp=int(m.group(2)) if m and m.group(2) else None; fuel=(m.group(3) or '').lower() if m else ''
    tr=next((TR[l] for l in L if l in TR),''); drive=next((DR[l] for l in L if l in DR),'')
    year=next((int(l) for l in L if re.fullmatch(r'(19|20)\d{2}',l)),None)
    km=next((int(re.sub(r'\D','',l)) for l in L if re.fullmatch(r'[\d\s]+км',l)),None)
    price=next((int(re.sub(r'\D','',l)) for l in L if re.fullmatch(r'[\d\s]+₽',l)),None)
    if not price or not year: continue
    owner='От собственника' in L
    # seller
    tail=[l for l in L if l!=place]
    seller=''
    if 'Проверенный дилер' in tail:
        i=tail.index('Проверенный дилер'); j=i-1
        if j>=0 and re.fullmatch(r'\d\.\d',tail[j]): j-=1
        seller=tail[j] if j>=0 else ''; is_dealer=True
    else:
        j=len(tail)-1
        if j>=0 and re.fullmatch(r'\d\.\d',tail[j]): j-=1; rated=True
        else: rated=False
        seller=tail[j] if j>=0 else ''
        if re.fullmatch(r'[\d\s]+₽',seller) or seller in ('От собственника','Справедливая цена'): seller=''
        is_dealer = rated or bool(re.search(r'авто|auto|салон|ООО|ИП |маркет|парк|компани|центр|trade|cars|моторс|motors|выкуп|пробег',seller,re.I)) or (seller.isupper() and len(seller)>3)
        if seller=='Частное лицо' or owner: is_dealer=False
    slug='/'.join(x['href'].split('/')[6:8])
    rows.append(dict(src='Авто.ру',name=clean(x['title']),slug='a:'+slug,year=year,vol=vol,hp=hp,fuel=fuel,tr=tr,drive=drive,km=km,price=price,rating='справедливая цена' if 'Справедливая цена' in L else '',owner=owner,private=not is_dealer,dealer=seller if is_dealer else '',broken=False,nodocs=False,loc=town,href=x['href'])); na+=1
print('drom',nd,'autoru',na)
# ---------- dedup across sources: same year+km+price
key=lambda r:(r['year'],r['km'],r['price'])
byk=collections.defaultdict(list)
for r in rows:
    if r['km']: byk[key(r)].append(r)
dups=0
for k,l in byk.items():
    srcs={r['src'] for r in l}
    if len(srcs)>1:
        a=[r for r in l if r['src']=='Авто.ру'][0]
        for r in l:
            if r['src']=='Дром':
                r['dup']=True; a['also']=r['href']; a['drom_rating']=r['rating']; a['broken']=a['broken'] or r['broken']; a['nodocs']=a['nodocs'] or r['nodocs']; dups+=1
uniq=[r for r in rows if not r.get('dup')]
print('cross-site dups',dups,'unique',len(uniq))
# ---------- comps: same source+slug, year +-2, exclude self; need >=5
bys=collections.defaultdict(list)
for r in rows: bys[r['slug']].append(r)
for r in uniq:
    comps=[c['price'] for c in bys[r['slug']] if c is not r and abs(c['year']-r['year'])<=2]
    if len(comps)>=5:
        med=st.median(comps); r['comp_n']=len(comps); r['comp_med']=int(med); r['disc']=round(1-r['price']/med,3)
    else: r['comp_n']=len(comps); r['comp_med']=None; r['disc']=None
json.dump(uniq,open('all_rows.json','w'),ensure_ascii=False)
print('with comps',sum(1 for r in uniq if r['disc'] is not None))
print(collections.Counter(r['loc'] for r in uniq).most_common(12))
print('private',sum(r['private'] for r in uniq),'dealer',sum(not r['private'] for r in uniq))
print(collections.Counter(r['dealer'] for r in uniq if r['src']=='Авто.ру' and not r['private']).most_common(15))
print(collections.Counter(r['name'] for r in uniq).most_common(25))
