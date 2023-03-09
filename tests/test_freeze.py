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
from obj_test_cases import (
    equivalents,
    immutables,
    non_copyable_types,
    non_equivalents,
    non_freezable_types,
    non_immutables,
)

from charmonium.freeze import (
    Config,
    FreezeRecursionError,
    UnfreezableTypeError,
    freeze,
    global_config,
    summarize_diffs_of_frozen,
)
from charmonium.freeze.lib import _freeze

logging.getLogger("charmonium.freeze").setLevel(logging.DEBUG)

configs = {
    True: copy.deepcopy(global_config),
    False: copy.deepcopy(global_config),
}
configs[True].use_hash = True
configs[False].use_hash = False


@pytest.mark.parametrize("input_kind", immutables.keys())
@pytest.mark.parametrize("use_hash", [True, False])
def test_immutability(input_kind: str, use_hash: bool) -> None:
    obj = immutables[input_kind]
    frozen = _freeze(obj, configs[use_hash], {}, 0, 0)
    assert frozen[1], f"frozen value: {frozen[0]}"


@pytest.mark.parametrize("input_kind", non_immutables.keys())
@pytest.mark.parametrize("use_hash", [True, False])
def test_non_immutability(input_kind: str, use_hash: bool) -> None:
    obj = non_immutables[input_kind]
    frozen = _freeze(obj, configs[use_hash], {}, 0, 0)
    assert not frozen[1], f"frozen value: {frozen[0]}"


@pytest.mark.parametrize("input_kind", non_equivalents.keys())
@pytest.mark.parametrize("use_hash", [True, False])
def test_freeze_works(input_kind: str, use_hash: bool) -> None:
    for value in non_equivalents[input_kind]:
        frozen = freeze(value, configs[use_hash])
        try:
            hash(frozen)
        except Exception as exc:
            pprint.pprint(value, width=1000)
            pprint.pprint(frozen, width=1000)
            raise exc
        if use_hash:
            assert isinstance(frozen, int)


@pytest.mark.parametrize("input_kind", non_equivalents.keys())
@pytest.mark.parametrize("use_hash", [True, False])
def test_freeze_total_uniqueness(input_kind: str, use_hash: bool) -> None:
    values = non_equivalents[input_kind]
    frozen_values = [(value, freeze(value, configs[use_hash])) for value in values]
    for i, (this_value, this_freeze) in enumerate(frozen_values):
        for j, (that_value, that_freeze) in enumerate(frozen_values):
            if i != j:
                if this_freeze == that_freeze:
                    print(
                        f"freeze({this_value!r}) = {pprint.pformat(that_freeze)} = freeze({that_value!r})"
                    )
                assert this_freeze != that_freeze


@pytest.mark.parametrize("input_kind", non_equivalents.keys() - non_copyable_types)
@pytest.mark.parametrize("use_hash", [True, False])
def test_determinism_over_copies(input_kind: str, use_hash: bool) -> None:
    for value in non_equivalents[input_kind]:
        freeze0 = freeze(copy.deepcopy(value), configs[use_hash])
        if input_kind == "@functools.singledispatch":
            # Call the singledispatch function to try and change its cache_token
            value(345)
            value((32, ((10), frozenset({"hello"}))))
        freeze1 = freeze(value, configs[use_hash])
        if freeze0 != freeze1:
            print(summarize_diffs_of_frozen(freeze0, freeze1))
            print(pprint.pformat(freeze0, width=1000))
            print(pprint.pformat(freeze1, width=1000))
        assert freeze0 == freeze1


@pytest.mark.parametrize("input_kind", non_equivalents.keys())
@pytest.mark.parametrize("use_hash", [True, False])
def test_determinism_over_processes(
    input_kind: str,
    use_hash: bool,
    past_freezes: Mapping[bool, Mapping[str, List[int]]],
) -> None:
    for past_hash, value in zip(
        past_freezes[use_hash][input_kind], non_equivalents[input_kind]
    ):
        new_hash = freeze(value, configs[use_hash])
        if past_hash != new_hash:
            print(summarize_diffs_of_frozen(past_hash, new_hash))
            pprint.pprint(past_hash, width=1000)
            pprint.pprint(new_hash, width=1000)
        assert past_hash == new_hash, f"Determinism-over-processes failed for {value}"


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
    import logging

    logging.basicConfig(level=logging.DEBUG)
    use_hash_config = Config(use_hash=True)
    no_use_hash_config = Config(use_hash=False)
    data = {
        use_hash: {
            value_kind: [freeze(value, configs[use_hash]) for value in values]
            for value_kind, values in non_equivalents.items()
        }
        for use_hash in [True, False]
    }
    sys.stdout.buffer.write(pickle.dumps(data))


@pytest.mark.parametrize("input_kind", equivalents.keys())
@pytest.mark.parametrize("use_hash", [True, False])
def test_consistency_over_equivalents(input_kind: str, use_hash: bool) -> None:
    values = equivalents[input_kind]
    expected = freeze(values[0], configs[use_hash])
    for value in values:
        assert freeze(value, configs[use_hash]) == expected


def test_freeze_has_instance_methods() -> None:
    class A:
        def stuff(self) -> str:
            return "foo"

    assert "foo" in repr(freeze(A, configs[False]))
    assert "foo" in repr(freeze(A(), configs[False]))

    def stuff() -> str:
        return "bar"

    assert "bar" in repr(freeze(stuff, configs[False]))


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


def test_config_attrs() -> None:
    with pytest.raises(AttributeError):
        global_config.wrong_attr_name = 4


def test_recursion_limit() -> None:
    with pytest.raises(FreezeRecursionError):
        freeze([[[[[["hi"]]]]]], Config(recursion_limit=2))


# TODO: test config.ignore_dict_order
