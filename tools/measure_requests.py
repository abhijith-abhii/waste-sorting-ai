from pathlib import Path
import sys,json,time,tempfile,platform
import numpy as np
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from lab.web import create_app
root=Path(__file__).resolve().parents[1];cfg=json.loads((root/'project.json').read_text());sample=next(s['id'] for s in json.loads((root/'samples/catalog.json').read_text()) if not s.get('synthetic'))
with tempfile.TemporaryDirectory() as td:
 app=create_app(cfg['kind'],root,Path(td)/'db');client=app.test_client();header={'X-Lab-Request':'1'}
 response=client.post('/api/sample',json={'name':sample},headers=header);assert response.status_code==200,response.json
 values=[]
 for _ in range(30):
  t=time.perf_counter();response=client.post('/api/sample',json={'name':sample},headers=header);assert response.status_code==200;values.append((time.perf_counter()-t)*1000)
 app.extensions['runtime'].store.close()
print(json.dumps({'environment':platform.platform(),'sample':sample,'count':30,'median_ms':float(np.median(values)),'p95_ms':float(np.percentile(values,95)),'samples_ms':values,'scope':'Flask test client request; no network or browser timing'},indent=2))
