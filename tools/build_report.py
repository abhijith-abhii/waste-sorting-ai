from pathlib import Path
import json
from docx import Document
from docx.shared import Inches,Pt,RGBColor
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
root=Path('outputs/raspberry-pi-ai')
for project in [Path(__file__).resolve().parents[1]]:
 m=json.loads((project/'docs/report-content.json').read_text());doc=Document();sec=doc.sections[0]
 for border in list(doc.styles.element.iter(qn('w:pBdr'))):border.getparent().remove(border)
 sec.page_width=Inches(8.5);sec.page_height=Inches(11);sec.top_margin=sec.bottom_margin=Inches(.65);sec.left_margin=sec.right_margin=Inches(.7)
 for name in ['Normal','Title','Subtitle','Heading 1','Heading 2']:
  style=doc.styles[name];style.font.name='Calibri';style.font.color.rgb=RGBColor(0,0,0)
 doc.styles['Normal'].font.size=Pt(10.5);doc.styles['Normal'].paragraph_format.space_after=Pt(7);doc.styles['Normal'].paragraph_format.line_spacing=1.08
 doc.styles['Title'].font.size=Pt(25);doc.styles['Heading 1'].font.size=Pt(17);doc.styles['Heading 2'].font.size=Pt(12)
 footer=sec.footer.paragraphs[0];footer.alignment=2;footer.add_run('Abhijith Viswanathan  |  Simulation engineering report  |  ').font.size=Pt(8)
 fld=OxmlElement('w:fldSimple');fld.set(qn('w:instr'),'PAGE');footer._p.append(fld)
 md=[]
 def p(text,style=None):doc.add_paragraph(text,style);md.extend([text,''])
 def h(text):doc.add_heading(text,1);md.extend(['## '+text,''])
 def page(text):doc.add_page_break();h(text)
 def pic(path,width=6.9):doc.add_picture(str(project/path),width=Inches(width));md.extend([f'![{path}]({path})',''])
 def table(headers,rows,widths):
  t=doc.add_table(rows=1,cols=len(headers));t.autofit=False
  for c,w in zip(t.columns,widths):c.width=Inches(w)
  for i,x in enumerate(headers):t.rows[0].cells[i].text=str(x)
  for values in rows:
   cells=t.add_row().cells
   for c,x in zip(cells,values):c.text=str(x)
  for ri,row in enumerate(t.rows):
   for ci,cell in enumerate(row.cells):
    cell.width=Inches(widths[ci]);cell.vertical_alignment=1;pr=cell._tc.get_or_add_tcPr();borders=OxmlElement('w:tcBorders')
    for edge in ['top','left','bottom','right']:
     e=OxmlElement('w:'+edge);e.set(qn('w:val'),'single');e.set(qn('w:sz'),'4');e.set(qn('w:color'),'D9D9D9');borders.append(e)
    pr.append(borders);mar=OxmlElement('w:tcMar')
    for edge in ['top','left','bottom','right']:
     e=OxmlElement('w:'+edge);e.set(qn('w:w'),'80');e.set(qn('w:type'),'dxa');mar.append(e)
    pr.append(mar);shade=OxmlElement('w:shd');shade.set(qn('w:fill'),'EDF2F5' if ri==0 else 'FFFFFF');pr.append(shade)
    for par in cell.paragraphs:
     par.paragraph_format.space_after=Pt(3);par.paragraph_format.space_before=Pt(3)
     for run in par.runs:run.font.size=Pt(9.5);run.bold=ri==0
   if ri==0:row._tr.get_or_add_trPr().append(OxmlElement('w:tblHeader'))
  doc.add_paragraph('');md.extend(['| '+' | '.join(headers)+' |','| '+' | '.join(['---']*len(headers))+' |']+['| '+' | '.join(map(str,row))+' |' for row in rows]+[''])
 p(m['title'],'Title');p('Technical report and reproducible evaluation','Subtitle');p('11 November 2026  |  Abhijith Viswanathan  |  AI-assisted implementation')
 p(m['intro']);p(m['scope']);h('Architecture')
 pic('docs/architecture.png');p('The application keeps perception, control and hardware interfaces separate. Virtual inputs and the explicit clock make decisions replayable; SQLite commits event identifiers and controller state together. The dashboard runs locally and never opens a webcam unless explicitly enabled.')
 h('Main measured comparison');r=m['metrics'][0];p(f"{r['metric']}: {r['baseline']:.3f} to {r['final']:.3f} {r['unit']}. {r['scope']}.")
 p('The following pages separate real image evaluation, host execution time, scripted control outcomes and future physical validation. Raw observations, exact selections, source attribution and regression logs accompany this report.')
 page('Control behavior and recovery');pic('docs/states.png')
 for i,text in enumerate(m['policies']):p(f'{i+1}. {text}')
 h('Freshness and persistence');p('For classroom and parking, real image evidence expires after two simulation seconds at a new check; advancing time cannot make a stored frame fresh. Restart invalidates camera evidence. A gate interrupted during a cycle enters FAULT, and an interrupted waste move requires review. Manual simulation inputs are explicitly labeled fixtures.')
 p('The classroom and parking tracker uses class-aware one-to-one overlap association, a five-second expiry, two-hit confirmation and a line deadband. An 80-frame synthetic trajectory produced one unique ID and one expected entry. This verifies mechanics, not tracking accuracy on crowded video. IDs and entry counters persist, but active tracks do not survive restart.')
 p('A state change and its event ID are stored in one SQLite transaction. Duplicate event IDs are ignored. Failed persistence rolls back in-memory controller state and newly accepted inference/tracker state. This cannot undo a real actuator movement; the physical design requires independent acknowledgement and reconciliation.')
 p('State-machine source: docs/state-machine.mmd. Controllers: lab/core.py. Hardware interfaces: lab/hal.py. The current app uses serialized, synchronous inference and virtual-clock control; it is not a real-time motor controller.')
 page('Models data and measured tradeoffs');p(m['model']);pic('evidence/benchmark.png',6.8)
 p(m['tradeoff']);p(m['limitations'])
 page('Measurement protocol and verification')
 table(['Metric','Baseline','Final','Unit'],[[r['metric'],f"{r['baseline']:.3f}",f"{r['final']:.3f}",r['unit']] for r in m['metrics']],[3.25,1,1,1.75])
 for r in m['metrics']:p(r['metric']+': '+r['scope']+'.')
 t=m['timing'];p(f"Complete local inference requests: median {t['median_ms']:.2f} ms and p95 {t['p95_ms']:.2f} ms over 30 repeated requests after one cold request ({t['cold_request_ms']:.2f} ms). Flask test-client timing includes image decode, inference, annotation, controller update, SQLite and JSON; it excludes network and browser rendering. The same selected image was repeated. CPU and cumulative process memory samples are in evidence/request-timing.json.")
 p('Environment: macOS 26.2 arm64, Python 3.12.14, ONNX Runtime 1.21.0 CPU, OpenCV 4.11.0.86 and NumPy 2.2.6. Detector timing separately compares 36 calls at each size; median 13.31 ms at 320 and 48.50 ms at 640. Short host runs do not predict Pi throughput, thermal behavior or sustained response bounds.')
 p('Regression result: 56 shared cases passed, covering state guards, invalid and stale input, manual requests, duplicate IDs, restart, large time steps, failed commits and HTTP input boundaries. The same suite is included in each standalone project; these are not 168 distinct tests. Browser checks exercised real inference and the advertised failure controls.')
 p('Version history preserves the initial 38 passing core cases, subsequent API and review regressions, and the final 56-case run. Decoder correction, stale image handling, obstruction-source separation, capacity changing during motion, scenario labeling and restart/rollback fixes are recorded in docs/FAILURES.md. Earlier detection results remain available and are not used as final metrics.')
 page('Hardware integration and physical validation');p(m['bom']);p(m['wiring'])
 table(['Interface','Implemented now','Required before physical use'],[['Camera','Recorded files and explicit USB camera option','Capture cadence and disconnect validation'],['Sensor readings','Virtual and recorded value valid at records','Calibrated GPIO or serial acquisition'],['Outputs','VirtualOutput and optional GPIO/servo classes','State-to-pin mapping and physical acknowledgement'],['Timing','VirtualClock and MonotonicClock interfaces','Separate control scheduling and deadline measurements'],['Persistence','SQLite event and state transaction','Power-loss and incomplete-actuation reconciliation']],[1,2.5,3.5])
 p('Required bench tools are a digital multimeter, logic analyzer and USB power meter; an oscilloscope is useful for supply transients. Use BCM numbering, verify 3.3 V GPIO levels and level-shift 5 V echoes. A servo needs a suitable separate supply and common signal ground. The lighting demonstration uses a low-voltage LED, and the gate is an unloaded bench mechanism.')
 p('The shipped app does not activate GPIO. Optional adapter classes are integration building blocks. A target runner must timestamp real acquisitions, disable synthetic acknowledgements, map outputs, and keep interlock checks independent of inference. Direct HX711 support is not included; weight expects a calibrated serial bridge.')
 p('Validate in stages: inspect disconnected rails; calibrate sensors; inject wiring and sensor faults; measure LED/servo command and stop timing; run sustained capture under load; interrupt power during writes and movement; then collect deployment data split by complete recording and location. Every physical test remains pending.')
 p('Hardware sources: Raspberry Pi computer documentation and gpiozero input/output API documentation. Full URLs, pin notes and the integration checklist are in docs/hardware.md.')
 page('Dashboard demonstration and learning')
 table(['Panel','Interpretation'],m['panels'],[1.65,5.35])
 p(m['demo'])
 p('Start with Python 3.12, create .venv, install requirements.txt and run app.py. Control fixtures need no model files. For AI, install requirements-training.txt and run tools/setup_models.py and tools/fetch_samples.py. The trained waste head is included; source packages omit pretrained backbones and COCO photos. Detailed commands and troubleshooting are in docs/setup-and-demo.md.')
 p('Use docs/mentor-guide.md for the code walkthrough, engineering alternatives, ten explained interview questions, modifications and three measured resume bullets. Begin with core.py and its tests, then trace a dashboard action through runtime.py, inference.py and the persistence interface.')
 p('Attribution: Ultralytics YOLO11, COCO, TrashNet by Gary Thung and Mindy Yang, and torchvision MobileNetV3. License texts and source links are retained in NOTICE.md, licenses and docs/model-and-data.md. No identity recognition is implemented. The project demonstrates reproducible simulation work; physical deployment and senior professional experience are not claimed.')
 doc.save(project/'docs/technical-report.docx');(project/'docs/technical-report.md').write_text('\n'.join(md));print(project.name,'report created',flush=True)
