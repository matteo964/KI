---
name: frucht-story-video
description: Erstellt deutsche TikTok-Story-Videos in der Nische „Frucht-/Gemüse-Köpfe mit Zahl auf der Stirn“ (Stil Referenz 2, dunkler Luxus-Look, trockene Ping-Pong-Dialoge) inklusive Mehrteiler (Teil 1/2/3). Nutzen, wenn ein neues Video, eine neue Serie, ein Skript, eine Shotlist, ElevenLabs-Stimmen oder ein Schnitt für diesen Kanal gebraucht wird.
---

# Frucht-Story-Videos (TikTok, DE)

Grundlage: `REFERENZ_ANALYSE.md` (5 analysierte Referenzen). Pipeline: `tools/build.py`.

## 1. Format (fest)
- Figuren: menschlicher Körper, **Kopf = Obst/Gemüse**, 3D-Kino-Look (Pixar trifft Fotorealismus), dunkle Luxus-Palette.
- **Leuchtende LED-Zahl auf der Stirn** = Kontostand. Sie ist das Story-Werkzeug: Zahlen springen, zählen runter, negative Zahlen entlarven Betrüger. Pro Shot über `"displays": {"FIGUR": "48.000.000 €"}` setzen.
- Pro Teil 35–40 Zeilen, **75–90 s**, jede Zeile = ein Clip (2–4 s). Kurze, trockene Zeilen, Umgangssprache („Bro“, „Digger“).
- Duo-Dynamik: **ein Aufgeregter** (fragt, schreit, staunt) und **ein Trockener** (einsilbig, deadpan: „Ja.“, „Eben.“, „Jetzt schon.“). Running Gags zwei- bis dreimal wiederholen und im Finale umdrehen.
- Keine Untertitel, kein Outro, kein Wasserzeichen (das setzt TikTok beim Download selbst). Beim Upload das KI-Label setzen.
- Musik: **„Batida Funk Medley“ ab 0:11**, etwa 5 dB unter den Stimmen. Am besten in der TikTok-App als Sound hinzufügen (Originalton 100 %, Sound 25–30 %). Liegt `music.mp3` im Ordner, mischt `assemble` selbst ab `start_s`.

## 2. Mehrteiler (Referenzen @karolyhe)
- **Teil 1:** Konflikt in den ersten 2 s, Eskalation, endet **mitten im Satz** auf einer Enthüllung („…überschrieben an…“).
- **Teil 2/3:** setzt **in derselben Sekunde** wieder ein (erste Zeile beantwortet bzw. wiederholt den Cliffhanger), keine Zusammenfassung. Jedes Ende bringt einen neuen Twist. Das Finale löst alles auf und endet mit einem Gag.
- Setups in Teil 1 pflanzen, die erst in Teil 2/3 zünden.
- `"end_text": "Teil 2…"` im story.json blendet den Text im letzten Shot ein.
- Gemeinsame Figuren, Orte, Stil und Musik in `videos/<serie>/serie.json`, jeder Teil verweist mit `"series": "../serie.json"` darauf.
- Thema immer **eigenständig**, nicht von den Referenz-Creatorn kopieren. Schon verwendet: Schwiegervater-Test (01), Lottoschein (02).

## 3. Stimmen (vom Creator abgenommen, nicht ändern ohne Rückfrage)
ElevenLabs-Library-Stimmen (brauchen mindestens den Creator-Tarif). Das Modell pro Figur über `"model"` in `voice` setzen.

| Rolle | Stimme | voice_id | Modell |
|---|---|---|---|
| Aufgeregter Hauptcharakter (jung, männlich) | **The Fox** | `h1IssowVS2h4nL5ZbkkK` | `eleven_multilingual_v2` |
| Trockener/Reicher/Deadpan (tief, männlich) | **Heiner** | `he4iF6V8tdCa0FGloXxE` | `eleven_v3` (Tag `[deadpan]`) |
| Junge Frau (frech/süß) | **Anna** | `DEZHhPbmb8LVZmWufkCh` | `eleven_multilingual_v2` |
| Nebenrollen | Wolfgang `aZQ0ZrBshbMCU6TJwtuk` (glatt), DiMario `DQ4rTqXxHr077oQgsA9D` (laut), Willi `RjLziZNN3CXUGWjzW67v` (tief, warm), Johanna `coPfQIqaxowKv5u2s2bV` (kühle Frau), Lucy Fennek `KXxZd16DiBqt82nbarJx` | | `eleven_multilingual_v2` |

- Heiner (v3) passt am besten zum Reichen aus Referenz 2. The Fox wurde nach Gehör gewählt, weil keine Library-Stimme eindeutig passte.
- Audio-Tags wie `[deadpan]` wirken nur bei v3. Bei v2 werden sie automatisch weggelassen.
- Zahlen im Text **ausschreiben** („Achtundvierzig Millionen“), Abkürzungen ausschreiben („Doktor“ statt „Dr.“).
- `voice_tempo: 1.1` beschleunigt die Stimmen (Tonhöhe bleibt), Stille an den Enden wird gekappt, innere Pausen auf 0,2 s gekürzt.

## 4. Ablauf
```bash
# 1. Serie/Teil anlegen: serie.json (Figuren, Orte) + teilN/story.json (Shots)
python3 tools/build.py docs     videos/<serie>/teil1   # SKRIPT.md + SHOTLIST.md (Bild- und Animations-Prompts)
python3 tools/build.py voices   videos/<serie>/teil1   # ElevenLabs, ca. 1 Credit pro Zeichen
python3 tools/build.py check    videos/<serie>/teil1 --fix 3   # Whisper-Prüfung, fehlerhafte Zeilen neu
python3 tools/build.py sfx      videos/<serie>/teil1   # optional (Feld "sfx")
python3 tools/build.py assemble videos/<serie>/teil1   # out/final.mp4 (Platzhalter für fehlende Clips)
```
- Bleibt eine Zeile nach `--fix` falsch, mit dem Feld `"tts"` eine andere Schreibweise vorgeben (Beispiel: „im Meer“ → „jetzt im Meer“; „Pfirsich“ wird nie sauber erkannt, besser meiden). Danach die Datei löschen, `voices` und `check` erneut ausführen.
- Credits vorher abschätzen: `docs` gibt die Zeichenzahl aus.
- Bilder und Videos kann diese Umgebung **nicht** erzeugen. Der Creator erstellt die Clips mit den Prompts aus `SHOTLIST.md` (Figuren-Referenzbild zuerst, dann pro Shot) und legt sie als `clips/01.mp4` … ab. Danach `assemble`.
- Vorschau für den Creator: `out/final.mp4` nach `VORSCHAU_*.mp4` kopieren und mit SendUserFile schicken. Stimmen und story.json committen, `out/` ist ignoriert.
