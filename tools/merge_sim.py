#!/usr/bin/env python3
"""Merge-Physik-Video (Format wie @lastbounce.tv, eigene Grafiken), komplett lokal, ohne KI-Kosten.

  python3 tools/merge_sim.py --levels assets/merge/tiere --sounds assets/merge/sounds --out videos/merge_01/FINAL.mp4

Figuren fallen durch ein Rohr in einen leuchtenden Kreis. Zwei gleiche Figuren, die sich berühren,
verschmelzen zur nächsten Stufe (Ringe + Funken + Sound der neuen Stufe).
Stufenbilder: PNG-Dateien im Ordner --levels, alphabetisch sortiert = Stufe 1, 2, 3 …
Sounds: 01.mp3, 02.mp3 … im Ordner --sounds (Sound der Stufe, die beim Verschmelzen entsteht).
"""
import argparse, glob, math, os, random, subprocess, sys
import numpy as np
import pymunk
from PIL import Image, ImageDraw, ImageFilter

W, H, FPS, SR = 1080, 1920, 30, 44100


def args():
    a = argparse.ArgumentParser()
    a.add_argument("--levels", required=True)
    a.add_argument("--sounds", default="")
    a.add_argument("--out", required=True)
    a.add_argument("--seconds", type=float, default=46)
    a.add_argument("--seed", type=int, default=7)
    a.add_argument("--spawn", type=float, default=0.5, help="Sekunden zwischen zwei Figuren")
    a.add_argument("--ring", default="#70747c", help="Farbe des Kreises (leuchtend)")
    a.add_argument("--r1", type=float, default=50, help="Radius Stufe 1 in px")
    a.add_argument("--grow", type=float, default=1.32, help="Größenfaktor pro Stufe")
    a.add_argument("--dry", action="store_true", help="nur Physik rechnen (Seed-Suche), kein Video")
    a.add_argument("--gravity", type=float, default=1900, help="Schwerkraft (kleiner = langsamer fallen)")
    a.add_argument("--perfect", action="store_true",
                   help="genau 2^(Stufen-1) Figuren; gleiche ziehen sich an; Ende, wenn nur die letzte Stufe übrig ist")
    a.add_argument("--magnet", type=float, default=260, help="Anziehung gleicher Figuren (px/s², nur mit --perfect)")
    a.add_argument("--hold", type=float, default=2.2, help="Sekunden nach der letzten Verschmelzung bis zum Ende")
    a.add_argument("--land", default="", help="Sound beim Aufprall (z. B. assets/merge/plopp.mp3)")
    return a.parse_args()


def hex_rgb(h):
    h = h.lstrip("#"); return tuple(int(h[i:i + 2], 16) for i in (0, 2, 4))


