#!/usr/bin/env python3
import argparse, json, os, re, shutil, subprocess, sys, tempfile
from pathlib import Path

HOME = Path(__file__).resolve().parent
CONFIG = HOME / "config.json"
STREAMERS = HOME / "streamers.json"
CLIPS = HOME / "clips"
OUT = HOME / "shorts"
FONT_CANDIDATES = {
    "label": ["~/Library/Fonts/BebasNeue-Bold.ttf", "/Library/Fonts/BebasNeue-Bold.ttf", "/usr/share/fonts/opentype/inter/Inter-Black.otf"],
    "text": ["~/Library/Fonts/Inter-Black.otf", "/Library/Fonts/Inter-Black.otf", "/usr/share/fonts/opentype/inter/Inter-Black.otf"],
}


def die(msg):
    print(f"\nSTOP: {msg}\n")
    sys.exit(1)


def load(path, default):
    return json.loads(path.read_text()) if path.exists() else default


def save(path, data):
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False))


def font(kind):
    for f in FONT_CANDIDATES[kind]:
        p = Path(os.path.expanduser(f))
        if p.exists():
            return str(p)
    die(f"no {kind} font found")


def run(cmd, quiet=True):
    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode != 0:
        die(f"command failed: {' '.join(map(str, cmd[:6]))} ...\n{r.stderr[-1500:]}")
    return r


def ytdlp():
    return [sys.executable, "-m", "yt_dlp", "--no-warnings", "--quiet"]


def probe(path):
    r = run(["ffprobe", "-v", "error", "-show_entries", "format=duration:stream=codec_type,width,height", "-of", "json", str(path)])
    d = json.loads(r.stdout)
    streams = d.get("streams", [])
    return {
        "duration": float(d["format"]["duration"]),
        "audio": any(s["codec_type"] == "audio" for s in streams),
        "video": any(s["codec_type"] == "video" for s in streams),
    }


def video_encoder():
    enc = run(["ffmpeg", "-hide_banner", "-encoders"]).stdout
    if "h264_videotoolbox" in enc:
        return ["-c:v", "h264_videotoolbox", "-b:v", "12M", "-profile:v", "high"]
    return ["-c:v", "libx264", "-preset", "veryfast", "-crf", "19"]


def approved(name):
    streamers = load(STREAMERS, {})
    if name == "me":
        return {"credit": "", "permission": "own footage"}
    if name not in streamers:
        die(f"'{name}' is not on your approved list. Add them first:\n"
            f"  clipper add-streamer {name} --credit 'twitch.tv/{name}' --permission '<where they say clipping is allowed>'")
    return streamers[name]


def cmd_add_streamer(a):
    streamers = load(STREAMERS, {})
    if not a.permission.strip():
        die("--permission is required: paste the link or note showing they allow clipping")
    streamers[a.name] = {"credit": a.credit, "permission": a.permission}
    save(STREAMERS, streamers)
    print(f"Added {a.name}  credit: {a.credit}")


def cmd_streamers(a):
    if a.names:
        print("\n".join(load(STREAMERS, {}).keys()))
        return
    for n, s in load(STREAMERS, {}).items():
        print(f"{n:20} credit: {s['credit']:30} permission: {s['permission']}")


def loudness_curve(path):
    r = subprocess.run(["ffmpeg", "-hide_banner", "-nostats", "-v", "verbose", "-i", str(path), "-vn", "-af", "ebur128=framelog=verbose", "-f", "null", "-"],
                       capture_output=True, text=True)
    pts = []
    for m in re.finditer(r"t:\s*([\d.]+).*?S:\s*(-?[\d.]+|-inf)", r.stderr):
        s = m.group(2)
        pts.append((float(m.group(1)), -70.0 if s == "-inf" else max(float(s), -70.0)))
    if not pts:
        die("could not read audio loudness (no audio track?)")
    return pts


def pick_peaks(points, top, gap):
    import numpy as np
    n = int(points[-1][0]) + 1
    v = np.full(n, -70.0)
    for ts, val in points:
        k = int(ts)
        v[k] = max(v[k], val)
    t = np.arange(n, dtype=float)
    w = 60
    pad = np.pad(v, (w, w), mode="edge")
    base = np.array([np.median(pad[i:i + 2 * w + 1]) for i in range(n)])
    score = v - base
    score[:5] = -99
    score[-5:] = -99
    order = np.argsort(-score)
    chosen = []
    for i in order:
        if len(chosen) >= top:
            break
        if score[i] < 3:
            break
        if all(abs(t[i] - t[j]) > gap for j in chosen):
            chosen.append(i)
    return [(float(t[i]), float(score[i])) for i in sorted(chosen)]


def heatmap_peaks(heat, top, gap):
    segs = sorted(heat, key=lambda h: -h["value"])
    chosen = []
    for h in segs:
        if len(chosen) >= top:
            break
        mid = (h["start_time"] + h["end_time"]) / 2
        if h["start_time"] < 10:
            continue
        if all(abs(mid - c[0]) > gap for c in chosen):
            chosen.append((mid, round(h["value"] * 100, 1)))
    return sorted(chosen)


def cut(src, start, dur, dst):
    run(["ffmpeg", "-y", "-v", "error", "-ss", f"{max(start, 0):.2f}", "-i", str(src), "-t", f"{dur:.2f}",
         *video_encoder(), "-c:a", "aac", "-b:a", "192k", "-movflags", "+faststart", str(dst)])


def write_sidecar(clip, streamer, info, source, start, score, kind, peak_offset=None):
    save(clip.with_suffix(".json"), {"streamer": streamer, "credit": info["credit"], "source": source,
                                    "start": round(start, 2), "score": score, "found_by": kind,
                                    "peak_offset": None if peak_offset is None else round(peak_offset, 2)})


