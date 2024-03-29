from __future__ import annotations

import os
import pprint
import re
import types
from typing import Any, cast

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
        # pylint: disable=pointless-statement,unused-variable

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


def test_get_closure_attrs() -> None:
    result = util.get_closure_attrs(get_function())
    pprint.pprint(result)
    assert len(result.parameters) == 6
    assert ("y", (), False, None) in result.parameters
    assert ("x", ("foo",), False, None) in result.parameters
    assert ("x", ("bar", "foo"), False, None) in result.parameters
    assert ("default_arg", ("to_bytes",), False, None) in result.parameters
    assert ("args", ("__len__",), False, None) in result.parameters
    assert ("kwargs", ("items",), False, None) in result.parameters

    assert len(result.nonlocals) == 1
    assert ("nonlocalvar", ("real",), True, 5) in result.nonlocals

    print(result.myglobals)
    assert len(result.myglobals) == 2
    assert ("re", (), True, re) in result.myglobals
    assert ("os", ("getcwd",), True, os.getcwd) in result.myglobals
