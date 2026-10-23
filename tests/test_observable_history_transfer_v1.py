"""Pure arrays, causal windows, fixed allocation and independent statistics."""
from copy import deepcopy
from dataclasses import asdict,replace
from pathlib import Path
import gzip
import json
import socket
import tempfile
import subprocess
import unittest
from unittest.mock import patch
import numpy as np

from src.analysis import observable_history_io_v1 as io
from src.analysis import observable_history_evaluation_v1 as evaluation
from src.analysis import observable_history_audit_v1 as audit
from src.probe import observable_history_model_v1 as model
from src.probe import observable_history_behavior_v1 as behavior
from src.probe.continuous import StepObservation


def trajectory(n=48,key="SYNTHETIC",split="TRAIN"):
    rng=np.random.default_rng(91723);u=rng.uniform(-.6,.6,(n,4));s=np.zeros(39);observations=[]
    for command in u:
        s=s.copy();s[:2]+=.002*command[:2]+[.0001,-.0002];s[2]+=.001*command[2];s[3]=command[3];s[4:7]=[.1,.6,.02];s[-3:]=[.2,.7,.1];observations.append(s)
    return model.HistoryTrajectory("push-v3",key,split,np.zeros(39),u,observations)


def gru(window):
    rng=np.random.default_rng(418);return {"method":"GRU_WINDOW"+str(window),"task":"push-v3","window":window,"input_mean":[0.]*43,"input_scale":[1.]*43,
        "target_mean":[0.,0.],"target_scale":[1.,1.],"output_weight":rng.normal(0,.1,(2,32)).tolist(),"output_bias":[0.,0.],
        "gru":{k:rng.normal(0,.1,shape).tolist() for k,shape in (("weight_ih_l0",(96,43)),("weight_hh_l0",(96,32)),("bias_ih_l0",(96,)),("bias_hh_l0",(96,)))}}


def stats_fixture(missing=False):
    registry=[];metrics=[]
    for c in io.population("TEST"):
        registry.append({k:c[k] for k in ("case_id","group","unit","task","context","measurement_program")})
        for bank in io.PROGRAMS:
            for j,name in enumerate(io.MODELS):
                metrics.append({**registry[-1],"source_bank":bank,"method":name,"stage":"POST_TASK","rmse":None if missing and c["group"]==0 else [1.,.9,1.3,.8,.7][j]+c["group"]*.001,"n":0 if missing and c["group"]==0 else 3})
    return metrics,registry


class ModelTests(unittest.TestCase):
    def test_common_targets_and_dimensions(self):
        t=trajectory();self.assertEqual(model.inputs20(t).shape,(46,20));self.assertEqual(model.inputs43(t).shape,(48,43));self.assertEqual(model.targets(t).shape,(46,2))
        np.testing.assert_array_equal(model.inputs43(t)[0,:39],t.initial)
        np.testing.assert_allclose(model.inputs20(t)[0,6:9],np.array(t.observations[0])[:3]-t.initial[:3])
        for n in (0,1,2):
            s=trajectory(n);self.assertEqual(model.inputs20(s).shape,(0,20));self.assertEqual(model.targets(s).shape,(0,2))

    def test_linear_known_response_and_all_five_common_populations(self):
        t=trajectory()
        for name,count in zip(io.MODELS[:3],(11,21,231)):
            m=model.fit_linear([t],t.task,name);self.assertEqual(m["feature_count"],count);self.assertEqual(model.predict(m,t).shape,(46,2))
            self.assertLess(np.sqrt(np.mean((model.predict(m,t)-model.targets(t))**2)),1e-5)
        for w in (1,16):self.assertEqual(model.predict(gru(w),t).shape,(46,2))

    def test_weighting_gives_each_trajectory_equal_weight(self):
        a=trajectory(20,"A");b=trajectory(70,"B");m=model.fit_linear([a,b],a.task,"STATE_LINEAR20")
        np.testing.assert_allclose(m["mean"],(model.inputs20(a).mean(axis=0)+model.inputs20(b).mean(axis=0))/2,atol=1e-13)
        stats=model.gru_normalization([a,b],a.task);np.testing.assert_allclose(stats["input_mean"],(model.inputs43(a)[2:].mean(axis=0)+model.inputs43(b)[2:].mean(axis=0))/2,atol=1e-13)

    def test_public_schema_rejects_all_private_metadata(self):
        t=asdict(trajectory())
        for k in ("seed","fault_oracle","executed_action_oracle","actual_noise","future_result","private_state"):
            with self.subTest(key=k),self.assertRaises(ValueError):model.HistoryTrajectory.from_dict({**t,k:{"value":0}})
        for command in ((2,0,0,0),(float("nan"),0,0,0)):
            with self.assertRaises(ValueError):replace(trajectory(),commands=[command]*48)

    def test_cal_test_duplicate_and_short_training_rejected(self):
        for split in ("CAL","TEST"):
            t=trajectory(split=split)
            with self.assertRaises(ValueError):model.fit_linear([t],t.task,"HISTORY_LINEAR10")
            with self.assertRaises(ValueError):model.gru_normalization([t],t.task)
        t=trajectory()
        with self.assertRaises(ValueError):model.fit_linear([t,t],t.task,"HISTORY_LINEAR10")
        with self.assertRaises(ValueError):model.fit_linear([trajectory(2)],t.task,"HISTORY_LINEAR10")

    def test_causal_window_uses_true_prefix_and_never_future(self):
        t=trajectory();self.assertEqual(model.causal_window(t,2,16).shape,(3,43));np.testing.assert_array_equal(model.causal_window(t,2,16)[0,:39],t.initial)
        changed=np.array(t.observations);changed[20:]+=100;future=replace(t,observations=changed)
        for w in (1,16):
            a=model.predict(gru(w),t);b=model.predict(gru(w),future);np.testing.assert_array_equal(a[:18],b[:18]);self.assertFalse(np.array_equal(a[19:],b[19:]))
        with self.assertRaises(ValueError):model.causal_window(t,len(t.commands),16)

    def test_gru_reset_gate_matches_declared_reset_after_affine(self):
        x=np.ones((1,43));h=np.ones((1,32));p={"weight_ih_l0":np.zeros((96,43)),"weight_hh_l0":np.zeros((96,32)),"bias_ih_l0":np.zeros(96),"bias_hh_l0":np.r_[np.zeros(64),np.ones(32)]}
        np.testing.assert_allclose(model.gru_cell(x,h,p),.5*np.tanh(.5)+.5)

    def test_constant_features_have_unit_scale(self):
        mean,scale=model.normalization([np.zeros((3,4))],[np.ones(3)]);np.testing.assert_array_equal(mean,0);np.testing.assert_array_equal(scale,1)


