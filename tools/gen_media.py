#!/usr/bin/env python3
"""Bild-/Video-Erzeugung über fal.ai (Queue-API). Der API-Key wird vom Proxy eingesetzt.

  from gen_media import image, video, motion
  image("prompt", "out.png", refs=["a.png"], aspect="9:16")          # Nano Banana Pro (edit, wenn refs)
  video("prompt", "out.mp4", start="bild.png", duration=5)            # Bild -> Video
  motion("out.mp4", image="person.png", ref_video="tanz.mp4")         # Kling Motion Control (Tanz übertragen)

CLI:  python3 tools/gen_media.py image "prompt" out.png [ref1.png ...]
"""
import base64, json, mimetypes, sys, time, urllib.request, urllib.error
from pathlib import Path

QUEUE = "https://queue.fal.run"
HDR = {"Content-Type": "application/json", "Authorization": "Key proxy-injected"}
LOG = Path(__file__).resolve().parent.parent / "assets" / "fal_log.jsonl"

IMAGE_MODEL = "fal-ai/nano-banana-pro"
VIDEO_MODEL = "fal-ai/kling-video/v3/standard/image-to-video"
MOTION_MODEL = "fal-ai/kling-video/v3/standard/motion-control"


def _call(method, url, body=None):
    r = urllib.request.Request(url, method=method, headers=HDR,
                               data=json.dumps(body).encode() if body is not None else None)
    try:
        with urllib.request.urlopen(r, timeout=300) as resp:
            return json.loads(resp.read())
    except urllib.error.HTTPError as e:
        raise RuntimeError(f"fal {e.code} {url}: {e.read().decode()[:800]}")


def data_uri(path):
    p = Path(path)
    mime = mimetypes.guess_type(p.name)[0] or "application/octet-stream"
    return f"data:{mime};base64,{base64.b64encode(p.read_bytes()).decode()}"


def run(model, args, timeout=1800):
    """Auftrag in die Queue stellen, warten, Ergebnis-JSON zurückgeben."""
    sub = _call("POST", f"{QUEUE}/{model}", args)
    t0 = time.time()
    while time.time() - t0 < timeout:
        st = _call("GET", sub["status_url"])
        if st.get("status") == "COMPLETED":
            res = _call("GET", sub["response_url"])
            with open(LOG, "a") as f:
                f.write(json.dumps({"t": time.strftime("%F %T"), "model": model, "request_id": sub["request_id"],
                                    "secs": round(time.time() - t0)}) + "\n")
            return res
        if st.get("status") not in ("IN_QUEUE", "IN_PROGRESS"):
            raise RuntimeError(f"fal Status: {st}")
        time.sleep(4)
    raise TimeoutError(model)


def upload(path):
    """Datei in den fal-Speicher laden (für Videos, die nicht als data-URI gehen). Gibt die öffentliche URL zurück."""
    p = Path(path)
    mime = mimetypes.guess_type(p.name)[0] or "application/octet-stream"
    init = _call("POST", "https://rest.fal.ai/storage/upload/initiate?storage_type=fal-cdn-v3",
                 {"content_type": mime, "file_name": p.name})
    req = urllib.request.Request(init["upload_url"], data=p.read_bytes(), method="PUT", headers={"Content-Type": mime})
    urllib.request.urlopen(req, timeout=300).read()
    return init["file_url"]


def _download(url, out):
    Path(out).parent.mkdir(parents=True, exist_ok=True)
    urllib.request.urlretrieve(url, out)
    return out


def image(prompt, out, refs=(), aspect="9:16", resolution="2K"):
    args = {"prompt": prompt, "aspect_ratio": aspect, "resolution": resolution, "num_images": 1,
            "output_format": "png"}
    model = IMAGE_MODEL
    if refs:
        model += "/edit"
        args["image_urls"] = [data_uri(r) for r in refs]
    res = run(model, args)
    return _download(res["images"][0]["url"], out)


def video(prompt, out, start, duration=5, model=VIDEO_MODEL, extra=None):
    args = {"prompt": prompt, "image_url": data_uri(start), "duration": str(duration), **(extra or {})}
    res = run(model, args)
    return _download(res["video"]["url"], out)


def motion(out, image, ref_video, prompt="", model=MOTION_MODEL, extra=None):
    args = {"image_url": data_uri(image), "video_url": upload(ref_video), "prompt": prompt, **(extra or {})}
    res = run(model, args)
    return _download(res["video"]["url"], out)


if __name__ == "__main__":
    kind, prompt, out, *refs = sys.argv[1:]
    if kind == "image":
        print(image(prompt, out, refs))
    else:
        print(video(prompt, out, refs[0]))
