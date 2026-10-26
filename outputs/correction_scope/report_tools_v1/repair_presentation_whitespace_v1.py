"""Retain failed SVG exports; remove only semantically irrelevant line spaces."""
from pathlib import Path
import hashlib,json,shutil,sys,xml.etree.ElementTree as ET
ROOT=Path(__file__).resolve().parents[3];sys.path.insert(0,str(ROOT))
from src.analysis import correction_scope_io_v1 as a
io=a.io

def semantics(data):
    def element(e):
        return [e.tag,sorted((k,' '.join(v.split())) for k,v in e.attrib.items()),
            e.text if e.text and e.text.strip() else None,
            e.tail if e.tail and e.tail.strip() else None,[element(c) for c in e]]
    return hashlib.sha256(json.dumps(element(ET.fromstring(data)),ensure_ascii=False).encode()).hexdigest()

def repair(manifest):
    manifest=Path(manifest).resolve();a.checked(manifest)
    figures=manifest.parent/'presentation/figures'
    backup=Path(r'C:/Users/Administrator/Documents/ChatGPT/robotic agent/correction_scope_svg_before_whitespace_v1')
    backup.mkdir(exist_ok=False)
    shutil.copyfile(Path(__file__).parent/'plot_report.py',backup/'plot_report_initial_v1.py.saved')
    shutil.copyfile(Path(__file__).parent/'plot_report.py',a.BASE/'result_validation_v1/plot_report_initial_v1.py.saved')
    for name in ('plot_receipt.json','visual_review.json'):
        shutil.copyfile(figures/name,backup/name)
    first=io.read(figures/'plot_receipt.json');review=io.read(figures/'visual_review.json')
    assert review['integrity']=='PASSED'
    changes=[]
    for source in sorted(figures.glob('*.svg')):
        before=source.read_bytes();assert io.sha(source)==first['artifact_sha256'][source.name]
        shutil.copyfile(source,backup/source.name)
        after=('\n'.join(line.rstrip(' \t\r') for line in before.decode('utf8').splitlines())+'\n').encode('utf8')
        assert semantics(before)==semantics(after)
        source.write_bytes(after)
        changes.append(dict(path=source.name,before_sha256=hashlib.sha256(before).hexdigest(),after_sha256=io.sha(source),
            normalized_xml_semantics_sha256=semantics(after),original_retained=str(backup/source.name)))
    for source in figures.glob('*.png'):
        assert io.sha(source)==first['artifact_sha256'][source.name]==review['artifact_sha256'][source.name]
    io.write(figures/'svg_whitespace_receipt.json',dict(integrity='PASSED',changes=changes,
        previous_plot_receipt_sha256=io.sha(backup/'plot_receipt.json'),previous_visual_review_sha256=io.sha(backup/'visual_review.json'),
        unchanged_png_bytes=True,svg_normalized_xml_semantics_equal=True,new_physics=0,new_fits=0,online_LLM_API_calls=0))
    io.write(figures/'visual_review_after_formatting.json',dict(integrity='PASSED',
        review_basis='The three previously inspected PNG images are byte-identical; all three SVG XML semantics are unchanged after trailing-space removal',
        previous_review_sha256=io.sha(figures/'visual_review.json'),whitespace_receipt_sha256=io.sha(figures/'svg_whitespace_receipt.json'),
        artifact_sha256={p.name:io.sha(p) for p in figures.iterdir() if p.suffix in ('.png','.svg')},
        scientific_results_unchanged=True,new_physics=0,new_fits=0,online_LLM_API_calls=0))
    print(dict(integrity='PASSED',svg_files=len(changes),png_files_unchanged=3,originals_retained=str(backup)))

if __name__=='__main__':repair(sys.argv[1])
