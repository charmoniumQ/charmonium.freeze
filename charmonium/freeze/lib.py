from __future__ import annotations

import builtins
import dis
import functools
import inspect
import logging
from pathlib import Path
import types
import textwrap

logger = logging.getLogger("charmonium.cache.freeze")

def freeze(obj: Any) -> Hashable:
    """Injectively, deterministically maps objects to hashable, immutable objects.

    ``frozenset`` is to ``set`` as ``freeze`` is to ``Any``.

    That is, ``type(a) is type(b) and a != b`` implies ``freeze(a) != freeze(b)``.

    And, ``a == b`` implies ``freeze(a) == freeze(b)``

    Moreover, this function is deterministic, so it can be used to compare
    states **across subsequent process invocations**.

    Special cases:

    - ``freeze`` on functions returns their bytecode, constants, and
      closure-vars. This means that ``freeze_state(f) == freeze_state(g)``
      implies ``f(x) == g(x)``. The remarkable thing is that this is true across
      subsequent invocations of the same process. If the user edits the script
      and changes the function, then it's ``freeze_state`` will change too.

    - ``freeze`` on objects with a ``__getstate__`` method defers to
      that. This intentionally reuses a method already used by
      `Pickle`_. Sometimes, process-dependent data may be stored in the
      attributes (imagine ``self.x = id(x)``), but this information would not be
      stored in pickle's ``__getstate__``.

    - In the cases where ``__getstate__`` is already defined, and this
      definition is not suitable for ``freeze_state``, one may override this
      with ``__getfrozenstate__`` which takes precedence.

    - Otherwise, objects are frozen by their class and their non-property
      owned-attributes. This excludes ``@property`` attributes, which are
      computed based on other attributes, and it excludes methods, which come
      from the class.

    - The frozen-state of objects with an atribute ``.data`` of type
      ``memoryview`` (e.g. Numpy arrays) are frozen by that state.

    Although, this function is not infallible for user-defined types; I will do
    my best, but sometimes these laws will be violated. These cases include:

    - Cases where ``__eq__`` makes objects equal despite differing attributes or
      inversely make objects inequal despite equal attributes.

       - This can be mitigated if ``__getstate__`` or ``__getfrozenstate__``

    """
    logging.debug(f"freeze begin")
    ret = freeze_helper(obj, set(), 0)
    logging.debug(f"freeze end")
    return ret


def freeze_helper(obj: Any, tabu: set[int], level: int) -> Hashable:
    # pylint: disable=too-many-branches,too-many-return-statements

    if level > 50:
        raise ValueError("Maximum recursion")

        logger.debug(
            " ".join(
                [
                    level * " ",
                    type(obj).__name__,
                    textwrap.shorten(repr(obj), width=100),
                ]
            )
        )
    if id(obj) in tabu:
        return b"cycle"
    else:
        return freeze_dispatch(obj, tabu, level)


def is_function_or_bound_method(func: Any) -> bool:
    return all([
        isinstance(func, types.FunctionType),
        any([
            not isinstance(func, types.MethodType),
            hasattr(func, "__self__"),
        ]),
    ])

@functools.singledispatch
def freeze_dispatch(obj: Any, tabu: set[int], level: int) -> Hashable:
    if hasattr(obj, "__getfrozenstate__") and is_function_or_bound_method(
        getattr(obj, "__getfrozenstate__")
    ):
        return freeze_helper(
            getattr(obj, "__getfrozenstate__")(),
            tabu | {id(obj)},
            level + 1,
        )
    if hasattr(obj, "__getstate__") and is_function_or_bound_method(
        getattr(obj, "__getstate__")
    ):
        return freeze_helper(
            getattr(obj, "__getstate__")(),
            tabu | {id(obj)},
            level + 1,
        )
    elif hasattr(obj, "data") and isinstance(getattr(obj, "data"), memoryview):
        # Fast path for numpy arrays
        return freeze_helper(
            getattr(obj, "data"),
            tabu | {id(obj), id(obj.data)},
            level + 1,
        )
    else:
        tabu = tabu | {id(obj)}
        all_slots = [
            slot
            # Have to travel up the classes MRO to get slots defined by parent class.
            for baseclass in obj.__class__.__mro__
            if baseclass != object
            for slot in getattr(baseclass, "__slots__", [])
        ]
        all_attributes = {
            # some slots will be empty, so `getattr(obj, attrib)` will fail.
            #
            #     >>> import pathlib
            #     >>> obj = pathlin.Path()
            #     >>> pathlib.PurePath in obj.__class__.__mro__
            #     >>> "_hash" in pathlib.PurePath.__slots__
            #     True
            #     >>> getattr(obj, "_hash")
            #     AttributeError: _hash
            #     >>> getattr(obj, "_hash", None)
            #     >>>
            #
            attrib: getattr(obj, attrib, None)
            for attrib in all_slots
        } + getattr(obj, "__dict__", {})
        return frozenset(
            (attr, freeze_helper(val, tabu, level + 1))
            for attr, val in all_attributes.items()
            if attr not in {"__module__", "__dict__", "__weakref__", "__doc__"}
        )


