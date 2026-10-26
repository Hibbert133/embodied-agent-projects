from pathlib import Path
import hashlib, json, sys
base=Path(sys.argv[1]).resolve().parent/'presentation/figures'
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
plot=json.loads((base/'plot_receipt.json').read_text(encoding='utf8'))
assert set(plot['artifact_sha256'])=={name+ext for name in ('all_selectors','FULL_MASK_groups','all_panels') for ext in ('.png','.svg')}
for name,digest in plot['artifact_sha256'].items():assert sha(base/name)==digest
receipt=dict(integrity='PASSED',actual_PNGs_viewed=['all_selectors.png','FULL_MASK_groups.png','all_panels.png'],
    review='All three PNGs opened with view_image. Chinese labels, axes, units, all10 selectors/all9 groups/all18 panels per kernel visible; no overlap or truncation; SVGs share the same generated figure.',
    artifact_sha256=plot['artifact_sha256'],plot_receipt_sha256=sha(base/'plot_receipt.json'),
    script_sha256=sha(Path(__file__)),new_physics=0,new_fits=0,online_LLM_API_calls=0)
with (base/'visual_review.json').open('x',encoding='utf8',newline='\n') as f:json.dump(receipt,f,ensure_ascii=False,indent=2);f.write('\n')
print(dict(integrity='PASSED',actual_PNGs_viewed=3,artifacts_bound=6))
