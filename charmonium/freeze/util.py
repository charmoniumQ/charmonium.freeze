import builtins
import dis
import inspect
import types
from typing import Any, Callable, Mapping, Optional, TypeVar, cast


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
    nonlocal_vars = {
        var: cell.cell_contents
        for var, cell in zip(func.__code__.co_freevars, func.__closure__ or [])
    }

    global_names = set()
    local_varnames = set(func.__code__.co_varnames)
    for instruction in dis.get_instructions(func):
        if instruction.opname in {
            "LOAD_GLOBAL",
            "STORE_GLOBAL",
            "LOAD_DEREF",
            "STORE_DEREF",
        }:
            name = instruction.argval
            if name not in local_varnames:
                global_names.add(name)

    # Global and builtin references are named in co_names and resolved
    # by looking them up in __globals__ or __builtins__
    global_ns = func.__globals__
    builtin_ns = global_ns.get("__builtins__", builtins.__dict__)
    if inspect.ismodule(builtin_ns):
        builtin_ns = builtin_ns.__dict__
    global_vars = {}
    builtin_vars = {}
    unbound_names = set()
    for name in global_names:
        if name in ("None", "True", "False"):
            # Because these used to be builtins instead of keywords, they
            # may still show up as name references. We ignore them.
            continue
        try:
            global_vars[name] = global_ns[name]
        except KeyError:
            try:
                builtin_vars[name] = builtin_ns[name]
            except KeyError:
                unbound_names.add(name)

    return inspect.ClosureVars(
        nonlocal_vars,
        global_vars,
        builtin_vars,
        unbound_names,
    )


def specializes_pickle(obj: Any) -> bool:
    return any(
        [
            has_callable(obj, "__reduce_ex__"),
            has_callable(obj, "__reduce__"),
        ]
    )


T = TypeVar("T")
V = TypeVar("V")


def sort_dict(obj: Mapping[T, V]) -> Mapping[T, V]:
    return dict(sorted(obj.items()))
