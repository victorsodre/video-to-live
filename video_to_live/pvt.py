"""Photos-style .pvt bundle: still + MOV + metadata.plist."""

from __future__ import annotations

import shutil
import zipfile
from pathlib import Path

PLIST = """\
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
	<key>PFVideoComplementMetadataVersionKey</key>
	<string>1</string>
</dict>
</plist>
"""


def write_pvt(bundle: Path, still: Path, movie: Path) -> None:
    if bundle.exists():
        shutil.rmtree(bundle)
    bundle.mkdir(parents=True)
    shutil.copy2(still, bundle / still.name)
    shutil.copy2(movie, bundle / movie.name)
    (bundle / "metadata.plist").write_text(PLIST, encoding="utf-8")


def zip_pvt(bundle: Path, zip_path: Path) -> Path:
    zip_path.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(zip_path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for child in sorted(bundle.iterdir()):
            archive.write(child, arcname=f"{bundle.name}/{child.name}")
    return zip_path
