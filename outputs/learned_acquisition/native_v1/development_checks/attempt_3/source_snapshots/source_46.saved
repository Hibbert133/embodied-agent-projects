"""Private, inspectable state witnesses with one explicit statistics projection.

The full graph/hash is retained. Only RecordEpisodeStatistics timing values
are projected for cross-instance comparison; queue length/capacity and the
uninitialized timer sentinel remain. This is a scoped comparison contract,
not a universal behavioral-equivalence or external-physics certificate.
No simulator state is restored, copied into an Env, or exposed to an actor.
"""
from collections import deque
from copy import deepcopy
import io
import json
import math
from pathlib import Path
import random
import types

import gymnasium.wrappers.common as common
import numpy as np

from src.analysis.capsule_record_json_v2 import normalize
from src.analysis.state_capsule_v1 import (
    ArrayPickler, layers, native_hash, python_state, sha, spec_callable_fingerprint,
    state_signature, validate_graph)

SCHEMA = "continuous_state_witness_v1"
STATISTICS_TYPE = "gymnasium.wrappers.common.RecordEpisodeStatistics"
COMMON_SOURCE_SHA256 = "2a2cd78973296d5871af0ae1334f4c567cacef380bc69b4a759fcc29cbcff51a"
PROJECTION = "EXACT_RECORD_EPISODE_STATISTICS_TIMER_AND_DURATION_VALUES_V1"
STATISTICS_METHODS = {name: getattr(common.RecordEpisodeStatistics, name) for name in ("__init__", "step", "reset")}
STATISTICS_FIELDS = {"_saved_kwargs", "_action_space", "_observation_space", "_metadata", "_cached_spec",
    "_stats_key", "episode_count", "episode_start_time", "episode_returns", "episode_lengths",
    "time_queue", "return_queue", "length_queue"}


def require(ok, message):
    if not ok: raise ValueError(message)


def graph_hash(value):
    # Must match the existing state_signature encoding, not the unrelated
    # sorted-key public-evidence digest. Graphs contain ordered node lists.
    return sha(json.dumps(value, ensure_ascii=True, separators=(",", ":"), allow_nan=False).encode())


def semantic_graph(value, model, data):
    """Materialize the existing signature's graph without deserializing objects.

    This version duplicates its traversal deliberately to preserve the frozen
    module. capture_witness checks equality with that module's hash each time.
    Array bytes remain hashes; graph/alias layout and scalar state are saved.
    """
    validate_graph(value);arrays = ArrayPickler(io.BytesIO(), model, data);memo = {}
    def visit(obj):
        if obj is None: return ["none"]
        if type(obj) in (str, bool, int): return [type(obj).__name__, obj]
        if type(obj) is bytes: return ["bytes", len(obj), sha(obj)]
        if type(obj) is float: return ["float", obj.hex()]
        if type(obj) is complex: return ["complex", obj.real.hex(), obj.imag.hex()]
        if isinstance(obj, np.dtype): return ["dtype", obj.str, repr(obj.descr)]
        if isinstance(obj, np.generic): return ["scalar", obj.dtype.str, obj.tobytes().hex()]
        if type(obj) is types.FunctionType: return ["spec_callable", spec_callable_fingerprint(obj)]
        if id(obj) in memo: return ["ref", memo[id(obj)][0]]
        number = len(memo);memo[id(obj)] = (number, obj)
        if type(obj) is np.ndarray:
            _, index = arrays.persistent_id(obj)
            return ["array", number, index, sha(obj.tobytes(order="C"))]
        if type(obj) is dict: return ["dict", number, [[visit(k), visit(v)] for k, v in obj.items()]]
        if isinstance(obj, (list, tuple, set, frozenset, deque)):
            children = list(obj)
            if isinstance(obj, (set, frozenset)): children.sort(key=repr)
            return [type(obj).__module__ + "." + type(obj).__qualname__, number,
                    obj.maxlen if isinstance(obj, deque) else None, [visit(v) for v in children]]
        if type(obj) is np.random.Generator: return ["generator", number, type(obj.bit_generator).__name__, visit(obj.bit_generator.state)]
        if type(obj) is random.Random: return ["random", number, visit(obj.getstate())]
        return [type(obj).__module__ + "." + type(obj).__qualname__, number, visit(vars(obj))]
    return normalize([visit(value), arrays.arrays, [sha(v) for v in arrays.buffers]])


