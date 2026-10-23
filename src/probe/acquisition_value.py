"""Frozen branch programs and outcome targets; not an online learned selector."""
from dataclasses import dataclass


@dataclass(frozen=True)
class Program:
    prefix_steps: int
    probe_steps: int
    magnitude: float
    guard: str | None = None
    uncorrected: bool = False
    keep_old: bool = False


PROGRAMS = {
    "CACHE_CONTINUE": Program(0, 0, 0),
    "MID8": Program(6, 8, .2),
    "MID16": Program(6, 16, .2),
    "MID8_WIDE": Program(6, 8, .4),
    "MID16_WIDE": Program(6, 16, .4),
    "MID8_WIDE_KEEP": Program(6, 8, .4, keep_old=True),
    "MID16_WIDE_KEEP": Program(6, 16, .4, keep_old=True),
    "G_OPTIMAL": Program(6, 0, 0, "G_OPTIMAL"),
    "RESPONSE_SET": Program(6, 0, 0, "RESPONSE_SET"),
    "EARLY8_WIDE": Program(0, 8, .4),
    "EARLY16_WIDE": Program(0, 16, .4),
    "NO_PROBE": Program(0, 0, 0, uncorrected=True),
}
METHODS = tuple(PROGRAMS)
MID_METHODS = tuple(m for m, p in PROGRAMS.items() if p.prefix_steps)
PRIOR_CACHE_METHODS = ("CACHE_CONTINUE", *MID_METHODS)
PRIMARY_PAIR = ("MID16_WIDE", "CACHE_CONTINUE")


def deadline_loss(success, stopped, total_steps):
    if type(success) is not bool or type(stopped) is not bool or type(total_steps) is not int or not 0 <= total_steps <= 500:
        raise ValueError("registered realized outcome required")
    if success and stopped:
        raise ValueError("successful stopped branch is inconsistent")
    return total_steps if success else 500


def paired_sign(target, reference):
    a, b = deadline_loss(**target), deadline_loss(**reference)
    return 1 if a < b else -1 if a > b else 0


def repeat_consistency(signs):
    if len(signs) != 4 or any(type(s) is not int or s not in (-1, 0, 1) for s in signs):
        raise ValueError("four registered replicate signs required")
    nonzero = [s for s in signs if s]
    checked = correct = ties = 0
    for index, sign in enumerate(signs):
        if not sign:
            continue
        other = sum(s for i, s in enumerate(signs) if i != index)
        if other == 0:
            ties += 1
            continue
        checked += 1
        correct += (1 if other > 0 else -1) == sign
    return {"has_non_tie": bool(nonzero), "sign_reversal": -1 in signs and 1 in signs,
            "leave_one_out_checked": checked, "leave_one_out_correct": correct,
            "leave_one_out_abstained": ties, "zero_ties": signs.count(0)}
