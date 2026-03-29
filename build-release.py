"""
Build release ZIP for NQNghia Tools.
Run: python build-release.py
"""
import os
import zipfile

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
VERSION = "1.0.0"
ZIP_NAME = f"NQNghia-Tools-v{VERSION}.zip"

# Files/folders to include
INCLUDE = [
    "index.html",
    "style.css",
    "app.js",
    "api_server.py",
    "video_downloader.py",
    "run.py",
    "tools/",
]

# Files/folders to exclude
EXCLUDE = {
    "__pycache__", "downloads", "temp", ".git",
    "build-release.py", ".env", "node_modules",
}

def should_include(path):
    parts = path.replace("\\", "/").split("/")
    return not any(ex in parts for ex in EXCLUDE)

def build():
    zip_path = os.path.join(BASE_DIR, ZIP_NAME)
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
        for item in INCLUDE:
            full = os.path.join(BASE_DIR, item)
            if os.path.isfile(full):
                zf.write(full, f"NQNghia-Tools/{item}")
                print(f"  + {item}")
            elif os.path.isdir(full):
                for root, dirs, files in os.walk(full):
                    for f in files:
                        filepath = os.path.join(root, f)
                        arcname = os.path.relpath(filepath, BASE_DIR)
                        if should_include(arcname):
                            zf.write(filepath, f"NQNghia-Tools/{arcname}")
                            print(f"  + {arcname}")

    size_mb = os.path.getsize(zip_path) / 1024 / 1024
    print(f"\nRelease: {ZIP_NAME} ({size_mb:.1f} MB)")

if __name__ == "__main__":
    build()
