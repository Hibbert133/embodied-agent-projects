"""Lossless byte transport for large completed and audited raw trajectories.

Keep originals intact. Publication can track the small parts and index instead
of an oversized blob; restoration writes exclusively to a previously absent file.
This tool never starts a simulator, invokes an API or changes research results.
"""
import argparse
import hashlib
import json
from pathlib import Path
import re
import sys

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from scripts.report_action_response import IDENTITY,load,matching_audit,sha

PART_BYTES=32*1024*1024
FORMAT="raw-byte-parts-v1"


def safe_name(name):
    if type(name) is not str or not re.fullmatch(r"[A-Za-z0-9_.-]+",name) or name in (".",".."):
        raise ValueError("plain artifact filename required")
    return name


def valid_sha(value):
    if type(value) is not str or not re.fullmatch(r"[0-9a-f]{64}",value):raise ValueError("SHA-256 required")
    return value


def split_file(source,output,expected_sha,part_bytes=PART_BYTES):
    valid_sha(expected_sha)
    if type(part_bytes) is not int or not 1<=part_bytes<=PART_BYTES:raise ValueError("bounded integer part size required")
    source=source.resolve();output=output.resolve()
    if output.exists() or output==source.parent or source.parent in output.parents:raise FileExistsError("new external part directory required")
    if sha(source)!=expected_sha:raise ValueError("source differs from the completed audit")
    output.mkdir(parents=True,exist_ok=False);parts=[];digest=hashlib.sha256();offset=0
    with source.open("rb") as handle:
        while True:
            data=handle.read(part_bytes)
            if not data:break
            name=f"part-{len(parts):05d}.bin"
            with (output/name).open("xb") as target:target.write(data)
            digest.update(data)
            parts.append({"file":name,"offset":offset,"size":len(data),"sha256":hashlib.sha256(data).hexdigest()})
            offset+=len(data)
    if digest.hexdigest()!=expected_sha:raise ValueError("source changed during archival; partial parts preserved")
    result={"format":FORMAT,"source_name":safe_name(source.name),"source_size":offset,"source_sha256":expected_sha,
            "part_bytes":part_bytes,"parts":parts,"new_environment_steps":0,"new_api_calls":0}
    (output/"parts.json").write_bytes((json.dumps(result,indent=2)+"\n").encode("utf-8"))
    return result


def members(index):
    value=load(index)
    if value.get("format")!=FORMAT:raise ValueError("unknown transport format")
    valid_sha(value["source_sha256"]);safe_name(value["source_name"])
    limit=value["part_bytes"]
    if type(limit) is not int or not 1<=limit<=PART_BYTES or type(value["source_size"]) is not int or value["source_size"]<0:
        raise ValueError("invalid transport sizes")
    offset=0;paths=[];digest=hashlib.sha256()
    for i,part in enumerate(value["parts"]):
        if part["file"]!=f"part-{i:05d}.bin" or type(part["offset"]) is not int or part["offset"]!=offset:
            raise ValueError("missing, reordered or foreign part")
        if type(part["size"]) is not int or not 1<=part["size"]<=limit:raise ValueError("invalid part size")
        valid_sha(part["sha256"])
        path=(index.parent/part["file"]).resolve()
        if path.parent!=index.parent.resolve():raise ValueError("part escapes the transport directory")
        if path.stat().st_size!=part["size"]:raise ValueError("part byte count differs")
        local=hashlib.sha256()
        with path.open("rb") as handle:
            for data in iter(lambda:handle.read(1024*1024),b""):local.update(data);digest.update(data)
        if local.hexdigest()!=part["sha256"]:raise ValueError("part checksum differs")
        paths.append(path);offset+=part["size"]
    if offset!=value["source_size"] or digest.hexdigest()!=value["source_sha256"]:
        raise ValueError("combined bytes differ from the original artifact")
    return value,paths


def restore(index,target):
    index=index.resolve();target=target.resolve()
    if target.exists():raise FileExistsError("restoration never overwrites an existing file")
    value,paths=members(index)  # Validate all bytes before creating the new target.
    target.parent.mkdir(parents=True,exist_ok=True);digest=hashlib.sha256();size=0
    with target.open("xb") as handle:
        for path in paths:
            with path.open("rb") as part:
                for data in iter(lambda:part.read(1024*1024),b""):handle.write(data);digest.update(data);size+=len(data)
    if size!=value["source_size"] or digest.hexdigest()!=value["source_sha256"]:
        raise ValueError("part changed during restoration; new partial target preserved")
    return {"target":str(target),"size":size,"sha256":digest.hexdigest(),"new_environment_steps":0,"new_api_calls":0}


def archive(manifest,audit_path,output):
    m=load(manifest);a=load(audit_path);matching_audit(m,a)
    if output.exists() or output==manifest.parent or manifest.parent in output.parents:
        raise FileExistsError("new external transport directory required")
    selected=[]
    for name,expected in a["artifact_sha256"].items():
        safe_name(name);valid_sha(expected);path=manifest.parent/name
        if sha(path)!=expected:raise ValueError("audited raw bytes changed")
        if path.stat().st_size>PART_BYTES:selected.append((name,expected))
    output.mkdir(parents=True,exist_ok=False);archives={}
    for name,expected in selected:
        folder=output/(name+".parts");result=split_file(manifest.parent/name,folder,expected,part_bytes=PART_BYTES)
        members(folder/"parts.json")
        archives[name]={"index":folder.name+"/parts.json","index_sha256":sha(folder/"parts.json"),
                        "source_sha256":expected,"source_size":result["source_size"],"parts":len(result["parts"])}
    result={**{k:m[k] for k in IDENTITY},"format":FORMAT,"primary_audit_sha256":sha(audit_path),
        "archive_source_sha256":sha(Path(__file__)),"part_bytes":PART_BYTES,"archives":archives,
        "original_files_preserved":True,"new_environment_steps":0,"new_api_calls":0,
        "scope":"Lossless transport of large completed audited files; part and concatenated checksums verified. No new physical or algorithm qualification."}
    (output/"archive.json").write_bytes((json.dumps(result,indent=2)+"\n").encode("utf-8"))
    return result


if __name__=="__main__":
    p=argparse.ArgumentParser(description=__doc__);sub=p.add_subparsers(dest="mode",required=True)
    pack=sub.add_parser("pack")
    for name in ("manifest","audit","output"):pack.add_argument("--"+name,type=Path,required=True)
    unpack=sub.add_parser("restore");unpack.add_argument("--index",type=Path,required=True);unpack.add_argument("--target",type=Path,required=True)
    a=p.parse_args()
    result=archive(a.manifest.resolve(),a.audit.resolve(),a.output.resolve()) if a.mode=="pack" else restore(a.index.resolve(),a.target.resolve())
    print(json.dumps(result))
