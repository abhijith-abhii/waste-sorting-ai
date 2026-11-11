from pathlib import Path
import json,sys,cv2
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from lab.inference import Detector,WasteClassifier
root=Path(__file__).resolve().parents[1];kind=json.loads((root/'project.json').read_text())['kind']
model=WasteClassifier(root/'models') if kind=='waste' else Detector(root/'models/detector-640.onnx')
print(json.dumps({'scope':'One AI-generated exploratory image; excluded from held-out metrics','result':model.predict(cv2.imread(str(root/'samples/generated-test.png')))},indent=2))
