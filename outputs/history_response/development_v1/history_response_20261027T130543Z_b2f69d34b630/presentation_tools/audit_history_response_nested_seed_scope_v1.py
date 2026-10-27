from pathlib import Path
import json,hashlib,sys
ROOT=Path(r'C:/Users/Administrator/Desktop/embodied-agent-projects')
path=ROOT/'outputs/history_response/freeze_validation_v1/seed_scope.json'
scope=json.loads(path.read_text('utf8'));found=[];ranges=0;checked=0
excluded=('noise','namespace','bootstrap','generator','generation','nonce','initialization','sampling')
def numeric(v,name,key):
 global ranges
 if type(v) is int:
  if 112000<=v<=112999:found.append((name,key,v))
 elif type(v) is list:
  if len(v)==2 and all(type(x) is int for x in v) and v[0]<=v[1]:
   ranges+=1
   if v[0]<=112999 and 112000<=v[1]:found.append((name,key,v))
  else:
   for item in v:numeric(item,name,key)
 elif type(v) is dict:
  for k,w in v.items():numeric(w,name,key+'.'+k)
def visit(v,name):
 if type(v) is dict:
  for k,w in v.items():
   if 'seed' in k.lower() and not any(x in k.lower() for x in excluded):numeric(w,name,k)
   else:visit(w,name)
 elif type(v) is list:
  for w in v:visit(w,name)
for name,expected in scope['inputs_sha256'].items():
 p=ROOT/name
 if p.suffix!='.json':continue
 assert hashlib.sha256(p.read_bytes()).hexdigest()==expected
 visit(json.loads(p.read_text('utf8')),name);checked+=1
print(json.dumps(dict(json_sources_checked=checked,nested_or_flat_ranges_checked=ranges,collisions=found),ensure_ascii=True))