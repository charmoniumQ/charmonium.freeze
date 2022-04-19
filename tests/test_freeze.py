import base64
import contextlib
import copy
import datetime
import functools
import io
import itertools
import logging
import os
import pickle
import re
import subprocess
import sys
import tempfile
import threading
import zlib
from pathlib import Path
from typing import Any, Hashable, IO, Iterable, List, Mapping, Set, Optional, Tuple, Type, cast

import matplotlib.figure
import numpy
import pandas
import pytest
from charmonium.determ_hash import determ_hash
from tqdm import tqdm

from charmonium.freeze import FreezeRecursionError, UnfreezableTypeError, config, freeze


def print_inequality_in_hashables(
    x: Hashable, y: Hashable, stack: Tuple[str, ...] = (), file: Optional[IO[str]] = None,
) -> None:
    if isinstance(x, tuple) and isinstance(y, tuple):
        for i, (xi, yi) in enumerate(itertools.zip_longest(x, y)):
            print_inequality_in_hashables(xi, yi, stack + (f"[{i}]",))
    elif isinstance(x, frozenset) and isinstance(y, frozenset):
        if x ^ y:
            print("x ^ y == ", x ^ y, "at obj" + "".join(stack), file=file)
    else:
        if x != y:
            print(x, "!=", y, "at obj" + "".join(stack), file=file)


def insert_recurrence(lst: List[Any], idx: int) -> List[Any]:
    lst = lst.copy()
    lst.insert(idx, lst)
    return lst


class WithProperties:
    def __init__(self, value: int) -> None:
        self._attrib = value

    @property
    def attrib(self) -> int:
        raise RuntimeError("Shouldn't try to read attrib")

    def __eq__(self, other: object) -> bool:
        return isinstance(other, WithProperties) and self._attrib == other._attrib


class WithGetFrozenState:
    def __init__(self, value: int) -> None:
        self._value = value

    def __getfrozenstate__(self) -> int:  # pylint: disable=no-self-use
        return 0


@functools.singledispatch
def single_dispatch_test(_obj: Any) -> Any:
    return _obj

@single_dispatch_test.register
def _(_obj: int) -> int:
    return _obj


def function_test(obj: int) -> int:
    return obj

def get_class(i: int) -> Type[Type]:
    class A:
        i: int = 0
        def foo(self):
            return self.i
    A.i = i
    return A


class ClassWithStaticMethod:
    @staticmethod
    def foo() -> int:
        return 1234
    @classmethod
    def bar(Cls) -> int:
        return len(Cls.__name__)
    def baz(self) -> int:
        return 3142


global0 = 0
global1 = 1
readme_rpb = open("README.rst", "r+b")  # pylint: disable=consider-using-with
readme_rpb.seek(10)

def generator():
    yield from range(10)

generator0 = generator()
generator1 = generator()
next(generator1)
context_manager = contextlib.contextmanager(generator)

range10p1 = iter(range(10))
next(range10p1)

