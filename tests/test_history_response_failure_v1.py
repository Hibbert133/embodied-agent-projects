"""Pure arrays and source hashes; no native simulator, training or API imports."""
from copy import deepcopy
import importlib
import unittest
import warnings
import numpy as np
import numpy.testing
from src.analysis import history_response_failure_v1 as a
from src.probe import observable_history_model_v1 as public
from scripts import audit_history_response_failure_v1 as audit


def case(n=36,key="SYNTHETIC",split="TRAIN",group=0):
    rng=np.random.default_rng(7129);commands=rng.uniform(-.5,.5,(n,4));noise=rng.normal(0,.05,(n,3)).astype(np.float32)
    initial=np.zeros(39);initial[:3]=[.1,.6,.2];initial[4:7]=[.2,.7,.02];initial[-3:]=[.3,.8,.1];states=[initial];rows=[]
    for i,u in enumerate(commands):
        s=states[-1].copy();s[:2]+=.002*u[:2]+.0005*noise[i,:2];s[2]=.31 if i>=14 else .2;states.append(s)
        rows.append({"logical_step":i,"noise_cursor_after":i+1,"command":u.tolist(),"after":{"observation":s.tolist()},
            "phase":"FIXED_PROBE" if i<8 else "POLICY" if i<12 else "REPOSITION" if i<16 else "MEASURE_FEEDBACK" if i<24 else "TASK_AFTER_MEASUREMENT"})
    return {"case_id":key,"split":split,"group":group,"task":"push-v3","context":"NOMINAL","measurement_program":"FEEDBACK8","initial":{"observation":initial.tolist()},
        "physical_rows":rows,"behavior":{"events":[] if n<=12 else [{"kind":"ACQUISITION_ENTRY","payload":{"before":{"observation":states[12].tolist()},"anchor":[.1,.6,.3]}}]}},noise


def models():
    result={};rng=np.random.default_rng(135)
    for name in public.METHODS[:3]:
        p=10 if name=="HISTORY_LINEAR10" else 20;columns=231 if name=="QUADRATIC_STATE20" else p+1;coefficient=np.zeros((columns,2));start=7 if p==10 else 10
        coefficient[start,0]=.002;coefficient[start+1,1]=.002
        result[name]={"task":"push-v3","method":name,"mean":[0.]*p,"scale":[1.]*p,"coefficients":coefficient.tolist()}
    parameters={k:rng.normal(0,.05,shape).tolist() for k,shape in (("weight_ih_l0",(96,43)),("weight_hh_l0",(96,32)),("bias_ih_l0",(96,)),("bias_hh_l0",(96,)))}
    for window in (1,16):result["GRU_WINDOW"+str(window)]={"task":"push-v3","method":"GRU_WINDOW"+str(window),"window":window,"gru":deepcopy(parameters),"input_mean":[0.]*43,"input_scale":[1.]*43,"target_mean":[0.,0.],"target_scale":[.002,.003],"output_weight":rng.normal(0,.05,(2,32)).tolist(),"output_bias":[0.,0.]}
    return result


def analyze(c,noise,bank=None,ranges=None):
    bank=models() if bank is None else bank
    ranges=a.training_ranges([c],("FEEDBACK8",),("push-v3",)) if ranges is None else ranges
    return a.analyze_case(c,{"FEEDBACK8":bank},ranges,noise)