class ProtocolTests(unittest.TestCase):
    def test_full_budget_and_disjoint_fresh_allocation(self):
        io.validate(io.expected_config());self.assertEqual([len(io.population(s)) for s in io.SPLITS],[216,108,432])
        seeds=[{c["seed"] for c in io.population(s)} for s in io.SPLITS]
        self.assertTrue(all(not a.intersection(b) for i,a in enumerate(seeds) for b in seeds[i+1:]))
        limits=io.expected_config()["limits"];self.assertEqual(limits["control_steps"],756*168);self.assertEqual(limits["physical_frames"],756*25500+127008*5);self.assertEqual(limits["all_resets"],756*51)

    def test_noise_and_balanced_order_are_paired_and_split_independent(self):
        specs=io.population("TEST");a,b=specs[:2];np.testing.assert_array_equal(io.noise(a["seed"]),io.noise(b["seed"]))
        self.assertFalse(io.noise(a["seed"]).flags.writeable);self.assertNotEqual(io.measurement_program(io.population("TRAIN")[0]),io.measurement_program(io.population("CAL")[0]))
        self.assertEqual(io.initial_fault(specs[0]),io.initial_fault(specs[2]));self.assertNotEqual(io.destination(specs[0]),io.destination(specs[2]))
        behavior.validate_program("BALANCED8",io.measurement_program(a))
        with self.assertRaises(ValueError):behavior.validate_program("BALANCED8",[[0,0,0,-1]]*8)

    def test_transport_fails_closed_and_is_counted(self):
        r={}
        with io.forbid_online_calls(r),self.assertRaises(RuntimeError):socket.create_connection(("invalid.example",443))
        self.assertEqual(r["attempted_network_calls"],1)

    def test_truth_noise_and_clip_order_are_independent(self):
        from src.analysis.short_probe_journal_audit_v1 import applied
        u=[1.,0.,0.,-1.];f={"matrix_xy":[[1.2,0],[0,1]],"bias_xy":[0,0],"deadzone_xy":[0,0]};n=np.array([-.3,0,0],np.float32)
        actual=applied(u,f,n);self.assertAlmostEqual(actual[0],.9,6);self.assertNotAlmostEqual(actual[0],.7,6)

    def test_invalid_c4_stops_without_controller_substitution(self):
        events=[];calls=[];initial=StepObservation([0.]*39,False,False,False);nominal=io.read(io.ROOT/io.C8)["joint"]["push-v3"]
        def emit(kind,payload):
            result={**payload,"sequence":len(events),"saved_ns":len(events)};events.append(result);return result
        def step(request):calls.append(request);return initial
        with patch.object(behavior,"infer_four",return_value={"valid":False,"reason":"SYNTHETIC_INVALID"}):
            result=behavior.run("push-v3",initial,nominal,16,"FEEDBACK8",io.measurement_program(io.population("TRAIN")[0]),lambda o:self.fail("no policy before valid C8"),step,emit)
        self.assertEqual(result["outcome"]["stop_reason"],"INVALID_FOUR");self.assertEqual(len(calls),4);self.assertEqual(result["outcome"]["measurement_steps"],0)


