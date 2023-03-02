from __future__ import annotations

import dataclasses
import pprint
from typing import Any, FrozenSet, Hashable, Iterable, Optional, Tuple, TypeVar, cast

from .config import Config
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


def summarize_diff(obj0: Any, obj1: Any, config: Optional[Config] = None) -> str:
    return summarize_diff_of_frozen(freeze(obj0, config), freeze(obj1, config))


def summarize_diff_of_frozen(obj0: Hashable, obj1: Hashable) -> str:
    differences = list(
        iterate_diffs_of_frozen(
            ObjectLocation(
                labels=("obj0",),
                objects=(obj0,),
            ),
            ObjectLocation(
                labels=("obj1",),
                objects=(obj1,),
            ),
        )
    )
    if differences:
        longest_common = differences[0][0].labels[1:]
        for difference in differences:
            longest_common = common_prefix(longest_common, difference[0].labels[1:])
            longest_common = common_prefix(longest_common, difference[1].labels[1:])
        ret = []
        if len(longest_common) > 3:
            ret.append(f"obj0_sub = obj0{''.join(longest_common)}")
            ret.append(
                pprint.pformat(
                    differences[0][0].objects[len(longest_common)], width=300
                )
            )
            ret.append(f"obj1_sub = obj1{''.join(longest_common)}")
            ret.append(
                pprint.pformat(
                    differences[0][1].objects[len(longest_common)], width=300
                )
            )
        for difference in differences:
            path_from_sub = "".join(difference[0].labels[len(longest_common) + 1 :])
            ret.append(
                f"obj0_sub{path_from_sub} == {difference[0].objects[-1]}"
            )
            ret.append(
                f"obj1_sub{path_from_sub} == {difference[1].objects[-1]}"
            )
        return "\n".join(ret)
    else:
        return "no differences"


def iterate_diffs_of_frozen(
    obj0: ObjectLocation,
    obj1: ObjectLocation,
) -> Iterable[tuple[ObjectLocation, ObjectLocation]]:
    if obj0.tail.__class__ != obj1.tail.__class__:
        yield (
            obj0.append(".__class__", obj0.tail.__class__.__name__),
            obj1.append(".__class__", obj1.tail.__class__.__name__),
        )
    elif isinstance(obj0.tail, dict) and isinstance(obj1.tail, dict):
        yield from iterate_diffs_of_frozen(
            obj0.append(".keys()", frozenset(obj0.tail.keys())),
            obj1.append(".keys()", frozenset(obj1.tail.keys())),
        )
        for key in obj0.tail.keys() & obj1.tail.keys():
            yield from iterate_diffs_of_frozen(
                obj0.append(f"[{key!r}]", obj0.tail[key]),
                obj1.append(f"[{key!r}]", obj1.tail[key]),
            )
    elif isinstance(obj0.tail, tuple) and isinstance(obj1.tail, tuple):
        # could be dict
        if is_frozen_dict(obj0.tail) and is_frozen_dict(obj1.tail):
            # treat as dict
            obj0.tail = dict(cast(FrozenSet[Tuple[Hashable, Any]], obj0.tail))
            obj1.tail = dict(cast(FrozenSet[Tuple[Hashable, Any]], obj1.tail))
            yield from iterate_diffs_of_frozen(obj0, obj1)
        else:
            # treat frozenset as a pure tuple
            if len(obj0.tail) != len(obj1.tail):
                yield (
                    obj0.append(".__len__()", len(obj0.tail)),
                    obj1.append(".__len__()", len(obj1.tail)),
                )
            for idx in range(min(len(obj0.tail), len(obj1.tail))):
                yield from iterate_diffs_of_frozen(
                    obj0.append(f"[{idx}]", obj0.tail[idx]),
                    obj1.append(f"[{idx}]", obj1.tail[idx]),
                )
    elif isinstance(obj0.tail, frozenset) and isinstance(obj1.tail, frozenset):
        # could be dict
        if is_frozen_dict(obj0.tail) and is_frozen_dict(obj1.tail):
            # treat as dict
            obj0.tail = dict(cast(FrozenSet[Tuple[Hashable, Any]], obj0.tail))
            obj1.tail = dict(cast(FrozenSet[Tuple[Hashable, Any]], obj1.tail))
            yield from iterate_diffs_of_frozen(obj0, obj1)
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
