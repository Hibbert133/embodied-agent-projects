"""Evaluator-only in-process restore. Never pickle an Env or invoke its constructor.

Scope: MuJoCo 3.3.0, one synchronous owner, no callbacks/plugins/active renderer.
Native objects keep their addresses. Python arrays retain native/shared-buffer
aliases. A capsule is private, process-local, and cannot be loaded from a file.
Finite continuation tests do not prove universal hidden-state completeness.
"""
from __future__ import annotations

import copy
from collections import deque
import ctypes
from dataclasses import dataclass
import hashlib
import io
import json
import marshal
import pickle
from pathlib import Path
import random
import threading
import types

import gymnasium as gym
from gymnasium.envs.registration import EnvSpec, WrapperSpec
import mujoco
import numpy as np


def sha(data):
    return hashlib.sha256(data).hexdigest()


def native_hash(model, data):
    return sha(pickle.dumps((model, data), protocol=5))


def dimensions(model):
    return tuple((name, int(getattr(model, name))) for name in sorted(dir(model))
                 if name.startswith("n") and isinstance(getattr(model, name), (int, np.integer)))


class NativeCopies:
    """Use the installed library's documented C API, with exact version/ABI guard."""
    def __init__(self):
        if mujoco.__version__ != "3.3.0":
            raise ValueError("capsule v1 requires the qualified MuJoCo 3.3.0 ABI")
        folder = Path(mujoco.__file__).parent
        libraries = list(folder.glob("mujoco.dll")) + list(folder.glob("libmujoco.so*")) + list(folder.glob("libmujoco*.dylib"))
        if len(libraries) != 1:
            raise ValueError("one installed native library required")
        self.library_path = libraries[0]
        self.library_sha256 = sha(self.library_path.read_bytes())
        self.dll = ctypes.CDLL(str(self.library_path))
        self.dll.mj_version.argtypes = []
        self.dll.mj_version.restype = ctypes.c_int
        if self.dll.mj_version() != 330:
            raise ValueError("Python/native ABI disagreement")
        self.model = self.dll.mj_copyModel
        self.model.argtypes = [ctypes.c_void_p, ctypes.c_void_p]
        self.model.restype = ctypes.c_void_p
        self.data = self.dll.mj_copyData
        self.data.argtypes = [ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p]
        self.data.restype = ctypes.c_void_p

    def copy_data(self, dst, model, src):
        if self.data(dst._address, model._address, src._address) != dst._address:
            raise RuntimeError("native data copy failed")

    def restore(self, model, data, saved_model, saved_data):
        if dimensions(model) != dimensions(saved_model) or data.narena != saved_data.narena:
            raise ValueError("native allocation/layout changed")
        if self.model(model._address, saved_model._address) != model._address:
            raise RuntimeError("native model copy failed")
        self.copy_data(data, model, saved_data)


def guards(base):
    if threading.active_count() != 1:
        raise ValueError("single synchronous Python owner required")
    for name in dir(mujoco):
        if name.startswith("get_mjcb_") and getattr(mujoco, name)() is not None:
            raise ValueError("untracked MuJoCo callback: " + name)
    if base.model.nplugin or getattr(base.data, "threadpool", 0):
        raise ValueError("plugins/threadpools outside capsule contract")
    if hasattr(base.model, "sensor_noise") and np.any(base.model.sensor_noise != 0):
        raise ValueError("untracked native sensor noise")
    if getattr(base, "render_mode", None) is not None:
        raise ValueError("headless restore contract only")
    renderer = getattr(base, "mujoco_renderer", None)
    if renderer is not None and (renderer._viewers or renderer.viewer is not None):
        raise ValueError("active renderer outside capsule contract")


def layers(env):
    result = []; seen = set()
    while True:
        if id(env) in seen or not hasattr(env, "__dict__"):
            raise ValueError("cyclic or opaque environment chain")
        seen.add(id(env)); result.append(env)
        if not isinstance(env, gym.Wrapper):
            break
        env = env.env
    return result


