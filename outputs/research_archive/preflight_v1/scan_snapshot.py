"""Read immutable Git blobs; publish no credential values or oversized history."""
from pathlib import Path
from time import perf_counter_ns
import hashlib,json,re,subprocess,sys
ROOT=Path(__file__).resolve().parents[3];sys.path.insert(0,str(ROOT))
from scripts.check_tracked_secrets import find_secret_rule
OUT=Path(__file__).parent
EXTRA={
    'literal_provider_credential':re.compile(r'(?i)\b(?:GLM_API_KEY|ZHIPUAI_API_KEY|OPENAI_API_KEY|ANTHROPIC_API_KEY|api_key|apikey|access_token|authorization)\b[\s"\x27]*[:=]\s*["\x27](?:Bearer\s+)?[A-Za-z0-9_.-]{20,}["\x27]'),
    'glm_key_shape':re.compile(r'\b[0-9a-fA-F]{32}\.[A-Za-z0-9_-]{16,64}\b'),
    'github_token_shape':re.compile(r'\b(?:gh[pousr]_[A-Za-z0-9]{30,}|github_pat_[A-Za-z0-9_]{40,})\b')}


def main():
    v=json.loads((OUT/'snapshot_selection.json').read_text(encoding='utf-8'));start=perf_counter_ns();findings=[];catalog=[];read_bytes=0
    selected={r['oid'] for r in v['selected']};cache={};p=subprocess.Popen(['git','cat-file','--batch'],cwd=ROOT,stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.PIPE)
    try:
        for i,r in enumerate(v['selected']+v['omitted']):
            oid=r['oid']
            if oid in cache:catalog.append({**r,**cache[oid]});continue
            p.stdin.write((oid+'\n').encode());p.stdin.flush();header=p.stdout.readline().split();assert len(header)==3 and header[1]==b'blob'
            size=remaining=int(header[2]);h=hashlib.sha256();data=[];scan=oid in selected
            while remaining:
                block=p.stdout.read(min(1048576,remaining));assert block;remaining-=len(block);h.update(block);read_bytes+=len(block)
                if scan:data.append(block)
            assert p.stdout.read(1)==b'\n'
            if scan:
                b=b''.join(data)
                if b'\0' not in b:
                    text=b.decode('utf-8',errors='replace');rule=find_secret_rule(text)
                    if rule:findings.append(dict(path=r['path'],rule=rule))
                    for name,pattern in EXTRA.items():
                        match=pattern.search(text)
                        if match:findings.append(dict(path=r['path'],rule=name,line=text.count('\n',0,match.start())+1))
            cache[oid]=dict(sha256=h.hexdigest(),bytes=size,published=scan);catalog.append({**r,**cache[oid]})
            if (i+1)%1000==0:print(dict(objects=i+1,bytes_hashed=read_bytes,credential_findings=len(findings)),flush=True)
        p.stdin.close();assert p.wait(timeout=60)==0
    finally:
        if p.poll() is None:p.kill();p.wait()
    receipt=dict(integrity='PASSED' if not findings else 'NEEDS_REVIEW',source_commit=v['source_commit'],selected_files=len(v['selected']),
        omitted_files=len(v['omitted']),all_source_file_catalog=catalog,credential_findings=findings,actual_git_blob_bytes_hashed=read_bytes,
        selected_secret_scan_only=True,local_history_and_all_raw_data_unchanged=True,wall_ns=perf_counter_ns()-start)
    with (OUT/'snapshot_blob_audit.json').open('x',encoding='utf-8') as f:json.dump(receipt,f,ensure_ascii=False,indent=2)
    print({k:receipt[k] for k in ('integrity','selected_files','omitted_files','actual_git_blob_bytes_hashed','credential_findings')},flush=True)


if __name__=='__main__':main()
