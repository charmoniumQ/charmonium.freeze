from charmonium.freeze import util

import re
import os

def get_function():
    nonlocalvar = 5
    def function(x, y, *args, default_arg=3, **kwargs) -> None:
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
        print(k)

    return function

def test_getclosurevars() -> None:
    result = util.getclosurevars(get_function())
    assert result.nonlocals == {"nonlocalvar": 5}
    assert result.globals == {"re": re, "os": os}
    assert result.builtins == {"print": print}
    assert result.unbound == {"k"}


def test_get_closure_attrs() -> None:
    result = util.get_closure_attrs(get_function())
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
