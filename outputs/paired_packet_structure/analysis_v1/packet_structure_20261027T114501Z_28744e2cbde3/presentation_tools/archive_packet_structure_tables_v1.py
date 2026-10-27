"""Lossless transport of every new table larger than4MiB; actual restore check."""
from pathlib import Path
import sys
ROOT=Path(r'C:/Users/Administrator/Desktop/embodied-agent-projects');sys.path.insert(0,str(ROOT))
from src.analysis import packet_structure_sources_v1 as a
from scripts.archive_action_response import split_file,restore
path=Path(sys.argv[1]).resolve();a.checked(path);run=path.parent;out=a.BASE/'archives_v1'/run.name;out.mkdir(parents=True,exist_ok=False);restored=a.BASE/'restoration_v1'/run.name;rows=[]
for source in sorted(run.rglob('*')):
    if not source.is_file() or source.stat().st_size<=4*1024**2:continue
    relative=source.relative_to(run);h=a.io.sha(source);folder=out/('__'.join(relative.parts)+'.parts');packed=split_file(source,folder,h,part_bytes=4*1024**2)
    proof=restore(folder/'parts.json',restored/relative);assert proof['sha256']==h and proof['size']==source.stat().st_size
    rows.append(dict(source=source.relative_to(ROOT).as_posix(),size=source.stat().st_size,sha256=h,index=(folder/'parts.json').relative_to(ROOT).as_posix(),index_sha256=a.io.sha(folder/'parts.json'),parts=len(packed['parts']),actual_restoration=proof))
a.io.write(out/'catalog.json',dict(integrity='PASSED',originals_preserved=True,restoration_copies_retained=True,files=rows,new_physics=0,new_fits=0,new_predictions=0,online_LLM_API_calls=0))
print(dict(large_tables=len(rows),parts=sum(r['parts'] for r in rows),originals_and_actual_restores_preserved=True))
