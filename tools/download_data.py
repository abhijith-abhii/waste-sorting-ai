from pathlib import Path
import urllib.request, zipfile, concurrent.futures, hashlib, json, time

root = Path(__file__).resolve().parents[1] / "data"
root.mkdir(exist_ok=True)
items = {
    "trashnet.zip": "https://huggingface.co/datasets/garythung/trashnet/resolve/94cd17e/dataset-resized.zip",
    "coco-annotations.zip": "http://images.cocodataset.org/annotations/annotations_trainval2017.zip",
}


def fetch(item):
    name, url = item
    p = root / name
    if not p.exists():
        print("Downloading", name, flush=True)
        urllib.request.urlretrieve(url, p)
    print(
        name, p.stat().st_size, hashlib.sha256(p.read_bytes()).hexdigest(), flush=True
    )
    with zipfile.ZipFile(p) as z:
        for info in z.infolist():
            if (
                name.startswith("trash")
                and info.filename.startswith("dataset-resized/")
                or info.filename == "annotations/instances_val2017.json"
            ):
                if ".." not in Path(info.filename).parts:
                    z.extract(info, root)


with concurrent.futures.ThreadPoolExecutor(max_workers=2) as ex:
    for value in ex.map(fetch, items.items()):
        pass