def contact_sheet(clips, dst):
    if not clips:
        return
    from PIL import Image, ImageDraw, ImageFont
    tmp = Path(tempfile.mkdtemp())
    tiles = []
    for i, c in enumerate(clips):
        f = tmp / f"{i:03}.jpg"
        d = probe(c)["duration"]
        subprocess.run(["ffmpeg", "-y", "-v", "error", "-ss", f"{d * 0.6:.2f}", "-i", str(c), "-frames:v", "1",
                        "-vf", "scale=480:270:force_original_aspect_ratio=decrease,pad=480:270:(ow-iw)/2:(oh-ih)/2", str(f)])
        im = Image.open(f).convert("RGB") if f.exists() else Image.new("RGB", (480, 270))
        ImageDraw.Draw(im).text((14, 8), str(i + 1), font=ImageFont.truetype(font("text"), 54), fill="yellow",
                                stroke_width=4, stroke_fill="black")
        tiles.append(im)
    cols = 4
    rows = (len(tiles) + cols - 1) // cols
    sheet = Image.new("RGB", (480 * cols, 270 * rows))
    for i, im in enumerate(tiles):
        sheet.paste(im, ((i % cols) * 480, (i // cols) * 270))
    sheet.save(dst, quality=90)
    shutil.rmtree(tmp, ignore_errors=True)


def is_cc(meta):
    return "creative commons" in (meta.get("license") or "").lower()


def cmd_find(a):
    info = approved(a.streamer)
    if info.get("cc_only") and a.source.startswith("http"):
        m = json.loads(run(ytdlp() + ["-J", "--skip-download", a.source]).stdout)
        if not is_cc(m):
            die(f"{a.streamer} was auto-approved only for their Creative Commons videos, and this video isn't one.\n"
                f"Add them properly (with a link showing they allow clipping) to use their other videos.")
    dest = CLIPS / a.streamer
    dest.mkdir(parents=True, exist_ok=True)
    src = a.source
    made = []
    is_url = src.startswith("http")

    if is_url and "twitch.tv" in src and "/clips" in src:
        r = run(ytdlp() + ["--flat-playlist", "-J", "--playlist-end", "60", src])
        entries = json.loads(r.stdout).get("entries", [])
        entries.sort(key=lambda e: -(e.get("view_count") or 0))
        for i, e in enumerate(entries[:a.top], 1):
            url = e.get("url") or e.get("webpage_url")
            out = dest / f"twitchclip_{i:02}.mp4"
            run(ytdlp() + ["-f", "best[height<=1080]/best", "--remux-video", "mp4", "-o", str(out), url])
            write_sidecar(out, a.streamer, info, url, 0, e.get("view_count"), "twitch top clips (views)")
            made.append(out)
            print(f"  {out.name}  views={e.get('view_count')}  {e.get('title', '')[:60]}")
    else:
        peaks, kind, meta = [], "", {}
        if is_url:
            meta = json.loads(run(ytdlp() + ["-J", "--skip-download", src]).stdout)
            if meta.get("heatmap"):
                peaks, kind = heatmap_peaks(meta["heatmap"], a.top, a.before + a.after), "youtube most-replayed"
        if not peaks:
            local = Path(src)
            if is_url:
                local = dest / f"audio_scan_{meta.get('id', 'x')}.m4a"
                for old in dest.glob("audio_scan*"):
                    old.unlink()
                print("No replay data; downloading audio only to find loud moments...")
                run(ytdlp() + ["--force-overwrites", "-f", "bestaudio[ext=m4a]/bestaudio", "-o", str(local), src])
            print("Scanning loudness (your reactions + big game moments)...")
            peaks, kind = pick_peaks(loudness_curve(local), a.top, a.before + a.after), "loudness spikes"
            if is_url and local.exists():
                local.unlink()
        print(f"Found {len(peaks)} moments via {kind}")
        length = float(meta.get("duration") or 0) if is_url else probe(src)["duration"]
        for i, (t, score) in enumerate(peaks, 1):
            start = max(t - a.before, 0)
            end = min(t + a.after, length) if length else t + a.after
            if end - start < 3:
                print(f"  {i:2}. skipped (too close to the end of the video)")
                continue
            out = dest / f"{(meta.get('id') or Path(src).stem).replace(' ', '_')}_{i:02}_{int(start)}s.mp4"
            try:
                if is_url:
                    sec = ["--download-sections", f"*{start:.0f}-{end:.0f}", "--merge-output-format", "mp4", "-o", str(out), src]
                    fmt = ["-f", "bv*[height<=1080]+ba/b[height<=1080]"]
                    r = subprocess.run(ytdlp() + fmt + sec + ["--force-keyframes-at-cuts"], capture_output=True, text=True)
                    if r.returncode != 0 or not out.exists():
                        run(ytdlp() + fmt + sec)
                else:
                    cut(src, start, end - start, out)
            except SystemExit:
                for junk in dest.glob(out.name + "*"):
                    junk.unlink()
                print(f"  {i:2}. skipped: couldn't download this moment ({int(start // 60):02}:{int(start % 60):02})")
                continue
            write_sidecar(out, a.streamer, info, src, start, score, kind, peak_offset=t - start)
            made.append(out)
            print(f"  {i:2}. {int(start // 60):02}:{int(start % 60):02}  score {score:5.1f}  -> {out.name}")
    sheet = dest / "contact_sheet.jpg"
    contact_sheet(made, sheet)
    if not getattr(a, "quiet_sheet", False):
        print(f"SHEET={sheet}")
        print(f"\nClips: {dest}\nPreview sheet: {sheet}")
    return made


def slug(name):
    return re.sub(r"[^A-Za-z0-9_]+", "", name.replace(" ", "_"))[:40] or "creator"


def cmd_auto(a):
    from urllib.parse import quote_plus
    q = a.query
    print(f"Searching YouTube for '{q}' videos marked Creative Commons (free to reuse with credit)...")
    cc_url = f"https://www.youtube.com/results?search_query={quote_plus(q)}&sp=EgIwAQ%3D%3D"
    entries = json.loads(run(ytdlp() + ["--flat-playlist", "-J", "--playlist-end", "30", cc_url]).stdout).get("entries", [])
    entries = [e for e in entries if (e.get("duration") or 0) >= a.min_seconds]
    entries.sort(key=lambda e: -(e.get("view_count") or 0))
    streamers = load(STREAMERS, {})
    made, used, skipped = [], 0, []
    for e in entries:
        if used >= a.videos:
            break
        url = e.get("url") or e.get("webpage_url")
        meta = json.loads(run(ytdlp() + ["-J", "--skip-download", url]).stdout)
        if not is_cc(meta):
            skipped.append(f"{meta.get('channel')} - license not Creative Commons on the page, skipped")
            continue
        name = slug(meta.get("channel") or "creator")
        handle = meta.get("uploader_id") or ""
        credit = f"youtube.com/{handle}" if handle.startswith("@") else (meta.get("channel_url") or meta.get("channel"))
        entry = streamers.get(name, {"credit": credit, "permission": "", "cc_only": True, "videos": []})
        if entry.get("cc_only"):
            entry["videos"] = sorted(set(entry.get("videos", []) + [meta.get("webpage_url", url)]))
            entry["permission"] = "YouTube Creative Commons (reuse allowed) on: " + ", ".join(entry["videos"])
        streamers[name] = entry
        save(STREAMERS, streamers)
        print(f"\n[{used + 1}/{a.videos}] {meta.get('channel')}  views={meta.get('view_count')}  {meta.get('title', '')[:60]}")
        ns = argparse.Namespace(source=meta.get("webpage_url", url), streamer=name, top=a.top, before=a.before,
                                after=a.after, quiet_sheet=True)
        made += cmd_find(ns) or []
        used += 1
    print("\nTop channels for this search WITHOUT a reuse license (not clipped; add them only if they allow clipping):")
    pop = json.loads(run(ytdlp() + ["--flat-playlist", "-J", "--playlist-end", "12", f"ytsearch12:{q}"]).stdout).get("entries", [])
    seen = set()
    for e in sorted(pop, key=lambda e: -(e.get("view_count") or 0)):
        ch = e.get("channel")
        if ch and ch not in seen and slug(ch) not in streamers:
            seen.add(ch)
            print(f"  - {ch}  ({e.get('view_count') or '?'} views)  {e.get('url')}")
    for sk in skipped:
        print("  - " + sk)
    if made:
        sheet = CLIPS / "auto_contact_sheet.jpg"
        contact_sheet(made, sheet)
        save(CLIPS / "auto_contact_sheet.json", [str(m) for m in made])
        print(f"SHEET={sheet}")
        print(f"\n{len(made)} expectation clips ready. Preview: {sheet}")
    else:
        print("\nNo Creative Commons videos matched. Try another search, e.g. 'gta 6 gameplay' or 'gta 6 chase'.")


def clean(text):
    kept = "".join(ch for ch in text if 32 <= ord(ch) < 127)
    if kept != text:
        print(f"  note: removed emoji/special characters the font can't draw: {text!r} -> {kept!r}")
    return kept.strip()


ANIM_FRAMES = 15


def detect_shots(src, start, dur, limit=30):
    import numpy as np
    r = subprocess.run(["ffmpeg", "-v", "error", "-ss", f"{start:.2f}", "-t", f"{dur:.2f}", "-i", str(src), "-vn",
                        "-ac", "1", "-ar", "16000", "-f", "s16le", "-"], capture_output=True)
    x = np.frombuffer(r.stdout, dtype=np.int16).astype(np.float32) / 32768
    hop = 160
    n = len(x) // hop
    if n < 20:
        return []
    rms = np.sqrt(np.mean(x[:n * hop].reshape(n, hop) ** 2, axis=1) + 1e-9)
    db = 20 * np.log10(rms)
    floor = np.percentile(db, 75)
    shots, last = [], -1.0
    for i in range(5, n):
        t = i * hop / 16000
        rise = db[i] - db[i - 5:i].max()
        if rise > 8 and db[i] > floor and db[i] > -40 and t - last > 0.09:
            shots.append(round(t, 3))
            last = t
    if len(shots) > limit:
        strength = sorted(shots, key=lambda t: -db[int(t * 16000 / hop)])[:limit]
        shots = sorted(strength)
    return shots


def shake_expr(shots, amp, axis_phase):
    if not shots:
        return "0"
    parts = [f"gte(t,{t:.3f})*{amp}*exp(-(t-{t:.3f})*28)*cos((t-{t:.3f})*95+{axis_phase})" for t in shots]
    return "+".join(parts)


def ease_out_back(x):
    c1, c3 = 1.70158, 2.70158
    return 1 + c3 * (x - 1) ** 3 + c1 * (x - 1) ** 2


def draw_text(base, text, fontfile, size, fill, xy, anchor, scale=1.0, alpha=255, fit=True):
    from PIL import Image, ImageDraw, ImageFont
    if not text or alpha <= 0:
        return None
    dr = ImageDraw.Draw(base)
    f = ImageFont.truetype(fontfile, size)
    while fit and dr.textlength(text, font=f) * 1.0 + 2 * max(3, size // 14) > 990 and size > 30:
        size -= 4
        f = ImageFont.truetype(fontfile, size)
    size = max(int(size * scale), 8)
    f = ImageFont.truetype(fontfile, size)
    layer = Image.new("RGBA", base.size, (0, 0, 0, 0))
    ImageDraw.Draw(layer).text(xy, text, font=f, fill=tuple(fill[:3]) + (alpha,), anchor=anchor,
                               stroke_width=max(3, size // 14), stroke_fill=(0, 0, 0, alpha))
    base.alpha_composite(layer)
    return ImageDraw.Draw(layer).textbbox(xy, text, font=f, anchor=anchor)


LOOP = 30
SYNC = True
SFX = True


def fit_font(fontfile, text, size, maxw=980):
    from PIL import ImageFont
    f = ImageFont.truetype(fontfile, size)
    while f.getlength(text) + 2 * max(3, size // 14) > maxw and size > 30:
        size -= 4
        f = ImageFont.truetype(fontfile, size)
    return size


def letters(im, text, fontfile, size, fill, cx, cy, per_letter, offset=(0, 0), stroke=True):
    from PIL import Image, ImageDraw, ImageFont
    f = ImageFont.truetype(fontfile, size)
    x0 = cx - f.getlength(text) / 2
    layer = Image.new("RGBA", im.size, (0, 0, 0, 0))
    dr = ImageDraw.Draw(layer)
    for i, ch in enumerate(text):
        dy, alpha = per_letter(i)
        if alpha <= 0:
            continue
        x = x0 + f.getlength(text[:i]) + offset[0]
        dr.text((x, cy + dy + offset[1]), ch, font=f, fill=tuple(fill[:3]) + (alpha,), anchor="lm",
                stroke_width=max(3, size // 14) if stroke else 0, stroke_fill=(0, 0, 0, alpha))
    im.alpha_composite(layer)
    return x0, f.getlength(text)


def words(im, text, fontfile, size, cx, cy, frame, word_frames, highlight):
    from PIL import Image, ImageDraw, ImageFont
    ws = text.split()
    f = ImageFont.truetype(fontfile, size)
    space = f.getlength(" ")
    widths = [f.getlength(w) for w in ws]
    x = cx - (sum(widths) + space * (len(ws) - 1)) / 2
    layer = Image.new("RGBA", im.size, (0, 0, 0, 0))
    dr = ImageDraw.Draw(layer)
    for i, w in enumerate(ws):
        k = (frame - word_frames[i]) / 5
        if k > 0:
            k = min(k, 1.0)
            sc = 0.5 + 0.5 * ease_out_back(k)
            fs = max(int(size * sc), 8)
            fw = ImageFont.truetype(fontfile, fs)
            col = (255, 212, 0) if (highlight and i == len(ws) - 1) else (255, 255, 255)
            a = int(255 * min(1, k * 2))
            dr.text((x + widths[i] / 2, cy), w, font=fw, fill=col + (a,), anchor="mm",
                    stroke_width=max(3, fs // 12), stroke_fill=(0, 0, 0, a))
        x += widths[i] + space
    im.alpha_composite(layer)


_SMOKE = {}


def smoke_sprite(seed):
    from PIL import Image, ImageDraw, ImageFilter
    import random
    if seed in _SMOKE:
        return _SMOKE[seed]
    rnd = random.Random(seed)
    im = Image.new("RGBA", (420, 420), (0, 0, 0, 0))
    dr = ImageDraw.Draw(im)
    for _ in range(16):
        r = rnd.randint(45, 115)
        x, y = rnd.randint(110, 310), rnd.randint(110, 310)
        g = rnd.randint(150, 215)
        dr.ellipse([x - r, y - r, x + r, y + r], fill=(g, g, g, rnd.randint(70, 140)))
    im = im.filter(ImageFilter.GaussianBlur(26))
    _SMOKE[seed] = im
    return im


def draw_smoke(im, cx, cy, age, max_age, size, seed, rise=3.0):
    if age < 0 or age > max_age:
        return
    k = age / max_age
    sp = smoke_sprite(seed)
    d = max(int(size * (0.55 + 0.95 * k ** 0.6)), 4)
    sp = sp.resize((d, d))
    a = sp.getchannel("A").point(lambda v: min(255, int(v * 1.6 * (1 - k) ** 1.4)))
    sp.putalpha(a)
    im.alpha_composite(sp, (int(cx - d / 2), int(cy - d / 2 - rise * age)))


def draw_flash(im, cx, cy, age, size=70):
    from PIL import Image, ImageDraw, ImageFilter
    if age < 0 or age > 2:
        return
    a = int(255 * (1 - age / 3))
    layer = Image.new("RGBA", (size * 3, size * 3), (0, 0, 0, 0))
    dr = ImageDraw.Draw(layer)
    c = size * 1.5
    dr.ellipse([c - size, c - size, c + size, c + size], fill=(255, 210, 90, a // 2))
    pts = []
    import math
    for j in range(16):
        r = size * (1.25 if j % 2 == 0 else 0.45)
        ang = j * math.pi / 8 + age * 0.4
        pts.append((c + r * math.cos(ang), c + r * math.sin(ang)))
    dr.polygon(pts, fill=(255, 245, 200, a))
    layer = layer.filter(ImageFilter.GaussianBlur(3))
    im.alpha_composite(layer, (int(cx - c), int(cy - c)))


def glyph(ch, fontfile, size, fill):
    from PIL import Image, ImageDraw, ImageFont
    f = ImageFont.truetype(fontfile, size)
    sw = max(3, size // 14)
    l, t, r, b = f.getbbox(ch, stroke_width=sw)
    g = Image.new("RGBA", (r - l + 4, b - t + 4), (0, 0, 0, 0))
    ImageDraw.Draw(g).text((2 - l, 2 - t), ch, font=f, fill=tuple(fill[:3]) + (255,), stroke_width=sw, stroke_fill=(0, 0, 0, 255))
    return g, f


def place_letters(im, text, fontfile, size, fill, cx, cy, spec):
    from PIL import ImageFont
    f = ImageFont.truetype(fontfile, size)
    x0 = cx - f.getlength(text) / 2
    centers = []
    for i, ch in enumerate(text):
        x = x0 + f.getlength(text[:i]) + f.getlength(ch) / 2
        centers.append((x, cy))
        sc, dy, rot, alpha = spec(i)
        if alpha <= 0 or ch == " ":
            continue
        g, _ = glyph(ch, fontfile, max(int(size * sc), 8), fill)
        if rot:
            g = g.rotate(rot, expand=True, resample=3)
        if alpha < 255:
            g.putalpha(g.getchannel("A").point(lambda v: v * alpha // 255))
        im.alpha_composite(g, (int(x - g.width / 2), int(cy + dy - g.height / 2)))
    return centers, x0, f.getlength(text)


def target_sheet(w, h):
    from PIL import Image, ImageDraw, ImageFilter
    im = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    dr = ImageDraw.Draw(im)
    dr.rounded_rectangle([6, 6, w - 6, h - 6], radius=18, fill=(238, 229, 206, 255), outline=(40, 32, 28, 255), width=6)
    cx, cy = w / 2, h / 2
    for k, r in enumerate(range(int(h * 0.48), 10, -int(h * 0.08))):
        rx = r * 2.1
        col = (200, 45, 40, 70) if k % 2 == 0 else (40, 32, 28, 55)
        dr.ellipse([cx - rx, cy - r, cx + rx, cy + r], outline=col, width=5)
    dr.ellipse([cx - 14, cy - 14, cx + 14, cy + 14], fill=(200, 45, 40, 70))
    dr.line([cx, 18, cx, h - 18], fill=(40, 32, 28, 60), width=3)
    dr.line([18, cy, w - 18, cy], fill=(40, 32, 28, 60), width=3)
    band = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    ImageDraw.Draw(band).rounded_rectangle([30, h * 0.12, w - 30, h * 0.88], radius=20, fill=(238, 229, 206, 215))
    band = band.filter(ImageFilter.GaussianBlur(10))
    im.alpha_composite(band)
    shadow = Image.new("RGBA", (w + 40, h + 40), (0, 0, 0, 0))
    ImageDraw.Draw(shadow).rounded_rectangle([20, 26, w + 20, h + 26], radius=18, fill=(0, 0, 0, 150))
    shadow = shadow.filter(ImageFilter.GaussianBlur(12))
    shadow.alpha_composite(im, (20, 20))
    return shadow


def hole_points(label, fontfile, size, w, h, step=11):
    import random
    from PIL import Image, ImageDraw, ImageFont
    f = ImageFont.truetype(fontfile, size)
    m = Image.new("L", (w, h), 0)
    ImageDraw.Draw(m).text((w / 2, h / 2), label, font=f, fill=255, anchor="mm")
    x0 = w / 2 - f.getlength(label) / 2
    bounds = [x0 + f.getlength(label[:i + 1]) for i in range(len(label))]
    rnd = random.Random(11)
    per = [[] for _ in label]
    px = m.load()
    for y in range(0, h, step):
        for x in range(0, w, step):
            jx, jy = x + rnd.randint(-1, 1), y + rnd.randint(-1, 1)
            if 0 <= jx < w and 0 <= jy < h and px[jx, jy] > 140:
                j = next((i for i, b in enumerate(bounds) if jx <= b), len(label) - 1)
                per[j].append((jx, jy))
    for lst in per:
        rnd.shuffle(lst)
    ink = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    ImageDraw.Draw(ink).text((w / 2, h / 2), label, font=f, fill=(200, 40, 35, 110), anchor="mm")
    slices, prev = [], 0
    for b in bounds:
        box = (int(prev), 0, min(int(b) + 1, w), h)
        slices.append((box, ink.crop(box)))
        prev = b
    return per, slices


def draw_hole(dr, x, y, r=4):
    dr.ellipse([x - r - 2, y - r - 2, x + r + 2, y + r + 2], fill=(150, 120, 90, 190))
    dr.ellipse([x - r, y - r, x + r, y + r], fill=(22, 16, 12, 255))


def perspective_coeffs(dst, src):
    import numpy as np
    m = []
    for (x, y), (u, v) in zip(dst, src):
        m.append([x, y, 1, 0, 0, 0, -u * x, -u * y])
        m.append([0, 0, 0, x, y, 1, -v * x, -v * y])
    a = np.array(m, dtype=float)
    b = np.array(src, dtype=float).reshape(8)
    return np.linalg.solve(a, b).tolist()


def fallen_board(sheet, theta, bottom_y, canvas=(1080, 1000)):
    import math
    from PIL import Image
    W, H = sheet.size
    c, sn = math.cos(theta), math.sin(theta)
    bx0, bx1 = canvas[0] / 2 - W / 2, canvas[0] / 2 + W / 2
    top = bottom_y - H * c
    inset = W * 0.16 * sn
    dst = [(bx0 + inset, top), (bx1 - inset, top), (bx1, bottom_y), (bx0, bottom_y)]
    src = [(0, 0), (W, 0), (W, H), (0, H)]
    out = sheet.transform(canvas, Image.PERSPECTIVE, perspective_coeffs(dst, src), resample=Image.BICUBIC)
    if sn > 0:
        shade = Image.new("RGBA", canvas, (0, 0, 0, 0))
        shade.putalpha(out.getchannel("A").point(lambda v: int(v * 0.45 * sn)))
        out.alpha_composite(shade)
    return out


def label_timeline(label, reality):
    n = len(label)
    if not reality:
        fire = [7 + 3 * j for j in range(n)]
        return {"fire": fire, "clicks": [], "puff": None, "reveal": None, "done": fire[-1] + 6}
    return {"fire": [], "clicks": [2, 9], "puff": None, "fall": 15, "impact": 27, "reveal": 31, "done": 50}


def motion_layers(folder, label, color, caption, credit, handle, reality, shots=()):
    import math, random
    from PIL import Image, ImageDraw
    lf, tf = font("label"), font("text")
    folder.mkdir(parents=True, exist_ok=True)
    lsize = fit_font(lf, label, 210, 900)
    csize = fit_font(tf, caption, 68) if caption else 68
    n_words = len(caption.split()) if caption else 0
    tl = label_timeline(label, reality)
    word_frames = []
    usable = [t for t in shots if t >= 0.25 and t * 30 > (tl["done"] if reality else 6)]
    for w in range(n_words):
        if w < len(usable):
            word_frames.append(int(usable[w] * 30))
        else:
            word_frames.append((word_frames[-1] + 4) if word_frames else tl["done"] + 4 * w)
    intro = max(60, tl["done"] + 10, (max(word_frames) + 10) if word_frames else 0)
    rnd = random.Random(7)
    wonky = [(rnd.uniform(-9, 9), rnd.uniform(-14, 14)) for _ in label]
    sheet_w, sheet_h = 1000, 330
    sheet_img = target_sheet(sheet_w, sheet_h)
    if not reality:
        hsize = fit_font(lf, label, 250, sheet_w - 90)
        holes, inks = hole_points(label, lf, hsize, sheet_w, sheet_h)
        holes_layer = Image.new("RGBA", (sheet_w, sheet_h), (0, 0, 0, 0))
    for i in range(intro + LOOP):
        im = Image.new("RGBA", (1080, 1920), (0, 0, 0, 0))
        phase = 2 * math.pi * max(i - intro, 0) / LOOP
        float_y = 5 * math.sin(phase)
        cy = 330 + float_y
        if not reality:
            fire = tl["fire"]
            sw_k = min(i / 6, 1.0)
            rot = -9 * (1 - ease_out_back(sw_k))
            sy = int(-260 * (1 - ease_out_back(sw_k)))
            frame_sheet = sheet_img.rotate(rot, expand=False, resample=3) if rot else sheet_img
            hd = ImageDraw.Draw(holes_layer)
            for j, pts in enumerate(holes):
                age = i - fire[j]
                if age == 0:
                    box, sl = inks[j]
                    holes_layer.alpha_composite(sl, (box[0], box[1]))
                if 0 <= age < 3:
                    chunk = pts[age * len(pts) // 3:(age + 1) * len(pts) // 3]
                    for (hx, hy) in chunk:
                        draw_hole(hd, hx, hy)
            comp = frame_sheet.copy()
            comp.alpha_composite(holes_layer, (20, 20))
            ox, oy = int(540 - comp.width / 2), int(cy - comp.height / 2 + sy)
            im.alpha_composite(comp, (max(ox, 0), oy))
            for j, pts in enumerate(holes):
                if pts:
                    lx = ox + 20 + sum(p_[0] for p_ in pts) / len(pts)
                    ly = oy + 20 + sum(p_[1] for p_ in pts) / len(pts)
                    draw_flash(im, lx, ly, i - fire[j], size=55)
                    draw_smoke(im, lx, ly - 30, i - fire[j] - 1, 22, 150, seed=j, rise=3.5)
            w = sheet_w - 80
        else:
            import math as _m
            rv, done = tl["reveal"], tl["done"]
            fall, impact = tl["fall"], tl["impact"]
            if i < fall:
                theta = 0.0
            elif i < impact:
                k = (i - fall) / (impact - fall)
                theta = 1.48 * k ** 2.2
            else:
                b = i - impact
                theta = 1.48 - (0.16 * _m.sin(b / 6 * _m.pi) * _m.exp(-b / 6) if b < 18 else 0)
            bottom = 330 + sheet_h / 2 + 10
            board = fallen_board(sheet_img, theta, bottom)
            im.alpha_composite(board, (0, 0))
            for c in tl["clicks"]:
                if 0 <= i - c < 6:
                    draw_text(im, "*click*", tf, 60, (255, 255, 255), (540, 140 - 4 * (i - c)), "mm", alpha=int(255 * (1 - (i - c) / 6)))
            for n_, dx in enumerate((-380, -120, 140, 400)):
                draw_smoke(im, 540 + dx, bottom - 10, i - impact - n_ % 2, 26, 300, seed=90 + n_, rise=1.5)
            if i >= rv:
                droop = min(max((i - rv - 10) / 14, 0), 1)
                land = min((i - rv) / 7, 1.0)
                ly = cy + 40 - 520 * (1 - ease_out_back(land))

                def spec(j):
                    rot, dy = -6 + wonky[j][0] * 0.6, wonky[j][1] * 0.5
                    if j == len(label) - 1:
                        rot += -38 * ease_out_back(droop) if droop > 0 else 0
                        dy += 26 * droop
                    return (1, dy, rot, 255)
                centers, x0, w = place_letters(im, label, lf, lsize, color, 540, ly, spec)
            else:
                from PIL import ImageFont
                f0 = ImageFont.truetype(lf, lsize)
                x0, w = 540 - f0.getlength(label) / 2, f0.getlength(label)
        bar_start = tl["done"] - 2
        bar_k = 0
        if bar_k > 0:
            y = cy + lsize * 0.42
            bw = w * (1 - (1 - bar_k) ** 3)
            ImageDraw.Draw(im).rounded_rectangle([540 - bw / 2, y, 540 + bw / 2, y + 14], radius=7, fill=tuple(color[:3]) + (255,))
        if caption:
            words(im, caption, tf, csize, 540, 1450 + 0.5 * float_y, i, word_frames, highlight=True)
        ca = int(255 * min(max((i - 12) / 8, 0), 1))
        draw_text(im, "Clip: " + credit if credit else "", tf, 40, (255, 255, 255), (540, 1640), "mm", alpha=ca)
        hx = 1030 + int(300 * (1 - ease_out_back(min(i / 10, 1.0))))
        draw_text(im, handle, tf, 42, (255, 255, 255), (hx, 110), "rt", alpha=110, fit=False)
        im.save(folder / f"f_{i:03}.png", compress_level=1)
    return intro, tl


def synth_sfx(path, tl, total):
    import numpy as np, wave
    sr = 48000
    out = np.zeros(int(sr * (total + 1)), dtype=np.float32)
    rng = np.random.default_rng(3)

    def put(sig, frame):
        i = int(frame / 30 * sr)
        n = min(len(sig), len(out) - i)
        if n > 0:
            out[i:i + n] += sig[:n]
    t = np.arange(int(sr * 0.35)) / sr
    shot = rng.uniform(-1, 1, len(t)) * np.exp(-t * 32) * 0.7 + np.sin(2 * np.pi * 65 * t) * np.exp(-t * 18) * 0.6
    shot[:240] += rng.uniform(-1, 1, 240) * 0.8
    shot = shot / np.abs(shot).max() * 0.42
    tc = np.arange(int(sr * 0.04)) / sr
    click = (rng.uniform(-1, 1, len(tc)) * 0.4 + np.sin(2 * np.pi * 2400 * tc) * 0.6) * np.exp(-tc * 260) * 0.45
    tp = np.arange(int(sr * 0.7)) / sr
    noise = rng.uniform(-1, 1, len(tp))
    lp = np.convolve(noise, np.ones(60) / 60, mode="same")
    env = np.minimum(tp / 0.03, 1) * np.exp(-tp * 5)
    puff = lp * env * 6
    puff = puff / max(np.abs(puff).max(), 1e-6) * 0.55
    for f in tl["fire"]:
        put(shot, f)
    for f in tl["clicks"]:
        put(click, f)
    if tl.get("puff") is not None:
        put(puff, tl["puff"])
    if tl.get("impact") is not None:
        tt = np.arange(int(sr * 0.9)) / sr
        thud = np.sin(2 * np.pi * (55 - 20 * tt) * tt) * np.exp(-tt * 7) * 0.8
        clack = np.sin(2 * np.pi * 320 * tt) * np.exp(-tt * 45) * 0.35
        dust = np.convolve(rng.uniform(-1, 1, len(tt)), np.ones(25) / 25, mode="same") * np.exp(-tt * 4) * 2.5
        crash = thud + clack + dust
        put(crash / np.abs(crash).max() * 0.55, tl["impact"])
    pcm = (np.clip(out, -1, 1) * 32767).astype(np.int16)
    with wave.open(str(path), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(sr)
        w.writeframes(pcm.tobytes())


def render_part(src, start, dur, label, color, caption, credit, handle, freeze, flash, dst, tmp, punch):
    label, caption = clean(label), clean(caption)
    p = probe(src)
    if start + dur > p["duration"] + 0.05:
        dur = max(p["duration"] - start, 0.5)
    total = dur + (freeze or 0)
    layers = Path(tmp) / f"layers_{label}"
    shots = detect_shots(src, start, dur) if SYNC else []
    print(f"  {label}: {len(shots)} gunshots/hits detected" + (" -> animations synced to them" if shots else " -> normal timing"))
    intro, tl = motion_layers(layers, label, color, caption, credit, handle, reality=punch, shots=shots)
    if tl.get("impact") is not None:
        shots = sorted(shots + [tl["impact"] / 30])
    sfx = Path(tmp) / f"sfx_{label}.wav"
    synth_sfx(sfx, tl if SFX else {"fire": [], "clicks": [], "puff": None}, total)
    t = "(in/30)"
    kick = "+".join(f"gte({t},{s_:.3f})*0.045*exp(-({t}-{s_:.3f})*22)" for s_ in shots) or "0"
    if punch:
        z = f"if(lt({t},0.13),1+0.12*{t}/0.13,if(gt({t},{dur:.2f}),1.12+0.2*min(({t}-{dur:.2f})/{max(freeze, 0.01):.2f},1),1.12))+{kick}"
    else:
        z = f"1+0.06*{t}/{total:.2f}+{kick}"
    vf = (f"[0:v]fps=30,tpad=stop_mode=clone:stop_duration={freeze or 0},split[a][b];"
          "[a]scale=1080:1920:force_original_aspect_ratio=increase,crop=1080:1920,boxblur=24:2,eq=brightness=-0.18[bg];"
          f"[b]scale=1920:1080:force_original_aspect_ratio=decrease,pad=1920:1080:(ow-iw)/2:(oh-ih)/2,"
          f"zoompan=z='{z}':x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':d=1:s=1080x608:fps=30[fg];"
          "[bg][fg]overlay=(W-w)/2:(H-h)/2[base];"
          f"[1:v]loop=loop=-1:size={LOOP}:start={intro},setpts=N/30/TB[mg];"
          f"[base][mg]overlay=x='{shake_expr(shots, 10, 0)}':y='{shake_expr(shots, 7, 1.3)}':shortest=1")
    if flash:
        vf += ",fade=t=in:st=0:d=0.15:color=white"
    vf += ",format=yuv420p,setsar=1[v]"
    inputs = ["-ss", f"{start:.2f}", "-t", f"{dur:.2f}", "-i", str(src), "-framerate", "30", "-i", str(layers / "f_%03d.png"),
              "-i", str(sfx)]
    sfxa = "[2:a]aformat=sample_rates=48000:channel_layouts=stereo[sx];"
    if p["audio"]:
        af = sfxa + f"[0:a]aresample=48000,aformat=channel_layouts=stereo,apad=pad_dur={freeze or 0}[ca];[ca][sx]amix=inputs=2:normalize=0:duration=first[a]"
    else:
        af = sfxa + "[3:a]aformat=channel_layouts=stereo[ca];[ca][sx]amix=inputs=2:normalize=0:duration=first[a]"
        inputs += ["-f", "lavfi", "-t", f"{total:.2f}", "-i", "anullsrc=r=48000:cl=stereo"]
    run(["ffmpeg", "-y", "-v", "error", *inputs, "-filter_complex", vf + ";" + af, "-map", "[v]", "-map", "[a]",
         *video_encoder(), "-c:a", "aac", "-b:a", "192k", "-ar", "48000", "-t", f"{total:.2f}", str(dst)])


def credit_for(clip):
    side = Path(clip).with_suffix(".json")
    if not side.exists():
        return None
    meta = json.loads(side.read_text())
    if meta["streamer"] != "me":
        approved(meta["streamer"])
    return meta.get("credit") or ""


def cmd_eor(a):
    global SYNC, SFX
    SYNC = not a.no_sync
    SFX = not a.no_sfx
    cfg = load(CONFIG, {})
    handle = a.handle if a.handle is not None else cfg.get("handle", "")
    credits = []
    for c in (a.expectation, a.reality):
        if not Path(c).exists():
            die(f"clip not found: {c}")
        cr = credit_for(c)
        if cr is None and not a.own:
            die(f"no clipper info for {Path(c).name}. If it's your own footage add --own, otherwise get it via 'clipper find'.")
        if cr and cr not in credits:
            credits.append(cr)
    credit = " | ".join(credits)

    def peak(c):
        side = Path(c).with_suffix(".json")
        if side.exists():
            return json.loads(side.read_text()).get("peak_offset")
        return None
    if a.e_start is None:
        pk = peak(a.expectation)
        a.e_start = max(pk - 4, 0) if pk is not None else 0
        a.e_dur = a.e_dur or 6
    if a.r_start is None:
        pk = peak(a.reality)
        a.r_start = max(pk - 5, 0) if pk is not None else 0
        a.r_dur = a.r_dur or 9
    e_dur = a.e_dur or min(probe(a.expectation)["duration"] - a.e_start, 8)
    r_dur = a.r_dur or min(probe(a.reality)["duration"] - a.r_start, 14)
    total = e_dur + r_dur + a.freeze
    if total > 60:
        die(f"Short would be {total:.1f}s; keep it under 60s (use --e-dur / --r-dur)")
    OUT.mkdir(exist_ok=True)
    out = Path(a.out) if a.out else OUT / f"eor_{Path(a.expectation).stem}__{Path(a.reality).stem}.mp4"
    tmp = tempfile.mkdtemp()
    p1, p2 = Path(tmp) / "p1.mp4", Path(tmp) / "p2.mp4"
    print("Rendering EXPECTATION...")
    render_part(a.expectation, a.e_start, e_dur, a.e_label, (255, 255, 255), a.e_caption, credit, handle, 0, False, p1, tmp, False)
    print("Rendering REALITY...")
    render_part(a.reality, a.r_start, r_dur, a.r_label, (255, 212, 0), a.r_caption, credit, handle, a.freeze, True, p2, tmp, True)
    lst = Path(tmp) / "list.txt"
    lst.write_text(f"file '{p1}'\nfile '{p2}'\n")
    run(["ffmpeg", "-y", "-v", "error", "-f", "concat", "-safe", "0", "-i", str(lst), "-c:v", "copy",
         "-af", "loudnorm=I=-14:TP=-1.5:LRA=11,alimiter=limit=0.85:level=false", "-c:a", "aac", "-b:a", "192k", "-movflags", "+faststart", str(out)])
    shutil.rmtree(tmp, ignore_errors=True)
    side = {"expectation": str(a.expectation), "reality": str(a.reality), "credit": credit, "length_s": round(total, 1)}
    save(out.with_suffix(".json"), side)
    print(f"OUTPUT={out}")
    print(f"\nDone: {out}  ({total:.1f}s)" + (f"\nCredit shown: {credit}  -> also put it in the video description." if credit else ""))


def main():
    ap = argparse.ArgumentParser(prog="clipper", description="Find best moments and make Expectation vs Reality Shorts")
    sub = ap.add_subparsers(dest="cmd", required=True)

    s = sub.add_parser("add-streamer", help="approve a streamer who allows clipping")
    s.add_argument("name")
    s.add_argument("--credit", required=True, help="shown on the Short, e.g. twitch.tv/name")
    s.add_argument("--permission", required=True, help="link or note showing they allow clipping")
    s.set_defaults(fn=cmd_add_streamer)

    s = sub.add_parser("streamers", help="list approved streamers")
    s.add_argument("--names", action="store_true")
    s.set_defaults(fn=cmd_streamers)

    s = sub.add_parser("find", help="find best moments in a stream (URL or local file)")
    s.add_argument("source", help="YouTube/Twitch URL, Twitch clips page, or a local .mp4")
    s.add_argument("--streamer", default="me", help="approved streamer name, or 'me' for your own footage")
    s.add_argument("--top", type=int, default=10)
    s.add_argument("--before", type=float, default=20, help="seconds kept before the peak")
    s.add_argument("--after", type=float, default=10, help="seconds kept after the peak")
    s.set_defaults(fn=cmd_find)

    s = sub.add_parser("auto", help="search YouTube, auto-clip top Creative Commons videos for EXPECTATION")
    s.add_argument("--query", default="gta 6 gameplay")
    s.add_argument("--videos", type=int, default=3, help="how many videos to clip from")
    s.add_argument("--top", type=int, default=3, help="moments per video")
    s.add_argument("--min-seconds", type=int, default=90)
    s.add_argument("--before", type=float, default=8)
    s.add_argument("--after", type=float, default=7)
    s.set_defaults(fn=cmd_auto)

    s = sub.add_parser("eor", help="make an Expectation vs Reality Short (9:16)")
    s.add_argument("expectation")
    s.add_argument("reality")
    s.add_argument("--e-start", type=float, default=None)
    s.add_argument("--e-dur", type=float)
    s.add_argument("--r-start", type=float, default=None)
    s.add_argument("--r-dur", type=float)
    s.add_argument("--e-label", default="EXPECTATION")
    s.add_argument("--r-label", default="REALITY")
    s.add_argument("--e-caption", default="")
    s.add_argument("--r-caption", default="")
    s.add_argument("--freeze", type=float, default=0.8, help="seconds to freeze on the last REALITY frame")
    s.add_argument("--handle", default=None, help="watermark text, default from config.json")
    s.add_argument("--own", action="store_true", help="clips are your own footage (no credit needed)")
    s.add_argument("--out")
    s.add_argument("--no-sync", action="store_true", help="don't sync animations to gunshots")
    s.add_argument("--no-sfx", action="store_true", help="no gun/click/puff sounds on the labels")
    s.set_defaults(fn=cmd_eor)

    a = ap.parse_args()
    a.fn(a)


if __name__ == "__main__":
    main()
