#!/usr/bin/env python3
"""Поиск автомобилей на Дроме и Авто.ру.

Запуск:
    python3 search.py            собрать объявления заново и построить подборку
    python3 search.py --offline  не ходить на сайты, пересчитать по уже собранным данным

Настройки лежат в config.json. Результат появляется в папке out/:
    data.json, meta.json  данные для страницы page.html
    Подборка авто.xlsx    таблица
"""
import collections
import datetime
import json
import os
import re
import statistics
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "out")
DROM_RAW = os.path.join(OUT, "drom_raw.json")
AUTORU_RAW = os.path.join(OUT, "autoru_raw.json")

DROM_RATINGS = ["отличная цена", "хорошая цена", "нормальная цена", "высокая цена", "без оценки"]
GEARBOX = {"Механика": "механика", "Автомат": "АКПП", "Вариатор": "вариатор", "Робот": "робот"}
DRIVE = {"Передний привод": "передний", "Полный привод": "4WD", "Задний привод": "задний"}
LADA_MODELS = {"Granta": "Гранта", "Kalina": "Калина", "Priora": "Приора", "Vesta": "Веста",
               "Largus": "Ларгус", "XRAY": "Х-рей", "Niva": "Нива"}
DEALER_WORDS = re.compile(r"авто|auto|салон|ООО|ИП |маркет|парк|компани|центр|trade|cars|моторс|motors|выкуп|пробег", re.I)
# Насколько может отличаться пробег одной и той же машины в объявлениях на двух сайтах.
SAME_CAR_KM_TOLERANCE = 3000
# Сколько аналогов нужно, чтобы медиане можно было доверять.
MIN_COMPS = 5
COMPS_YEAR_WINDOW = 2


def digits(text):
    found = re.sub(r"\D", "", text or "")
    return int(found) if found else None


def collect(config):
    """Запускает сбор с обоих сайтов. Каждый сборщик сохраняет то, что успел."""
    os.makedirs(OUT, exist_ok=True)
    pages = str(config.get("max_pages", 70))
    for script, url, raw in (("collect_drom.js", config["drom_url"], DROM_RAW),
                             ("collect_autoru.js", config["autoru_url"], AUTORU_RAW)):
        if os.path.exists(raw):
            os.remove(raw)
        subprocess.run(["node", os.path.join(HERE, script), url, raw, pages], check=False)


def load_raw(path):
    if not os.path.exists(path):
        return []
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def parse_drom(raw):
    rows, seen = [], set()
    for card in raw:
        href = card.get("href", "")
        if not href or href in seen:
            continue
        seen.add(href)
        match = re.match(r"(.+),\s*(\d{4})$", card.get("bull_title", ""))
        price = digits(card.get("bull_price"))
        if not match or not price:
            continue
        desc = card.get("component_inline-bull-description", "")
        km = re.search(r"([\d\s]+)\s*км", desc)
        vol = re.search(r"(\d\.\d)\s*л", desc)
        hp = re.search(r"\((\d+)\s*л\.с\.\)", desc)
        lines = [l.strip() for l in card.get("text", "").split("\n") if l.strip()]
        known = {card.get("bull_title"), card.get("bull_subtitle"), desc, card.get("bull_location"),
                 card.get("bull_date"), "только на Дроме", "от собственника", *DROM_RATINGS}
        other = [l for l in lines if l not in known and not re.fullmatch(r"[\d\s]+₽", l)]
        dealer = other[0] if other else ""
        rows.append({
            "src": "Дром", "name": match.group(1), "year": int(match.group(2)),
            "vol": vol.group(1) if vol else "", "hp": int(hp.group(1)) if hp else None,
            "tr": next((k for k in ("АКПП", "механика", "вариатор", "робот") if k in desc), ""),
            "drive": next((k for k in ("4WD", "передний", "задний") if k in desc), ""),
            "km": digits(km.group(1)) if km else None, "price": price,
            "drom_rating": next((r for r in DROM_RATINGS if r in lines), ""),
            "owner": "bull_label_owner" in card, "private": not dealer, "dealer": dealer,
            "broken": "bull_label_broken" in card, "nodocs": "bull_label_nodocs" in card,
            "loc": card.get("bull_location", ""), "href": href, "also": "",
        })
    return rows


