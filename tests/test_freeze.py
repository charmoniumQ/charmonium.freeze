import base64
import copy
import functools
import io
import itertools
import logging
import os
import pickle
import re
import subprocess
import sys
import zlib
from pathlib import Path
from typing import Any, Hashable, Iterable, List, Mapping, Set, cast

import matplotlib.figure
import numpy
import pandas  # type: ignore
import pytest
from charmonium.determ_hash import determ_hash
from charmonium.freeze import FreezeRecursionError, UnfreezableTypeError, config, freeze
from tqdm import tqdm

def print_inequality_in_hashables(x: Hashable, y: Hashable) -> None:
    if isinstance(x, tuple) and isinstance(y, tuple):
        for xi, yi in itertools.zip_longest(x, y):
            print_inequality_in_hashables(xi, yi)
    elif isinstance(x, frozenset) and isinstance(y, frozenset):
        if x ^ y:
            print("x ^ y == ", x ^ y)
    else:
        if x != y:
            print(x, "!=", y)


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
    return "Any"


def function_test(obj: int) -> int:
    return obj


global0 = 0
global1 = 1
readme_rpb = open("README.rst", "r+b")  # pylint: disable=consider-using-with
readme_rpb.seek(10)

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
    "singledispatch function": [single_dispatch_test],
    # freeze, determ_hash],
    "function": [cast, tqdm],
    "lambda": [lambda: 1, lambda: 2, lambda: global0, lambda: global1],
    "builtin_function": [open, input],
    "code": [freeze.__code__, determ_hash.__code__],
    "module": [zlib, pickle],
    "logger": [logging.getLogger("a.b"), logging.getLogger("a.c")],
    "type": [List[int], List[float]],
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
    "tqdm": [tqdm(range(10), disable=True)],
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
def test_freeze_total_uniqueness(input_kind: str) -> None:
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
}


@pytest.mark.parametrize("input_kind", non_equivalents.keys())
def test_determinism_over_copies(
    caplog: pytest.LogCaptureFixture, input_kind: str
) -> None:
    caplog.set_level(logging.DEBUG, logger="charmonium.freeze")
    if input_kind not in non_copyable_types:
        for value in non_equivalents[input_kind]:
            value_copy = copy.deepcopy(value)
            assert freeze(value) == freeze(value_copy)


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
        print_inequality_in_hashables(past_hash, freeze(value))
        assert past_hash == freeze(
            value
        ), f"Determinism-over-processes failed for {value}"


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
