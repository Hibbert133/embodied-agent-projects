"""Plot tuning and validation recovery/cost for compensation and value routing."""
from __future__ import annotations
import argparse,csv,sys
from pathlib import Path
def parse()->argparse.Namespace:
 p=argparse.ArgumentParser(description=__doc__);p.add_argument("--tuning-summary",type=Path,required=True);p.add_argument("--validation-summary",type=Path,required=True);p.add_argument("--output",type=Path,required=True);return p.parse_args()
def read(path:Path)->dict[str,dict[str,str]]:
 with path.open(encoding="utf-8") as f:return {r["method"]:r for r in csv.DictReader(f)}
def main()->int:
 a=parse()
 try:
  from PIL import Image,ImageDraw
  splits=[("Tuning",read(a.tuning_summary)),("Validation",read(a.validation_summary))];methods=[("bias_compensation","Bias compensation","#1b9e77"),("value_aware","Value-aware retry","#d95f02")]
  image=Image.new("RGB",(1300,570),"white");draw=ImageDraw.Draw(image);draw.text((430,20),"Stochastic retry: tuning gain does not validate",fill="#111111")
  for panel,(split,rows) in enumerate(splits):
   left=110+panel*620;right=left+500;top=90;bottom=470;draw.line((left,top,left,bottom,right,bottom),fill="#333333",width=2);draw.text((left+210,55),split,fill="#111111")
   for index,(method,label,color) in enumerate(methods):
    rate=float(rows[method]["conditional_recovery_rate"]);steps=float(rows[method]["mean_recovery_environment_steps"]);x=left+90+index*230;height=rate*(bottom-top);draw.rectangle((x,bottom-height,x+90,bottom),fill=color);draw.text((x,bottom-height-22),f"{rate*100:.1f}%",fill="#222222");draw.text((x-15,bottom+18),label,fill="#333333");draw.text((x,bottom-height+18),f"{steps:.1f} steps",fill="white")
  output=a.output.resolve();output.parent.mkdir(parents=True,exist_ok=True);image.save(output,dpi=(180,180));print(f"figure: {output}");return 0
 except Exception as e:print(f"[FAIL] {type(e).__name__}: {e}",file=sys.stderr);return 1
if __name__=="__main__":raise SystemExit(main())