def clean_autoru_name(title):
    """Убирает из названия поколение и рестайлинг: «Ford Focus II Рестайлинг» -> «Ford Focus»."""
    name = re.sub(r"\s+Рестайлинг.*$", "", title)
    name = re.sub(r"\s+[IVX]+$", "", name).strip()
    if not name.endswith("(4x4)"):
        name = re.sub(r"\s+\([^)]*\)$", "", name).strip()
    name = re.sub(r"\s+[IVX]+$", "", name).strip()
    if name.startswith("Lada (ВАЗ)"):
        model = name.replace("Lada (ВАЗ)", "").strip()
        for latin, cyr in LADA_MODELS.items():
            model = re.sub(r"\b" + latin + r"\b", cyr, model)
        name = "Лада " + model
    return name


def autoru_seller(lines, place, owner):
    """Возвращает (название продавца, это автосалон?)."""
    tail = [l for l in lines if l != place]
    if "Проверенный дилер" in tail:
        i = tail.index("Проверенный дилер") - 1
        if i >= 0 and re.fullmatch(r"\d\.\d", tail[i]):
            i -= 1
        return (tail[i] if i >= 0 else ""), True
    i = len(tail) - 1
    rated = i >= 0 and bool(re.fullmatch(r"\d\.\d", tail[i]))
    if rated:
        i -= 1
    seller = tail[i] if i >= 0 else ""
    if re.fullmatch(r"[\d\s]+₽", seller) or seller in ("От собственника", "Справедливая цена"):
        seller = ""
    if seller == "Частное лицо" or owner:
        return seller, False
    is_dealer = rated or bool(DEALER_WORDS.search(seller)) or (seller.isupper() and len(seller) > 3)
    return seller, is_dealer


def parse_autoru(raw, exclude_towns):
    rows, seen = [], set()
    for card in raw:
        href = card.get("href", "")
        if not href or href in seen:
            continue
        seen.add(href)
        lines = [l.strip() for l in card.get("text", "").replace("\xa0", " ").split("\n") if l.strip()]
        place = card.get("place", "").replace("\xa0", " ").strip() or (lines[-1] if lines else "")
        town = place.split(",")[0].strip()
        if town in exclude_towns:
            continue
        year = next((int(l) for l in lines if re.fullmatch(r"(19|20)\d{2}", l)), None)
        price = next((digits(l) for l in lines if re.fullmatch(r"[\d\s]+₽", l)), None)
        if not year or not price:
            continue
        engine = re.match(r"(\d\.\d) л(?:, (\d+) л\.с\.)?", next((l for l in lines if re.match(r"\d\.\d л", l)), ""))
        owner = "От собственника" in lines
        seller, is_dealer = autoru_seller(lines, place, owner)
        rows.append({
            "src": "Авто.ру", "name": clean_autoru_name(card.get("title", "")), "year": year,
            "vol": engine.group(1) if engine else "", "hp": int(engine.group(2)) if engine and engine.group(2) else None,
            "tr": next((GEARBOX[l] for l in lines if l in GEARBOX), ""),
            "drive": next((DRIVE[l] for l in lines if l in DRIVE), ""),
            "km": next((digits(l) for l in lines if re.fullmatch(r"[\d\s]+км", l)), None), "price": price,
            "drom_rating": "", "owner": owner, "private": not is_dealer, "dealer": seller if is_dealer else "",
            "broken": False, "nodocs": False, "loc": town, "href": href, "also": "",
        })
    return rows


def merge(drom, autoru):
    """Убирает машины, которые выложены на обоих сайтах: оставляет объявление Авто.ру со ссылкой на Дром."""
    by_year_price = collections.defaultdict(list)
    for row in autoru:
        by_year_price[(row["year"], row["price"])].append(row)
    kept_drom = []
    for d in drom:
        twin = next((a for a in by_year_price.get((d["year"], d["price"]), [])
                     if a["km"] and d["km"] and abs(a["km"] - d["km"]) <= SAME_CAR_KM_TOLERANCE), None)
        if twin is None:
            kept_drom.append(d)
            continue
        twin["also"] = twin["also"] or d["href"]
        twin["drom_rating"] = twin["drom_rating"] or d["drom_rating"]
        twin["broken"] = twin["broken"] or d["broken"]
        twin["nodocs"] = twin["nodocs"] or d["nodocs"]
    # Заказные машины из Японии физически не в регионе.
    return [r for r in autoru + kept_drom if "Япония" not in r["loc"]]


