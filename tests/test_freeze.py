import copy
import json
import logging
import pickle
import zlib
from pathlib import Path
from typing import Any, List, Mapping

import numpy
import pytest
from charmonium.determ_hash import determ_hash

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


def fn1() -> int:
    return 3


def fn2() -> int:
    return 4


non_equivalents: Mapping[str, Any] = {
    "recursive_list": [
        insert_recurrence([1, 2, 3, 4], 2),
        insert_recurrence([1, 2, 3, 5], 2),
    ],
    "module": [zlib, pickle],
    "dict of dicts": [dict(a=1, b=2, c=3), dict(a=1, b=2, c=4)],
    "set": [{1, 2, 3}, {1, 2, 4}],
    "bytearray": [bytearray(b"hello"), bytearray(b"world")],
    "function": [fn1, fn2],
    "obj with properties": [WithProperties(3), WithProperties(4)],
    "numpy array": [numpy.zeros(4), numpy.zeros(4, dtype=int), numpy.ones(4)],
    "lambdas": [lambda: 1, lambda: 2],
    "numpy numbers": [
        numpy.int64(123),
        numpy.int64(456),
        numpy.float32(3.2),
        numpy.float32(3.3),
    ],
    "Paths": [Path(), Path("abc"), Path("def")],
    "builtin_functions": [open, input],
    "ellipses": [...],
    "memoryview": [memoryview(b"abc")],
    "dict with diff order": [{"a": 1, "b": 2}, {"b": 2, "a": 1}],
}


@pytest.mark.parametrize("input_kind", non_equivalents.keys())
def test_freeze_works(caplog: pytest.LogCaptureFixture, input_kind: str) -> None:
    caplog.set_level(logging.DEBUG, logger="charmonium.freeze")
    for value in non_equivalents[input_kind]:
        freeze(value)


def test_freeze_total_uniqueness() -> None:
    values = [
        (value, freeze(value))
        for values in non_equivalents.values()
        for value in values
    ]
    for i, (this_value, this_freeze) in enumerate(values):
        for j, (that_value, that_freeze) in enumerate(values):
            if i != j:
                assert (
                    this_freeze != that_freeze
                ), f"freeze({this_value}) == freeze({that_value})"


@pytest.mark.parametrize("input_kind", non_equivalents.keys())
def test_persistence_over_copies(input_kind: str) -> None:
    if input_kind not in {"module", "memoryview"}:
        for value in non_equivalents[input_kind]:
            value_copy = copy.deepcopy(value)
            assert freeze(value) == freeze(value_copy)


def test_persistence_over_processes() -> None:
    datafile = Path() / "hashes.json"
    hashes = {
        f"{value_kind}-{i}": determ_hash(freeze(value))
        for value_kind, values in non_equivalents.items()
        for i, value in enumerate(values)
    }
    if datafile.exists():
        past_hashes = json.loads(datafile.read_text())
        for key, this_hash in hashes.items():
            assert past_hashes[key] == this_hash, key
    else:
        datafile.write_text(json.dumps(hashes))
        assert False, "Run the tests again."


p = Path()
hash(p)
equivalents: Mapping[str, List[Any]] = {
    "list": [[1, 2, 3], [1, 2, 3]],
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
