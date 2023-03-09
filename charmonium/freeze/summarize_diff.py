from __future__ import annotations

import copy
import dataclasses
from typing import Any, FrozenSet, Hashable, Iterable, Optional, Tuple, TypeVar, cast

from .config import Config, global_config
from .lib import freeze
from .util import common_prefix

_T = TypeVar("_T")


def is_frozen_dict(obj: Iterable[Any]) -> bool:
    return (
        isinstance(obj, (tuple, frozenset))
        and bool(obj)
        and all(isinstance(elem, tuple) and len(elem) == 2 for elem in obj)
    )


@dataclasses.dataclass
class ObjectLocation:
    labels: tuple[str, ...]
    objects: tuple[object, ...]

    @staticmethod
    def create(label: int, obj: object) -> ObjectLocation:
        return ObjectLocation((f"obj{label}",), (obj,))

    def append(self, label: str, obj: object) -> ObjectLocation:
        return self.__class__((*self.labels, label), (*self.objects, obj))

    @property
    def tail(self) -> object:
        return self.objects[-1]

    @tail.setter
    def tail(self, obj: object) -> None:
        self.objects = (*self.objects[:-1], obj)


def summarize_diffs(
    obj0: Any,
    obj1: Any,
    config: Optional[Config] = None,
) -> str:
    if config is None:
        config = copy.deepcopy(global_config)
        config.use_hash = False
    else:
        if config.use_hash:
            raise RuntimeError("Must supply a config with use_hash = False")
    frozen_obj0 = freeze(obj0, config)
    frozen_obj1 = freeze(obj1, config)
    return summarize_diffs_of_frozen(frozen_obj0, frozen_obj1)


def iterate_diffs(
    obj0: Any,
    obj1: Any,
    config: Optional[Config] = None,
) -> Iterable[tuple[ObjectLocation, ObjectLocation]]:
    if config is None:
        config = copy.deepcopy(global_config)
        config.use_hash = False
    else:
        if config.use_hash:
            raise RuntimeError("Must supply a config with use_hash = False")
    frozen_obj0 = freeze(obj0, config)
    frozen_obj1 = freeze(obj1, config)
    return iterate_diffs_of_frozen(frozen_obj0, frozen_obj1)


def summarize_diffs_of_frozen(
    frozen_obj0: Hashable,
    frozen_obj1: Hashable,
) -> str:
    differences = list(iterate_diffs_of_frozen(frozen_obj0, frozen_obj1))
    if differences:
        longest_common = differences[0][0].labels[1:]
        for difference in differences:
            longest_common = common_prefix(longest_common, difference[0].labels[1:])
            longest_common = common_prefix(longest_common, difference[1].labels[1:])
        ret = []
        ret.append(f"let obj0_sub = obj0{''.join(longest_common)}")
        ret.append(f"let obj1_sub = obj1{''.join(longest_common)}")
        for difference in differences:
            path_from_sub = "".join(difference[0].labels[len(longest_common) + 1 :])
            ret.append(f"obj0_sub{path_from_sub} == {difference[0].objects[-1]}")
            ret.append(f"obj1_sub{path_from_sub} == {difference[1].objects[-1]}")
        return "\n".join(ret)
    else:
        return "no differences"


def iterate_diffs_of_frozen(
    frozen_obj0: Hashable,
    frozen_obj1: Hashable,
) -> Iterable[tuple[ObjectLocation, ObjectLocation]]:
    yield from recursive_find_diffs(
        ObjectLocation(
            labels=("obj0",),
            objects=(frozen_obj0,),
        ),
        ObjectLocation(
            labels=("obj1",),
            objects=(frozen_obj1,),
        ),
    )


def recursive_find_diffs(
    obj0: ObjectLocation,
    obj1: ObjectLocation,
) -> Iterable[tuple[ObjectLocation, ObjectLocation]]:
    if obj0.tail.__class__ != obj1.tail.__class__:
        yield (
            obj0.append(".__class__", obj0.tail.__class__.__name__),
            obj1.append(".__class__", obj1.tail.__class__.__name__),
        )
    elif isinstance(obj0.tail, dict) and isinstance(obj1.tail, dict):
        yield from recursive_find_diffs(
            obj0.append(".keys()", frozenset(obj0.tail.keys())),
            obj1.append(".keys()", frozenset(obj1.tail.keys())),
        )
        for key in obj0.tail.keys() & obj1.tail.keys():
            yield from recursive_find_diffs(
                obj0.append(f"[{key!r}]", obj0.tail[key]),
                obj1.append(f"[{key!r}]", obj1.tail[key]),
            )
    elif isinstance(obj0.tail, tuple) and isinstance(obj1.tail, tuple):
        # could be dict
        if is_frozen_dict(obj0.tail) and is_frozen_dict(obj1.tail):
            # treat as dict
            obj0.tail = dict(cast(FrozenSet[Tuple[Hashable, Any]], obj0.tail))
            obj1.tail = dict(cast(FrozenSet[Tuple[Hashable, Any]], obj1.tail))
            yield from recursive_find_diffs(obj0, obj1)
        else:
            # treat frozenset as a pure tuple
            if len(obj0.tail) != len(obj1.tail):
                yield (
                    obj0.append(".__len__()", len(obj0.tail)),
                    obj1.append(".__len__()", len(obj1.tail)),
                )
            for idx in range(min(len(obj0.tail), len(obj1.tail))):
                yield from recursive_find_diffs(
                    obj0.append(f"[{idx}]", obj0.tail[idx]),
                    obj1.append(f"[{idx}]", obj1.tail[idx]),
                )
    elif isinstance(obj0.tail, frozenset) and isinstance(obj1.tail, frozenset):
        # could be dict
        if is_frozen_dict(obj0.tail) and is_frozen_dict(obj1.tail):
            # treat as dict
            obj0.tail = dict(cast(FrozenSet[Tuple[Hashable, Any]], obj0.tail))
            obj1.tail = dict(cast(FrozenSet[Tuple[Hashable, Any]], obj1.tail))
            yield from recursive_find_diffs(obj0, obj1)
        else:
            # treat frozenset as a pure frozenset
            for elem in obj0.tail - obj1.tail:
                yield (
                    obj0.append(".has()", elem),
                    obj1.append(".has()", "no such element"),
                )
            for elem in obj1.tail - obj0.tail:
                yield (
                    obj0.append(".has()", "no such element"),
                    obj1.append(".has()", elem),
                )
    else:
        if obj0.tail != obj1.tail:
            yield (obj0, obj1)
