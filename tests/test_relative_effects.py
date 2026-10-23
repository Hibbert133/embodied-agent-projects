import copy
from dataclasses import asdict
import itertools
import math
import random
import unittest

from src.probe.relative_effects import RelativeEffectMonitor, RelativeRequest, score_and_range, mixture_interval


def request(**changes):
    values = dict(trial=1, history_digest="a"*64, baseline_action=(0.,0.,0.,0.), candidate_action=(.4,0.,0.,0.),
                  probability=.5, predicted_baseline=.2, predicted_candidate=-.1, remaining_steps=500)
    values.update(changes)
    return RelativeRequest(**values)


class RelativeEffectsTest(unittest.TestCase):
    def test_conditional_contrast_unbiased_with_misspecified_predictions_and_adaptive_propensity(self):
        for history in itertools.product((0,1), repeat=5):
            p = .25 if sum(history)%2 else .75
            y0 = .1*sum(history)-.3; y1 = y0 + .2-.05*history[-1]
            r = request(probability=p, predicted_baseline=-.8, predicted_candidate=.9)
            d0, low, high = score_and_range(r,0,y0); d1, _, _ = score_and_range(r,1,y1)
            self.assertAlmostEqual((1-p)*d0+p*d1,y1-y0,places=13)
            self.assertLessEqual(low,min(d0,d1)); self.assertGreaterEqual(high,max(d0,d1))

    def test_exact_range_contains_all_assignment_and_outcome_endpoints(self):
        for p,m0,m1 in itertools.product((.1,.25,.5,.9),(-1.,.3,1.),(-1.,-.2,1.)):
            r=request(probability=p,predicted_baseline=m0,predicted_candidate=m1)
            values=[score_and_range(r,z,y)[0] for z,y in itertools.product((0,1),(-1.,1.))]
            _,low,high=score_and_range(r,0,0.)
            self.assertEqual(low,min(values));self.assertEqual(high,max(values))

    def test_request_rejects_extra_oracle_future_and_nested_fields(self):
        base=asdict(request())
        for key in ("true_gain","seed","future_return","executed_action_oracle"):
            payload=copy.deepcopy(base);payload[key]={"value":1}
            with self.assertRaises(ValueError):RelativeRequest.from_payload(payload)
        for key,value in (("probability",0.),("probability",1.),("predicted_baseline",float('nan')),
                          ("candidate_action",(2,0,0,0)),("history_digest","unknown"),("trial",True)):
            payload=copy.deepcopy(base);payload[key]=value
            with self.assertRaises(ValueError):RelativeRequest.from_payload(payload)

    def test_action_assignment_changes_the_saved_executable_command(self):
        for draw,expected in ((.1,1),(.9,0)):
            monitor=RelativeEffectMonitor(lambda:draw);r=request()
            prepared=monitor.prepare(r);assigned=monitor.randomize()
            self.assertEqual(assigned['request_id'],prepared['request_id'])
            self.assertEqual(assigned['assignment'],expected)
            self.assertEqual(assigned['command'],r.candidate_action if expected else r.baseline_action)

    def test_outcome_requires_prior_saved_assignment_and_cannot_be_reused(self):
        monitor=RelativeEffectMonitor(lambda:.1)
        with self.assertRaises(ValueError):monitor.observe('unknown',.2)
        saved=monitor.prepare(request())
        with self.assertRaises(ValueError):monitor.observe(saved['request_id'],.2)
        monitor.randomize()
        with self.assertRaises(ValueError):monitor.randomize()
        with self.assertRaises(ValueError):monitor.prepare(request())
        with self.assertRaises(ValueError):monitor.observe('unknown',.2)
        with self.assertRaises(ValueError):monitor.observe(saved['request_id'],float('inf'))
        result=monitor.observe(saved['request_id'],.2)
        self.assertFalse(result['task_utility_guarantee']);self.assertFalse(result['controller_returned'])
        with self.assertRaises(ValueError):monitor.observe(saved['request_id'],.2)

    def test_budget_and_noncontiguous_history_fail_without_consuming_draw(self):
        draws=[]
        monitor=RelativeEffectMonitor(lambda:draws.append(1) or .1)
        for r in (request(remaining_steps=32),request(trial=2)):
            with self.assertRaises(ValueError):monitor.prepare(r)
        self.assertEqual(draws,[])
        saved=monitor.prepare(request());monitor.randomize();monitor.observe(saved['request_id'],.2)
        with self.assertRaises(ValueError):monitor.prepare(request(trial=2,remaining_steps=498))
        saved=monitor.prepare(request(trial=2,remaining_steps=499));monitor.randomize();monitor.observe(saved['request_id'],.2)
        self.assertEqual(len(draws),2)

    def test_normal_mixture_crossing_matches_integrated_evalue(self):
        alpha,rho,total,v,n=.05,4.,9.,12.,7
        interval=mixture_interval(total,v,n,alpha,rho)
        b=interval['half_width_before_intersection']*n
        e=math.sqrt(rho/(v+rho))*math.exp(b*b/(2*(v+rho)))
        self.assertAlmostEqual(e,1/alpha,places=12)
        with self.assertRaises(ValueError):mixture_interval(0.,-1.,1)

    def test_empty_confidence_set_is_preserved_not_censored_or_repaired(self):
        interval=mixture_interval(100.,1.,100)
        self.assertFalse(interval['empty'])
        interval=mixture_interval(500.,1.,100)
        self.assertTrue(interval['empty']);self.assertGreater(interval['lower'],interval['upper'])

    def test_identical_proximal_history_does_not_identify_terminal_policy_order(self):
        records=[]
        for world in ('good','bad'):
            monitor=RelativeEffectMonitor(random.Random(20261015).random)
            part=[]
            for t in range(1,65):
                saved=monitor.prepare(request(trial=t,remaining_steps=501-t,predicted_baseline=0.,predicted_candidate=0.))
                assigned=monitor.randomize()
                part.append(monitor.observe(saved['request_id'],.5 if assigned['assignment'] else -.5))
            records.append(part)
        self.assertEqual(records[0],records[1])
        self.assertGreater(records[0][-1]['interval']['lower'],0.)
        terminal_baseline=.5;terminal_candidate={'good':1.,'bad':0.}
        self.assertGreater(terminal_candidate['good'],terminal_baseline)
        self.assertLess(terminal_candidate['bad'],terminal_baseline)

    def test_past_average_is_not_the_effect_at_the_next_state(self):
        monitor=RelativeEffectMonitor(lambda:.2)
        for t in range(1,65):
            saved=monitor.prepare(request(trial=t,remaining_steps=501-t,predicted_baseline=0.,predicted_candidate=0.))
            assigned=monitor.randomize()
            potential=(-.5,.5) if t<64 else (.5,-.5)
            observed=potential[assigned['assignment']]
            result=monitor.observe(saved['request_id'],observed)
        self.assertGreater(result['interval']['lower'],0.)
        self.assertLess(potential[1]-potential[0],0.)


if __name__ == '__main__':unittest.main()