class PureDiagnosticTests(unittest.TestCase):
    def test_common_history_real_initial_and_fixed_reference_causality(self):
        c,_=case();t=a.visible(c);self.assertEqual(public.targets(t).shape,(34,2))
        np.testing.assert_array_equal(a.reference_predictions(t,"ZERO_DISPLACEMENT"),0)
        np.testing.assert_array_equal(a.reference_predictions(t,"LAST_DISPLACEMENT")[0],np.array(t.observations[1])[:2]-np.array(t.observations[0])[:2])
        changed=deepcopy(c);changed["physical_rows"][20]["after"]["observation"][0]+=10
        for name in ("ZERO_DISPLACEMENT","LAST_DISPLACEMENT"):
            np.testing.assert_array_equal(a.reference_predictions(t,name)[:18],a.reference_predictions(a.visible(changed),name)[:18])

    def test_trace_matches_independent_equations_for_both_windows(self):
        c,_=case();t=a.visible(c);_,_,x,_=audit.arrays(c)
        for name in public.METHODS[3:]:
            model=models()[name];prediction,trace=a.gru_trace(model,t);independent,other=audit.independently_traced(model,x)
            np.testing.assert_allclose(prediction,independent,atol=1e-14)
            for key in trace:np.testing.assert_allclose(trace[key],other[key],atol=1e-13)

    def test_known_linear_noise_residual_and_full_stage_population(self):
        c,noise=case();rows=analyze(c,noise);self.assertEqual(len(rows),7*8)
        original=next(r for r in rows if (r["method"],r["stage"])==("HISTORY_LINEAR10","ALL_RESPONSE"))
        self.assertAlmostEqual(original["rmse"],float(np.sqrt(np.mean((noise[2:,:2]*.0005)**2))),10)
        self.assertAlmostEqual(original["raw_noise_correlation"][0]["correlations"][0][0],1.,10)
        self.assertEqual({r["stage"] for r in rows},set(a.STAGES))

    def test_phase_objective_identity_and_no_fake_lift(self):
        c,n=case();rows=analyze(c,n);labels=a.phase_labels(c);self.assertEqual(labels.tolist(),audit.labels(c))
        self.assertEqual(sum(labels=="LIFT"),3);self.assertEqual(sum(labels=="POST_LIFT"),1)
        for name in a.MODELS:
            part=[r for r in rows if r["method"]==name];whole=next(r for r in part if r["stage"]=="ALL_RESPONSE");pieces=[r for r in part if r["stage"] in a.EXCLUSIVE]
            self.assertAlmostEqual(sum(r["optimization_sampling_mass"] for r in pieces),1.)
            self.assertAlmostEqual(sum(r["optimization_error_mass"] or 0 for r in pieces),whole["standardized_mse"])

    def test_empty_short_and_early_trajectories_preserve_nulls(self):
        for length in (0,1,2,6,14):
            c,noise=case(length);ranges={"FEEDBACK8":{"push-v3":{"minimum":[-1.]*43,"maximum":[1.]*43}}}
            with warnings.catch_warnings():
                warnings.simplefilter("error");rows=analyze(c,noise,ranges=ranges)
            for r in rows:
                if r["responses"]==0:self.assertIsNone(r["rmse"]);self.assertIsNotNone(r["missing_reason"])
            if length<3:self.assertTrue(all(r["responses"]==0 for r in rows))

    def test_training_range_rejects_cal_test_and_includes_all_real_inputs(self):
        for split in ("CAL","TEST"):
            with self.assertRaises(ValueError):a.training_ranges([case(split=split)[0]],("FEEDBACK8",),("push-v3",))
        c,_=case();ranges=a.training_ranges([c],("FEEDBACK8",),("push-v3",));x=public.inputs43(a.visible(c))[2:]
        np.testing.assert_array_equal(ranges["FEEDBACK8"]["push-v3"]["minimum"],x.min(axis=0))

    def test_small_saved_scale_is_measured_without_changing_it(self):
        c,noise=case();bank=models();bank["GRU_WINDOW16"]["input_scale"][39]=1e-6;before=deepcopy(bank)
        rows=analyze(c,noise,bank);r=next(r for r in rows if r["method"]=="GRU_WINDOW16" and r["stage"]=="ALL_RESPONSE")
        self.assertGreater(r["gru"]["current_input_any_abs_z_over_10"],.9);self.assertEqual(bank,before)
        self.assertEqual(len(r["gru"]["feature_input_affine_rms_contribution"]),43)

    def test_known_gate_saturation_and_no_hidden_padding(self):
        c,_=case(3);t=a.visible(c);m=models()["GRU_WINDOW16"]
        for k in m["gru"]:m["gru"][k]=np.zeros(np.shape(m["gru"][k])).tolist()
        m["gru"]["bias_ih_l0"]=[100.]*32+[-100.]*32+[100.]*32
        _,trace=a.gru_trace(m,t)
        self.assertEqual(trace["reset_saturated"].tolist(),[1.]);self.assertEqual(trace["update_saturated"].tolist(),[1.]);self.assertEqual(trace["hidden_saturated"].tolist(),[1.])

    def test_noise_cursor_shape_and_missing_boundary_are_rejected(self):
        c,n=case();bad=deepcopy(c);bad["physical_rows"][2]["noise_cursor_after"]+=1
        with self.assertRaises(ValueError):analyze(bad,n)
        with self.assertRaises(ValueError):analyze(c,n[1:])
        bad=deepcopy(c);bad["behavior"]["events"]=[]
        with self.assertRaises(ValueError):analyze(bad,n)

    def test_lag_alignment_uses_past_source_including_real_first_two(self):
        source=np.arange(30,dtype=float)[:,None]**2;target=source[2:];indices=np.arange(2,30)
        for result in a.correlation_matrix(target,source,indices):
            count,expected=audit.correlations(target,source,indices,result["lag"]);self.assertEqual(result["pairs"],count)
            np.testing.assert_allclose(result["correlations"],expected,atol=1e-14)
        constant=np.zeros((30,1));self.assertIsNone(a.correlation_matrix(target,constant,indices)[0]["correlations"][0][0])

    def test_future_observations_and_private_fields_cannot_change_earlier_forward(self):
        c,n=case();changed=deepcopy(c);changed["future_oracle"]={"bias_xy":[10,20]};changed["physical_rows"][25]["after"]["observation"][0]+=20
        for name in public.METHODS[3:]:
            m=models()[name];a1,_=a.gru_trace(m,a.visible(c));a2,_=a.gru_trace(m,a.visible(changed));np.testing.assert_array_equal(a1[:23],a2[:23])

    def test_evaluator_noise_cannot_change_any_frozen_prediction(self):
        c,n=case();bank=models();one=analyze(c,n,bank);two=analyze(c,n*5,bank)
        for r,s in zip(one,two):self.assertEqual(r["prediction_rms"],s["prediction_rms"]);self.assertEqual(r["rmse"],s["rmse"])

    def test_original_prediction_chronology_is_verified(self):
        c,n=case(6);t=a.visible(c);bank=models();source=[]
        for name in public.METHODS:
            prediction=public.predict(bank[name],t)
            for j,(p,y) in enumerate(zip(prediction,public.targets(t))):source.append({"case_id":c["case_id"],"source_bank":"FEEDBACK8","method":name,"step":j+2,"stage":"FIXED_PROBE","prediction":p.tolist(),"target":y.tolist()})
        geometry=a.training_ranges([c],("FEEDBACK8",),("push-v3",))
        a.analyze_case(c,{"FEEDBACK8":bank},geometry,n,iter(source))
        source[0]["step"]+=1
        with self.assertRaises(ValueError):a.analyze_case(c,{"FEEDBACK8":bank},geometry,n,iter(source))


