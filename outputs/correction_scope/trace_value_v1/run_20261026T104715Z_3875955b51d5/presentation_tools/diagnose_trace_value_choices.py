"""Post-hoc description of saved decisions; no fitting or new model query."""
from pathlib import Path
from time import perf_counter_ns
import csv, json, math, sys

ROOT = Path(r'C:/Users/Administrator/Desktop/embodied-agent-projects')
sys.path.insert(0, str(ROOT))
from src.analysis import correction_trace_value_v1 as m
io = m.io


def diagnose(path):
    path = Path(path).resolve()
    manifest = m.checked(path)
    base = path.parent
    audit = io.read(base / 'replay_audit.json')
    result = io.read(base / 'results.json')
    assert audit['integrity'] == 'PASSED'
    assert audit['results_sha256'] == io.sha(base / 'results.json')
    assert audit['replay_sha256'] == io.sha(base / 'replay.jsonl')
    out = base / 'posthoc_choice_diagnosis_v2'
    out.mkdir(exist_ok=False)
    start = perf_counter_ns()
    guard = {}
    with m.old.recorded_guard(guard, out / 'failure.json'):
        with (base / 'replay.jsonl').open(encoding='utf8') as stream:
            events = [json.loads(line) for line in stream]
        choices = {}
        for event in events:
            if event['kind'] == 'RATE_CHOICE':
                key = (tuple(event['unit']), event['selector'])
                assert key not in choices
                choices[key] = event
        outcomes = {(tuple(r['unit']), r['selector']): r for r in result['results']}
        units = sorted({tuple(r['unit']) for r in result['results']})
        rows = []
        for unit in units:
            for kind in ('LINEAR', 'RBF'):
                full = outcomes[unit, 'MOVE_FULL_' + kind]
                mask = outcomes[unit, 'MOVE_MASK_' + kind]
                fc = choices.get((unit, full['selector']))
                mc = choices.get((unit, mask['selector']))
                assert (fc is None) == (mc is None)
                live = fc is not None
                row = dict(unit=list(unit), kind=kind, live_pair=live,
                    missing_reason=None if live else 'PREFIX_OR_ACQUISITION_ALREADY_TERMINAL',
                    FULL_rate=full['rate'], MASK_rate=mask['rate'],
                    choice_changed=live and fc['rate'] != mc['rate'],
                    FULL_loss=full['loss'], MASK_loss=mask['loss'],
                    actual_FULL_minus_MASK=full['loss'] - mask['loss'],
                    FULL_success=full['success'], MASK_success=mask['success'],
                    FULL_predicted_difference_steps=None, MASK_predicted_difference_steps=None,
                    FULL_predicted_tie=None, FULL_optimistic_but_actually_harmful=None)
                if live:
                    assert fc['model_sha256'] == mc['model_sha256']
                    rf, rm = fc['rate'], mc['rate']
                    row['FULL_predicted_difference_steps'] = 500 * (fc['values'][rf] - fc['values'][rm])
                    row['MASK_predicted_difference_steps'] = 500 * (mc['values'][rf] - mc['values'][rm])
                    row['FULL_predicted_tie'] = abs(fc['values'][rf] - fc['values'][rm]) <= 1e-10
                    row['FULL_optimistic_but_actually_harmful'] = (
                        fc['values'][rf] < fc['values'][rm] - 1e-10 and full['loss'] > mask['loss'])
                rows.append(row)
        summaries = []
        for kind in ('LINEAR', 'RBF'):
            rr = [r for r in rows if r['kind'] == kind]
            live = [r for r in rr if r['live_pair']]
            changed = [r for r in live if r['choice_changed']]
            summaries.append(dict(kind=kind, all_units=len(rr), live_pairs=len(live),
                missing_terminal_pairs=len(rr)-len(live), changed=len(changed),
                FULL_optimistic_but_actually_harmful=sum(r['FULL_optimistic_but_actually_harmful'] for r in live),
                FULL_harm_cases=sum(r['actual_FULL_minus_MASK'] > 0 for r in rr),
                FULL_help_cases=sum(r['actual_FULL_minus_MASK'] < 0 for r in rr),
                FULL_harm_predicted_tie_cases=sum(r['actual_FULL_minus_MASK'] > 0 and r['FULL_predicted_tie'] is True for r in rr),
                mean_actual_difference=sum(r['actual_FULL_minus_MASK'] for r in rr)/len(rr),
                changed_mean_FULL_predicted_difference_steps=sum(r['FULL_predicted_difference_steps'] for r in changed)/len(changed)))

        # A second, literal pass uses journal OUTCOMEs, not the result summary,
        # and does not call the row-building code or query a receiver again.
        literal = {}
        for event in events:
            if event['kind'] in ('RATE_CHOICE', 'OUTCOME'):
                key = (tuple(event['unit']), event['selector'])
                literal.setdefault(key, {})[event['kind']] = event
        checked = 0
        for row in rows:
            unit = tuple(row['unit'])
            left = literal[unit, 'MOVE_FULL_' + row['kind']]
            right = literal[unit, 'MOVE_MASK_' + row['kind']]
            assert left['OUTCOME']['loss'] - right['OUTCOME']['loss'] == row['actual_FULL_minus_MASK']
            assert left['OUTCOME']['success'] == row['FULL_success']
            assert right['OUTCOME']['success'] == row['MASK_success']
            checked += 3
            if 'RATE_CHOICE' in left:
                a, b = left['RATE_CHOICE'], right['RATE_CHOICE']
                assert a['sequence'] < left['OUTCOME']['sequence'] and b['sequence'] < right['OUTCOME']['sequence']
                assert math.isclose((a['values'][a['rate']] - a['values'][b['rate']])*500,
                                    row['FULL_predicted_difference_steps'], abs_tol=1e-12)
                assert math.isclose((b['values'][a['rate']] - b['values'][b['rate']])*500,
                                    row['MASK_predicted_difference_steps'], abs_tol=1e-12)
                assert m.R[a['rate']] == row['FULL_rate'] and m.R[b['rate']] == row['MASK_rate']
                checked += 4
            else:
                assert row['FULL_predicted_difference_steps'] is None and row['MASK_predicted_difference_steps'] is None
                checked += 1
        assert len(rows) == 108
        with (out / 'all_108_pairs.csv').open('x', encoding='utf-8-sig', newline='') as f:
            writer = csv.DictWriter(f, fieldnames=list(rows[0]))
            writer.writeheader()
            writer.writerows(rows)
        io.write(out / 'all_pairs.json', dict(classification='POST_HOC_DESCRIPTIVE_SAVED_CHOICE_DIAGNOSIS',
            manifest_id=manifest['manifest_id'], rows=rows, summaries=summaries))
    io.write(out / 'audit.json', dict(integrity='PASSED', classification='POST_HOC_DESCRIPTIVE_ONLY',
        script_sha256=io.sha(__file__), manifest_id=manifest['manifest_id'],
        results_sha256=io.sha(base/'results.json'), replay_sha256=io.sha(base/'replay.jsonl'),
        all_pairs_sha256=io.sha(out/'all_pairs.json'), csv_sha256=io.sha(out/'all_108_pairs.csv'),
        summaries=summaries, literal_checked_fields=checked, guard=guard,
        no_unique_physical_cause_or_intrinsic_information_claim=True,
        new_physics=0, new_fits=0, new_receiver_queries=0, online_LLM_API_calls=0,
        wall_ns=perf_counter_ns()-start))
    print(dict(integrity='PASSED', summaries=summaries, literal_checked_fields=checked))


if __name__ == '__main__':
    diagnose(sys.argv[1])
