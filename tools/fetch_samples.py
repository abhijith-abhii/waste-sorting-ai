from pathlib import Path
import json, urllib.request

root = Path(__file__).resolve().parents[1]
for item in json.loads((root / "samples/catalog.json").read_text()):
    if "url" in item:
        urllib.request.urlretrieve(item["url"], root / "samples" / item["file"])
print("Sample inputs ready")
