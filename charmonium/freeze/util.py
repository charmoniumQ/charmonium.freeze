import builtins
import dis
import inspect
import types
import inspect
from pathlib import Path
from typing import Any, Callable, Iterable, Mapping, NamedTuple, Optional, TypeVar, Generic, Union, Sequence, cast


class VarAttr(NamedTuple):
    name: str
    attr_path: tuple[str, ...]
    has_val: bool
    val: Any


class ClosureAttrs(NamedTuple):
    parameters: Iterable[VarAttr]
    nonlocals: Iterable[VarAttr]
    myglobals: Iterable[VarAttr]

def get_closure_attrs(func: types.FunctionType) -> ClosureAttrs:
    """Like ``getclosurevars``, but is more precise with attributes.

    For example, if your code depends on ``os.path.join``, this should return
    [("os", ("path", "join"), os.path.join)].

    """

    closurevars = getclosurevars(func)
    instructions = list(dis.get_instructions(func))
    param_names = set(inspect.signature(func).parameters.keys())
    parameters = []
    nonlocals = []
    myglobals = []
    for i, instruction in enumerate(instructions):
        var_name = instruction.argval
        is_global = var_name in closurevars.globals.keys()
        is_param = var_name in param_names
        is_nonlocal = var_name in closurevars.nonlocals.keys()
        if (is_param or is_global or is_nonlocal) and instruction.opname in {"LOAD_GLOBAL", "LOAD_FAST", "LOAD_DEREF"}:
            attr_path: tuple[str, ...] = ()
            var = None
            if is_global:
                val = closurevars.globals[var_name]
            if is_nonlocal:
                val = closurevars.nonlocals[var_name]
            j = i + 1
            while instructions[j].opname in {"LOAD_ATTR", "LOAD_METHOD"} and j < len(instructions):
                attr_path = (*attr_path, instructions[j].argval)
                if is_global or is_nonlocal:
                    val = getattr(val, instructions[j].argval)
                j += 1
            if is_param:
                parameters.append(VarAttr(var_name, attr_path, False, None))
            if is_global:
                myglobals.append(VarAttr(var_name, attr_path, True, val))
            if is_nonlocal:
                nonlocals.append(VarAttr(var_name, attr_path, True, val))

    def uniquify(var_attrs: Iterable[VarAttr]) -> Iterable[VarAttr]:
        ret_var_attrs = []
        chosen_attrs: set[tuple[str, ...]] = set()
        for var_attr in sorted(var_attrs, key=lambda x: (x.name, x.attr_path)):
            if not any(
                    (var_attr.name, *var_attr.attr_path[:i]) in chosen_attrs
                    for i in range(len(var_attr.attr_path) + 1)
            ):
                chosen_attrs.add((var_attr.name, *var_attr.attr_path))
                ret_var_attrs.append(var_attr)
        return ret_var_attrs
    return ClosureAttrs(uniquify(parameters), uniquify(nonlocals), uniquify(myglobals))

def has_callable(
    obj: object,
    attr: str,
    default: Optional[Callable[[], Any]] = None,
) -> Optional[Callable[[], Any]]:
    "Returns a callble if attr of obj is a function or bound method."
    func = cast(Optional[Callable[[], Any]], getattr(obj, attr, default))
    if all(
        [
            func,
            callable(func),
            (not isinstance(func, types.MethodType) or hasattr(func, "__self__")),
        ]
    ):
        return func
    else:
        return None


def getclosurevars(func: types.FunctionType) -> inspect.ClosureVars:
    """A clone of inspect.getclosurevars that is robust to [this bug][1]

    [1]: https://stackoverflow.com/a/61964607/1078199"""
    nonlocal_ns = {
        var: cell.cell_contents
        for var, cell in zip(func.__code__.co_freevars, func.__closure__ or [])
    }
    local_varnames = set(func.__code__.co_varnames)
    global_vars = {}
    builtin_vars = {}
    global_ns = func.__globals__
    builtin_ns = global_ns.get("__builtins__", builtins.__dict__)
    if inspect.ismodule(builtin_ns):
        builtin_ns = builtin_ns.__dict__
    unbound_names = set()
    forbidden_varnames = {"True", "False", "None"}
    for instruction in dis.get_instructions(func):
        if instruction.opname == "LOAD_GLOBAL":
            name = instruction.argval
            if name in forbidden_varnames:
                pass
            elif name in global_ns:
                global_vars[name] = global_ns[name]
            elif name in builtin_ns:
                builtin_vars[name] = builtin_ns[name]
            else:
                unbound_names.add(name)

    return inspect.ClosureVars(
        nonlocal_ns,
        global_vars,
        builtin_vars,
        unbound_names,
    )


class Sentinel:
    pass

sentinel = Sentinel()


T = TypeVar("T")
class Ref(Generic[T]):
    def __init__(self, default_val: T) -> None:
        self.val = default_val

    def get(self) -> T:
        return self.val

    def set(self, new_val: T) -> None:
        self.val = new_val

    def __call__(self, new_val: Union[T, Sentinel] = sentinel) -> T:
        if not isinstance(new_val, Sentinel):
            self.set(new_val)
        return self.get()


# Only Python 3.9 has Path.is_relative_to :'(
def is_relative_to(a: Path, b: Path) -> bool:
    try:
        a.relative_to(b)
    except ValueError:
        return False
    else:
        return True