def dict_fields(node):
    require(type(node) is list and len(node) == 3 and node[0] == "dict" and type(node[1]) is int
            and type(node[2]) is list, "materialized state dictionary required")
    result = {}
    for pair in node[2]:
        require(type(pair) is list and len(pair) == 2, "malformed dictionary pair")
        key, value = pair
        require(type(key) is list and len(key) == 2 and key[0] == "str" and type(key[1]) is str
                and key[1] not in result, "unique string state field required")
        result[key[1]] = value
    return result


def inspect_shape(graph, layer_types):
    require(type(graph) is list and len(graph) == 3 and type(graph[1]) is list and type(graph[2]) is list, "complete semantic graph required")
    root = dict_fields(graph[0])
    require(set(root) == {"layers", "renderer", "policy", "context", "numpy_global", "python_global"}, "registered Python state roots required")
    stack = root["layers"]
    require(type(stack) is list and len(stack) == 4 and stack[0] == "builtins.list" and stack[2] is None
            and type(stack[3]) is list, "materialized environment layer list required")
    require(type(layer_types) is list and len(layer_types) == len(stack[3]) and layer_types
            and all(type(x) is str and x for x in layer_types), "exact layer type sequence required")
    require(layer_types.count(STATISTICS_TYPE) == 1, "exactly one reviewed statistics wrapper required")
    return root, [dict_fields(node) for node in stack[3]]


def finite_timer(node, *, initial=False):
    require(type(node) is list and len(node) == 2, "scalar timing field required")
    if initial and node == ["int", -1] and type(node[1]) is int: return None
    require(node[0] == "float" and type(node[1]) is str, "ordinary floating-point timing value required")
    try: value = float.fromhex(node[1])
    except ValueError as error: raise ValueError("invalid float timer encoding") from error
    require(math.isfinite(value) and value >= 0 and value.hex() == node[1], "finite nonnegative canonical timer required")
    return value


def project_graph(raw, layer_types):
    """Pure replayable edit of two exact fields; all other nodes stay verbatim."""
    projected = deepcopy(raw);_, fields = inspect_shape(projected, layer_types)
    index = layer_types.index(STATISTICS_TYPE);stats = fields[index]
    require(set(stats) == STATISTICS_FIELDS, "unreviewed statistics wrapper fields")
    timer = stats["episode_start_time"];duration = stats["time_queue"]
    initialized = finite_timer(timer, initial=True) is not None
    require(type(duration) is list and len(duration) == 4 and duration[0] == "collections.deque"
            and type(duration[1]) is int and type(duration[2]) is int and duration[2] > 0
            and type(duration[3]) is list and len(duration[3]) <= duration[2], "owned bounded timing queue required")
    # A queue exposed through another field could become a controller input;
    # do not erase an alias's contents just because one owner is statistics.
    def references(value):
        if type(value) is not list: return 0
        if len(value) == 2 and value[0] == "ref" and value[1] == duration[1]: return 1
        return sum(references(v) for v in value)
    require(references(projected[0]) == 0, "timing queue alias escapes the statistics field")
    for value in duration[3]: finite_timer(value)
    before = {"episode_start_time": deepcopy(timer), "time_queue": deepcopy(duration)}
    if initialized: timer[:] = ["float", 0.0.hex()]
    for value in duration[3]: value[:] = ["float", 0.0.hex()]
    edits = [{"layer_index": index, "layer_type": STATISTICS_TYPE, "field": name,
              "raw_node": before[name], "comparison_node": deepcopy(stats[name])}
             for name in ("episode_start_time", "time_queue")]
    return projected, edits


def components(raw, projected, layer_types):
    left, llayers = inspect_shape(raw, layer_types);right, rlayers = inspect_shape(projected, layer_types)
    result = []
    def add(path, a, b):
        result.append({"path": path, "raw_sha256": graph_hash(a), "comparison_sha256": graph_hash(b)})
    for key in left:
        if key != "layers": add([key], left[key], right[key])
    for index, fields in enumerate(llayers):
        for key in fields: add(["layers", index, key], fields[key], rlayers[index][key])
    add(["array_alias_layout"], raw[1], projected[1]);add(["array_buffer_hashes"], raw[2], projected[2])
    return result


