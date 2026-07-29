import json, unittest
from types import SimpleNamespace
from src.research_agent import AnthropicResearchAgent

class Messages:
    def __init__(self,payload): self.payload=payload
    def create(self,**kwargs):
        self.kwargs=kwargs
        return SimpleNamespace(id="mock",model="mock",content=[SimpleNamespace(type="text",text=json.dumps(self.payload))],usage=SimpleNamespace(input_tokens=1,output_tokens=2))
class ResearchAgentTest(unittest.TestCase):
    def config(self,i):
        return {"config_id":i,"probe_steps_per_direction":4,"probe_magnitude":.2,"secondary_axis_threshold":.04,
                "dominance_ratio":2.0,"allowed_schedules":["whole"],"offer_abstain":True,"evidence_detail":"terminal","max_recovery_rollouts":1}
    def test_valid_bounded_proposal(self):
        payload={"candidates":[self.config("a"),self.config("b")],"hypothesis":"shorter probes preserve success",
                 "targeted_counterexample_ids":["case_1"],"expected_metric_change":"fewer environment steps"}
        agent=AnthropicResearchAgent(client=SimpleNamespace(messages=Messages(payload)))
        proposal,audit=agent.propose(agent_cases=[{"case_id":"case_1"}],prior_results=[],search_space={"probe_steps":[2,4,8]},round_id=1)
        self.assertEqual(len(proposal.candidates),2); self.assertEqual(audit["usage"]["output_tokens"],2)
        self.assertEqual(proposal.candidates[0].config_id,"research_r1_c1")
    def test_missing_model_config_ids_are_assigned_by_harness(self):
        first=self.config("ignored"); second=self.config("also_ignored")
        first.pop("config_id"); second.pop("config_id")
        payload={"candidates":[first,second],"hypothesis":"reduce probe cost",
                 "targeted_counterexample_ids":["case_1"],"expected_metric_change":"fewer steps"}
        agent=AnthropicResearchAgent(client=SimpleNamespace(messages=Messages(payload)))
        proposal,_=agent.propose(agent_cases=[{"case_id":"case_1"}],prior_results=[],search_space={},round_id=2)
        self.assertEqual([x.config_id for x in proposal.candidates],["research_r2_c1","research_r2_c2"])
    def test_unknown_target_fails_closed(self):
        payload={"candidates":[self.config("a"),self.config("b")],"hypothesis":"h","targeted_counterexample_ids":["oracle_case"],"expected_metric_change":"m"}
        agent=AnthropicResearchAgent(client=SimpleNamespace(messages=Messages(payload)))
        with self.assertRaisesRegex(RuntimeError,"unknown counterexample"):
            agent.propose(agent_cases=[{"case_id":"case_1"}],prior_results=[],search_space={},round_id=1)

if __name__=="__main__": unittest.main()