@freeze_dispatch.register(type(None))
@freeze_dispatch.register(bytes)
@freeze_dispatch.register(str)
@freeze_dispatch.register(int)
@freeze_dispatch.register(float)
def _(obj: Any, tabu: set[int], level: int) -> Hashable:
    return object


@freeze_dispatch.register(types.BuiltinFunctionType)
def _(obj: Any, tabu: set[int], level: int) -> Hashable:
    return obj.__name__


@freeze_dispatch.register(bytearray)
def _(obj: Any, tabu: set[int], level: int) -> Hashable:
    return bytes(obj)


@freeze_dispatch.register(tuple)
@freeze_dispatch.register(list)
def _(obj: list[Any], tabu: set[int], level: int) -> Hashable:
    tabu = tabu | {id(obj)}
    return tuple(freeze_helper(elem, tabu, level + 1) for elem in cast(List[Any], obj))


@freeze_dispatch.register(set)
@freeze_dispatch.register(frozenset)
def _(obj: set[Any], tabu: set[int], level: int) -> Hashable:
    tabu = tabu | {id(obj)}
    return frozenset(
        freeze_helper(elem, tabu, level + 1) for elem in cast(Set[Any], obj)
    )


@freeze_dispatch.register(dict)
@freeze_dispatch.register(types.MappingProxyType)
def _(obj: dict[Any, Any], tabu: set[int], level: int) -> Hashable:
    tabu = tabu | {id(obj)}
    # The elements of a dict remember their insertion order, as of Python 3.7.
    # So I will hash this as an ordered collection.
    return tuple(
        (key, freeze_helper(val, tabu, level + 1))
        for key, val in cast(Dict[Any, Any], obj).items()
    )


@freeze_dispatch.register(Path)
def _(obj: Path, tabu: set[int], level: int) -> Hashable:
    # Special case needed because Path objects have a `_hash` attribute, containing a process-specific hash.
    return obj.__fspath__()


@freeze_dispatch.register(memoryview)
def _(obj: memoryview, tabu: set[int], level: int) -> Hashable:
    return freeze_helper(
        obj.tobytes(),
        tabu | {id(obj), id(obj.data)},
        level + 1,
    )


# @freeze_dispatch.register(types.BuiltinMethodType)
# @freeze_dispatch.register(types.MethodWrapperType)
# @freeze_dispatch.register(types.WrapperDescriptorType)
# @freeze_dispatch.register(types.MethodDescriptorType)
# @freeze_dispatch.register(types.MemberDescriptorType)
# @freeze_dispatch.register(types.ClassMemberDescriptorType)
# @freeze_dispatch.register(types.GetSetDescriptorType)
# @freeze_dispatch.register(types.MethodType)
# def _(obj: Any, tabu: set[int], level: int) -> Hashable:
#     return (
#         obj.__qualname__,
#         freeze_helper(
#             getattr(obj, "__self__", None),
#             tabu | {id(obj)},
#             level + 1,
#         )
#     )


@freeze_dispatch.register(types.FunctionType)
def _(obj: Any, tabu: set[int], level: int) -> Hashable:
    tabu = tabu | {id(obj)}
    closure = getclosurevars(obj)
    return (
        freeze_helper(obj.__code__, tabu, level + 1),
        freeze_helper(closure.nonlocals, tabu, level + 1),
        freeze_helper(closure.globals, tabu, level + 1),
    )


@freeze_dispatch.register(types.CodeType)
def _(obj: Any, tabu: set[int], level: int) -> Hashable:
    tabu = tabu | {id(obj)}
    return (
        obj.co_name,  # name of function
        obj.co_varnames,  # argument names and local var names
        freeze_helper(obj.co_consts, tabu, level + 1),  # constants used by code
        freeze_helper(obj.co_code, tabu, level + 1),  # source code of function
    )


@freeze_dispatch.register(types.ModuleType)
def _(obj: Any, tabu: set[int], level: int) -> Hashable:
    return (obj.__name__, getattr(obj, "__version__", None))


@freeze_dispatch.register(Path)
def _(obj: Path, tabu: set[int], level: int) -> Hashable:
    return obj.__fspath__()


@freeze_dispatch.register(type)
def _(obj: Type[Any], tabu: set[int], level: int) -> Hashable:
    # return obj.__qualname__
    raise NotImplementedError("`freeze` is Not implemented for types")


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
