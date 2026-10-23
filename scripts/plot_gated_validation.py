"""Plot success and interaction cost from frozen validation summary CSV."""
from __future__ import annotations
import argparse,csv,sys
from pathlib import Path
def parse()->argparse.Namespace:
 p=argparse.ArgumentParser(description=__doc__);p.add_argument("--summary-csv",type=Path,required=True);p.add_argument("--output",type=Path,required=True);return p.parse_args()
def main()->int:
 a=parse()
 try:
  from PIL import Image,ImageDraw
  with a.summary_csv.open(encoding="utf-8") as f:rows=list(csv.DictReader(f))
  labels={"no_recovery":"No recovery","research_r1_c1":"Research r1_c1","random_03":"Random 03","consistency_gated_r1_c1":"Consistency gated"}
  image=Image.new("RGB",(1400,600),"white");draw=ImageDraw.Draw(image);draw.text((470,20),"Frozen validation: recovery versus interaction cost",fill="#111111")
  colors=["#777777","#1b9e77","#7570b3","#d95f02"]
  for panel,(field,title,maximum) in enumerate((("conditional_recovery_rate","Conditional recovery rate",1.0),("mean_recovery_environment_steps","Mean recovery environment steps",max(float(r["mean_recovery_environment_steps"]) for r in rows)*1.15))):
   left=90+panel*690;right=left+570;top=80;bottom=500;draw.line((left,top,left,bottom,right,bottom),fill="#333333",width=2);draw.text((left+170,50),title,fill="#111111")
   for i,row in enumerate(rows):
    value=float(row[field]);x1=left+35+i*135;x2=x1+75;y=bottom-(value/maximum)*(bottom-top);draw.rectangle((x1,y,x2,bottom),fill=colors[i]);draw.text((x1,y-20),f"{value*100:.1f}%" if field.endswith("rate") else f"{value:.1f}",fill="#222222");draw.text((x1-10,bottom+18),labels[row["method"]],fill="#333333")
  output=a.output.resolve();output.parent.mkdir(parents=True,exist_ok=True);image.save(output,dpi=(180,180));print(f"figure: {output}");return 0
 except Exception as e:print(f"[FAIL] {type(e).__name__}: {e}",file=sys.stderr);return 1
if __name__=="__main__":raise SystemExit(main())
