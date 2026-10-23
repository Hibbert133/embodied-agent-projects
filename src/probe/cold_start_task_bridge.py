"""Visible-only dispatch for fixed response-estimator task controls."""
from src.probe.cold_start_response import ColdPrefix, infer_operator as infer_joint
from src.probe.operator_identification import OperatorSample, infer_operator as infer_arx

TASKS = ("push-v3", "reach-v3", "door-open-v3")
METHODS = ("JOINT8", "JOINT_DROP2_8", "SAME_DATA_POINT8", "OLD_POINT8", "OLD_G8", "OLD_POINT16_CYCLE", "NO_PROBE", "IDENTITY_AFTER8")
PORTFOLIO = tuple(m for m in METHODS if m != "NO_PROBE")
NEW_SOURCE = ("JOINT8", "JOINT_DROP2_8", "SAME_DATA_POINT8")
OLD_SOURCE = ("OLD_POINT8", "OLD_G8", "OLD_POINT16_CYCLE")
RESPONSE_SHA = "08d2f6a7451e8e6f63aed9bf5bd15ce34158b2c219025547a483f6d925b423ad"
OLD_SHA = "b3f2d7e69316dba65e722d74d49df25c7d651043e78bf4c0f6e1d37f1e599c80"


def source_hash(method):
    if method not in METHODS: raise ValueError("unregistered fixed control")
    return RESPONSE_SHA if method in NEW_SOURCE else OLD_SHA if method in OLD_SOURCE else None


def point_fit(method, old_model, joint_model, new_arx, prefix, samples):
    if method not in ("JOINT8", "JOINT_DROP2_8", "SAME_DATA_POINT8", "OLD_POINT8", "OLD_POINT16_CYCLE"):
        raise ValueError("registered point estimator required")
    if method != "OLD_POINT16_CYCLE" and (type(prefix) is not ColdPrefix or len(prefix.commands) != 8):
        raise ValueError("complete real eight-step visible prefix required")
    if method == "OLD_POINT16_CYCLE" and (prefix is not None or len(samples) != 14):
        raise ValueError("registered sixteen-step history required")
    if any(type(s) is not OperatorSample for s in samples) or tuple(s.step for s in samples) != tuple(range(3,17 if method == "OLD_POINT16_CYCLE" else 9)):
        raise ValueError("completed chronological visible history required")
    if method in ("JOINT8", "JOINT_DROP2_8"):
        return infer_joint(joint_model, prefix, method == "JOINT_DROP2_8")
    return infer_arx(new_arx if method == "SAME_DATA_POINT8" else old_model, samples)
