import base64
import copy
import itertools
import logging
import os
import pickle
from pathlib import Path
import subprocess
import sys
from typing import Any, Hashable, IO, Iterable, List, Mapping, Set, Optional, Tuple, cast

import pytest
from charmonium.freeze import FreezeRecursionError, UnfreezableTypeError, config, freeze
from charmonium.determ_hash import determ_hash

from obj_test_cases import equivalents, non_equivalents, non_copyable_types, non_freezable_types

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