def verify_witness(value, *, full_sha256=None, native_sha256=None):
    """Reconstruct projection and component hashes from a private saved record."""
    normalize(value)
    keys = {"schema", "projection", "statistics_source_sha256", "layer_types", "native_sha256",
            "full_python_sha256", "comparison_python_sha256", "raw_graph", "projection_edits", "components"}
    require(type(value) is dict and set(value) == keys, "strict versioned witness record required")
    require(value["schema"] == SCHEMA and value["projection"] == PROJECTION
            and value["statistics_source_sha256"] == COMMON_SOURCE_SHA256, "unreviewed comparison contract")
    for key in ("native_sha256", "full_python_sha256", "comparison_python_sha256"):
        h = value[key];require(type(h) is str and len(h) == 64 and all(c in "0123456789abcdef" for c in h), "valid hash required")
    require(graph_hash(value["raw_graph"]) == value["full_python_sha256"], "raw semantic graph differs from full witness")
    projected, edits = project_graph(value["raw_graph"], value["layer_types"])
    require(graph_hash(projected) == value["comparison_python_sha256"], "comparison graph differs")
    require(graph_hash(value["projection_edits"]) == graph_hash(edits), "unregistered or incorrect projection edits")
    require(graph_hash(value["components"]) == graph_hash(components(value["raw_graph"], projected, value["layer_types"])), "component evidence differs")
    if full_sha256 is not None: require(value["full_python_sha256"] == full_sha256, "full source witness differs")
    if native_sha256 is not None: require(value["native_sha256"] == native_sha256, "native source witness differs")
    return projected


def capture_witness(env, policy, context):
    """Read-only host observation; callers must also enforce physical ledgers."""
    require(sha(Path(common.__file__).read_bytes()) == COMMON_SOURCE_SHA256, "statistics source has not been reviewed")
    require(all(getattr(common.RecordEpisodeStatistics, name) is method for name, method in STATISTICS_METHODS.items()), "statistics methods changed in memory")
    chain = layers(env);base = chain[-1]
    stats = [layer for layer in chain if isinstance(layer, common.RecordEpisodeStatistics)]
    require(len(stats) == 1 and type(stats[0]) is common.RecordEpisodeStatistics, "one exact statistics wrapper, no subclass")
    addresses = (base.model._address, base.data._address)
    native = native_hash(base.model, base.data);state = python_state(chain, policy, context)
    full = state_signature(state, base.model, base.data)
    raw = semantic_graph(state, base.model, base.data)
    require(graph_hash(raw) == full, "new graph encoder disagrees with frozen signature")
    types_ = [type(layer).__module__ + "." + type(layer).__qualname__ for layer in chain]
    projected, edits = project_graph(raw, types_)
    value = {"schema": SCHEMA, "projection": PROJECTION, "statistics_source_sha256": COMMON_SOURCE_SHA256,
        "layer_types": types_, "native_sha256": native, "full_python_sha256": full,
        "comparison_python_sha256": graph_hash(projected), "raw_graph": raw, "projection_edits": edits,
        "components": components(raw, projected, types_)}
    verify_witness(value)
    require(addresses == (base.model._address, base.data._address)
            and native_hash(base.model, base.data) == native
            and state_signature(python_state(layers(env), policy, context), base.model, base.data) == full,
            "witness construction changed live state")
    return value


def compare_witnesses(left, right):
    """Return all field diagnostics, preserving full and projected verdicts."""
    verify_witness(left);verify_witness(right)
    require(left["layer_types"] == right["layer_types"], "different wrapper stack cannot be matched")
    maps = [{json.dumps(v["path"]): v for v in x["components"]} for x in (left, right)]
    keys = sorted(set(maps[0]) | set(maps[1]))
    differences = [{"path": json.loads(key), "left": maps[0].get(key), "right": maps[1].get(key)} for key in keys if maps[0].get(key) != maps[1].get(key)]
    same_native = left["native_sha256"] == right["native_sha256"]
    return {"same_native": same_native, "same_full_python": left["full_python_sha256"] == right["full_python_sha256"],
        "same_comparison_python": left["comparison_python_sha256"] == right["comparison_python_sha256"],
        "comparison_equal": same_native and left["comparison_python_sha256"] == right["comparison_python_sha256"],
        "component_differences": differences,
        "only_registered_timing_components_differ": bool(differences) and all(
            d["path"][:1] == ["layers"] and d["path"][-1] in ("episode_start_time", "time_queue")
            and d["left"] is not None and d["right"] is not None
            and d["left"]["comparison_sha256"] == d["right"]["comparison_sha256"] for d in differences)}