def validate_graph(value, seen=None):
    """Whitelist before pickle: no Env reducers, arbitrary objects or callables."""
    seen = set() if seen is None else seen
    if id(value) in seen:
        return
    seen.add(id(value))
    if value is None or type(value) in (str, bytes, bool, int, float, complex):
        return
    if isinstance(value, (np.generic, np.dtype)):
        if np.dtype(value.dtype if isinstance(value, np.generic) else value).hasobject:
            raise ValueError("object dtype outside restore contract")
        return
    if type(value) is np.ndarray:
        if value.dtype.hasobject or value.dtype.fields or value.dtype.subdtype:
            raise ValueError("object/structured arrays outside restore contract")
        return
    if type(value) is dict:
        for key, child in value.items():
            validate_graph(key, seen)
            validate_graph(child, seen)
        return
    if type(value) in (list, tuple, set, frozenset, deque) or (isinstance(value, tuple) and type(value).__module__ == "metaworld.types"):
        for child in value:
            validate_graph(child, seen)
        return
    if type(value) is EnvSpec:
        for key, child in vars(value).items():
            if key in ("entry_point", "vector_entry_point") and type(child) is types.FunctionType:
                spec_callable_fingerprint(child)
            else:
                validate_graph(child, seen)
        return
    if type(value) in (gym.spaces.Box, WrapperSpec):
        validate_graph(vars(value), seen)
        return
    if type(value) is np.random.Generator:
        if type(value.bit_generator).__name__ not in ("PCG64", "PCG64DXSM", "MT19937", "Philox", "SFC64"):
            raise ValueError("unknown NumPy generator")
        return
    if type(value) is random.Random:
        return
    raise ValueError("opaque Python state: " + type(value).__module__ + "." + type(value).__qualname__)


def spec_callable_fingerprint(value, seen=None):
    # MT1's registered lambda is metadata, not a constructor we execute/pickle.
    if value.__module__ != "metaworld":
        raise ValueError("untracked callable in EnvSpec metadata")
    seen = set() if seen is None else seen
    signature = (value.__module__, value.__qualname__, sha(marshal.dumps(value.__code__)),
                 repr(value.__defaults__), repr(value.__kwdefaults__))
    if id(value) in seen: return signature
    seen.add(id(value)); closure = []
    for name, cell in zip(value.__code__.co_freevars, value.__closure__ or ()):
        child = cell.cell_contents
        if type(child) is types.FunctionType:
            item = spec_callable_fingerprint(child, seen)
        elif child is None or type(child) in (str, bytes, bool, int, float):
            item = (type(child).__name__, repr(child))
        else:
            raise ValueError("opaque closure in EnvSpec metadata")
        closure.append((name, item))
    return (*signature, tuple(closure))


def bounds(array):
    return np.lib.array_utils.byte_bounds(array)


class ArrayPickler(pickle.Pickler):
    def __init__(self, file, model, data):
        super().__init__(file, protocol=5)
        self.native = []
        for owner, obj in (("model", model), ("data", data)):
            for name in sorted(dir(obj)):
                value = getattr(obj, name)
                if type(value) is np.ndarray and value.nbytes and value.flags.c_contiguous:
                    self.native.append((owner, name, value, bounds(value)))
        self.array_ids, self.arrays, self.buffer_ids, self.buffers = {}, [], {}, []
        self.statics = []

    def persistent_id(self, value):
        if type(value) is types.FunctionType and value.__module__ == "metaworld":
            signature = spec_callable_fingerprint(value)
            for index, (obj, _) in enumerate(self.statics):
                if obj is value: return ("spec_callable", index)
            self.statics.append((value, signature))
            return ("spec_callable", len(self.statics)-1)
        if type(value) is not np.ndarray:
            return None
        if id(value) in self.array_ids:
            return ("array", self.array_ids[id(value)])
        index = len(self.arrays); self.array_ids[id(value)] = index
        low, high = bounds(value); pointer = value.__array_interface__["data"][0]
        common = (value.shape, value.dtype.str, value.strides, bool(value.flags.writeable))
        for owner, name, native, (start, end) in self.native:
            if value.nbytes and low >= start and high <= end and np.shares_memory(value, native):
                descriptor = ("native", owner, name, pointer-start, *common)
                break
        else:
            root = value
            while type(root.base) is np.ndarray:
                root = root.base
            storage = root if root.base is None else root.base
            while isinstance(storage, memoryview):
                storage = storage.obj
            if not isinstance(storage, (np.ndarray, bytes, bytearray)):
                raise ValueError("unresolved external array alias")
            if type(storage) is np.ndarray and not (storage.flags.c_contiguous or storage.flags.f_contiguous):
                raise ValueError("noncontiguous owning array outside contract")
            content = storage.tobytes(order="A") if type(storage) is np.ndarray else bytes(storage)
            if len(content) > 64*1024*1024:
                raise ValueError("oversize Python array buffer")
            if id(storage) not in self.buffer_ids:
                self.buffer_ids[id(storage)] = len(self.buffers)
                self.buffers.append(content)
            start = (storage if type(storage) is np.ndarray else np.frombuffer(storage, dtype=np.uint8)).__array_interface__["data"][0]
            descriptor = ("python", self.buffer_ids[id(storage)], pointer-start, *common)
        self.arrays.append(descriptor)
        return ("array", index)