class GuardAndAggregationTests(unittest.TestCase):
    def test_simulator_optimizer_training_and_child_process_imports_fail_closed(self):
        with a.diagnostic_guard():
            for name in ("mujoco","metaworld","gymnasium","requests","torch","scipy.optimize"):
                with self.subTest(name=name),self.assertRaises(RuntimeError):__import__(name)
            with self.assertRaises(RuntimeError):np.linalg.lstsq(np.ones((3,1)),np.ones(3),rcond=None)
            with self.assertRaises(RuntimeError):public.fit_linear([],"push-v3","HISTORY_LINEAR10")
            import subprocess
            with self.assertRaises(RuntimeError):subprocess.run(["python","--version"])

    def test_equal_group_weight_not_equal_time_or_source_replicates(self):
        a1,n1=case(26,"A",group=0);b,n2=case(60,"B",group=1);bank=models();ranges=a.training_ranges([a1,b],("FEEDBACK8",),("push-v3",))
        rows=analyze(a1,n1,bank,ranges)+analyze(b,n2,bank,ranges)
        table=a.grouped(rows,("method","stage"));row=next(r for r in table if (r["method"],r["stage"])==("HISTORY_LINEAR10","POST_TASK"))
        expected=[r["rmse"] for r in rows if (r["method"],r["stage"])==("HISTORY_LINEAR10","POST_TASK")]
        self.assertAlmostEqual(row["rmse"],sum(expected)/2);self.assertEqual(row["available_groups"],2)

    def test_absent_stage_objective_mass_is_zero_but_predictive_error_stays_null(self):
        c,n=case(6);rows=analyze(c,n);row=next(r for r in a.grouped(rows,("method","stage")) if (r["method"],r["stage"])==("HISTORY_LINEAR10","POST_TASK"))
        self.assertIsNone(row["rmse"]);self.assertEqual(row["optimization_error_mass"],0);self.assertEqual(row["available_groups"],0)

    def test_full_feature_arrays_have_equal_group_weight_and_missing_markers(self):
        c,n=case();rows=analyze(c,n);selected=[r for r in rows if r["method"]=="GRU_WINDOW16" and r["stage"]=="POST_TASK"]
        other=deepcopy(selected[0]);other["group"]=1
        for key in ("feature_abs_z_q95","feature_outside_train_fraction","feature_input_affine_rms_contribution"):other["gru"][key]=[2*x for x in other["gru"][key]]
        table=a.feature_tables([*selected,other]);self.assertEqual(len(table),1)
        np.testing.assert_allclose(table[0]["feature_abs_z_q95"],np.array(selected[0]["gru"]["feature_abs_z_q95"])*1.5)
        missing=deepcopy(other);missing["responses"]=0
        result=a.feature_tables([missing])[0];self.assertEqual(result["available"],0);self.assertIsNone(result["feature_abs_z_q95"])


if __name__=="__main__":unittest.main()
