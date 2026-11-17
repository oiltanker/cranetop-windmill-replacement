"""Build/deploy: copy mod/ into the local Timberborn mods folder.

Usage:
    python build.py [--mods-dir DIR] [--folder-name NAME]
"""
import argparse
import os
import shutil
from pathlib import Path

FOLDER_NAME = "cranetop-windmill-replacement"
VERSION_DIR = "version-1.1"
APP_ID = "1062090"


def default_mods_dir():
    home = Path.home()
    documents = home / "Documents" / "Timberborn" / "Mods"
    if os.name != "nt":
        # SteamOS/Linux: the game usually runs through Proton, whose prefix
        # carries its own Documents directory for local mods.
        proton = (home / ".steam" / "steam" / "steamapps" / "compatdata" /
                  APP_ID / "pfx" / "drive_c" / "users" / "steamuser" /
                  "Documents" / "Timberborn" / "Mods")
        if proton.is_dir():
            return proton
    return documents


def preview_source(repo):
    """Preferred preview: an already-compressed JPEG if present, else the PNG source."""
    for name in ("preview.jpg", "preview.jpeg"):
        p = repo / name
        if p.is_file():
            return p
    p = repo / "preview.png"
    return p if p.is_file() else None


def write_thumbnail(preview, dst):
    """The upload panel requires thumbnail.png/jpg < 1 MB in the mod directory root.

    A pre-compressed JPEG under the limit is copied verbatim (no recompression);
    anything else is converted/downscaled into JPEG.
    """
    if preview.suffix.lower() in (".jpg", ".jpeg") and preview.stat().st_size < 1_000_000:
        shutil.copyfile(preview, dst)
        print(f"thumbnail copied as-is: {dst.stat().st_size} bytes")
        return
    try:
        from PIL import Image
    except ImportError:
        print("WARNING: Pillow missing and no sub-1MB preview JPEG - no thumbnail written")
        return
    img = Image.open(preview).convert("RGB")
    quality = 90
    while True:
        img.save(dst, quality=quality, optimize=True)
        if dst.stat().st_size < 1_000_000 or quality <= 60:
            break
        quality -= 10
    if dst.stat().st_size >= 1_000_000:
        while dst.stat().st_size >= 1_000_000 and min(img.size) > 64:
            img = img.resize((img.width * 3 // 4, img.height * 3 // 4), Image.LANCZOS)
            img.save(dst, quality=90, optimize=True)
    print(f"thumbnail {dst.stat().st_size} bytes, {img.size[0]}x{img.size[1]}, q{quality}")


def main():
    repo = Path(__file__).resolve().parent
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--mods-dir", type=Path, default=default_mods_dir(),
                        help="Timberborn mods directory (default: auto-detected)")
    parser.add_argument("--folder-name", default=FOLDER_NAME)
    args = parser.parse_args()

    src = repo / "mod"
    if not src.is_dir():
        raise SystemExit(f"missing {src}")
    dst = args.mods_dir / args.folder_name / VERSION_DIR
    if dst.exists():
        shutil.rmtree(dst)
    shutil.copytree(src, dst)
    preview = preview_source(repo)
    root = dst.parent
    if preview:
        # thumbnail lives in the deployment directory root, not in version dirs
        for stale in root.glob("thumbnail.*"):
            stale.unlink()
        write_thumbnail(preview, root / "thumbnail.jpg")
    workshop = repo / "workshop_data.json"
    if workshop.is_file():
        # keep Steam upload metadata (ItemId etc.) in the deployment for the update flow
        shutil.copyfile(workshop, root / "workshop_data.json")
    print(f"deployed {src} -> {dst}")

    # zip distribution inside the build directory, named with the manifest version
    import json
    import zipfile
    manifest = dst / "manifest.json"
    if not manifest.is_file():  # fall back to the repo manifest
        manifest = repo / "mod" / "manifest.json"
    version = json.load(manifest.open(encoding="utf-8"))["Version"]
    zip_path = repo / f"{args.folder_name}-{version}.zip"
    if zip_path.exists():
        zip_path.unlink()
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
        for p in sorted(root.rglob("*")):
            if p.is_file() and p.name != "workshop_data.json":  # Steam-local metadata
                zf.write(p, p.relative_to(root))
    print(f"zip {zip_path} ({zip_path.stat().st_size} bytes)")
    for p in sorted(dst.rglob("*")):
        if p.is_file():
            print(f"  {p.relative_to(dst)}")


if __name__ == "__main__":
    main()
