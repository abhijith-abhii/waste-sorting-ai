from pathlib import Path
import os, json, hashlib, shutil

root = Path(__file__).resolve().parents[1]
os.environ["YOLO_CONFIG_DIR"] = str(root / "ultralytics-config")
os.environ["TORCH_HOME"] = str(root / "torch-cache")
(root / 'ultralytics-config').mkdir(exist_ok=True)
import torch
from torchvision.models import mobilenet_v3_small, MobileNet_V3_Small_Weights
from ultralytics import YOLO

torch.set_num_threads(2)
models = root / "models"
models.mkdir(exist_ok=True)
os.chdir(models)
yolo = YOLO("yolo11n.pt")
for size in [320, 640]:
    out = yolo.export(
        format="onnx", imgsz=size, opset=17, simplify=False, dynamic=False, device="cpu"
    )
    shutil.copy2(out, models / f"detector-{size}.onnx")
m = mobilenet_v3_small(weights=MobileNet_V3_Small_Weights.IMAGENET1K_V1).eval()
features = torch.nn.Sequential(m.features, m.avgpool, torch.nn.Flatten(1))
torch.onnx.export(
    features,
    torch.zeros(1, 3, 224, 224),
    str(models / "mobilenet_features.onnx"),
    input_names=["images"],
    output_names=["features"],
    dynamic_axes={"images": {0: "batch"}, "features": {0: "batch"}},
    opset_version=17,
)
records = [
    {
        "file": p.name,
        "bytes": p.stat().st_size,
        "sha256": hashlib.sha256(p.read_bytes()).hexdigest(),
    }
    for p in models.glob("*.onnx")
]
(models / "manifest.json").write_text(json.dumps(records, indent=2))
print("Models exported", records, flush=True)
