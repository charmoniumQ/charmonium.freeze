import os
import pprint
import re
import types
from typing import Any, Callable, TypeVar, cast

from charmonium.freeze import util


def get_function() -> types.FunctionType:
    nonlocalvar = 5

    def function(
        x: Any,
        y: Any,
        *args: Any,
        default_arg: Any = 3,
        **kwargs: Any,
    ) -> None:
        # handle naked arg
        y

        # handle arg attr
        x.foo
        x.bar.foo
        # x.foo.bar is subsumed by x.foo
        x.foo.bar

        # handle default_arg
        default_arg.to_bytes

        # handle args
        args.__len__()

        # Handle kwargs
        kwargs.items()

        # handle nonlocalvar
        nonlocal nonlocalvar
        nonlocalvar.real

        # handle naked module
        re

        # handle module.func
        os.getcwd()

        # handle repeats
        os.getcwd()
        os.getcwd

        # handle local variables
        s = os.getcwd()
        i = s.index("h")

        # handle builtins
        print()

        # handle unbound
        print(k)  # type: ignore

    return cast(types.FunctionType, function)


def test_getclosurevars() -> None:
    result = util.getclosurevars(get_function())
    assert result.nonlocals == {"nonlocalvar": 5}
    assert result.globals == {"re": re, "os": os}
    assert result.builtins == {"print": print}
    assert result.unbound == {"k"}


_T = TypeVar("_T")


def unsized_tuple(*args: _T) -> tuple[_T, ...]:
    return tuple(args)


def test_get_closure_attrs() -> None:
    result = util.get_closure_attrs(get_function())
    pprint.pprint(result)
    assert len(result.parameters) == 6
    assert ("y", unsized_tuple(), False, None) in result.parameters
    assert (
        "x",
        unsized_tuple(
            "foo",
        ),
        False,
        None,
    ) in result.parameters
    assert ("x", unsized_tuple("bar", "foo"), False, None) in result.parameters
    assert ("default_arg", unsized_tuple("to_bytes"), False, None) in result.parameters
    assert ("args", unsized_tuple("__len__"), False, None) in result.parameters
    assert ("kwargs", unsized_tuple("items"), False, None) in result.parameters

    assert len(result.nonlocals) == 1
    assert ("nonlocalvar", unsized_tuple("real"), True, 5) in result.nonlocals

    print(result.myglobals)
    assert len(result.myglobals) == 2
    assert ("re", (), True, re) in result.myglobals
    assert ("os", ("getcwd",), True, os.getcwd) in result.myglobals
