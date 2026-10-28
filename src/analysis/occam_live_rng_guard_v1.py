"""Deny global RNG reseeding after the controlled task initialization."""
from contextlib import contextmanager,ExitStack
from unittest.mock import patch
import random
import numpy as np


@contextmanager
def no_global_reseed(receipt):
    counts={k:0 for k in ('numpy_seed','numpy_set_state','python_seed','python_setstate')}
    def denied(name):
        def f(*args,**kwargs):counts[name]+=1;raise RuntimeError('global RNG reseed/restore forbidden during live task: '+name)
        return f
    with ExitStack() as stack:
        for obj,name,key in ((np.random,'seed','numpy_seed'),(np.random,'set_state','numpy_set_state'),(random,'seed','python_seed'),(random,'setstate','python_setstate')):
            stack.enter_context(patch.object(obj,name,denied(key)))
        try:yield
        finally:receipt.update(attempts=counts,scope='LIVE_TASK_ONLY_AFTER_INITIAL_RESET',draws_not_rewound=True)
