"""Literal RAW PI arithmetic independent of the current actor and PI helpers."""
import numpy as np
from src.analysis.response_qualification_io_v1 import require,digest


def reference(initial,steps,task,boundary):
    gains={'push-v3':10.,'reach-v3':5.,'door-open-v3':25.};integral=[0.,0.];current=initial;memories=[];clip_count=0
    for i,row in enumerate(steps):
        require(row['at_calls']==i and digest(row['before'])==digest(current),'independent source chronology')
        raw=np.asarray(row['raw_policy'],dtype=np.float32)
        base=np.minimum(1.,np.maximum(-1.,raw)).astype(np.float32).astype(float)
        error=raw[:2].astype(float)/gains[task]
        # Keep the same stated floating-point operation order, separately written.
        velocity=(np.eye(2)@(gains[task]*error))/.5
        proposed=np.asarray(integral)+.0125*velocity
        bounded=np.maximum(-2.,np.minimum(2.,proposed));unclipped=base[:2]+bounded
        command=base.copy();command[:2]=np.maximum(-1.,np.minimum(1.,unclipped));command=command.astype(np.float32).astype(float)
        require(command.tolist()==row['command'],'independent saved actual PI command')
        clip_count+=int(np.any(unclipped!=command[:2]))
        integral=(command[:2]-base[:2]).tolist();current=row['after']
        memories.append(dict(schema='TASK_MEMORY_OPTION_V1',task=task,completed_steps=i+1,current=current,
            controller=dict(source='UNCORRECTED',matrix_xy=[[1.,0.],[0.,1.]],offset=[0.,0.,0.,0.]),integral_xy=integral,time_constant_s=.5))
    n=len(steps);available=max(0,min(8,n-boundary));before=memories[boundary-1] if n>boundary else None
    after=memories[boundary+available-1] if available else None
    return dict(final_memory=memories[-1] if memories else None,before_memory=before,after_memory=after,
        memory_sha256_sequence=[digest(m) for m in memories],
        available_validation_steps=available,missing_reason='EARLY_END_AT_OR_BEFORE_BOUNDARY' if n<=boundary else 'SHORT_WINDOW_EARLY_END' if available<8 else None,
        source_command_steps=n,roundoff_or_clipping_steps=clip_count)
