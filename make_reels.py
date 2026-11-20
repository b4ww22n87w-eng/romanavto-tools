#!/usr/bin/env python3
"""Монтаж вертикального ролика: субтитры, заголовок, плашки шагов, приближения.

Запуск:
    python3 make_reels.py <видео.mp4> <субтитры.srt> <план.json> <результат.mp4>

План описывает заголовок, шаги и слова, которые нужно выделить в субтитрах.
"""
import json
import re
import subprocess
import sys

W, H = 1080, 1920
YELLOW = "&H0000D4FF"  # ASS хранит цвет как BGR: это #FFD400
WHITE = "&H00FFFFFF"
DARK = "&H00141414"
# Зоны, которые Instagram закрывает своим интерфейсом: сверху и снизу текст не ставим.
TITLE_TOP = 300
PLATE_TOP = 280
CAPTION_BOTTOM = 470
ZOOM = 1.10
ZOOM_RAMP = 0.18
FACE_Y = 0.33  # лицо в кадре примерно на трети высоты, приближаем к нему


def parse_srt(path):
    """Возвращает список (начало, конец, текст) в секундах."""
    blocks = re.split(r"\n\s*\n", open(path, encoding="utf-8-sig").read().strip())
    out = []
    for block in blocks:
        lines = [l for l in block.splitlines() if l.strip()]
        stamp = next((l for l in lines if "-->" in l), None)
        if not stamp:
            continue
        a, b = [to_seconds(x.strip()) for x in stamp.split("-->")]
        text = " ".join(lines[lines.index(stamp) + 1:]).strip()
        if text:
            out.append((a, b, text))
    return out


def to_seconds(stamp):
    h, m, s = stamp.replace(",", ".").split(":")
    return int(h) * 3600 + int(m) * 60 + float(s)


def ass_time(t):
    t = max(0.0, t)
    return f"{int(t // 3600)}:{int(t % 3600 // 60):02d}:{t % 60:05.2f}"


def step_windows(cues, steps, duration):
    """Находит, когда начинается каждый шаг, по первому слову шага в субтитрах."""
    starts = []
    for step in steps:
        hit = next((a for a, _, text in cues if step["starts_with"].lower() in text.lower()), None)
        if hit is None:
            raise SystemExit(f"В субтитрах не найдено начало шага: {step['starts_with']}")
        starts.append(hit)
    return starts


def highlight(text, replacements, words):
    for old, new in replacements.items():
        text = re.sub(re.escape(old), new, text, flags=re.I)
    for word in words:
        text = re.sub(f"({re.escape(word)}[\\w-]*)", "{\\\\c" + YELLOW + "&}\\1{\\\\c" + WHITE + "&}", text, flags=re.I)
    return text


def build_ass(cues, plan, starts, outro_at, duration, path):
    head = f"""[Script Info]
ScriptType: v4.00+
PlayResX: {W}
PlayResY: {H}
WrapStyle: 0
ScaledBorderAndShadow: yes

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Cap,Inter Display ExtraBold,82,{WHITE},{WHITE},&H00000000,&H96000000,0,0,0,0,100,100,0,0,1,8,3,2,80,80,{CAPTION_BOTTOM},1
Style: Title,Inter Display Black,112,{WHITE},{WHITE},&H00000000,&H96000000,0,0,0,0,100,100,-1,0,1,7,4,8,60,60,{TITLE_TOP},1
Style: Plate,Inter Display ExtraBold,56,{DARK},{DARK},{YELLOW},&H00000000,0,0,0,0,100,100,0,0,3,16,0,7,76,60,{PLATE_TOP},1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""
    events = []
    title = plan["title"]
    events.append(f"Dialogue: 2,{ass_time(0.15)},{ass_time(starts[0] - 0.1)},Title,,0,0,0,,"
                  f"{{\\fad(200,150)}}{{\\c{YELLOW}&}}{title['accent']}{{\\c{WHITE}&}}\\N{{\\fs76}}{title['rest']}")
    ends = starts[1:] + [outro_at]
    for i, step in enumerate(plan["steps"]):
        events.append(f"Dialogue: 1,{ass_time(starts[i])},{ass_time(ends[i] - 0.05)},Plate,,0,0,0,,"
                      f"{{\\fad(150,100)}}ШАГ {i + 1} · {step['label']}")
    if plan.get("outro"):
        events.append(f"Dialogue: 1,{ass_time(outro_at)},{ass_time(duration)},Plate,,0,0,0,,{{\\fad(150,0)}}{plan['outro']}")
    for a, b, text in cues:
        events.append(f"Dialogue: 0,{ass_time(a)},{ass_time(b)},Cap,,0,0,0,,"
                      + highlight(text, plan.get("replace", {}), plan.get("highlight", [])))
    with open(path, "w", encoding="utf-8") as f:
        f.write(head + "\n".join(events) + "\n")


def zoom_expression(windows):
    """Плавное приближение внутри каждого окна (начало, конец)."""
    parts = [f"(clip((it-{a:.2f})/{ZOOM_RAMP},0,1)-clip((it-{b:.2f})/{ZOOM_RAMP},0,1))" for a, b in windows]
    return f"1+{ZOOM - 1:.2f}*({'+'.join(parts)})" if parts else "1"


def probe(video):
    out = subprocess.run(["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries",
                          "stream=r_frame_rate:format=duration", "-of", "json", video],
                         capture_output=True, text=True, check=True).stdout
    info = json.loads(out)
    num, den = info["streams"][0]["r_frame_rate"].split("/")
    return float(info["format"]["duration"]), float(num) / float(den)


def main():
    video, srt, plan_path, result = sys.argv[1:5]
    plan = json.load(open(plan_path, encoding="utf-8"))
    cues = parse_srt(srt)
    duration, fps = probe(video)
    starts = step_windows(cues, plan["steps"], duration)
    outro_at = next((a for a, _, text in cues if plan["outro_starts_with"].lower() in text.lower()), duration)
    ass = result.rsplit(".", 1)[0] + ".ass"
    build_ass(cues, plan, starts, outro_at, duration, ass)
    ends = starts[1:] + [outro_at]
    zoomed = [(starts[i], ends[i]) for i in range(len(starts)) if plan["steps"][i].get("zoom")]
    z = zoom_expression(zoomed)
    vf = (f"zoompan=z='{z}':x='iw/2-(iw/zoom/2)':y='ih*{FACE_Y}-(ih/zoom*{FACE_Y})':d=1:s={W}x{H}:fps={fps:.3f},"
          f"ass='{ass}'")
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", video, "-vf", vf, "-c:v", "libx264", "-preset", "medium",
                    "-crf", "21", "-maxrate", "5M", "-bufsize", "10M", "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "192k", "-movflags", "+faststart", result],
                   check=True)
    print("Готово:", result, f"длина {duration:.1f} с, шаги начинаются на", [round(s, 2) for s in starts])


if __name__ == "__main__":
    main()
