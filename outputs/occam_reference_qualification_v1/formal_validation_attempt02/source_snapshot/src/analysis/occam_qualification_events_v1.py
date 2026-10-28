"""Keep case cohort separate from lifecycle/command phase; preserve ownership."""
from src.analysis.response_qualification_io_v1 import require


def emit_owned(journal,owner,event,payload):
    require(type(owner) is dict and owner.get('cohort') in ('NATIVE','QUAL') and 'phase' not in owner,
        'case header requires cohort; phase is reserved for lifecycle/command events')
    require(type(payload) is dict,'event payload mapping')
    require(all(k not in payload or payload[k]==v for k,v in owner.items()),'case ownership override')
    return journal.emit(event,{**owner,**payload})
