import copy
import io
import logging
import pickle
import platform
import re
import sys
import zlib
from pathlib import Path
from typing import Any, List, Mapping, cast

import numpy
import pytest
from charmonium.determ_hash import determ_hash
from tqdm import tqdm

from charmonium.freeze import freeze


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


global0 = 0
global1 = 1
readme_rpb = open("README.rst", "r+b")  # pylint: disable=consider-using-with
readme_rpb.seek(10)
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
    # "function": [cast, tqdm, freeze, determ_hash],
    "function": [cast, tqdm],
    "lambda": [lambda: 1, lambda: 2, lambda: global0, lambda: global1],
    "builtin_function": [open, input],
    "code": [freeze.__code__, determ_hash.__code__],
    "module": [zlib, pickle],
    "logger": [logging.getLogger("a.b"), logging.getLogger("a.c")],
    "type": [List[int], List[float]],
    "io.BytesIO": [io.BytesIO(b"abc"), io.BytesIO(b"def")],
    "io.StringIO": [io.StringIO("abc"), io.StringIO("def")],
    "io.TextIOWrapper": [sys.stderr, sys.stdout],
    "io.BufferedWriter": [sys.stderr.buffer, sys.stdout.buffer],
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
    # should have two distinct matches
    "re.Match": list(re.finditer("a", "abca")),
    "numpy numbers": [
        # floats should be different from ints of the same value
        numpy.int64(123),
        numpy.float32(123),
        numpy.int64(456),
        numpy.float32(456),
    ],
    "Paths": [Path(), Path("abc"), Path("def")],
    "numpy array": [numpy.zeros(4), numpy.zeros(4, dtype=int), numpy.ones(4)],
    "obj with properties": [WithProperties(3), WithProperties(4)],
    "tqdm": [tqdm(range(10), disable=True)],
}


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


@pytest.mark.parametrize("input_kind", non_equivalents.keys())
def test_determinism_over_copies(
    caplog: pytest.LogCaptureFixture, input_kind: str
) -> None:
    caplog.set_level(logging.DEBUG, logger="charmonium.freeze")
    if input_kind not in {
        "module",
        "memoryview",
        "io.TextIOWrapper",
        "io.BufferedWriter",
        "io.BufferedRandom",
        "tqdm",
    }:
        for value in non_equivalents[input_kind]:
            value_copy = copy.deepcopy(value)
            if getattr(value, "__name__", None) == "freeze":
                pass

                # TODO: fix this test case
                # This test case won't work for some reason.
                # Here is my debugging:
                # import inspect
                # x = inspect.getclosurevars(inspect.getclosurevars(value).globals["freeze_helper"]).globals["freeze_dispatch"].registry
                # y = inspect.getclosurevars(inspect.getclosurevars(value_copy).globals["freeze_helper"]).globals["freeze_dispatch"].registry

                # This one passes
                # assert x == y

                # This one fails
                # assert freeze(x) == freeze(y)
                # The top-level object is a `WeakKeyDiectionary`, mapping types to underscore-functions set by `@freeze_dispatch.register`.
                # Somehow it has different keys.

            else:
                assert freeze(value) == freeze(value_copy)


datafile = (
    Path()
    / "tests"
    / f"frozen-{platform.python_implementation()}-{sys.version_info.major}{sys.version_info.minor}.pkl"
)

# This is a fixture because it should only be evaluated once.
@pytest.fixture(name="past_freezes")
def fixture_past_freezes() -> Mapping[str, List[List[Any]]]:
    if datafile.exists():
        past_freezes = cast(
            Mapping[str, List[List[Any]]], pickle.loads(datafile.read_bytes())
        )
        if len(past_freezes) == len(non_equivalents) and all(
            len(past_values) == len(values)
            for past_values, values in zip(
                past_freezes.values(), non_equivalents.values()
            )
        ):
            return past_freezes
        else:
            raise RuntimeError(
                "freezes.pkl is out of date. Run this file without pytest first."
            )
    else:
        raise RuntimeError(
            "freezes.pkl doesn't exist. Run this file without pytest first."
        )


def write_freezes() -> None:
    datafile.write_bytes(
        pickle.dumps(
            {
                value_kind: [freeze(value) for value in values]
                for value_kind, values in non_equivalents.items()
            }
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
        assert past_hash == freeze(
            value
        ), f"Determinism-over-processes failed for {value}"


p = Path()
hash(p)
readme_rpb2 = open("README.rst", "r+b")  # pylint: disable=consider-using-with
readme_rpb2.read(10)
equivalents: Mapping[str, List[Any]] = {
    "list": [[1, 2, 3], [1, 2, 3]],
    "ellipsis": [..., ...],
    "recursive_list": [
        insert_recurrence([1, 2, 3, 4], 2),
        insert_recurrence([1, 2, 3, 4], 2),
    ],
    "lambda": [lambda: 1, lambda: 1],
    "obj with properties": [WithProperties(3), WithProperties(3)],
    "numpy array": [numpy.zeros(4), numpy.zeros(4)],
    "Paths": [
        Path(),
        p,
        # when p gets hashed, the hash gets cached in an extra field.
    ],
    "dict with same order": [{"a": 1, "b": 2}, {"a": 1, "b": 2}],
    "object with getfrozenstate": [WithGetFrozenState(3), WithGetFrozenState(4)],
    "loggers": [logging.getLogger("a.b"), logging.getLogger("a.b")],
    "BytesIO": [io.BytesIO(b"abc"), io.BytesIO(b"abc")],
    "StringIO": [io.StringIO("abc"), io.StringIO("abc")],
    # readme_rpb and readme_rpb2 are seeked to the same point
    "BufferedRandom": [readme_rpb, readme_rpb2],
}


def test_consistency_over_identicals() -> None:
    for values in equivalents.values():
        expected = freeze(values[0])
        for value in values:
            assert freeze(value) == expected


def test_logs(caplog: pytest.LogCaptureFixture) -> None:
    with caplog.at_level(logging.INFO, logger="charmonium.freeze"):
        freeze(frozenset({(1, "hello")}))
    assert not caplog.text
    with caplog.at_level(logging.DEBUG, logger="charmonium.freeze"):
        freeze(frozenset({(1, "hello")}))
    assert caplog.text


# TODO: Test for unique representation between types.
# TODO: Test functions with minor changes
# TODO: Test set/dict with diff hash
# TODO: Test obj with slots

if __name__ == "__main__":
    write_freezes()
