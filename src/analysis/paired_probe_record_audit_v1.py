"""Saved-record replay independent of the collector, actor and capsule executor.

Shared fixed policies, numeric fitter, encoder and cache/check mathematics are
declared dependencies. No Env, capture, restore or host implementation is used.
Native/Python signatures are source-generated witnesses, not a second native
state proof. All physical charges are reconstructed without rewinding them.
"""
import copy
from dataclasses import asdict
import numpy as np
from src.analysis.capsule_record_json_v2 import normalize
from src.probe.cache_acquisition_evidence_v1 import CacheAcquisitionEvidenceV1,digest
from src.probe.chronological_cache_reference import VerifiedPoint,accepted_cache,check_choice
from src.probe.cold_start_response import ColdPrefix,infer_operator
from src.probe.operator_identification import affine_controller,encode_controller
from src.rollout.task_registry import create_task_policy

ARMS=('REUSE_OLD','PROBE_KEEP','PROBE_UPDATE','PROBE_UPDATE_KEEP')
BLOCK=np.asarray([[.4,0,0,0],[.4,0,0,0],[-.4,0,0,0],[-.4,0,0,0],
    [0,.4,0,0],[0,.4,0,0],[0,-.4,0,0],[0,-.4,0,0]],np.float32).astype(float).tolist()
PHYSICAL=('logical_step','phase','command','raw_policy','executed_action_oracle','after','reward','info',
          'simulation_time_before','simulation_time_after','noise_cursor_after')


def require(condition,message):
    if not condition:raise ValueError(message)


def original_noise(seed):
    key=int(np.random.SeedSequence([seed,47001]).generate_state(1)[0])
    return np.random.default_rng(key).normal(0,.05,(500,3)).astype('<f4')


def fresh_noise(seed,future):
    return np.random.default_rng(np.random.SeedSequence([seed,65001,future])).normal(0,.05,(496,3)).astype('<f4')


def applied(command,fault,noise):
    value=np.asarray(command,np.float32).copy()
    latent=np.asarray(fault['matrix_xy'],np.float32)@value[:2]+np.asarray(fault['bias_xy'],np.float32)
    zone=np.asarray(fault['deadzone_xy'],np.float32)
    value[:2]=np.sign(latent)*np.maximum(np.abs(latent)-zone,np.float32(0))/(np.float32(1)-zone)
    value[:3]=value[:3]+noise
    return np.clip(value,-1,1)


def physical(event):
    value=copy.deepcopy({k:event[k] for k in PHYSICAL})
    if 'episode' in value['info']:value['info']['episode'].pop('t',None)
    return value


def nfev(fit):
    return 0 if fit is None else int(fit.get('nfev',sum(v['nfev'] for v in fit.get('optimizer_trials',[]))))


def add_cost(ledger,phase,field,number):
    value=copy.deepcopy(ledger)
    for cell in (value.setdefault('counts',{}),value.setdefault('by_phase',{}).setdefault(phase,{})):
        cell[field]=cell.get(field,0)+number
    return value


def advance_simulation(ledger,phase,calls,frames):
    for field,amount in (('simulation_attempts',calls),('simulation_completed',calls),
                         ('simulation_frames_attempted',frames),('simulation_frames_completed',frames)):
        ledger=add_cost(ledger,phase,field,amount)
    return ledger


