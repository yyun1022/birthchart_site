import os
import sys
import urllib.request

BASE = "https://www.astro.com/ftp/swisseph/ephe/"
OUTDIR = os.environ.get("SWEPHE_PATH", "ephe")

# “Big download” (practical): 1 BCE – 5999 CE
# Files are in 600-year blocks. See Swiss Ephemeris docs for naming scheme.  :contentReference[oaicite:3]{index=3}
BLOCKS = ["00","06","12","18","24","30","36","42","48","54"]

FILES = []
for b in BLOCKS:
    FILES.append(f"sepl_{b}.se1")  # planetary
    FILES.append(f"semo_{b}.se1")  # moon

def download(url: str, dest: str):
    os.makedirs(os.path.dirname(dest), exist_ok=True)
    if os.path.exists(dest) and os.path.getsize(dest) > 0:
        print(f"[skip] {dest}")
        return
    print(f"[get ] {url}")
    urllib.request.urlretrieve(url, dest)

def main():
    os.makedirs(OUTDIR, exist_ok=True)

    failed = []
    for fn in FILES:
        url = BASE + fn
        dest = os.path.join(OUTDIR, fn)
        try:
            download(url, dest)
        except Exception as e:
            failed.append((fn, str(e)))

    if failed:
        print("\nSome downloads failed:")
        for fn, err in failed:
            print(f" - {fn}: {err}")
        sys.exit(1)

    print("\nEphemeris download complete.")
    print("Files in:", OUTDIR)

if __name__ == "__main__":
    main()
