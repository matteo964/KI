#!/usr/bin/env python3
"""Pipeline für die Frucht-Story-Videos.

  python3 tools/build.py docs     videos/01_schwiegervater   # Skript + Shotlist (Prompts) erzeugen
  python3 tools/build.py voices   videos/01_schwiegervater [--voices library|premade] [--model eleven_v3]
  python3 tools/build.py sfx      videos/01_schwiegervater   # Korkenknall etc. per ElevenLabs
  python3 tools/build.py music    videos/01_schwiegervater   # Hintergrundbeat per ElevenLabs Music
  python3 tools/build.py assemble videos/01_schwiegervater   # fertiges Video -> out/final.mp4

Ordner pro Video:
  story.json        Figuren, Orte, Shots (einzige Quelle)
  clips/01.mp4 ...  animierte Clips aus Kling/Veo/... (fehlende Clips -> Platzhalterkarte)
  voices/01.mp3 ... werden von `voices` erzeugt (fehlende -> Stille in geschätzter Länge)
  sfx/<name>.mp3    optionale Soundeffekte (Feld "sfx" im Shot)
  music.mp3         optionale Hintergrundmusik (oder eigene Datei hineinlegen)
"""
import json, os, re, subprocess, sys, textwrap, urllib.request, urllib.error
from pathlib import Path

W, H, FPS = 1080, 1920, 30
GAP = 0.15          # Pause nach jeder Zeile (Ref. 2: sehr knappes Timing)
MIN_SHOT = 1.2      # kein Clip kürzer als das
API = "https://api.elevenlabs.io"
FONT = "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"


def load(d):
    return json.loads((Path(d) / "story.json").read_text())


def run(cmd):
    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode:
        sys.exit(f"Fehler: {' '.join(cmd)}\n{r.stderr[-2000:]}")
    return r.stdout