def add_comps(rows):
    """Для каждой машины считает медианную цену той же модели близких годов."""
    by_name = collections.defaultdict(list)
    for row in rows:
        by_name[row["name"]].append(row)
    for row in rows:
        comps = [c["price"] for c in by_name[row["name"]]
                 if c is not row and abs(c["year"] - row["year"]) <= COMPS_YEAR_WINDOW]
        row["comp_n"] = len(comps)
        row["comp_med"] = int(statistics.median(comps)) if len(comps) >= MIN_COMPS else None
        row["disc"] = round(1 - row["price"] / row["comp_med"], 3) if row["comp_med"] else None


def selected(row, sel):
    if row["broken"] or row["nodocs"] or not row["km"]:
        return False
    if not sel["price_min"] <= row["price"] <= sel["price_max"]:
        return False
    if row["year"] < sel["year_from"] or row["km"] > sel["km_max"]:
        return False
    if sel.get("private_only") and not row["private"]:
        return False
    if sel.get("transmissions") and row["tr"] not in sel["transmissions"]:
        return False
    if sel.get("brands") and row["name"].split()[0] not in sel["brands"]:
        return False
    cheap = row["disc"] is not None and row["disc"] >= sel["min_discount"]
    return cheap or row["drom_rating"] in ("отличная цена", "хорошая цена")


def write_page_data(rows, config, today):
    records = [{
        "n": r["name"], "y": r["year"], "v": r["vol"], "h": r["hp"], "t": r["tr"], "d": r["drive"],
        "k": r["km"], "p": r["price"], "m": r["comp_med"], "c": r["comp_n"], "r": r["drom_rating"],
        "s": 1 if r["private"] else 0, "o": 1 if r["owner"] else 0, "e": r["dealer"],
        "b": 1 if (r["broken"] or r["nodocs"]) else 0, "l": r["loc"], "a": r["src"], "u": r["href"], "u2": r["also"],
    } for r in rows]
    with open(os.path.join(OUT, "data.json"), "w", encoding="utf-8") as f:
        f.write("[\n" + ",\n".join(json.dumps(x, ensure_ascii=False, separators=(",", ":")) for x in records) + "\n]\n")
    meta = {"date": today, "total": len(rows),
            "autoru": sum(1 for r in rows if r["src"] == "Авто.ру"),
            "drom": sum(1 for r in rows if r["src"] == "Дром"),
            "defaults": config["selection"]}
    with open(os.path.join(OUT, "meta.json"), "w", encoding="utf-8") as f:
        json.dump(meta, f, ensure_ascii=False)