class StatisticsTests(unittest.TestCase):
    def test_full_groups_and_independent_reconstruction(self):
        metrics,registry=stats_fixture();stats=evaluation.statistics(metrics,registry);audit.audit_statistics(stats,metrics,registry)
        self.assertEqual(stats["qualification"],"PASSED_PREDICTIVE_QUALIFICATION_ONLY");self.assertEqual(stats["available_primary_trajectories"],432)
        self.assertAlmostEqual(stats["primary_difference"],-.1);self.assertEqual(len(stats["task_context_program_cells"]),24)

    def test_missing_group_is_not_zero_or_silently_replaced(self):
        metrics,registry=stats_fixture(True);stats=evaluation.statistics(metrics,registry);audit.audit_statistics(stats,metrics,registry)
        self.assertEqual(stats["qualification"],"NOT_QUALIFIED");self.assertIsNone(stats["primary_difference"]);self.assertIsNone(stats["groups"][0]["means"][io.MODELS[0]])
        self.assertEqual(stats["available_primary_trajectories"],408)

    def test_changed_denominator_and_result_are_rejected(self):
        metrics,registry=stats_fixture();stats=evaluation.statistics(metrics,registry)
        for field in ("denominator","primary"):
            bad=deepcopy(stats)
            if field=="denominator":bad["groups"][0]["available"]-=1
            else:bad["primary_difference"]+=.1
            with self.assertRaises(ValueError):audit.audit_statistics(bad,metrics,registry)


class TrainingPipelineTests(unittest.TestCase):
    def test_all_sources_fit_train_only_cal_describes_then_locks(self):
        # Full allocation as pure synthetic arrays. GRU weights are explicit
        # software stubs; actual optimizer/forward qualification is separate.
        def records(split):
            out=[]
            for spec in io.population(split):
                t=trajectory(12,spec["case_id"],split)
                out.append({**spec,"initial":{"observation":t.initial},"physical_rows":[{"command":u,"after":{"observation":o},"phase":"TASK_AFTER_MEASUREMENT"} for u,o in zip(t.commands,t.observations)],"behavior":{"events":[]}})
            return out
        def worker(mode,bundle,models,output,log):
            if mode=="train":
                output.mkdir()
                for e in io.read(bundle)["entries"]:
                    for w in (1,16):
                        value={**gru(w),**e["statistics"],"task":e["task"],"updates":5000,"parameter_count":7458,"initial_parameters_sha256":"SOFTWARE_STUB","sampling_schedule_sha256":"SOFTWARE_STUB"}
                        io.write(output/(e["source_bank"]+"_"+e["task"]+"_GRU_WINDOW"+str(w)+".json"),value)
                io.write(output/"completion.json",{"status":"TWELVE_GRU_MODELS_SAVED"})
            else:io.write(output,{"integrity":"PASSED","scope":"SOFTWARE_STUB_NOT_SCIENTIFIC_QUALIFICATION"})
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);path=root/"manifest.json";manifest={k:"SOFTWARE" for k in io.IDENTITY}
            for split in ("TRAIN","CAL"):
                directory=root/split.lower();directory.mkdir()
                with gzip.open(directory/"cases.jsonl.gz","xt",encoding="utf-8") as log:
                    for r in records(split):log.write(json.dumps(r)+"\n")
                io.write(directory/"completion.json",{"status":"COLLECTED_FOR_INDEPENDENT_AUDIT","artifact_sha256":{}});io.write(directory/"audit.json",{"integrity":"PASSED"})
            with patch.object(io,"load",return_value=manifest),patch.object(evaluation,"worker",worker):
                evaluation.train(path);audit.audit_models(path)
                original=io.sha(root/"training/models.json");evaluation.calibrate(path);audit.audit_calibration(path);evaluation.lock(path)
                self.assertEqual(original,io.sha(root/"training/models.json"));self.assertEqual(io.read(root/"training/models.json")["fits"],30)
                self.assertEqual(len(io.read(root/"calibration/description.json")["cases"]),1080);io.phase_gate(root,"TEST")
                io.write(root/"training/models.json",{},exclusive=False)
                with self.assertRaises(ValueError):io.phase_gate(root,"TEST")

    def test_unlocked_test_and_unqualified_cal_rejected(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder)
            with self.assertRaises(FileNotFoundError):io.phase_gate(root,"TEST")
            (root/"training").mkdir();io.write(root/"training/completion.json",{"status":"TRAINING_FAILED_NO_REPAIR"})
            with self.assertRaises(ValueError):io.phase_gate(root,"CAL")

    def test_training_process_timeout_is_not_retried(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);runtime=root/"runtime.json";io.write(runtime,{"file_sha256":{}})
            with patch.object(io,"RUNTIME",runtime),patch.object(evaluation.subprocess,"run",side_effect=subprocess.TimeoutExpired("SOFTWARE",7200)) as child:
                with self.assertRaises(subprocess.TimeoutExpired):evaluation.worker("train",root/"bundle.json",None,root/"models",root/"process.txt")
                self.assertEqual(child.call_count,1);self.assertEqual(child.call_args.kwargs["timeout"],7200);self.assertTrue((root/"process.txt").exists())


if __name__=="__main__":unittest.main()
