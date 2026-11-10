#!/usr/bin/env python3
"""Rechnet Kamera-Zoom/-Wackeln aus einem Clip heraus (feste Perspektive wie vom Stativ).

  python3 tools/lock_camera.py in.mp4 out.mp4 [--roi 0.25]

Misst pro Bild die Verschiebung/Skalierung des Hintergrunds (obere linke und rechte Ecke,
dort ist keine Person) relativ zum ersten Bild, wendet die Umkehrung an und schneidet
alle Bilder gleichmäßig so weit zu, dass keine Ränder sichtbar werden.
"""
import sys, subprocess, cv2, numpy as np

def main(src, dst, roi=0.25):
    cap = cv2.VideoCapture(src); fps = cap.get(cv2.CAP_PROP_FPS)
    frames = []
    while True:
        ok, f = cap.read()
        if not ok: break
        frames.append(f)
    h, w = frames[0].shape[:2]
    g0 = cv2.cvtColor(frames[0], cv2.COLOR_BGR2GRAY)
    mask = np.zeros_like(g0)
    mask[:int(h * roi), :int(w * 0.3)] = 255          # obere linke Ecke
    mask[:int(h * roi), int(w * 0.7):] = 255          # obere rechte Ecke
    p0 = cv2.goodFeaturesToTrack(g0, 500, 0.01, 6, mask=mask)
    mats, scales = [], []
    for f in frames:
        g = cv2.cvtColor(f, cv2.COLOR_BGR2GRAY)
        p1, st, _ = cv2.calcOpticalFlowPyrLK(g0, g, p0, None, winSize=(31, 31), maxLevel=4)
        m, _ = cv2.estimateAffinePartial2D(p1[st == 1], p0[st == 1], method=cv2.RANSAC)  # aktuelles -> erstes Bild
        if m is None: m = mats[-1] if mats else np.float32([[1, 0, 0], [0, 1, 0]])
        mats.append(m); scales.append(np.hypot(m[0, 0], m[1, 0]))
    # glätten gegen Zittern
    M = np.array(mats); k = 5
    Ms = np.array([M[max(0, i - k):i + k + 1].mean(0) for i in range(len(M))])
    # Rand bestimmen: wie weit schrumpft der Inhalt maximal
    shrink = max(1.0, 1 / min(np.hypot(m[0, 0], m[1, 0]) for m in Ms))
    tx = max(abs(m[0, 2]) for m in Ms) / w; ty = max(abs(m[1, 2]) for m in Ms) / h
    crop = min(0.85, 1 / shrink - 2 * max(tx, ty) - 0.01)
    cw, ch = int(w * crop) // 2 * 2, int(h * crop) // 2 * 2
    x0, y0 = (w - cw) // 2, (h - ch) // 2
    p = subprocess.Popen(["ffmpeg", "-v", "error", "-y", "-f", "rawvideo", "-pix_fmt", "bgr24", "-s", f"{cw}x{ch}",
                          "-r", str(fps), "-i", "-", "-vf", "scale=1080:1920:flags=lanczos", "-c:v", "libx264",
                          "-preset", "slow", "-crf", "17", "-pix_fmt", "yuv420p", "-movflags", "+faststart", dst],
                         stdin=subprocess.PIPE)
    for f, m in zip(frames, Ms):
        out = cv2.warpAffine(f, m, (w, h), flags=cv2.INTER_LANCZOS4, borderMode=cv2.BORDER_REFLECT)
        p.stdin.write(out[y0:y0 + ch, x0:x0 + cw].tobytes())
    p.stdin.close(); p.wait()
    print(f"Zoom vorher {min(scales):.3f}–{max(scales):.3f}, Zuschnitt {crop:.3f}")

if __name__ == "__main__":
    a = sys.argv[1:]
    main(a[0], a[1], float(a[3]) if len(a) > 3 else 0.25)