# pylint: disable=consider-using-with
non_equivalents: Mapping[str, Any] = {
    "ellipses": [...],
    "bytearray": [bytearray(b"hello"), bytearray(b"world")],
    "tuple": [(), (1, 2)],
    "recursive_list": [
        insert_recurrence([1, 2, 3, 4], 2),
        insert_recurrence([1, 2, 3, 5], 2),
    ],
    "set": [{1, 2, 3}, {1, 2, 4}],
    "dict of dicts": [dict(a=1, b=2, c=3), dict(a=1, b=2, c=4)],
    "dict with diff order": [{"a": 1, "b": 2}, {"b": 2, "a": 1}],
    "memoryview": [memoryview(b"abc"), memoryview(b"def")],
    "@functools.singledispatch": [single_dispatch_test, determ_hash, freeze],
    "function": [cast, tqdm, *dir(tempfile)],
    "unbound methods": [ClassWithStaticMethod.foo, ClassWithStaticMethod.baz],
    "bound methods": [ClassWithStaticMethod.bar, ClassWithStaticMethod().baz],
    "lambda": [lambda: 1, lambda: 2, lambda: global0, lambda: global1],
    "builtin_function": [open, input],
    "code": [freeze.__code__, determ_hash.__code__],
    "module": [zlib, pickle],
    "range": [range(10), range(20)],
    "iterator": [iter(range(10)), range10p1],
    # TODO: make freeze work on generators
    # "generator": [generator0, generator1],
    "context manager": [context_manager],
    "logger": [logging.getLogger("a.b"), logging.getLogger("a.c")],
    "type": [List[int], List[float], ClassWithStaticMethod],
    "class": [WithProperties, WithGetFrozenState],
    "diff classes with same name": [get_class(3), get_class(4)],
    "obj of diff classes with the same name": [get_class(3)(), get_class(4)()],
    "instance method of diff classes with same name": [get_class(3)().foo, get_class(4)().foo],
    "io.BytesIO": [io.BytesIO(b"abc"), io.BytesIO(b"def")],
    "io.StringIO": [io.StringIO("abc"), io.StringIO("def")],
    "io.TextIOWrapper": [open("/tmp/test1", "w"), open("/tmp/test2", "w"), sys.stdout],
    "io.BufferedWriter": [
        open("/tmp/test3", "wb"),
        open("/tmp/test4", "wb"),
        sys.stdout.buffer,
    ],
    # `readme_rpb` already read 10 bytes, so it should be different than `open(...)`
    "io.BufferedRandom": [
        open("README.rst", "r+b"),  # pylint: disable=consider-using-with
        readme_rpb,
    ],
    "re.Pattern": [
        re.compile("abc"),
        re.compile("def"),
        re.compile("def", flags=re.MULTILINE),
    ],
    "matplotlib.figure.Figure": [matplotlib.figure.Figure()],
    # should have two distinct matches
    "re.Match": list(re.finditer("a", "abca")),
    "numpy numbers": [
        # floats should be different from ints of the same value
        numpy.int64(123),
        numpy.float32(123),
        numpy.int64(456),
        numpy.float32(456),
    ],
    "Path": [Path(), Path("abc"), Path("def")],
    "numpy.ndarray": [numpy.zeros(4), numpy.zeros(4, dtype=int), numpy.ones(4)],
    "obj with properties": [WithProperties(3), WithProperties(4)],
    # "tqdm": [tqdm(range(10), disable=True)], # TODO: uncomment
    "pandas.DataFrame": [
        pandas.DataFrame(data={"col1": [1, 2], "col2": [3, 4]}),
        pandas.DataFrame(data={"col1": [1, 3], "col2": [5, 4]}),  # change data
        pandas.DataFrame(data={"abc1": [1, 2], "abc2": [3, 4]}),  # change column names
        pandas.DataFrame(
            data={"col1": [1, 2], "col2": [3, 4]}, index=[45, 65]
        ),  # change index
    ],
    "functools.partial": [
        functools.partial(function_test, 3),
        functools.partial(function_test, 4),
    ],
    "datetime": [datetime.timedelta(days=3), datetime.timedelta(days=4)],
    "locky objects": [threading.Lock(), threading.RLock()],
}


def mark_failing(params: Iterable[Any], failing: Set[Any]) -> Iterable[Any]:
    return [
        pytest.param(param, marks=[pytest.mark.xfail]) if param in failing else param
        for param in params
    ]


@pytest.mark.parametrize("input_kind", non_equivalents.keys())
def test_freeze_works(caplog: pytest.LogCaptureFixture, input_kind: str) -> None:
    caplog.set_level(logging.DEBUG, logger="charmonium.freeze")
    for value in non_equivalents[input_kind]:
        frozen = freeze(value)
        hash(frozen)
        determ_hash(frozen)


@pytest.mark.parametrize("input_kind", non_equivalents.keys())
def test_freeze_total_uniqueness(caplog: pytest.LogCaptureFixture, input_kind: str) -> None:
    caplog.set_level(logging.DEBUG, logger="charmonium.freeze")
    values = non_equivalents[input_kind]
    frozen_values = [(value, freeze(value)) for value in values]
    for i, (this_value, this_freeze) in enumerate(frozen_values):
        for j, (that_value, that_freeze) in enumerate(frozen_values):
            if i != j:
                assert (
                    this_freeze != that_freeze
                ), f"freeze({this_value}) should be different than freeze({that_value})"


non_copyable_types = {
    "module",
    "memoryview",
    "io.TextIOWrapper",
    "io.BufferedWriter",
    "io.BufferedRandom",
    "tqdm",
    "locky objects",
}


@pytest.mark.parametrize("input_kind", non_equivalents.keys() - non_copyable_types)
def test_determinism_over_copies(
    caplog: pytest.LogCaptureFixture, input_kind: str
) -> None:
    caplog.set_level(logging.DEBUG, logger="charmonium.freeze")
    for value in non_equivalents[input_kind]:
        freeze0 = freeze(copy.deepcopy(value))
        if input_kind == "@functools.singledispatch":
            # Call the singledispatch function to try and change its cache_token
            value(345)
            value((32, ((10), frozenset({"hello"}))))
        freeze1 = freeze(value)
        if freeze0 != freeze1:
            print_inequality_in_hashables(freeze0, freeze1)
        assert freeze0 == freeze1


