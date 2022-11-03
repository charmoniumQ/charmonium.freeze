import base64
import copy
import itertools
import logging
import os
import pickle
import pprint
import subprocess
import sys
import textwrap
from pathlib import Path
from typing import (
    IO,
    Any,
    Hashable,
    Iterable,
    List,
    Mapping,
    Optional,
    Set,
    Tuple,
    cast,
)

import pytest
from charmonium.determ_hash import determ_hash
from obj_test_cases import (
    equivalents,
    immutables,
    non_copyable_types,
    non_equivalents,
    non_freezable_types,
    non_immutables,
)

from charmonium.freeze import FreezeRecursionError, UnfreezableTypeError, config, freeze
from charmonium.freeze.lib import _freeze


def print_inequality_in_hashables(
    x: Hashable,
    y: Hashable,
    stack: Tuple[str, ...] = (),
    file: Optional[IO[str]] = None,
) -> None:
    if isinstance(x, tuple) and isinstance(y, tuple):
        for i, (xi, yi) in enumerate(itertools.zip_longest(x, y)):
            print_inequality_in_hashables(xi, yi, stack + (f"[{i}]",))
    elif isinstance(x, frozenset) and isinstance(y, frozenset):
        if x ^ y:
            print("x ^ y == ", x ^ y, "at obj" + "".join(stack), file=file)
    else:
        if x != y:
            print(
                textwrap.shorten(repr(x), 70),
                "!=",
                textwrap.shorten(repr(y), 70),
                "at obj" + "".join(stack),
                file=file,
            )


def test_immmutability(caplog: pytest.LogCaptureFixture) -> None:
    caplog.set_level(logging.DEBUG, logger="charmonium.freeze")
    for obj in immutables:
        frozen = _freeze(obj, {}, 0, 0)
        if not frozen[1]:
            pprint.pprint(obj, width=1000)
            pprint.pprint(frozen, width=1000)
        assert frozen[1]
    for obj in non_immutables:
        frozen = _freeze(obj, {}, 0, 0)
        if frozen[1]:
            pprint.pprint(obj, width=1000)
            pprint.pprint(frozen, width=1000)
        assert not frozen[1]


@pytest.mark.parametrize("input_kind", non_equivalents.keys())
def test_freeze_works(caplog: pytest.LogCaptureFixture, input_kind: str) -> None:
    caplog.set_level(logging.DEBUG, logger="charmonium.freeze")
    for value in non_equivalents[input_kind]:
        frozen = freeze(value)
        try:
            hash(frozen)
            determ_hash(frozen)
        except Exception as exc:
            pprint.pprint(value, width=1000)
            pprint.pprint(frozen, width=1000)
            raise exc


@pytest.mark.parametrize("input_kind", non_equivalents.keys())
def test_freeze_total_uniqueness(
    caplog: pytest.LogCaptureFixture, input_kind: str
) -> None:
    caplog.set_level(logging.DEBUG, logger="charmonium.freeze")
    values = non_equivalents[input_kind]
    frozen_values = [(value, freeze(value)) for value in values]
    for i, (this_value, this_freeze) in enumerate(frozen_values):
        for j, (that_value, that_freeze) in enumerate(frozen_values):
            if i != j:
                if this_freeze == that_freeze:
                    print(f"freeze({this_value!r}) = {pprint.pformat(this_freeze)}")
                    print(f"freeze({that_value!r}) = {pprint.pformat(that_freeze)}")
                assert this_freeze != that_freeze


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
            print(pprint.pformat(freeze0, width=1000))
            print(pprint.pformat(freeze1, width=1000))
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
    data = {
        value_kind: [freeze(value) for value in values]
        for value_kind, values in non_equivalents.items()
    }
    data_ser = "\n".join(textwrap.wrap(base64.b64encode(pickle.dumps(data)).decode()))
    data_deser = pickle.loads(base64.b64decode(data_ser))
    assert data_deser == data
    sys.stdout.write(data_ser)


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
            pprint.pprint(past_hash, width=1000)
            pprint.pprint(new_hash, width=1000)
        assert past_hash == new_hash, f"Determinism-over-processes failed for {value}"


def test_consistency_over_identicals() -> None:
    for values in equivalents.values():
        expected = freeze(values[0])
        for value in values:
            assert freeze(value) == expected


@pytest.mark.parametrize("input_kind", non_freezable_types.keys())
def test_reject_bad_types(input_kind: str) -> None:
    with pytest.raises(UnfreezableTypeError):
        freeze(non_freezable_types[input_kind])


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
