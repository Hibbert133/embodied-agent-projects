"""Generate 150-DPI PNG plots directly from Day 2.5 CSV files."""
from __future__ import annotations
import csv
from pathlib import Path
from PIL import Image,ImageDraw
ROOT=Path(__file__).resolve().parents[1]; OUT=ROOT/'outputs/figures'
def read(path):
    with path.open(encoding='utf-8',newline='') as f:return list(csv.DictReader(f))
def chart(rows,metric,title,filename,percent=False):
    im=Image.new('RGB',(1800,900),'white');d=ImageDraw.Draw(im); d.text((60,25),title,fill='black'); left,top,right,bottom=100,80,1750,760
    vals=[float(r[metric]) for r in rows]; ymax=max(vals+[1 if percent else 0])
    d.line((left,top,left,bottom,right,bottom),fill='black',width=3)
    bw=(right-left)/len(rows)
    for i,(r,v) in enumerate(zip(rows,vals)):
        x=left+(i+.15)*bw; y=bottom-(v/ymax)*(bottom-top); selected=r.get('bias_axis')=='x' and r.get('bias_direction')=='positive' and abs(float(r.get('perturbation_level',0))-.145)<1e-9
        color='#f59e0b' if selected else '#2563eb'; d.rectangle((x,y,x+bw*.7,bottom),fill=color)
        label=f"{r.get('bias_axis','')}{'+' if r.get('bias_direction')=='positive' else '-'} {float(r['perturbation_level']):g}"; d.text((x,bottom+8),label,fill='black')
        d.text((x,max(top,y-18)),f'{v*100:.0f}%' if percent else f'{v:.3f}',fill='black')
    OUT.mkdir(parents=True,exist_ok=True); im.save(OUT/filename,dpi=(150,150))
def outcomes(rows):
    im=Image.new('RGB',(1500,700),'white');d=ImageDraw.Draw(im);d.text((50,25),'Selected +x bias 0.145: per-seed outcomes and final distance (m)',fill='black'); left,top,bottom=80,70,600; ymax=max(float(r['final_object_goal_distance']) for r in rows)
    for i,r in enumerate(rows):
        x=left+i*27;y=bottom-float(r['final_object_goal_distance'])/ymax*(bottom-top);d.ellipse((x-5,y-5,x+5,y+5),fill='#16a34a' if r['success'].lower()=='true' else '#dc2626');d.text((x-6,bottom+10),r['seed'],fill='black')
    im.save(OUT/'per_seed_outcomes_selected_config.png',dpi=(150,150))
def main():
    coarse=read(ROOT/'outputs/day2_5/single_axis_bias_20_seed_summary.csv'); fine=read(ROOT/'outputs/day2_5/single_axis_bias_fine_20_seed_summary.csv'); rows=coarse+fine
    chart(rows,'success_rate','Single-axis bias success rate','single_axis_bias_success_rate.png',True);chart(rows,'mean_final_object_goal_distance','Mean final object-goal distance (m)','single_axis_bias_final_distance.png');chart(rows,'mean_steps','Mean episode steps','single_axis_bias_mean_steps.png');chart(rows,'clipped_step_fraction','Clipped-step fraction','single_axis_bias_clipping.png',True);outcomes(read(ROOT/'outputs/day2_5/selected_config_50_seed.csv'))
if __name__=='__main__':main()
