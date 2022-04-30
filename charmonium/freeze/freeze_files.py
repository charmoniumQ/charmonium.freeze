import io
import sys
import types
from typing import Any, Hashable

from .lib import (
    UnfreezableTypeError,
    _freeze,
    config,
    freeze_dispatch,
    immutable_if_children_are,
)


@freeze_dispatch.register
def _(
    obj: io.TextIOBase, tabu: dict[int, tuple[int, int]], depth: int, index: int
) -> tuple[Hashable, bool]:
    if hasattr(obj, "buffer"):
        return _freeze(obj.buffer, tabu, depth, index)[0], False
    else:
        raise UnfreezableTypeError(
            f"Don't know how to serialize {type(obj)} {obj}. See source code for special cases."
        )


@freeze_dispatch.register
def _(
    obj: io.BufferedWriter, tabu: dict[int, tuple[int, int]], depth: int, index: int
) -> tuple[Hashable, bool]:
    # If a buffered writers is both pointing to the same file, writing on it has the same side-effect.
    # Otherwise, it has a different side-effect.
    name = getattr(obj, "name", None)
    if name:
        # Since pytest captures stderr and stdout, they are renamed to <stderr> and <stdout>, but not when run natively
        # This standardization helps me pass the tests.
        return {"stderr": "<stderr>", "stdout": "<stdout>"}.get(name, name), True
    else:
        raise UnfreezableTypeError(
            "There's no way to know the side-effects of writing to an `io.BufferedWriter`, without knowing its filename."
        )


@freeze_dispatch.register
def _(
    obj: io.BufferedReader, tabu: dict[int, tuple[int, int]], depth: int, index: int
) -> tuple[Hashable, bool]:
    raise UnfreezableTypeError(
        f"Cannot freeze readable non-seekable streams such as {obj}. I have no way of knowing your position in the stream without modifying it."
    )


@freeze_dispatch.register
def _(
    obj: io.BufferedRandom, tabu: dict[int, tuple[int, int]], depth: int, index: int
) -> tuple[Hashable, bool]:
    name = getattr(obj, "name", None)
    if name is not None:
        cursor = obj.tell()
        obj.seek(0, io.SEEK_SET)
        value = obj.read()
        obj.seek(cursor, io.SEEK_SET)
        # `(value, cursor)` determines the side-effect of reading.
        # `(name, cursor)` determines the side-effect of writing.
        return (cursor, value, name), False
    else:
        raise UnfreezableTypeError(
            f"Don't know how to serialize {type(obj)} {obj} because it doesn't have a filename."
        )


@freeze_dispatch.register
def _(
    obj: io.FileIO, tabu: dict[int, tuple[int, int]], depth: int, index: int
) -> tuple[Hashable, bool]:
    if obj.fileno() == sys.stderr.fileno():
        return "<stderr>", True
    elif obj.fileno() == sys.stdout.fileno():
        return "<stdout>", True
    elif obj.mode in {"w", "x", "a", "wb", "xb", "ab"}:
        return obj.name, True
    elif obj.mode in {"r", "rb"}:
        raise UnfreezableTypeError(
            f"Cannot freeze readable non-seekable streams such as {obj}."
        )
    elif obj.mode in {"w+", "r+", "wb+", "rb+"}:
        name = getattr(obj, "name", None)
        if name is not None:
            cursor = obj.tell()
            obj.seek(0, io.SEEK_SET)
            value = obj.read()
            obj.seek(cursor, io.SEEK_SET)
            # `(value, cursor)` determines the side-effect of reading.
            # `(name, cursor)` determines the side-effect of writing.
            return (cursor, value, name), False
        else:
            raise UnfreezableTypeError(
                f"Don't know how to serialize {type(obj)} {obj} because it doesn't have a filename."
            )
    else:
        raise UnfreezableTypeError(
            f"{obj.name} {obj.mode} must be a special kind of file."
        )