class ArrayUnpickler(pickle.Unpickler):
    """Loads only an internally created private payload, never an external file."""
    def __init__(self, file, graph, model, data):
        super().__init__(file)
        self.graph, self.model, self.data = graph, model, data
        self.buffers = [bytearray(value) for value in graph.buffers]
        self.cache = {}

    def persistent_load(self, pid):
        if type(pid) is not tuple or len(pid) != 2:
            raise ValueError("unrecognized private array reference")
        if pid[0] == "spec_callable":
            value, signature = self.graph.statics[pid[1]]
            if spec_callable_fingerprint(value) != signature:
                raise ValueError("frozen EnvSpec callable changed")
            return value
        if pid[0] != "array": raise ValueError("unknown private persistent reference")
        index = pid[1]
        if index not in self.cache:
            descriptor = self.graph.arrays[index]
            if descriptor[0] == "native":
                _, owner, name, offset, shape, dtype, strides, writeable = descriptor
                buffer = getattr(self.model if owner == "model" else self.data, name)
            else:
                _, number, offset, shape, dtype, strides, writeable = descriptor
                buffer = self.buffers[number]
            array = np.ndarray(shape, dtype=np.dtype(dtype), buffer=buffer, offset=offset, strides=strides)
            array.flags.writeable = writeable
            self.cache[index] = array
        return self.cache[index]


@dataclass(frozen=True)
class PythonGraph:
    payload: bytes
    arrays: tuple
    buffers: tuple
    statics: tuple

    @classmethod
    def capture(cls, value, model, data):
        validate_graph(value)
        file = io.BytesIO(); writer = ArrayPickler(file, model, data); writer.dump(value)
        return cls(file.getvalue(), tuple(writer.arrays), tuple(writer.buffers), tuple(writer.statics))

    def restore(self, model, data):
        return ArrayUnpickler(io.BytesIO(self.payload), self, model, data).load()

    @property
    def digest(self):
        return sha(pickle.dumps((self.payload, self.arrays, self.buffers, tuple(signature for _, signature in self.statics)), protocol=5))


def python_state(chain, policy, context):
    states = [{k: v for k, v in vars(layer).items() if k not in ("env", "model", "data", "mujoco_renderer")} for layer in chain]
    renderer = getattr(chain[-1], "mujoco_renderer", None)
    renderer_state = None if renderer is None else {k: v for k, v in vars(renderer).items() if k not in ("model", "data")}
    return {"layers": states, "renderer": renderer_state, "policy": dict(vars(policy)), "context": context,
            "numpy_global": np.random.get_state(), "python_global": random.getstate()}


