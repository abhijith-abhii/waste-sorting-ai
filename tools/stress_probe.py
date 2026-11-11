"""Frozen-config stress probes and complete Flask inference requests; no retuning."""
from pathlib import Path
import json,sys,time,tempfile,platform,collections
import cv2,numpy as np,psutil
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from lab.inference import WasteClassifier,Detector
from lab.web import create_app
root=Path(__file__).resolve().parents[1];out=root/'extra-evaluation';out.mkdir(exist_ok=True)
records=json.loads((root/'waste-evaluation/split-manifest.json').read_text());chosen=[]
for label in ['cardboard','glass','metal','paper','plastic','trash']:
 chosen += [r for r in records if r['split']=='test' and r['label']==label][:10]
w=WasteClassifier(root/'models');cfg=json.loads((root/'waste-evaluation/frozen-config.json').read_text());stress=[]
for i,r in enumerate(chosen):
 im=cv2.imread(str(root/'data/dataset-resized'/r['path']));im=cv2.resize(im,(256,256));other=cv2.imread(str(root/'data/dataset-resized'/chosen[(i+13)%len(chosen)]['path']));other=cv2.resize(other,(256,256))
 dirty=im.copy();cv2.circle(dirty,(120,120),60,(28,45,66),-1)
 partial=im.copy();partial[:,:100]=0
 crushed=cv2.resize(cv2.resize(im,(100,256)),(256,256))
 mixed=np.concatenate([im[:,:128],other[:,128:]],axis=1)
 for variant,img in [('original',im),('synthetic_dirt',dirty),('resampled_compression',crushed),('partial_visibility',partial),('mixed_composite',mixed)]:
  p=w.predict(img)['probabilities'];best=sorted(p,key=p.get,reverse=True);accept=p[best[0]]>=cfg['threshold'] and p[best[0]]-p[best[1]]>=cfg['margin'];prediction=best[0] if accept else 'unknown';truth='unknown' if r['label']=='trash' or variant=='mixed_composite' else r['label']
  stress.append({'path':r['path'],'variant':variant,'truth':truth,'prediction':prediction,'confidence':p[best[0]],'accepted':accept})
summary={v:{'count':len(rows),'correct':sum(r['truth']==r['prediction'] for r in rows),'rejected':sum(not r['accepted'] for r in rows)} for v,rows in ((v,[r for r in stress if r['variant']==v]) for v in sorted(set(r['variant'] for r in stress)))}
(out/'waste-stress.json').write_text(json.dumps({'summary':summary,'records':stress,'limitations':'Synthetic pixel transformations, not real dirty/crushed/mixed-object validation. Resampling is only a distortion proxy, not physical crushing. Mixed composite target is review. Frozen thresholds; no retuning.'},indent=2))
d=Detector(root/'models/detector-640.onnx');manifest=json.loads((root/'data/coco-sample/manifest.json').read_text());rows=[]
for r in [r for r in manifest['images'] if r['split']=='test' and r['group']=='vehicles'][:10]:
 im=cv2.imread(str(root/'data/coco-sample'/r['file_name']));shadow=im.copy();shadow[:,:im.shape[1]//2]=(shadow[:,:im.shape[1]//2]*.2).astype('uint8');partial=im.copy();partial[:,:im.shape[1]//3]=0;reflection=cv2.addWeighted(im,.65,cv2.flip(im,1),.35,0)
 for name,img in [('original',im),('shadow',shadow),('partial',partial),('reflection_blend',reflection)]:
  result=d.predict(img);rows.append({'image_id':r['id'],'variant':name,'vehicle_candidates':sum(x['label'] in ['car','motorcycle','bus','truck'] for x in result['detections']),'pedestrian_candidates':sum(x['label']=='person' for x in result['detections']),'latency_ms':result['latency_ms']})
(out/'parking-stress.json').write_text(json.dumps({'records':rows,'limitations':'Ten transformed source photos; candidate counts only. No reannotated visibility truth; not accuracy or real reflection performance.'},indent=2))

print('Stress probes saved in extra-evaluation; no thresholds changed')
