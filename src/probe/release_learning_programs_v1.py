"""Registered public procedures for a fresh information-release learning study."""
from src.probe.information_release_v1 import ACTIONS,RATES

NATIVE=('N_CONT_KEEP','N_CONT_0125','N_CONT_05','N_CONT_2','N_CONT_8','N_VALIDATE_RANDOM','N_MOVE_MASK','N_MOVE_FULL','N_MOVE_RANDOM')
TAIL=tuple('TAIL_'+a+'_'+str(i) for a in ACTIONS for i in range(4))
GATE=tuple('GATE_'+a for a in ACTIONS)
CAL=('CAL_CONTINUE_MASK','CAL_VALIDATE8_MASK','CAL_VALIDATE8_FULL','CAL_MOVE_MEASURE_MASK','CAL_MOVE_MEASURE_FULL')
EVALUATION=('LEARNED_EFFECT','DIRECT_RISK','EFFECT_DISABLED','RELEASE_ALWAYS','FORCE_MASKED',
    'ALWAYS_MOVE_FULL','ALWAYS_MOVE_MASK','MOVE_NO_UPDATE','REFERENCE_NO_PROBE','PURE_MOVE_KEEP','RAW','RAW_T0125','RAW_T2','RAW_T8',
    'DIRECT_C8','MOVE_INTEGRAL','VALIDATE_FULL','VALIDATE_MASK','VALIDATE_NO_UPDATE','TRAIN_BEST_PROGRAM')
ALL=set(NATIVE+TAIL+GATE+CAL+EVALUATION)


def legacy(program):return program in ('DIRECT_C8','MOVE_INTEGRAL','REFERENCE_NO_PROBE','PURE_MOVE_KEEP')
def legacy_name(program):return 'LOCAL_PID_REFERENCE_RESET_NO_PROBE' if program=='REFERENCE_NO_PROBE' else 'LOCAL_PID_KEEP' if program=='PURE_MOVE_KEEP' else program
def calibrated_prefix(program):return program in ('DIRECT_C8','MOVE_INTEGRAL')


def fixed(program):
    """None action/rate/exposure denotes an actual frozen learned or random choice."""
    if program in ('LEARNED_EFFECT','DIRECT_RISK','EFFECT_DISABLED','RELEASE_ALWAYS','FORCE_MASKED','TRAIN_BEST_PROGRAM'):return None,None,None
    if program.startswith('TAIL_'):
        a,i=program[5:].rsplit('_',1);return a,RATES[int(i)],True
    if program.startswith('GATE_'):return program[5:],None,'RANDOM'
    if program.startswith('CAL_'):
        a,r=program[4:].rsplit('_',1);return a,None,r=='FULL'
    if program.startswith('N_CONT_'):
        return 'CONTINUE',{'KEEP':.5,'0125':.125,'05':.5,'2':2.,'8':8.}[program[7:]],False
    if program.startswith('N_VALIDATE_'):return 'VALIDATE8',.5,'RANDOM'
    if program.startswith('N_MOVE_'):return 'MOVE_MEASURE',.5,'RANDOM' if program.endswith('_RANDOM') else program.endswith('_FULL')
    if program.startswith('RAW'):
        return 'CONTINUE',{'RAW':.5,'RAW_T0125':.125,'RAW_T2':2.,'RAW_T8':8.}[program],False
    if program=='MOVE_NO_UPDATE':return 'MOVE_MEASURE',.5,False
    if program in ('ALWAYS_MOVE_FULL','ALWAYS_MOVE_MASK'):return 'MOVE_MEASURE',None,program.endswith('_FULL')
    if program in ('VALIDATE_FULL','VALIDATE_MASK'):return 'VALIDATE8',None,program.endswith('_FULL')
    if program=='VALIDATE_NO_UPDATE':return 'VALIDATE8',.5,False
    if legacy(program):return None,None,None
    raise ValueError('unregistered complete procedure')