def state_signature(value, model, data):
    """Semantic graph/alias signature; pickle byte layouts are not canonical."""
    validate_graph(value)
    arrays = ArrayPickler(io.BytesIO(), model, data); memo = {}
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
        number = len(memo); memo[id(obj)] = (number, obj)
        if type(obj) is np.ndarray:
            _, index = arrays.persistent_id(obj)
            return ["array", number, index, sha(obj.tobytes(order="C"))]
        if type(obj) is dict: return ["dict", number, [[visit(k), visit(v)] for k, v in obj.items()]]
        if isinstance(obj, (list, tuple, set, frozenset, deque)):
            children = list(obj)
            if isinstance(obj, (set, frozenset)): children.sort(key=repr)
            return [type(obj).__module__+"."+type(obj).__qualname__, number,
                    obj.maxlen if isinstance(obj, deque) else None, [visit(v) for v in children]]
        if type(obj) is np.random.Generator: return ["generator", number, type(obj.bit_generator).__name__, visit(obj.bit_generator.state)]
        if type(obj) is random.Random: return ["random", number, visit(obj.getstate())]
        return [type(obj).__module__+"."+type(obj).__qualname__, number, visit(vars(obj))]
    nodes = visit(value)
    body = [nodes, arrays.arrays, [sha(v) for v in arrays.buffers]]
    return sha(json.dumps(body, ensure_ascii=True, separators=(",", ":"), allow_nan=False).encode())


def static_state(chain):
    result = {}
    for layer in chain:
        for cls in type(layer).__mro__:
            for name, value in vars(cls).items():
                if not name.startswith("__") and (type(value) in (str, bytes, bool, int, float, dict, list, tuple, set, np.ndarray, gym.spaces.Box) or value is None):
                    result[(cls.__module__, cls.__qualname__, name)] = value
    return result


@dataclass(frozen=True)
class Capsule:
    _chain: tuple
    _model: object
    _data: object
    _model_address: int
    _data_address: int
    _policy: object
    _graph: PythonGraph
    native_sha256: str
    python_sha256: str
    library_sha256: str
    dimensions: tuple
    static_sha256: str


def capture(env, policy, context):
    chain = layers(env); base = chain[-1]; guards(base); api = NativeCopies()
    graph = PythonGraph.capture(python_state(chain, policy, context), base.model, base.data)
    model = copy.copy(base.model)
    data = mujoco.MjData(model)
    api.copy_data(data, model, base.data)
    return Capsule(tuple(chain), model, data, base.model._address, base.data._address, policy, graph,
                   native_hash(model, data), graph.digest, api.library_sha256, dimensions(model),
                   PythonGraph.capture(static_state(chain), base.model, base.data).digest)


def restore(capsule, env, policy):
    if not isinstance(capsule, Capsule) or tuple(layers(env)) != capsule._chain or policy is not capsule._policy:
        raise ValueError("capsule belongs to a different environment/policy owner")
    base = capsule._chain[-1]; guards(base); api = NativeCopies()
    if (base.model._address, base.data._address) != (capsule._model_address, capsule._data_address):
        raise ValueError("native owner objects changed")
    if dimensions(base.model) != capsule.dimensions or api.library_sha256 != capsule.library_sha256:
        raise ValueError("runtime/model layout changed")
    if PythonGraph.capture(static_state(capsule._chain), base.model, base.data).digest != capsule.static_sha256:
        raise ValueError("shared class state changed outside restore contract")
    if native_hash(capsule._model, capsule._data) != capsule.native_sha256 or capsule._graph.digest != capsule.python_sha256:
        raise ValueError("saved capsule was mutated")
    # Decode before native mutation, then retain the original native/view owners.
    saved = capsule._graph.restore(base.model, base.data)
    api.restore(base.model, base.data, capsule._model, capsule._data)
    for layer, state in zip(capsule._chain, saved["layers"]):
        protected = {k: v for k, v in vars(layer).items() if k in ("env", "model", "data", "mujoco_renderer")}
        vars(layer).clear(); vars(layer).update(state); vars(layer).update(protected)
    renderer = getattr(base, "mujoco_renderer", None)
    if renderer is not None:
        vars(renderer).clear(); vars(renderer).update(saved["renderer"]); renderer.model, renderer.data = base.model, base.data
    vars(policy).clear(); vars(policy).update(saved["policy"])
    np.random.set_state(saved["numpy_global"]); random.setstate(saved["python_global"])
    if native_hash(base.model, base.data) != capsule.native_sha256:
        raise RuntimeError("native restore digest differs")
    return saved["context"]
