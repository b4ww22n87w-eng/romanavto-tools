import json, collections, statistics as st
from openpyxl import Workbook
from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
from openpyxl.utils import get_column_letter
u=[r for r in json.load(open('all_rows.json')) if 'Япония' not in r['loc']]
# fuzzy cross-site dedup: same year+price, km within 3000
g=collections.defaultdict(list)
for r in u: g[(r['year'],r['price'])].append(r)
drop=set()
for l in g.values():
    A=[r for r in l if r['src']=='Авто.ру']; D=[r for r in l if r['src']=='Дром']
    for d in D:
        for a in A:
            if a['km'] and d['km'] and abs(a['km']-d['km'])<=3000 and id(d) not in drop:
                drop.add(id(d)); a.setdefault('also',d['href']); a['drom_rating']=a.get('drom_rating') or d['rating']; a['broken']=a['broken'] or d['broken']; a['nodocs']=a['nodocs'] or d['nodocs']
u=[r for r in u if id(r) not in drop]
byn=collections.defaultdict(list)
for r in u: byn[r['name']].append(r)
for r in u:
    comps=[c['price'] for c in byn[r['name']] if c is not r and abs(c['year']-r['year'])<=2]
    r['comp_n']=len(comps); r['comp_med']=int(st.median(comps)) if len(comps)>=5 else None
    r['disc']=round(1-r['price']/r['comp_med'],3) if r['comp_med'] else None
    r['dr']=r.get('drom_rating') or (r['rating'] if r['src']=='Дром' else '')
def good(r):
    base=(r['year']>=2007 and r['km'] and r['km']<=250000 and not r['broken'] and not r['nodocs'] and r['price']>=100000)
    return base and ((r['disc'] is not None and r['disc']>=0.12) or r['dr'] in ('отличная цена','хорошая цена'))
sel=[r for r in u if good(r)]
sel.sort(key=lambda r:(-(r['disc'] if r['disc'] is not None else -1)))
print('all',len(u),'sel',len(sel),'private',sum(r['private'] for r in sel))
F='Arial'
hf=Font(name=F,bold=True,color='FFFFFF',size=10); hfill=PatternFill('solid',fgColor='1F3864')
base=Font(name=F,size=10); link=Font(name=F,size=10,color='0563C1',underline='single')
thin=Side(style='thin',color='D9D9D9'); brd=Border(left=thin,right=thin,top=thin,bottom=thin)
COLS=['Марка, модель','Год','Двигатель, л','Мощность, л.с.','КПП','Привод','Пробег, км','Цена, ₽','Медиана аналогов, ₽','Дешевле аналогов','Аналогов, шт.','Оценка Дрома','Продавец','От собственника','Город','Сайт','Ссылка','Вторая ссылка (Дром)']
W=[26,7,10,11,10,10,11,11,13,11,9,16,30,11,16,9,10,12]
def fill(ws,data,start):
    for j,c in enumerate(COLS,1):
        cell=ws.cell(row=start,column=j,value=c); cell.font=hf; cell.fill=hfill; cell.alignment=Alignment(horizontal='center',vertical='center',wrap_text=True); cell.border=brd
        ws.column_dimensions[get_column_letter(j)].width=W[j-1]
    ws.row_dimensions[start].height=44
    for i,r in enumerate(data,start+1):
        v=[r['name'],r['year'],float(r['vol']) if r['vol'] else None,r['hp'],r['tr'],r['drive'],r['km'],r['price'],r['comp_med'],
           (f'=IF(I{i}="","",1-H{i}/I{i})'),r['comp_n'],r['dr'],r['dealer'] if not r['private'] else 'частное лицо','да' if r['owner'] else '',r['loc'],r['src'],'открыть','открыть' if r.get('also') else '']
        for j,x in enumerate(v,1):
            cell=ws.cell(row=i,column=j,value=x); cell.font=base; cell.border=brd
            if j in (7,8,9): cell.number_format='#,##0'
            if j==3: cell.number_format='0.0'
            if j==10: cell.number_format='0%'
        c=ws.cell(row=i,column=17); c.hyperlink=r['href']; c.font=link
        if r.get('also'): c=ws.cell(row=i,column=18); c.hyperlink=r['also']; c.font=link
        if r['disc'] is not None and r['disc']>=0.25: ws.cell(row=i,column=10).fill=PatternFill('solid',fgColor='C6EFCE')
        elif r['disc'] is not None and r['disc']>=0.12: ws.cell(row=i,column=10).fill=PatternFill('solid',fgColor='E2EFDA')
    ws.auto_filter.ref=f"A{start}:{get_column_letter(len(COLS))}{start+len(data)}"
    ws.freeze_panes=ws.cell(row=start+1,column=2)
