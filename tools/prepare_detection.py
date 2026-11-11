from pathlib import Path
import json, hashlib, urllib.request, concurrent.futures, collections

root = Path(__file__).resolve().parents[1]
raw = json.loads((root / "data/annotations/instances_val2017.json").read_text())
by = collections.defaultdict(list)
for a in raw["annotations"]:
    by[a["image_id"]].append(a)
images = {i["id"]: i for i in raw["images"] if i["license"] in [4, 5]}
selected = {}
# Select by metadata only, before inference. Stratify positive and negative coverage.
for group, n, predicate in [
    ("people", 40, lambda c: 1 in c),
    ("vehicles", 40, lambda c: bool(c & {3, 4, 6, 8})),
    ("negative", 40, lambda c: not c & {1, 3, 4, 6, 8}),
]:
    eligible = [
        i
        for i in images
        if predicate({a["category_id"] for a in by[i]}) and i not in selected
    ]
    eligible.sort(
        key=lambda i: hashlib.sha256(f"detection-20261111-{i}".encode()).hexdigest()
    )
    for j, i in enumerate(eligible[:n]):
        im = images[i]
        selected[i] = {
            **im,
            "group": group,
            "split": "validation" if j % 3 == 0 else "test",
            "annotations": [
                {
                    "category": a["category_id"],
                    "bbox": a["bbox"],
                    "iscrowd": a["iscrowd"],
                }
                for a in by[i]
            ],
        }
folder = root / "data/coco-sample"
folder.mkdir(exist_ok=True)


def fetch(im):
    p = folder / im["file_name"]
    if not p.exists():
        for attempt in range(3):
            try:
                urllib.request.urlretrieve(im["coco_url"], p)
                break
            except Exception:
                if attempt == 2:
                    raise
    im["sha256"] = hashlib.sha256(p.read_bytes()).hexdigest()
    return im


with concurrent.futures.ThreadPoolExecutor(max_workers=8) as ex:
    result = list(ex.map(fetch, selected.values()))
(folder / "manifest.json").write_text(
    json.dumps(
        {
            "selection": "metadata-only SHA256 order, 40 per stratum, every third validation; exact images disjoint; scene provenance unavailable",
            "licenses": raw["licenses"],
            "images": result,
        },
        indent=2,
    )
)
print("Downloaded", len(result), "COCO images", flush=True)
