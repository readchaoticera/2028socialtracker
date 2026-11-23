#!/usr/bin/env python3
"""Download each candidate's X profile picture into assets/avatars/<id>.jpg (96x96 thumbnails).

  python3 scripts/fetch_avatars.py            # only candidates without a picture yet
  python3 scripts/fetch_avatars.py --all      # refresh every picture
  python3 scripts/fetch_avatars.py rubio      # refresh one (or several) by candidate id
Pictures are cropped around the detected face (needs opencv-python-headless<5); data/avatar_crops.json
holds manual crops for photos where detection picks the wrong face.

build.py embeds these into the page, so they ship with it (no external image requests).
"""
import io, json, sys, time, urllib.request
from pathlib import Path
from PIL import Image

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "assets/avatars"
CROPS = {}
UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36"


def get(url, tries=4):
    for i in range(tries):
        try:
            with urllib.request.urlopen(urllib.request.Request(url, headers={"User-Agent": UA}), timeout=30) as r:
                return r.read()
        except Exception:  # noqa: BLE001
            if i == tries - 1:
                raise
            time.sleep(2 * (i + 1))


def face_box(img):
    """Square crop centred on the largest detected face (about 2.4x the face width), so faces stay
    recognisable in a small circle. Falls back to a centre crop if OpenCV is missing or finds no face."""
    w, h = img.size
    try:
        import cv2, numpy as np
        gray = cv2.cvtColor(np.array(img), cv2.COLOR_RGB2GRAY)
        det = cv2.CascadeClassifier(cv2.data.haarcascades + "haarcascade_frontalface_default.xml")
        faces = det.detectMultiScale(gray, scaleFactor=1.1, minNeighbors=6, minSize=(max(20, w // 20),) * 2)
        if len(faces):
            fx, fy, fw, fh = max(faces, key=lambda f: f[2] * f[3])
            side = min(int(fw * 2.4), w, h)
            cx, cy = fx + fw / 2, fy + fh * 0.58  # a little below centre so the chin and shoulders show
            x0 = int(min(max(cx - side / 2, 0), w - side))
            y0 = int(min(max(cy - side / 2, 0), h - side))
            return (x0, y0, x0 + side, y0 + side), "face crop"
    except ImportError:
        pass
    s = min(w, h)
    return ((w - s) // 2, (h - s) // 2, (w + s) // 2, (h + s) // 2), "centre crop"


def main():
    refresh = "--all" in sys.argv
    OUT.mkdir(parents=True, exist_ok=True)
    cfg = json.loads((ROOT / "data/candidates.json").read_text())
    global CROPS
    crops_file = ROOT / "data/avatar_crops.json"
    CROPS = {k: v for k, v in json.loads(crops_file.read_text()).items() if not k.startswith("_")} if crops_file.exists() else {}
    only = [a for a in sys.argv[1:] if not a.startswith("--")]
    for c in cfg["candidates"]:
        dest = OUT / f"{c['id']}.jpg"
        if only and c["id"] not in only:
            continue
        if dest.exists() and not refresh and not only:
            continue
        handle = (c["accounts"].get("x") or {}).get("handle", "").lstrip("@")
        if not handle:
            print(f"{c['id']}: no X handle, skipped")
            continue
        try:
            user = json.loads(get(f"https://api.fxtwitter.com/{handle}"))["user"]
            url = user["avatar_url"].replace("_normal.", "_400x400.").replace("_bigger.", "_400x400.")
            img = Image.open(io.BytesIO(get(url))).convert("RGB")
            if c["id"] in CROPS:
                cx, cy, size = CROPS[c["id"]]
                w, h = img.size
                side = int(size * min(w, h))
                x0 = int(min(max(cx * w - side / 2, 0), w - side)); y0 = int(min(max(cy * h - side / 2, 0), h - side))
                box, how = (x0, y0, x0 + side, y0 + side), "manual crop"
            else:
                box, how = face_box(img)
            img = img.crop(box).resize((96, 96), Image.LANCZOS)
            img.save(dest, "JPEG", quality=82, optimize=True)
            print(f"{c['id']}: saved, {how} ({dest.stat().st_size // 1024} KB)")
        except Exception as e:  # noqa: BLE001
            print(f"{c['id']}: failed ({e})")


if __name__ == "__main__":
    main()
