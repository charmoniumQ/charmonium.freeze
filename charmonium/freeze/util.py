from __future__ import annotations

import builtins
import dis
import inspect
import pathlib
import types
from typing import (
    Any,
    Callable,
    Iterable,
    NamedTuple,
    Optional,
    TypeVar,
    cast,
)


_T = TypeVar("_T")


class VarAttr(NamedTuple):
    name: str
    attr_path: tuple[str, ...]
    has_val: bool
    val: Any


class ClosureAttrs(NamedTuple):
    parameters: list[VarAttr]
    nonlocals: list[VarAttr]
    myglobals: list[VarAttr]


def get_closure_attrs(func: types.FunctionType) -> ClosureAttrs:
    """Like ``getclosurevars``, but is more precise with attributes.

    For example, if your code depends on ``os.path.join``, this should return
    [("os", ("path", "join"), os.path.join)].

    """

    closurevars = getclosurevars(func)
    instructions = list(dis.get_instructions(func))
    param_names = set(inspect.signature(func, follow_wrapped=False).parameters.keys())
    parameters = []
    nonlocals = []
    myglobals = []
    for i, instruction in enumerate(instructions):
        var_name = instruction.argval
        is_global = var_name in closurevars.globals.keys()
        is_param = var_name in param_names
        is_nonlocal = var_name in closurevars.nonlocals.keys()
        if (is_param or is_global or is_nonlocal) and instruction.opname in {
            "LOAD_GLOBAL",
            "LOAD_FAST",
            "LOAD_DEREF",
        }:
            attr_path: tuple[str, ...] = ()
            val = None
            if is_global:
                val = closurevars.globals[var_name]
            if is_nonlocal:
                val = closurevars.nonlocals[var_name]
            j = i + 1
            while instructions[j].opname in {"LOAD_ATTR", "LOAD_METHOD"} and j < len(
                instructions
            ):
                attr_segment = instructions[j].argval
                if is_global or is_nonlocal:
                    if hasattr(val, attr_segment):
                        val = getattr(val, attr_segment)
                    else:
                        break
                attr_path = (*attr_path, attr_segment)
                j += 1
            if is_param:
                parameters.append(VarAttr(var_name, attr_path, False, None))
            if is_global:
                myglobals.append(VarAttr(var_name, attr_path, True, val))
            if is_nonlocal:
                nonlocals.append(VarAttr(var_name, attr_path, True, val))

    def uniquify(var_attrs: list[VarAttr]) -> list[VarAttr]:
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


# Only Python 3.9 has Path.is_relative_to :'(
def is_relative_to(a: pathlib.Path, b: pathlib.Path) -> bool:
    try:
        a.relative_to(b)
    except ValueError:
        return False
    else:
        return True


def common_prefix(it0: Iterable[_T], it1: Iterable[_T]) -> tuple[_T, ...]:
    ret: tuple[_T, ...] = ()
    for elem0, elem1 in zip(it0, it1):
        if elem0 == elem1:
            ret = (*ret, elem0)
        else:
            break
    return ret