# This is a fixture because it should only be evaluated once.
@pytest.fixture(name="past_freezes", scope="session")
def fixture_past_freezes() -> Mapping[str, List[List[Any]]]:
    path_to_package = Path(freeze.__code__.co_filename).resolve().parent.parent.parent
    proc = subprocess.run(
        [sys.executable, __file__],
        check=True,
        capture_output=True,
        env={
            **os.environ,
            "PYTHONPATH": str(path_to_package) + ":" + os.environ.get("PYTHONPATH", ""),
        },
    )
    return cast(
        Mapping[str, List[List[Any]]],
        pickle.loads(base64.b64decode(proc.stdout)),
    )


if __name__ == "__main__":
    sys.stdout.buffer.write(
        base64.b64encode(
            pickle.dumps(
                {
                    value_kind: [freeze(value) for value in values]
                    for value_kind, values in non_equivalents.items()
                }
            )
        )
    )


@pytest.mark.parametrize("input_kind", non_equivalents.keys())
def test_determinism_over_processes(
    caplog: pytest.LogCaptureFixture,
    input_kind: str,
    past_freezes: Mapping[str, List[int]],
) -> None:
    caplog.set_level(logging.DEBUG, logger="charmonium.freeze")
    for past_hash, value in zip(past_freezes[input_kind], non_equivalents[input_kind]):
        new_hash = freeze(value)
        if past_hash != new_hash:
            print_inequality_in_hashables(past_hash, new_hash)
        assert past_hash == new_hash, f"Determinism-over-processes failed for {value}"


p = Path()
hash(p)
readme_rpb2 = open("README.rst", "r+b")  # pylint: disable=consider-using-with
readme_rpb2.read(10)
# pylint: disable=consider-using-with
equivalents: Mapping[str, List[Any]] = {
    "list": [[1, 2, 3], [1, 2, 3]],
    "Ellipsis": [..., ...],
    "recursive_list": [
        insert_recurrence([1, 2, 3, 4], 2),
        insert_recurrence([1, 2, 3, 4], 2),
    ],
    "lambda": [lambda: 1, lambda: 1],
    "obj with properties": [WithProperties(3), WithProperties(3)],
    "numpy.ndarray": [numpy.zeros(4), numpy.zeros(4)],
    "Path": [
        Path(),
        p,
        # when p gets hashed, the hash gets cached in an extra field.
    ],
    "diff identical class": [get_class(3), get_class(3)],
    "instances of diff identical classes": [get_class(3)(), get_class(3)()],
    "dict with same order": [{"a": 1, "b": 2}, {"a": 1, "b": 2}],
    "object with getfrozenstate": [WithGetFrozenState(3), WithGetFrozenState(4)],
    "logging.Logger": [logging.getLogger("a.b"), logging.getLogger("a.b")],
    "io.BytesIO": [io.BytesIO(b"abc"), io.BytesIO(b"abc")],
    "io.StringIO": [io.StringIO("abc"), io.StringIO("abc")],
    "io.TextIOWrapper": [open("/tmp/test5", "w"), open("/tmp/test5", "w")],
    "io.BufferedWriter": [open("/tmp/test6", "wb"), open("/tmp/test6", "wb")],
    # readme_rpb and readme_rpb2 are seeked to the same point
    "io.BufferedRandom": [readme_rpb, readme_rpb2],
    "pandas.DataFrame": [
        pandas.DataFrame(data={"col1": [1, 2], "col2": [3, 4]}),
        pandas.DataFrame(data={"col1": [1, 2], "col2": [3, 4]}),
    ],
    "functools.partial": [
        functools.partial(function_test, 3),
        functools.partial(function_test, 3),
    ],
    "threading.Lock": [threading.Lock(), threading.Lock()],
    "threading.RLock": [threading.RLock(), threading.RLock()],
}


def test_consistency_over_identicals() -> None:
    for values in equivalents.values():
        expected = freeze(values[0])
        for value in values:
            assert freeze(value) == expected


# pylint: disable=consider-using-with
bad_types: Mapping[str, Any] = {
    "io.BufferedReader": open("README.rst", "rb"),
    "io.TextIOBase": open("README.rst", "r"),
}


@pytest.mark.parametrize("input_kind", bad_types.keys())
def test_reject_bad_types(input_kind: str) -> None:
    with pytest.raises(UnfreezableTypeError):
        freeze(bad_types[input_kind])


def test_logs(caplog: pytest.LogCaptureFixture) -> None:
    with caplog.at_level(logging.INFO, logger="charmonium.freeze"):
        freeze(frozenset({(1, "hello")}))
    assert not caplog.text
    with caplog.at_level(logging.DEBUG, logger="charmonium.freeze"):
        freeze(frozenset({(1, "hello")}))
    assert caplog.text


def test_recursion_limit() -> None:
    old_recursion_limit = config.recursion_limit
    config.recursion_limit = 2
    with pytest.raises(FreezeRecursionError):
        freeze([[[[[["hi"]]]]]])
    config.recursion_limit = old_recursion_limit
