#!/usr/bin/env python3
"""Bild-/Video-Erzeugung über ElevenLabs Flows (Gemini 3 Pro Image, Seedance 2, Veo 3.1).

  from gen_media import image, video
  image("prompt", out="x.png", refs=["a.png"], aspect="9:16")
  video("prompt", out="x.mp4", start="x.png", audio="line.mp3", model="bytedance-seedance-v2")
"""
import base64, json, mimetypes, os, sys, time, urllib.request, urllib.error
from pathlib import Path

API = "https://api.elevenlabs.io"
HDR = {"Content-Type": "application/json", "xi-api-key": os.environ.get("ELEVENLABS_API_KEY", "proxy")}


def _req(method, path, body=None):
    r = urllib.request.Request(API + path, method=method, headers=HDR,
                               data=json.dumps(body).encode() if body is not None else None)
    try:
        with urllib.request.urlopen(r, timeout=300) as resp:
            return json.loads(resp.read())
    except urllib.error.HTTPError as e:
        raise RuntimeError(f"ElevenLabs {e.code}: {e.read().decode()[:600]}")


def ref(path_or_gen):
    """Datei -> inline_base64, 'gen:<id>' -> generation reference."""
    if str(path_or_gen).startswith("gen:"):
        return {"type": "generation", "generation_id": str(path_or_gen)[4:]}
    p = Path(path_or_gen)
    mime = mimetypes.guess_type(p.name)[0] or "image/png"
    if p.suffix == ".mp3":
        mime = "audio/mpeg"
    return {"type": "inline_base64", "content_base64": base64.b64encode(p.read_bytes()).decode(), "mime_type": mime}


def _wait(kind, gid, out, timeout=1800):
    t0 = time.time()
    while time.time() - t0 < timeout:
        r = _req("GET", f"/v1/flows/{kind}/{gid}")
        if r["status"] == "completed":
            urllib.request.urlretrieve(r["content_url"], out)
            return gid
        if r["status"] == "failed":
            raise RuntimeError(f"{kind} {gid} fehlgeschlagen: {r.get('failure_reason')} – {r.get('error_message')}")
        time.sleep(5)
    raise TimeoutError(f"{kind} {gid} Timeout")


def image(prompt, out, refs=(), aspect="9:16", model="gemini-3-pro-image", resolution="2K"):
    body = {"model_id": model, "prompt": prompt, "aspect_ratio": aspect}
    if model.startswith("gemini-3"):
        body["resolution"] = resolution
    if refs:
        body["images"] = [ref(r) for r in refs]
    gid = _req("POST", "/v1/flows/image", body)["id"]
    return _wait("image", gid, out)


def video(prompt, out, start=None, refs=(), audio=None, model="bytedance-seedance-v2", duration=5,
          aspect="9:16", resolution="720p", sound=False):
    body = {"model_id": model, "prompt": prompt, "aspect_ratio": aspect, "duration_secs": duration,
            "resolution": resolution, "generate_audio": sound}
    if start:
        body["start_frame"] = ref(start)
    if refs:
        body["images"] = [ref(r) for r in refs]
    if audio:
        body["audios"] = [ref(audio)]
    gid = _req("POST", "/v1/flows/video", body)["id"]
    return _wait("video", gid, out)


if __name__ == "__main__":
    kind, prompt, out, *refs = sys.argv[1:]
    print((image if kind == "image" else video)(prompt, out, refs) if kind == "image" else video(prompt, out, start=refs[0] if refs else None))