def write_table(rows, picks, config, today):
    from openpyxl import Workbook
    from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
    from openpyxl.utils import get_column_letter

    font = "Arial"
    head_font = Font(name=font, bold=True, color="FFFFFF", size=10)
    head_fill = PatternFill("solid", fgColor="1F3864")
    base = Font(name=font, size=10)
    link = Font(name=font, size=10, color="0563C1", underline="single")
    side = Side(style="thin", color="D9D9D9")
    border = Border(left=side, right=side, top=side, bottom=side)
    columns = ["Марка, модель", "Год", "Двигатель, л", "Мощность, л.с.", "КПП", "Привод", "Пробег, км", "Цена, ₽",
               "Медиана аналогов, ₽", "Дешевле аналогов", "Аналогов, шт.", "Оценка Дрома", "Продавец",
               "От собственника", "Город", "Сайт", "Ссылка", "Вторая ссылка (Дром)"]
    widths = [26, 7, 10, 11, 10, 10, 11, 11, 13, 11, 9, 16, 30, 11, 16, 9, 10, 12]

    def fill(ws, data, start):
        for j, title in enumerate(columns, 1):
            cell = ws.cell(row=start, column=j, value=title)
            cell.font, cell.fill, cell.border = head_font, head_fill, border
            cell.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)
            ws.column_dimensions[get_column_letter(j)].width = widths[j - 1]
        ws.row_dimensions[start].height = 44
        for i, r in enumerate(data, start + 1):
            values = [r["name"], r["year"], float(r["vol"]) if r["vol"] else None, r["hp"], r["tr"], r["drive"],
                      r["km"], r["price"], r["comp_med"], f'=IF(I{i}="","",1-H{i}/I{i})', r["comp_n"],
                      r["drom_rating"], "частное лицо" if r["private"] else r["dealer"],
                      "да" if r["owner"] else "", r["loc"], r["src"], "открыть", "открыть" if r["also"] else ""]
            for j, value in enumerate(values, 1):
                cell = ws.cell(row=i, column=j, value=value)
                cell.font, cell.border = base, border
                if j in (7, 8, 9):
                    cell.number_format = "#,##0"
                elif j == 3:
                    cell.number_format = "0.0"
                elif j == 10:
                    cell.number_format = "0%"
            ws.cell(row=i, column=17).hyperlink = r["href"]
            ws.cell(row=i, column=17).font = link
            if r["also"]:
                ws.cell(row=i, column=18).hyperlink = r["also"]
                ws.cell(row=i, column=18).font = link
        ws.auto_filter.ref = f"A{start}:{get_column_letter(len(columns))}{start + len(data)}"
        ws.freeze_panes = ws.cell(row=start + 1, column=2)

    sel = config["selection"]
    wb = Workbook()
    ws = wb.active
    ws.title = "Подборка"
    notes = [
        "Подборка автомобилей (Авто.ру + Дром)",
        f"Собрано {today}. В базе {len(rows)} объявлений после удаления дублей между сайтами. Авито не собирается.",
        f"Критерии: цена {sel['price_min']:,}–{sel['price_max']:,} ₽; год от {sel['year_from']}; пробег до {sel['km_max']:,} км; "
        f"без отметок «битый» и «проблемы с документами»; цена минимум на {round(sel['min_discount'] * 100)}% ниже медианы аналогов "
        "или оценка Дрома «отличная/хорошая цена».".replace(",", " "),
        f"Медиана аналогов: та же модель, год ±{COMPS_YEAR_WINDOW}, не меньше {MIN_COMPS} объявлений в базе. "
        "Пробег и состояние в сравнении не учтены.",
        "Объявления не проверялись по базам и не осматривались. Часть могла быть снята после сбора.",
    ]
    for i, text in enumerate(notes, 1):
        ws.cell(row=i, column=1, value=text).font = Font(name=font, size=12 if i == 1 else 10, bold=(i == 1))
    fill(ws, picks, 7)
    fill(wb.create_sheet("Все объявления"), sorted(rows, key=lambda r: (r["name"], -r["year"], r["price"])), 1)
    wb.save(os.path.join(OUT, "Подборка авто.xlsx"))


def main():
    with open(os.path.join(HERE, "config.json"), encoding="utf-8") as f:
        config = json.load(f)
    if "--offline" not in sys.argv:
        collect(config)
    drom = parse_drom(load_raw(DROM_RAW))
    autoru = parse_autoru(load_raw(AUTORU_RAW), set(config.get("exclude_towns", [])))
    if not drom and not autoru:
        sys.exit("Нет данных: оба сайта ничего не отдали. Попробуйте позже.")
    rows = merge(drom, autoru)
    add_comps(rows)
    picks = sorted((r for r in rows if selected(r, config["selection"])),
                   key=lambda r: -(r["disc"] if r["disc"] is not None else -1))
    today = datetime.date.today().strftime("%d.%m.%Y")
    write_page_data(rows, config, today)
    write_table(rows, picks, config, today)
    print(f"Дром: {len(drom)}, Авто.ру: {len(autoru)}, после удаления дублей: {len(rows)}, в подборке: {len(picks)}")
    if not drom or not autoru:
        print("Внимание: один из сайтов ничего не отдал, подборка неполная.")


if __name__ == "__main__":
    main()
