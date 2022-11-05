import copy
import logging
import os
import pickle
import pprint
import subprocess
import sys
from pathlib import Path
from typing import Any, List, Mapping, cast

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

from charmonium.freeze import (
    FreezeRecursionError,
    UnfreezableTypeError,
    config,
    freeze,
    summarize_diff_of_frozen,
)
from charmonium.freeze.lib import _freeze


def test_immmutability() -> None:
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
def test_freeze_works(input_kind: str) -> None:
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
def test_freeze_total_uniqueness(input_kind: str) -> None:
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
def test_determinism_over_copies(input_kind: str) -> None:
    for value in non_equivalents[input_kind]:
        freeze0 = freeze(copy.deepcopy(value))
        if input_kind == "@functools.singledispatch":
            # Call the singledispatch function to try and change its cache_token
            value(345)
            value((32, ((10), frozenset({"hello"}))))
        freeze1 = freeze(value)
        if freeze0 != freeze1:
            summarize_diff_of_frozen(freeze0, freeze1)
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
        pickle.loads(proc.stdout),
    )


if __name__ == "__main__":
    data = {
        value_kind: [freeze(value) for value in values]
        for value_kind, values in non_equivalents.items()
    }
    sys.stdout.buffer.write(pickle.dumps(data))


@pytest.mark.parametrize("input_kind", non_equivalents.keys())
def test_determinism_over_processes(
    input_kind: str,
    past_freezes: Mapping[str, List[int]],
) -> None:
    for past_hash, value in zip(past_freezes[input_kind], non_equivalents[input_kind]):
        new_hash = freeze(value)
        if past_hash != new_hash:
            summarize_diff_of_frozen(past_hash, new_hash)
            pprint.pprint(past_hash, width=1000)
            pprint.pprint(new_hash, width=1000)
        assert past_hash == new_hash, f"Determinism-over-processes failed for {value}"


def test_consistency_over_identicals() -> None:
    for values in equivalents.values():
        expected = freeze(values[0])
        for value in values:
            assert freeze(value) == expected


def test_freeze_has_instance_methods() -> None:
    class A:
        def stuff(self) -> str:
            return "foo"
    assert "foo" in repr(freeze(A))
    assert "foo" in repr(freeze(A()))
    def stuff(self) -> str:
        return "bar"
    assert "bar" in repr(freeze(stuff))


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


def test_config_wrong_attr() -> None:
    # Real attributes should work
    old_recursion_limit = config.recursion_limit
    config.recursion_limit = old_recursion_limit
    with pytest.raises(AttributeError):
        config.attr_does_not_exist = 4