def duration(p):
    return float(run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", str(p)]).strip())


def estimate(text):
    return max(MIN_SHOT - GAP, len(text) / 15 + 0.25)


def nr(i):
    return f"{i + 1:02d}"


def image_prompt(s, shot):
    chars = "; ".join(s["characters"][c]["prompt"] for c in shot["cast"])
    return (f"{s['style']}. {shot['camera']}. Scene: {s['locations'][shot['loc']]}. "
            f"Characters: {chars}. Action: {shot['action']}.")


# ---------------------------------------------------------------- docs
def cmd_docs(d):
    s = load(d)
    t, script, shots = 0.0, [], []
    for i, sh in enumerate(s["shots"]):
        dur = estimate(sh["text"]) + GAP
        who = s["characters"][sh["speaker"]]["name"]
        sfx = f" *({sh['sfx']})*" if sh.get("sfx") else ""
        script.append(f"| {nr(i)} | {t:5.1f}s | **{who}** | {sh['text']}{sfx} |")
        shots.append(
            f"### Shot {nr(i)} · {t:.1f}s · ~{dur:.1f}s · {sh['loc']} · {sh['camera']}\n"
            f"**{who}:** „{sh['text']}“{sfx}\n\n"
            f"**Bild-Prompt:**\n```\n{image_prompt(s, sh)}\n```\n"
            f"**Animations-Prompt (Bild → Video):**\n```\n{sh['motion']}. Subtle realistic lip movement while speaking, "
            f"cinematic, keep characters consistent, no text changes except the forehead display.\n```\n")
        t += dur
    chars = sum(len(sh["text"]) for sh in s["shots"])
    refs = "\n".join(
        f"**{c['name']}**\n```\n{s['style']}. Character reference sheet, full body front view and close-up portrait, "
        f"neutral dark studio background: {c['prompt']}.\n```\n"
        + (f"Stimme: {c['voice_note']}\n" if c.get("voice") else "")
        for c in s["characters"].values())
    locs = "\n".join(f"- **{k}:** {v}" for k, v in s["locations"].items())
    (Path(d) / "SKRIPT.md").write_text(
        f"# {s['title']} – Skript\n\nLänge ca. **{t:.0f} s**, {len(s['shots'])} Zeilen = {len(s['shots'])} Clips, "
        f"{chars} Zeichen (≈ {chars} ElevenLabs-Credits).\n\n| # | Start | Sprecher | Text |\n|---|---|---|---|\n"
        + "\n".join(script) + "\n")
    (Path(d) / "SHOTLIST.md").write_text(
        f"# {s['title']} – Shotlist\n\n## Schritt 1: Figuren-Referenzbilder\nZuerst je Figur ein Referenzbild erzeugen und "
        f"für ALLE Shots als Charakter-Referenz mitgeben (Nano Banana: Bild anhängen · Midjourney: `--cref` · "
        f"Kling: Elements), damit die Figuren überall gleich aussehen.\n\n{refs}\n## Orte\n{locs}\n\n"
        f"## Schritt 2: Shots\nFormat immer **9:16**, Clips 5 s erzeugen (wird im Schnitt gekürzt). "
        f"Dateien als `clips/01.mp4`, `clips/02.mp4` … speichern.\n\n" + "\n".join(shots))
    print(f"SKRIPT.md + SHOTLIST.md geschrieben ({len(s['shots'])} Shots, ~{t:.0f}s, {chars} Zeichen)")


# ---------------------------------------------------------------- ElevenLabs
def eleven(path, body, out):
    req = urllib.request.Request(API + path, data=json.dumps(body).encode(),
                                 headers={"Content-Type": "application/json",
                                          "xi-api-key": os.environ.get("ELEVENLABS_API_KEY", "proxy")})
    try:
        with urllib.request.urlopen(req, timeout=300) as r:
            Path(out).write_bytes(r.read())
    except urllib.error.HTTPError as e:
        sys.exit(f"ElevenLabs-Fehler {e.code}: {e.read().decode()[:400]}")


def cmd_voices(d, voices="library", model="eleven_v3"):
    s = load(d)
    out = Path(d) / "voices"
    out.mkdir(exist_ok=True)
    for i, sh in enumerate(s["shots"]):
        f = out / f"{nr(i)}.mp3"
        if f.exists():
            continue
        vc = s["characters"][sh["speaker"]]["voice"]
        voice, m = vc[voices], vc.get("model", model)  # Modell pro Figur überschreibbar
        spoken = sh.get("tts", sh["text"])
        text = f"{sh.get('tag', '')} {spoken}".strip() if m == "eleven_v3" else spoken
        print(f"{nr(i)} {sh['speaker']}: {sh['text']}")
        eleven(f"/v1/text-to-speech/{voice}?output_format=mp3_44100_128",
               {"text": text, "model_id": m, "language_code": "de"}, f)


def cmd_sfx(d):
    s = load(d)
    prompts = {"Korkenknall": "a single loud champagne cork pop followed by a short fizz"}
    (Path(d) / "sfx").mkdir(exist_ok=True)
    for name in {sh["sfx"] for sh in s["shots"] if sh.get("sfx")}:
        f = Path(d) / "sfx" / f"{name}.mp3"
        if not f.exists():
            eleven("/v1/sound-generation", {"text": prompts.get(name, name), "duration_seconds": 1.5}, f)
            print("SFX", f)


def cmd_music(d):
    s = load(d)
    eleven("/v1/music", {"prompt": s["music"]["description"], "music_length_ms": 90000,
                         "force_instrumental": True}, Path(d) / "music.mp3")
    print("music.mp3 erzeugt")


# ---------------------------------------------------------------- Schnitt
def cmd_assemble(d):
    s, d = load(d), Path(d)
    tmp = d / "out" / "seg"
    tmp.mkdir(parents=True, exist_ok=True)
    vf = f"scale={W}:{H}:force_original_aspect_ratio=increase,crop={W}:{H},fps={FPS},format=yuv420p"
    segs, missing = [], []
    for i, sh in enumerate(s["shots"]):
        raw, clip = d / "voices" / f"{nr(i)}.mp3", d / "clips" / f"{nr(i)}.mp4"
        voice = tmp / f"{nr(i)}_vo.wav"
        if raw.exists():  # Stille an den Enden kappen + Tempo anpassen (Tonhöhe bleibt)
            trim = "silenceremove=start_periods=1:start_threshold=-45dB:start_silence=0.03"
            run(["ffmpeg", "-y", "-v", "error", "-i", str(raw), "-af",
                 f"{trim},areverse,{trim},areverse,"
                 f"silenceremove=stop_periods=-1:stop_duration=0.2:stop_threshold=-45dB:stop_silence=0.2,atempo={s.get('voice_tempo', 1.0)}", "-ar", "44100", str(voice)])
        dur = (duration(voice) if voice.exists() else estimate(sh["text"])) + GAP
        dur = max(dur, MIN_SHOT)
        if clip.exists():
            vin = ["-stream_loop", "-1", "-i", str(clip)]
            vchain = vf
        else:
            missing.append(nr(i))
            card = tmp / f"{nr(i)}.txt"
            who = s["characters"][sh["speaker"]]["name"]
            card.write_text(f"SHOT {nr(i)}  ·  {sh['loc']}\n\n{who}:\n\n" + "\n".join(textwrap.wrap(sh["text"], 22)))
            vin = ["-f", "lavfi", "-i", f"color=c=0x1a1410:s={W}x{H}:r={FPS}"]
            vchain = (f"drawtext=fontfile={FONT}:textfile={card}:fontcolor=white:fontsize=64:line_spacing=18:"
                      f"x=(w-text_w)/2:y=(h-text_h)/2,format=yuv420p")
        ain = ["-i", str(voice)] if voice.exists() else ["-f", "lavfi", "-i", "anullsrc=r=44100:cl=stereo"]
        achain = "[1:a]aresample=44100,aformat=channel_layouts=stereo,apad[v]"
        sfx = d / "sfx" / f"{sh.get('sfx')}.mp3"
        extra = []
        if sh.get("sfx") and sfx.exists():
            extra = ["-i", str(sfx)]
            achain += ";[2:a]aresample=44100,aformat=channel_layouts=stereo,volume=0.8,apad[s];[v][s]amix=2:normalize=0[a]"
        else:
            achain += ";[v]anull[a]"
        out = tmp / f"{nr(i)}.mp4"
        run(["ffmpeg", "-y", "-v", "error", *vin, *ain, *extra, "-filter_complex",
             f"[0:v]{vchain}[vo];{achain}", "-map", "[vo]", "-map", "[a]", "-t", f"{dur:.3f}",
             "-c:v", "libx264", "-preset", "veryfast", "-crf", "18", "-c:a", "aac", "-b:a", "192k", "-ar", "44100", str(out)])
        segs.append(out)
    lst = tmp / "list.txt"
    lst.write_text("".join(f"file '{p.resolve()}'\n" for p in segs))
    joined = tmp / "joined.mp4"
    run(["ffmpeg", "-y", "-v", "error", "-f", "concat", "-safe", "0", "-i", str(lst), "-c", "copy", str(joined)])
    final = d / "out" / "final.mp4"
    music = d / "music.mp3"
    if music.exists():
        g = s["music"]["gain_db"]
        fc = (f"[0:a]loudnorm=I=-16:TP=-2[v];[1:a]loudnorm=I={-16 + g}:TP=-2,aformat=channel_layouts=stereo[m];"
              f"[v][m]amix=2:duration=first:normalize=0,loudnorm=I=-14:TP=-1.5[a]")
        run(["ffmpeg", "-y", "-v", "error", "-i", str(joined), "-ss", str(s["music"].get("start_s", 0)),
             "-stream_loop", "-1", "-i", str(music),
             "-filter_complex", fc, "-map", "0:v", "-map", "[a]", "-c:v", "copy", "-c:a", "aac", "-b:a", "192k",
             "-ar", "44100", str(final)])
    else:
        run(["ffmpeg", "-y", "-v", "error", "-i", str(joined), "-af", "loudnorm=I=-14:TP=-1.5", "-c:v", "copy",
             "-c:a", "aac", "-b:a", "192k", "-ar", "44100", str(final)])
    print(f"{final}  ({duration(final):.1f}s)")
    if missing:
        print(f"Platzhalter für fehlende Clips: {', '.join(missing)}")


if __name__ == "__main__":
    if len(sys.argv) < 3:
        sys.exit(__doc__)
    cmd, d, *rest = sys.argv[1:]
    opts = dict(zip([a.lstrip("-") for a in rest[::2]], rest[1::2]))
    {"docs": cmd_docs, "voices": cmd_voices, "sfx": cmd_sfx, "music": cmd_music,
     "assemble": cmd_assemble}[cmd](d, **opts)