wb=Workbook(); ws=wb.active; ws.title='Подборка'
nd=sum(1 for r in u if r['src']=='Дром'); na=sum(1 for r in u if r['src']=='Авто.ру')
notes=['Подборка автомобилей до 750 000 ₽ — Ярославль и окрестности (Авто.ру + Дром)',
 f'Источники: auto.ru (Ярославль +50 км) и yaroslavl.drom.ru, собрано 19.11.2026. Авито не открылся. После удаления дублей между сайтами в базе {len(u)} объявлений: Авто.ру {na}, только на Дроме {nd}.',
 'Критерии: год от 2007; пробег до 250 000 км; цена от 100 000 ₽; без отметок «битый» и «проблемы с документами» (эти отметки есть только на Дроме); и одно из двух: цена минимум на 12% ниже медианы аналогов ИЛИ оценка Дрома «отличная/хорошая цена».',
 'Медиана аналогов: медианная цена той же модели с годом выпуска ±2 года по этой базе, если аналогов 5 и больше (число посчитано при сборе). «Дешевле аналогов» — формула от цены и медианы. Пробег и состояние в сравнении не учтены.',
 'Скидка больше 40% чаще означает проблему с машиной или ошибку в объявлении, а не удачу. Объявления не проверялись по базам и не осматривались; часть могла быть снята после сбора.']
for i,t in enumerate(notes,1):
    ws.cell(row=i,column=1,value=t).font=Font(name=F,size=12 if i==1 else 10,bold=(i==1))
fill(ws,sel,7)
ws2=wb.create_sheet('Все объявления'); fill(ws2,sorted(u,key=lambda r:(r['name'],-r['year'],r['price'])),1)
n=len(u)+1
ws3=wb.create_sheet('Рынок')
ws3.cell(row=1,column=1,value='Модели на рынке: формулы считают по листу «Все объявления»').font=Font(name=F,size=11,bold=True)
H=['Марка, модель','Объявлений','Средняя цена, ₽','Средний год','Средний пробег, км']
for j,h in enumerate(H,1):
    c=ws3.cell(row=3,column=j,value=h); c.font=hf; c.fill=hfill; c.alignment=Alignment(horizontal='center',vertical='center',wrap_text=True); c.border=brd
for j,w in enumerate([28,12,16,12,18],1): ws3.column_dimensions[get_column_letter(j)].width=w
cnt=collections.Counter(r['name'] for r in u); models=[m for m,c in cnt.most_common() if c>=8]
A="'Все объявления'"
for i,m in enumerate(models,4):
    ws3.cell(row=i,column=1,value=m)
    ws3.cell(row=i,column=2,value=f"=COUNTIF({A}!$A$2:$A${n},A{i})")
    ws3.cell(row=i,column=3,value=f"=AVERAGEIF({A}!$A$2:$A${n},A{i},{A}!$H$2:$H${n})").number_format='#,##0'
    ws3.cell(row=i,column=4,value=f"=AVERAGEIF({A}!$A$2:$A${n},A{i},{A}!$B$2:$B${n})").number_format='0'
    ws3.cell(row=i,column=5,value=f"=AVERAGEIFS({A}!$G$2:$G${n},{A}!$A$2:$A${n},A{i},{A}!$G$2:$G${n},\">0\")").number_format='#,##0'
    for j in range(1,6): ws3.cell(row=i,column=j).font=base; ws3.cell(row=i,column=j).border=brd
ws3.cell(row=len(models)+5,column=1,value='Показаны модели с 8 и более объявлениями. Названия моделей на двух сайтах иногда пишутся по-разному, поэтому часть моделей может быть разбита на две строки.').font=Font(name=F,size=9,italic=True)
ws3.freeze_panes='B4'
out='Подборка авто.xlsx'
wb.save(out)
print(len(models))
print('median price',st.median(r['price'] for r in u),'median year',st.median(r['year'] for r in u),'private',sum(r['private'] for r in u))
print('sel by disc bands', sum(1 for r in sel if r['disc'] and r['disc']>0.4), sum(1 for r in sel if r['disc'] and 0.12<=r['disc']<=0.4), sum(1 for r in sel if not r['disc'] or r['disc']<0.12))
print('sel AT', sum(1 for r in sel if r['tr'] in ('АКПП','вариатор')), 'year>=2013', sum(1 for r in sel if r['year']>=2013))