class Scene:
    def __init__(s, o):
        s.o = o
        random.seed(o.seed)
        s.files = sorted(glob.glob(os.path.join(o.levels, "*.png")))
        s.radius = [o.r1 * o.grow ** i for i in range(len(s.files))]
        s.cx, s.cy, s.R = W / 2, 1100, 505
        s.tube = o.r1 + 18                      # halbe Rohrbreite
        s.top = s.cy - math.sqrt(s.R ** 2 - s.tube ** 2)
        s.space = pymunk.Space(); s.space.gravity = (0, o.gravity); s.space.iterations = 30
        s.balls = []                             # (shape, level)
        s.effects = []                           # dict
        s.events = []                            # (zeit, level) für Audio
        s.last_merge = 0.0
        s._walls()
        s._sprites()
        s._static_layer()

    # ---------- Physik
    def _walls(s):
        sb = s.space.static_body
        segs = []
        a0 = math.asin(s.tube / s.R)            # Öffnung oben für das Rohr
        n = 120
        pts = [(s.cx + s.R * math.sin(a), s.cy - s.R * math.cos(a))
               for a in np.linspace(a0, 2 * math.pi - a0, n)]
        for p, q in zip(pts, pts[1:]):
            segs.append(pymunk.Segment(sb, p, q, 4))
        segs.append(pymunk.Segment(sb, (s.cx - s.tube, -400), (s.cx - s.tube, s.top), 4))
        segs.append(pymunk.Segment(sb, (s.cx + s.tube, -400), (s.cx + s.tube, s.top), 4))
        for g in segs:
            g.elasticity, g.friction = 0.35, 0.5
            g.filter = pymunk.ShapeFilter(categories=0b001)
        s.space.add(*segs)
        s.outline = [(s.cx - s.tube, 0), (s.cx - s.tube, s.top)] + pts + [(s.cx + s.tube, s.top), (s.cx + s.tube, 0)]

    def add_ball(s, level, pos, vel=(0, 0)):
        r = s.radius[level]
        b = pymunk.Body(math.pi * r * r * 0.01, float("inf"))   # dreht sich nicht (Bilder bleiben aufrecht)
        b.position, b.velocity = pos, vel
        sh = pymunk.Circle(b, r); sh.elasticity, sh.friction = 0.3, 0.45
        sh.filter = pymunk.ShapeFilter(categories=0b010)
        b.pvy, b.landed = 0.0, level > 0
        s.space.add(b, sh); s.balls.append([sh, level, level > 0])  # [Form, Stufe, schon geschubst]

    def kick(s):
        """Seitlicher Zufallsschubs beim Austritt aus dem Rohr, damit sich die Figuren verteilen."""
        for bl in s.balls:
            sh, lvl, done = bl
            if not done and sh.body.position.y > s.top + sh.radius:
                sh.body.velocity += (random.choice((-1, 1)) * random.uniform(140, 380), 0)
                bl[2] = True

    def attract(s, t=0.0):
        """Gleiche Figuren ziehen sich sanft an. Steckt alles fest (1,5 s keine Verschmelzung),
        gleitet das kleinste gleiche Paar durch die anderen Figuren hindurch zueinander."""
        inside = [b for b in s.balls if b[0].body.position.y > s.top + b[0].radius]
        for sh, lvl, *_ in inside:                                   # sanfte Grund-Anziehung
            mates = [o[0] for o in inside if o[1] == lvl and o[0] is not sh]
            if not mates: continue
            m = min(mates, key=lambda o: (o.body.position - sh.body.position).length)
            d = m.body.position - sh.body.position
            if d.length > 1: sh.body.velocity += d.normalized() * s.o.magnet / FPS
        if t - s.last_merge < 1.5 or len(inside) < 2:
            return
        for lvl in sorted({b[1] for b in inside}):                   # festgefahren -> Paar befreien
            pair = [b[0] for b in inside if b[1] == lvl][:2]
            if len(pair) < 2: continue
            for sh in pair:
                sh.filter = pymunk.ShapeFilter(categories=0b100, mask=0b001)   # nur noch Wände
            a, b = pair; d = b.body.position - a.body.position
            if d.length > 1:
                a.body.velocity = d.normalized() * 520 + (0, 0); b.body.velocity = -d.normalized() * 520
            break

    def landings(s, t):
        for sh, *_ in s.balls:
            b = sh.body
            if not b.landed and b.position.y > s.top + sh.radius and b.pvy > 250 and b.velocity.y < 0.35 * b.pvy:
                b.landed = True; s.events.append((t, -1))
            b.pvy = b.velocity.y

    def merges(s, t):
        done = set(); new = []
        for i in range(len(s.balls)):
            if i in done: continue
            a, la = s.balls[i][:2]
            if a.body.position.y < s.top + s.radius[la] or la >= len(s.files) - 1: continue
            for j in range(i + 1, len(s.balls)):
                if j in done: continue
                b, lb = s.balls[j][:2]
                if lb != la or b.body.position.y < s.top + s.radius[lb]: continue
                d = (a.body.position - b.body.position).length
                if d <= a.radius + b.radius + 1.5:
                    done |= {i, j}
                    p = (a.body.position + b.body.position) / 2
                    v = (a.body.velocity + b.body.velocity) / 2 + (0, -180)
                    new.append((la + 1, p, v)); break
        if not done: return
        for k in sorted(done, reverse=True):
            sh = s.balls[k][0]; s.space.remove(sh.body, sh); s.balls.pop(k)
        for lvl, p, v in new:
            # nicht aus dem Kreis ragen lassen
            off = p - (s.cx, s.cy); lim = s.R - s.radius[lvl] - 6
            if off.length > lim: p = (s.cx, s.cy) + off.normalized() * lim
            s.add_ball(lvl, p, v)
            s.effects.append({"t": t, "p": (p.x, p.y), "r": s.radius[lvl],
                              "sparks": [(random.uniform(0, 2 * math.pi), random.uniform(150, 520)) for _ in range(26)]})
            s.events.append((t, lvl)); s.last_merge = t

    # ---------- Grafik
    def _sprites(s):
        s.spr = []
        for f, r in zip(s.files, s.radius):
            img = Image.open(f).convert("RGBA")
            d = int(2 * r * 1.08)
            img = img.resize((d, d), Image.LANCZOS)
            g = int(2 * r * 1.9)
            halo = Image.new("RGBA", (g, g), (0, 0, 0, 0))
            hd = ImageDraw.Draw(halo)
            hd.ellipse([g * 0.22, g * 0.22, g * 0.78, g * 0.78], fill=(255, 236, 200, 120))
            halo = halo.filter(ImageFilter.GaussianBlur(g * 0.12))
            halo.alpha_composite(img, ((g - d) // 2, (g - d) // 2))
            s.spr.append(halo)

    def _static_layer(s):
        col = hex_rgb(s.o.ring)
        base = Image.new("RGB", (W, H), (0, 0, 0))
        glow = Image.new("RGB", (W, H), (0, 0, 0))
        ImageDraw.Draw(glow).line(s.outline, fill=col, width=22, joint="curve")
        glow = glow.filter(ImageFilter.GaussianBlur(22))
        base = Image.fromarray(np.clip(np.asarray(base, np.float32) + np.asarray(glow, np.float32) * 1.6, 0, 255).astype(np.uint8))
        d = ImageDraw.Draw(base)
        d.line(s.outline, fill=tuple(min(255, int(c * 1.25)) for c in col), width=7, joint="curve")
        d.line(s.outline, fill=tuple(min(255, int(c * 1.55)) for c in col), width=2, joint="curve")
        s.bg = base

    def render(s, t):
        frame = s.bg.copy()
        for sh, lvl, *_ in sorted(s.balls, key=lambda x: x[1]):
            sp = s.spr[lvl]; x, y = sh.body.position
            frame.paste(sp, (int(x - sp.width / 2), int(y - sp.height / 2)), sp)
        fx = Image.new("RGBA", (W, H), (0, 0, 0, 0)); d = ImageDraw.Draw(fx)
        keep = []
        for e in s.effects:
            age = t - e["t"]
            if age > 0.7: continue
            keep.append(e); k = age / 0.7; x, y = e["p"]
            for n in range(3):                                  # Schockwellen-Ringe
                rr = e["r"] * (0.9 + 1.4 * k + 0.25 * n)
                a = int(230 * (1 - k) * (1 - 0.25 * n))
                d.ellipse([x - rr, y - rr, x + rr, y + rr], outline=(255, 255, 255, a), width=3)
            for ang, sp in e["sparks"]:                           # Funken
                px = x + math.cos(ang) * sp * age; py = y + math.sin(ang) * sp * age + 500 * age * age
                a = int(255 * (1 - k)); rr = 3.2 * (1 - k) + 1
                d.ellipse([px - rr, py - rr, px + rr, py + rr], fill=(255, 225, 150, a))
        s.effects = keep
        frame.paste(fx, (0, 0), fx)
        return frame


def load_sound(path):
    raw = subprocess.run(["ffmpeg", "-v", "error", "-i", path, "-f", "f32le", "-ac", "1", "-ar", str(SR), "-"],
                         capture_output=True).stdout
    return np.frombuffer(raw, np.float32)


def main():
    o = args()
    sc = Scene(o)
    total = int(o.seconds * FPS)
    count = 2 ** (len(sc.files) - 1) if o.perfect else 10 ** 9
    spawned, end_at = 0, None
    os.makedirs(os.path.dirname(os.path.abspath(o.out)), exist_ok=True)
    tmpv = o.out + ".video.mp4"
    if o.dry:
        ff = None
    else:
      ff = subprocess.Popen(["ffmpeg", "-v", "error", "-y", "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{W}x{H}",
                           "-r", str(FPS), "-i", "-", "-c:v", "libx264", "-preset", "medium", "-crf", "18",
                           "-pix_fmt", "yuv420p", tmpv], stdin=subprocess.PIPE)
    next_spawn, sub = 0.3, 4
    for f in range(total):
        t = f / FPS
        while t >= next_spawn and spawned < count:
            sc.add_ball(0, (sc.cx + random.uniform(-2.5, 2.5), -sc.radius[0] - 10), (0, 250))
            next_spawn += o.spawn; spawned += 1
        if o.perfect:
            sc.attract(t)
        for _ in range(sub):
            sc.space.step(1 / (FPS * sub))
        sc.kick()
        sc.landings(t)
        sc.merges(t)
        if o.perfect and end_at is None and spawned == count and len(sc.balls) == 1 and sc.balls[0][1] == len(sc.files) - 1:
            end_at = t + o.hold
        if end_at is not None and t >= end_at:
            break
        if ff:
            ff.stdin.write(sc.render(t).tobytes())
        if not o.dry and f % (FPS * 5) == 0:
            top = max((b[1] for b in sc.balls), default=0) + 1
            print(f"{t:5.1f}s  Figuren {len(sc.balls):3d}  höchste Stufe {top}", flush=True)
    if o.dry:
        lv = [l for _, l in sc.events if l >= 0]
        print(f"seed {o.seed}: höchste Stufe {max(lv, default=0) + 1}, erreicht bei {next((t for t, l in sc.events if l == max(lv)), 0):.1f}s"
              + (f", Ende bei {end_at:.1f}s" if end_at else (f", NICHT aufgegangen ({len(sc.balls)} übrig)" if o.perfect else "")))
        return
    ff.stdin.close(); ff.wait()
    dur = (f + 1) / FPS
    # Audio mischen
    audio = np.zeros(int(dur * SR) + SR, np.float32)
    snd = {}
    for t, lvl in sc.events:
        if lvl < 0:  # Aufprall
            if o.land and os.path.exists(o.land):
                snd.setdefault(-1, load_sound(o.land)); x = snd[-1] * 0.25; i = int(t * SR)
                audio[i:i + len(x)] += x[:len(audio) - i]
            continue
        p = os.path.join(o.sounds, f"{lvl + 1:02d}.mp3") if o.sounds else ""
        if not p or not os.path.exists(p): continue
        snd.setdefault(lvl, load_sound(p))
        x = snd[lvl] * (0.55 + 0.05 * lvl); i = int(t * SR)
        audio[i:i + len(x)] += x[:len(audio) - i]
    peak = np.abs(audio).max() or 1
    audio = (audio / peak * 0.9)[:int(dur * SR)]
    wav = o.out + ".wav"
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "f32le", "-ar", str(SR), "-ac", "1", "-i", "-", wav],
                   input=audio.tobytes())
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", tmpv, "-i", wav, "-c:v", "copy", "-c:a", "aac", "-b:a", "192k",
                    "-ar", str(SR), "-ac", "2", "-af", "loudnorm=I=-14:TP=-1.5", "-shortest", "-movflags", "+faststart", o.out],
                   check=True)
    os.remove(tmpv); os.remove(wav)
    print("fertig:", o.out, "| Verschmelzungen:", len(sc.events),
          "| höchste Stufe:", max((l for _, l in sc.events), default=0) + 1, f"| Länge {dur:.1f}s",
          f"| übrig: {len(sc.balls)}")


if __name__ == "__main__":
    main()
