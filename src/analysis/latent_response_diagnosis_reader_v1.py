"""Shared raw byte reader only; queries and arithmetic are independently rebuilt."""
from itertools import zip_longest
from src.analysis import latent_response_diagnosis_io_v1 as a
from src.analysis.command_target_sources_v1 import GroupedJournal
io=a.io


def latent_cases():
    index=0;manifest=io.read(a.LATENT/'manifest.json');identity={k:manifest[k] for k in a.latent.IDENTITY}
    for split in a.latent.SPLITS:
        folder=a.LATENT/split.lower();events=GroupedJournal(io.rows(folder/'events.jsonl.gz'),a.latent.KEYS,identity);private=GroupedJournal(io.rows(folder/'private_targets.jsonl.gz'),a.latent.KEYS,identity)
        iterator=zip_longest(io.rows(folder/'cases.jsonl.gz'),io.rows(folder/'public_trajectories.jsonl.gz'),io.rows(folder/'public_packet_metadata.jsonl.gz'))
        for spec,record in zip_longest(a.latent.population(split),iterator):
            io.require(record is not None,'missing aligned public source record');case,public,meta=record
            io.require(spec is not None and case is not None and public is not None and meta is not None,'complete source population and aligned public data')
            io.require(all(case[k]==v for k,v in spec.items()) and io.digest(public)==case['public_trajectory_sha256'],'source case/public identity')
            chunk=events.take_case(case);native=private.take_case(case);io.require(chunk[-1]['case_record_sha256']==io.digest(case),'source case digest')
            yield index,case,public,meta,chunk,native;index+=1
        events.finish();private.finish()
    io.require(index==792,'all source executions')


def reference_cases():
    folder=a.REFERENCE/'qual';manifest=io.read(a.REFERENCE/'manifest.json');identity={k:manifest[k] for k in a.reference.IDENTITY}
    events=GroupedJournal(io.rows(folder/'events.jsonl.gz'),a.reference.KEYS,identity);count=0
    for spec,case in zip_longest(a.reference.population('QUAL'),io.rows(folder/'cases.jsonl.gz')):
        io.require(spec is not None and case is not None and all(case[k]==v for k,v in spec.items()),'full reference population')
        chunk=events.take_case(case);io.require(chunk[-1]['case_record_sha256']==io.digest(case),'reference source case digest')
        yield case,chunk;count+=1
    events.finish();io.require(count==540,'full reference cases')
