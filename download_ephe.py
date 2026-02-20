import os
import sys
import gzip
import shutil
import urllib.request

# IMPORTANT:
# raw.githubusercontent.com does NOT list directories.
# You must download each file by its full path.

BASE = "https://raw.githubusercontent.com/aloistr/swisseph/master/ephe/"
OUTDIR = os.environ.get("SWEPHE_PATH", "ephe")

# “Big but practical”: 1 BCE – 5999 CE (600-year blocks)
BLOCKS = ["00","06","12","18","24","30","36","42","48","54"]
FILES = []
for b in BLOCKS:
    FILES.append(f"sepl_{b}.se1")  # planets
    FILES.append(f"semo_{b}.se1")  # moon

def http_get(url: str, dest: str):
    os.makedirs(os.path.dirname(dest), exist_ok=True)
    if os.path.exists(dest) and os.path.getsize(dest) > 0:
        print(f"[skip] {dest}")
        return True
    print(f"[get ] {url}")
    req = urllib.request.Request(url, headers={"User-Agent": "birthchart-render/1.0"})
    try:
        with urllib.request.urlopen(req, timeout=60) as r, open(dest, "wb") as f:
            f.write(r.read())
        return True
    except Exception as e:
        print(f"[miss] {url} ({e})")
        return False

def gunzip_file(gz_path: str, out_path: str):
    print(f"[gunz] {os.path.basename(gz_path)} -> {os.path.basename(out_path)}")
    with gzip.open(gz_path, "rb") as f_in, open(out_path, "wb") as f_out:
        shutil.copyfileobj(f_in, f_out)
    os.remove(gz_path)

def main():
    os.makedirs(OUTDIR, exist_ok=True)

    missing = []
    for fn in FILES:
        dest = os.path.join(OUTDIR, fn)

        # Try plain .se1 first
        ok = http_get(BASE + fn, dest)
        if ok:
            continue

        # Some distributions store compressed files. Try .se1.gz and decompress.
        gz_fn = fn + ".gz"
        gz_dest = dest + ".gz"
        ok2 = http_get(BASE + gz_fn, gz_dest)
        if ok2:
            gunzip_file(gz_dest, dest)
            continue

        missing.append(fn)

    if missing:
        # Don’t fail the build unless you want “strict mode”.
        # We print what’s missing so you can adjust BLOCKS or source later.
        print("\nMissing files (not found at source):")
        for fn in missing:
            print(" -", fn)
        print("\nContinuing anyway (site may not support years that need these files).")

    print("\nEphemeris ready in:", OUTDIR)

if __name__ == "__main__":
    main()