class CaseReplay:
    def __init__(self,row,spec,events,model,previous_cache,ledger,fresh_futures):
        self.row,self.spec,self.events,self.model=row,spec,events,model
        self.previous_cache=previous_cache;self.ledger=copy.deepcopy(ledger);self.j=fresh_futures
        self.byseq={v['sequence']:v for v in events};self.policy=create_task_policy(spec['task'])
        self.tape=original_noise(spec['seed']);self.initial=None;self.public=None;self.time=None;self.logical=None
        self.commands=[];self.observations=[];self.pending=None;self.active=None;self.latest=None
        self.snapshots={};self.snapshot_intents={};self.restore_intents={};self.resets={}
        self.finished=[];self.evidence=None;self.references=None;self.source_cache=None;self.returned=False
        self.steps=self.attempts=self.queries=self.fits=self.optimizer=0
        self.captures=self.restores=self.capture_ns=self.restore_ns=0;self.reset_completed=0;self.controls=0
        self.prefix_choice=None;self.prefix_commands=0;self.prefix_rows=[];self.cache_writes=0
        self.branch_order=[];self.last_restore=None;self.check_sequence=None;self.cache_sequence=None
        self.source_record=None;self.saved_cache_after=None
        self.current_future=0

    def live(self):return not any(self.public[k] for k in ('success','terminated','truncated'))

    def prefix(self):
        return ColdPrefix(self.spec['task'],tuple(self.initial),tuple(map(tuple,self.commands)),tuple(map(tuple,self.observations)),True)

    def witness(self,value):
        require(value['simulation_time']==self.time,'witness simulation clock')
        require(value['noise_past_sha256']==digest(self.tape[:self.logical].tolist()),'witness past noise')
        for key in ('native_sha256','python_semantic_sha256'):
            require(type(value[key]) is str and len(value[key])==64 and all(c in '0123456789abcdef' for c in value[key]),'invalid source witness')
        self.latest={k:value[k] for k in ('native_sha256','python_semantic_sha256','noise_past_sha256','simulation_time')}

    def state(self):
        return copy.deepcopy((self.logical,self.public,self.time,self.commands,self.observations,self.tape,self.latest,self.current_future))

    def expected_outcome(self,branch):
        rows=branch['rows'];choice=branch['choice'];fit=branch['fit']
        return {'success':self.public['success'],'stopped':choice['action']=='STOP_INVALID_FIT' and self.live(),
            'total_steps':self.logical,'suffix_steps':len(rows),'deadline_loss':self.logical if self.public['success'] else 500,
            'fixed_probe_suffix_steps':sum(r['phase']=='FIXED_PROBE' for r in rows),
            'policy_suffix_steps':sum(r['phase']=='POLICY' for r in rows),'online_parameter_fits':int(fit is not None),
            'optimizer_nfev':nfev(fit),'policy_queries':branch['queries'],'applied_new_controller':choice['action']=='RUN_NEW'}

    def choose(self,event):
        b=self.active;p=event['public_payload'];program=b['program']
        require(p['at_calls']==self.logical and self.live(),'choice outside live boundary')
        expected={'sequence':p['sequence'],'saved_ns':p['saved_ns'],'at_calls':self.logical}
        if b['choice'] is None:
            if program=='REUSE_OLD':expected.update(action='RUN_OLD',controller=b['old'])
            else:expected.update(action='PROBE8',program=BLOCK if program=='COLD8' else BLOCK[4:],prefix_steps=self.logical)
        else:
            require(b['choice']['action']=='PROBE8' and self.logical==8,'duplicate/substituted choice')
            if program=='PROBE_KEEP':expected.update(action='RUN_OLD',controller=b['old'])
            else:
                prefix=self.prefix();fit=normalize(infer_operator(self.model,prefix));b['fit']=fit;b['fit_prefix']=normalize(asdict(prefix))
                self.fits+=1;self.optimizer+=nfev(fit)
                if fit['valid']:
                    expected.update(action='RUN_NEW',controller=normalize(affine_controller(fit['matrix_xy'],fit['bias_xy'])),
                        fit=fit,prefix_evidence_sha256=digest(asdict(prefix)))
                elif program=='PROBE_UPDATE_KEEP':expected.update(action='REJECT_KEEP_OLD',controller=b['old'],fit=fit)
                else:expected.update(action='STOP_INVALID_FIT',fit=fit)
        require(p==expected,'choice/controller/shared numerical fit differs')
        b['choice']=p;b['choices'].append(event['sequence'])

    def agent_command(self,event):
        b=self.active;p=event['public_payload'];choice=b['choice']
        require(choice is not None and self.live() and self.logical<500,'command without live saved choice')
        require(set(p)=={'sequence','saved_ns','at_calls','decision_sequence','phase','command','before','raw_policy'},'extra agent command field')
        require(p['before']==self.public and p['at_calls']==self.logical and p['decision_sequence']==choice['sequence'],'stale/substituted command evidence')
        if choice['action']=='PROBE8':
            require(self.logical<8 and p['phase']=='FIXED_PROBE' and p['raw_policy'] is None,'repeated/substituted probe')
            expected=BLOCK[self.logical]
        else:
            require(choice['action'] in ('RUN_OLD','RUN_NEW','REJECT_KEEP_OLD') and p['phase']=='POLICY','policy after stop/probe')
            raw=np.asarray(self.policy.get_action(np.asarray(self.public['observation'])),np.float32)
            self.queries+=1;b['queries']+=1
            require(p['raw_policy']==raw.astype(float).tolist(),'fixed policy query differs')
            expected=encode_controller(choice['controller'],raw).astype(float).tolist()
        require(p['command']==expected,'saved controller not used by command')
        require(b['pending_command'] is None,'multiple outstanding agent commands');b['pending_command']=event

    def cache_commit(self,event):
        require(self.cache_sequence is None and self.active is None,'duplicate/early source cache transaction')
        source=[r['compact'] for r in self.finished if r['role']=='SOURCE']
        if source:require(len(source)==1,'multiple actual source branches');source=source[0]
        else:
            ended=self.row['disposition']=='WARM_PREFIX_ENDED'
            require(ended or (self.references and self.references['UNCERTAINTY4']['action']=='STOP_PUBLIC_CHECK'),'missing actual source outcome')
            require((not self.live() and 1<=self.logical<=4) if ended else self.logical==4,'invalid synthetic source stop/end')
            outcome={'success':self.public['success'],'stopped':not ended,'total_steps':self.logical,'suffix_steps':0,
                'deadline_loss':self.logical if self.public['success'] else 500,'fixed_probe_suffix_steps':0,'policy_suffix_steps':0,
                'online_parameter_fits':0,'optimizer_nfev':0,'policy_queries':0,'applied_new_controller':False}
            source={'role':'SOURCE','future':0,'program':'PREFIX_ENDED' if ended else 'STOP_PUBLIC_CHECK','outcome':outcome,'fit':None,'fit_prefix':None}
        cache=self.previous_cache;error=None
        if not source['outcome']['success']:cache=None
        elif source['outcome']['applied_new_controller']:
            try:
                cache=normalize(asdict(accepted_cache(source['fit'],ColdPrefix.from_dict(source['fit_prefix']),self.spec['task'],
                    self.spec['episode'],success=True,joint_model=self.model)));self.cache_writes+=1
            except (ValueError,np.linalg.LinAlgError) as exc:cache=None;error=str(exc)
        require(event['source']==source and event['cache_before']==self.previous_cache and event['cache_after']==cache and event['cache_write_error']==error,'source-only cache transaction differs')
        require(self.row['source']==source and self.row['cache_after']==cache and self.row['cache_write_error']==error,'case source/cache differs from journal')
        self.source_record=source;self.saved_cache_after=cache;self.cache_sequence=event['sequence']

    def consume(self,event):
        kind=event['event'];seq=event['sequence']
        if kind=='LIFECYCLE_RESET_INTENT':
            require(event['before']==self.ledger and self.initial is None,'reset after controlled initial or ledger mismatch')
            require(event['phase'] in ('GOAL_GENERATION','CONTROLLED_RESET'),'unexpected reset phase')
            self.resets[seq]=event;self.ledger=add_cost(self.ledger,event['phase'],'reset_attempts',1)
        elif kind=='LIFECYCLE_RESET_COMPLETE':
            start=self.resets.pop(event['intent_sequence']);require(start['phase']==event['phase'],'reset phase mismatch')
            self.ledger=advance_simulation(self.ledger,event['phase'],100,500)
            self.ledger=add_cost(self.ledger,event['phase'],'reset_completed',1)
            require(event['after']==self.ledger,'independent complete reset/frame ledger differs');self.reset_completed+=1
            self.controls+=int(event['phase']=='CONTROLLED_RESET')
        elif kind in ('FACTORY_INTENT','FACTORY_COMPLETE'):
            require(event['ledger']==self.ledger,'factory ledger mismatch')
        elif kind=='CONTROLLED_INITIAL':
            require(self.initial is None and self.controls==1 and self.reset_completed==51 and event['ledger']==self.ledger,'one initial plus 50 factory resets required')
            self.initial=event['observation'];self.public={'observation':self.initial,'terminated':False,'truncated':False,'success':False}
            self.logical=0;self.time=event['simulation_time']
        elif kind=='PREFIX_CHOICE':
            require(self.previous_cache is not None and self.prefix_choice is None and self.logical==0 and event['program_commands']==BLOCK[:4],'invalid saved warm prefix')
            self.prefix_choice=event
        elif kind=='PREFIX_COMMAND':
            require(self.active is None and self.live() and self.logical<4 and self.prefix_choice is not None,'repeated prefix')
            require(event['program_sequence']==self.prefix_choice['sequence'] and event['program_index']==self.logical and event['logical_step']==self.logical and
                event['command']==BLOCK[self.logical] and event['before']==self.public,'unsaved/substituted prefix command');self.prefix_commands+=1
        elif kind=='SOURCE_CHECK_CHOICE':
            require(self.previous_cache is not None and self.logical==4 and self.live() and self.evidence is None and self.cache_sequence is None,'public check order')
            evidence=CacheAcquisitionEvidenceV1.from_dict(event['evidence']);cache=VerifiedPoint.from_dict(self.previous_cache)
            raw=np.asarray(self.policy.get_action(np.asarray(self.public['observation'])),np.float32);self.queries+=1
            expected=CacheAcquisitionEvidenceV1(self.prefix(),cache.parameters,cache.belief.covariance,cache.source_task,
                self.spec['episode']-cache.source_episode,bool(cache.belief.active_parameter_bound),tuple(raw),496)
            require(evidence.to_dict()==expected.to_dict() and event['evidence_sha256']==expected.evidence_sha256,'future/foreign evidence')
            references={}
            for method in ('UNCERTAINTY4','TASK_IVR4'):
                try:references[method]=normalize(check_choice(method,self.model,self.prefix(),cache,0.,raw))
                except (ValueError,np.linalg.LinAlgError) as exc:references[method]={'action':'STOP_PUBLIC_CHECK','reason':str(exc)}
            require(event['references']==references and self.row['evidence']==expected.to_dict() and self.row['references']==references and self.row['evidence_sha256']==expected.evidence_sha256,'source recommendation differs')
            self.evidence=evidence;self.references=references;self.check_sequence=seq
        elif kind=='PROGRAM_START':
            require(self.active is None and self.live() and event['logical_step']==self.logical,'program start boundary')
            role,future,program=event['role'],event['future'],event['program']
            require(future==self.current_future,'branch future differs from installed independent noise')
            if role=='SOURCE':
                require(self.cache_sequence is None and future==0 and not self.finished,'source order')
                if self.previous_cache is None:require(program=='COLD8' and self.logical==0,'cold source changed')
                else:require(self.evidence is not None and self.references['UNCERTAINTY4']['action'] in ('REFRESH8','RUN_CACHED') and self.logical==4 and program==('PROBE_UPDATE' if self.references['UNCERTAINTY4']['action']=='REFRESH8' else 'REUSE_OLD'),'saved source decision not executed')
            else:
                require(role in ('EVAL','SENTINEL') and self.cache_sequence is not None and 1<=future<=self.j and program in ARMS and self.logical==4,'evaluator before source/invalid program')
                require(self.last_restore=='FOUR_STEP_SOURCE_BOUNDARY','evaluator did not restore registered boundary')
            if self.latest is not None:require(self.latest=={k:event[k] for k in self.latest},'program did not start at latest physical boundary')
            self.witness(event)
            old=None
            if self.evidence is not None:
                theta=np.asarray(self.evidence.old_parameters).reshape(2,3);old=normalize(affine_controller(theta[:,:2],theta[:,2]))
            self.active={'role':role,'future':future,'program':program,'start':seq,'rows':[],'choice':None,'choices':[],'local':0,
                'old':old,'fit':None,'fit_prefix':None,'pending_command':None,'queries':0,'boundary8':None}
            self.branch_order.append((role,future,program))
        elif kind=='AGENT_EVENT':
            require(self.active is not None,'agent outside program');b=self.active;p=event['public_payload']
            require(all(event[k]==b[k] for k in ('role','future','program')) and type(p['sequence']) is int and p['sequence']==b['local'] and type(p['saved_ns']) is int and self.byseq[b['start']]['saved_ns']<=p['saved_ns']<=event['saved_ns'],'local agent order/identity')
            b['local']+=1
            if event['agent_event']=='CHOICE':self.choose(event)
            elif event['agent_event']=='COMMAND':self.agent_command(event)
            else:raise ValueError('unknown agent event')
        elif kind=='STEP_INTENT':
            require(self.pending is None and self.live() and self.logical<500 and event['logical_step']==self.logical and event['ledger_before']==self.ledger,'step order/budget/ledger')
            command=self.byseq[event['global_command_sequence']]
            if command['event']=='PREFIX_COMMAND':
                require(self.active is None and self.logical<4 and event['phase']=='FIXED_PROBE','prefix after program');sent=command['command']
            else:
                require(command['event']=='AGENT_EVENT' and command['agent_event']=='COMMAND' and self.active is not None and self.active['pending_command']==command,'unsaved command')
                p=command['public_payload'];require(event['phase']==p['phase'],'phase changed after save');sent=p['command']
            require(command['sequence']<seq and command['saved_ns']<=event['saved_ns'] and sent==event['command'],'command not saved first/consumed')
            self.pending=event;self.attempts+=1
        elif kind=='STEP_COMPLETE':
            p=self.pending;require(p is not None and event['intent_sequence']==p['sequence'] and event['logical_step']==self.logical,'completion without intent')
            command=self.byseq[p['global_command_sequence']]
            require(event['global_command_sequence']==p['global_command_sequence'] and event['command']==p['command'],'command substitution')
            require(p['saved_ns']<=event['execution_started_ns']<=event['completed_ns']<=event['saved_ns'] and command['saved_ns']<=event['execution_started_ns'],'decision/execution chronology')
            require(event['simulation_time_before']==self.time and np.isclose(event['simulation_time_after']-self.time,.0125,atol=1e-10,rtol=0),'continuous simulator clock')
            require(event['ledger_before']==self.ledger,'step rewound ledger')
            self.ledger=advance_simulation(self.ledger,'CONTROL',1,5);require(event['ledger_after']==self.ledger,'independent step/frame ledger')
            expected=applied(event['command'],self.spec['fault_oracle'],self.tape[self.logical])
            require(np.array_equal(expected,np.asarray(event['executed_action_oracle'],np.float32)),'private applied action/noise mismatch')
            self.logical+=1;self.steps+=1;self.time=event['simulation_time_after'];self.public=event['after']
            require(set(self.public)=={'observation','success','terminated','truncated'} and len(self.public['observation'])==39 and np.isfinite(self.public['observation']).all() and
                all(type(self.public[k]) is bool for k in ('success','terminated','truncated')) and self.public['success']==bool(event['info'].get('success',False)),'invalid public observation/outcome flags')
            require(event['noise_cursor_after']==self.logical,'noise cursor')
            if self.logical<=8:self.commands.append(event['command']);self.observations.append(self.public['observation'])
            if self.active is not None:
                require(all(event[k]==self.active[k] for k in ('role','future','program')),'branch changed during step')
                require(event['raw_policy']==self.active['pending_command']['public_payload']['raw_policy'],'policy record substitution')
                self.active['rows'].append(physical(event));self.active['pending_command']=None
            else:self.prefix_rows.append(physical(event))
            self.latest=None;self.pending=None
        elif kind=='PHYSICAL_BOUNDARY':
            require(event['logical_step']==self.logical and self.logical in (4,8),'physical boundary order');self.witness(event)
            if self.active is not None and self.logical==8:self.active['boundary8']=copy.deepcopy(self.latest)
        elif kind=='PROGRAM_COMPLETE':
            b=self.active;require(b is not None and self.pending is None and b['pending_command'] is None,'incomplete program')
            require(not self.live() or self.logical==500 or b['choice']['action']=='STOP_INVALID_FIT','premature live program end')
            require(event['outcome']==self.expected_outcome(b) and event['fit']==b['fit'] and event['fit_prefix']==b['fit_prefix'],'program outcome/fit differs')
            require(event['boundary8']==b['boundary8'] and event['final_observation']==self.public and event['choice_global_sequences']==b['choices'] and event['start_sequence']==b['start'],'program record differs')
            self.witness(event['end_witness'])
            keys=('role','future','program','start_sequence','outcome','fit','fit_prefix','choice_global_sequences','boundary8','final_observation','end_witness')
            b['compact']={**{k:event[k] for k in keys},'end_sequence':seq};self.finished.append(b);self.active=None
        elif kind=='SNAPSHOT_INTENT':
            require(self.active is None and self.pending is None and event['ledger']==self.ledger and event['logical_step']==self.logical,'capture physical cost/active program');self.snapshot_intents[seq]=event
        elif kind=='SNAPSHOT_COMPLETE':
            start=self.snapshot_intents.pop(event['intent_sequence']);purpose=event['purpose']
            require(purpose==start['purpose'] and purpose not in self.snapshots and purpose in ('FOUR_STEP_SOURCE_BOUNDARY','ACTUAL_SOURCE_AFTER_OUTCOME'),'capture owner/purpose')
            require(event['ledger']==self.ledger and self.latest is not None and event['logical_step']==self.logical,'capture state/physical work')
            require(all(event[k]==self.latest[k] for k in ('native_sha256','python_semantic_sha256')),'capture witness differs')
            if purpose=='FOUR_STEP_SOURCE_BOUNDARY':require(self.check_sequence is not None and self.cache_sequence is None and self.logical==4,'four-step capture chronology')
            else:require(self.cache_sequence is not None,'source capture before outcome/cache')
            self.snapshots[purpose]=(event,self.state());self.captures+=1;self.capture_ns+=event['wall_ns']
        elif kind=='RESTORE_INTENT':
            require(event['ledger']==self.ledger and self.active is None,'restore physical work/active program');self.restore_intents[seq]=event
        elif kind=='RESTORE_COMPLETE':
            start=self.restore_intents.pop(event['intent_sequence']);require(start['ledger']==self.ledger and event['ledger']==self.ledger and start['purpose']==event['purpose'],'restore rewound ledger')
            require(event['purpose'] in ('RETURN_TO_ACTUAL_SOURCE','EVALUATOR_FORK','SENTINEL'),'unregistered restore purpose')
            purpose='ACTUAL_SOURCE_AFTER_OUTCOME' if event['purpose']=='RETURN_TO_ACTUAL_SOURCE' else 'FOUR_STEP_SOURCE_BOUNDARY'
            cap,state=self.snapshots[purpose]
            require(all(event[k]==cap[k] for k in ('native_sha256','python_semantic_sha256','model_address','data_address','logical_step')),'restore registered boundary differs')
            self.logical,self.public,self.time,self.commands,self.observations,self.tape,self.latest,self.current_future=copy.deepcopy(state)
            self.witness(event);self.restores+=1;self.restore_ns+=event['wall_ns'];self.last_restore=purpose
        elif kind=='FRESH_FUTURE_INSTALLED':
            require(self.logical==4 and self.last_restore=='FOUR_STEP_SOURCE_BOUNDARY' and event['namespace']==65001 and 1<=event['future']<=self.j,'future install boundary')
            self.tape[4:]=fresh_noise(self.spec['seed'],event['future'])
            self.current_future=event['future']
            require(event['past_sha256']==digest(self.tape[:4].tolist()) and event['full_sha256']==digest(self.tape.tolist()),'fresh-future commitment')
            require(event['native_sha256']==self.latest['native_sha256'],'future installation changed native state');self.witness(event)
        elif kind=='SOURCE_CACHE_AFTER_ACTUAL_OUTCOME':self.cache_commit(event)
        elif kind=='SOURCE_STATE_RETURNED':
            require(self.last_restore=='ACTUAL_SOURCE_AFTER_OUTCOME' and not self.returned and event['cache_after_sha256']==digest(self.saved_cache_after) and event['logical_step']==self.logical,'return to source state/cache')
            require(self.latest=={k:event[k] for k in self.latest},'source return witness');self.returned=True
            require(self.row['source_return_sequence']==seq,'case source return reference')
        elif kind=='SOURCE_CASE_COMPLETE':
            require(event['ledger']==self.ledger and self.source_record is not None,'incomplete case ledger/source')
        else:raise ValueError('unregistered journal event: '+kind)

    def audit(self):
        require(self.row['cache_before']==self.previous_cache,'future/evaluator cache entered next source case')
        for event in self.events:self.consume(event)
        require(self.pending is None and self.active is None and not self.resets and not self.restore_intents and not self.snapshot_intents,'unfinished recorded transactions')
        require(self.events[-1]['event']=='SOURCE_CASE_COMPLETE' and self.source_record is not None,'case not completed')
        warm=self.row['disposition']=='WARM_ELIGIBLE'
        expected_disposition='COLD_SOURCE' if self.previous_cache is None else ('WARM_ELIGIBLE' if self.evidence is not None else 'WARM_PREFIX_ENDED')
        require(self.row['disposition']==expected_disposition,'population eligibility uses future')
        require(self.row['source_cache_sequence']==self.cache_sequence,'source cache event reference')
        if warm:require(self.row['source_choice_sequence']==self.check_sequence and self.returned and self.captures==2,'eligible case source/check/return missing')
        else:require(self.evidence is None and self.row['evidence'] is None and self.row['references'] is None and not self.returned and self.captures==0 and self.restores==0 and not self.row['evaluations'] and not self.row['sentinels'],'ineligible evaluator selection')
        evaluated=[b for b in self.finished if b['role']=='EVAL'];sentinels=[b for b in self.finished if b['role']=='SENTINEL']
        expected=[(j,p) for j in range(1,self.j+1) for p in ARMS] if warm else []
        require([(b['future'],b['program']) for b in evaluated]==expected,'missing/duplicate/reordered fresh future program')
        require([b['compact'] for b in evaluated]==self.row['evaluations'] and [b['compact'] for b in sentinels]==self.row['sentinels'],'case branches differ from journal')
        require(self.restores==len(evaluated)+len(sentinels)+int(warm),'restore actual charges')
        matches=valid=invalid=0
        for j in range(1,self.j+1) if warm else ():
            cells={b['program']:b for b in evaluated if b['future']==j};p,u,k=(cells[name] for name in ARMS[1:])
            for other in (u,k):
                require([r for r in p['rows'] if r['logical_step']<8]==[r for r in other['rows'] if r['logical_step']<8] and p['boundary8']==other['boundary8'],'matched actual probe prefix');matches+=1
            require(u['fit']==k['fit'],'matched-prefix fit differs')
            if u['fit'] is None or u['fit']['valid']:require(u['rows']==k['rows'],'valid update/fallback trajectory differs');valid+=1
            else:require(p['rows']==k['rows'],'invalid fallback did not really retain old control');invalid+=1
        for sentinel in sentinels:
            require(sentinel['future']==1 and sentinel['program']=='REUSE_OLD','unregistered sentinel')
            original=next(b for b in evaluated if b['future']==1 and b['program']=='REUSE_OLD')
            require(sentinel['rows']==original['rows'],'full repeat sentinel differs')
        actual={'completed_steps':self.steps,'attempted_steps':self.attempts,'policy_queries':self.queries,
            'captures':self.captures,'restores':self.restores,'capture_ns':self.capture_ns,'restore_ns':self.restore_ns}
        require(self.row['case_actual']==actual,'case physical/computational cost differs')
        return {'ledger':self.ledger,'cache_after':self.saved_cache_after,'actual':actual,'warm':warm,'cache_writes':self.cache_writes,
            'matched_probe_prefixes':matches,'valid_update_equalities':valid,'invalid_fallback_equalities':invalid,
            'sentinels':len(sentinels),'fits':self.fits,'nfev':self.optimizer,'policy_queries':self.queries,
            'branch_executions':len(self.finished),'source_returns':int(self.returned)}
