"""Plot real tuning and validation probe-consistency scores."""
from __future__ import annotations
import argparse,csv,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
def parse()->argparse.Namespace:
 p=argparse.ArgumentParser(description=__doc__);p.add_argument("--tuning-csv",type=Path,required=True)
 p.add_argument("--validation-csv",type=Path,required=True);p.add_argument("--threshold",type=float,required=True)
 p.add_argument("--output",type=Path,required=True);return p.parse_args()
def read(path:Path)->list[dict[str,str]]:
 with path.open(encoding="utf-8") as f:return list(csv.DictReader(f))
def main()->int:
 a=parse()
 try:
  from PIL import Image,ImageDraw
  labels={"fault_01":"+x bias","fault_02":"-x bias","fault_03":"-y bias","fault_04":"planar bias","fault_05":"Gaussian OOD"}
  panels=(("Tuning seeds 300-309",a.tuning_csv),("Validation seeds 310-319",a.validation_csv))
  all_rows=[read(path) for _,path in panels];maximum=max(float(r["estimated_bias_std_norm"]) for rows in all_rows for r in rows)*1.08
  image=Image.new("RGB",(1500,620),"white");draw=ImageDraw.Draw(image)
  draw.text((400,20),"Agent-visible repeated probe consistency",fill="#111111")
  for panel_index,((name,_),rows) in enumerate(zip(panels,all_rows)):
   left=90+panel_index*730;right=left+620;top=80;bottom=520
   draw.line((left,top,left,bottom,right,bottom),fill="#333333",width=2)
   threshold_y=bottom-(a.threshold/maximum)*(bottom-top);draw.line((left,threshold_y,right,threshold_y),fill="#333333",width=2)
   draw.text((left+5,threshold_y-18),f"frozen threshold={a.threshold:.3f}",fill="#333333")
   draw.text((left+230,50),name,fill="#111111")
   for tick in range(6):
    value=maximum*tick/5;y=bottom-(value/maximum)*(bottom-top);draw.line((left-5,y,left,y),fill="#333333")
    draw.text((left-55,y-7),f"{value:.2f}",fill="#555555")
   for index,(condition,label) in enumerate(labels.items()):
    values=[float(r["estimated_bias_std_norm"]) for r in rows if r["condition_id"]==condition]
    center=left+65+index*120;offsets=[(i-(len(values)-1)/2)*5 for i in range(len(values))]
    color="#d95f02" if condition=="fault_05" else "#1b9e77"
    for offset,value in zip(offsets,values):
     y=bottom-(value/maximum)*(bottom-top);draw.ellipse((center+offset-4,y-4,center+offset+4,y+4),fill=color)
    draw.text((center-35,bottom+18),label,fill="#333333")
  draw.text((15,280),"bias std norm",fill="#333333")
  output=a.output.resolve();output.parent.mkdir(parents=True,exist_ok=True);image.save(output,dpi=(180,180))
  print(f"figure: {output}");return 0
 except Exception as e:print(f"[FAIL] {type(e).__name__}: {e}",file=sys.stderr);return 1
if __name__=="__main__":raise SystemExit(main())
