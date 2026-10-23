"""Strict NumPy-to-JSON record boundary. No changes to capsule/control semantics."""
import json
import math
from time import perf_counter_ns
import numpy as np


def normalize(value):
    if type(value) is np.ndarray:
        if value.dtype.hasobject or value.dtype.fields: raise ValueError('opaque record array')
        return normalize(value.tolist())
    if isinstance(value,np.generic):
        item=value.item()
        if isinstance(item,np.generic):raise ValueError('unsupported NumPy record scalar')
        return normalize(item)
    if type(value) is dict:
        if any(type(k) is not str for k in value):raise ValueError('record object keys must be strings')
        return {k:normalize(v) for k,v in value.items()}
    if type(value) in (list,tuple):return [normalize(v) for v in value]
    if value is None or type(value) in (str,bool,int):return value
    if type(value) is float and math.isfinite(value):return value
    raise ValueError('nonfinite or unsupported record value: '+type(value).__name__)


class JsonJournal:
    def __init__(self,handle,identity):
        self.handle=handle;self.identity=normalize(identity);self.sequence=0

    def emit(self,event,payload):
        if set(payload).intersection((*self.identity,'event','sequence','saved_ns')):
            raise ValueError('record envelope override')
        value=normalize({**self.identity,'event':event,'sequence':self.sequence,'saved_ns':perf_counter_ns(),**payload})
        text=json.dumps(value,ensure_ascii=False,allow_nan=False)+'\n'
        self.handle.write(text);self.handle.flush();self.sequence+=1
        return value
