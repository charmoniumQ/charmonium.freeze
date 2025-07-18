from __future__ import annotations

import io
import logging
import pathlib
import re
import ssl
import sys
import struct
import types
from typing import Any, Dict, Hashable, Optional, Tuple

from .config import Config
from .lib import freeze_attrs, freeze_dispatch, freeze_sequence
from .util import int_to_bytes, get_version


@freeze_dispatch.register(type(None))
def _(
    obj: Any, config: Config, tabu: Dict[int, Tuple[int, int]], depth: int, index: int
) -> Tuple[Hashable, bool, Optional[int]]:
    if config.use_hash:
        return 0, True, None
    return obj, True, None


@freeze_dispatch.register(type(...))
def _(
    obj: Any, config: Config, tabu: Dict[int, Tuple[int, int]], depth: int, index: int
) -> Tuple[Hashable, bool, Optional[int]]:
    if config.use_hash:
        return 1, True, None
    return obj, True, None


@freeze_dispatch.register
def _(
    obj: int, config: Config, tabu: Dict[int, Tuple[int, int]], depth: int, index: int
) -> Tuple[Hashable, bool, Optional[int]]:
    if config.use_hash:
        return config.hasher(int_to_bytes(obj)), True, None
    return obj, True, None


@freeze_dispatch.register
def _(
    obj: bytes, config: Config, tabu: Dict[int, Tuple[int, int]], depth: int, index: int
) -> Tuple[Hashable, bool, Optional[int]]:
    if config.use_hash:
        return config.hasher(obj), True, None
    return obj, True, None


@freeze_dispatch.register
def _(
    obj: str, config: Config, tabu: Dict[int, Tuple[int, int]], depth: int, index: int
) -> Tuple[Hashable, bool, Optional[int]]:
    if config.use_hash:
        return config.hasher(obj.encode()), True, None
    return obj, True, None


@freeze_dispatch.register
def _(
    obj: float, config: Config, tabu: Dict[int, Tuple[int, int]], depth: int, index: int
) -> Tuple[Hashable, bool, Optional[int]]:
    if config.use_hash:
        return config.hasher(struct.pack("!d", obj)), True, None
    return obj, True, None


@freeze_dispatch.register
def _(
    obj: complex,
    config: Config,
    tabu: Dict[int, Tuple[int, int]],
    depth: int,
    index: int,
) -> Tuple[Hashable, bool, Optional[int]]:
    return freeze_sequence((obj.real, obj.imag), True, True, config, tabu, depth)


@freeze_dispatch.register
def _(
    obj: bytearray,
    config: Config,
    _tabu: Dict[int, Tuple[int, int]],
    _depth: int,
    _index: int,
) -> Tuple[Hashable, bool, Optional[int]]:
    if config.use_hash:
        return config.hasher(bytes(obj)), False, None
    return bytes(obj), False, None


@freeze_dispatch.register(set)
def _(
    obj: set[Any],
    config: Config,
    tabu: Dict[int, Tuple[int, int]],
    depth: int,
    index: int,
) -> Tuple[Hashable, bool, Optional[int]]:
    return freeze_sequence(obj, False, False, config, tabu, depth)


@freeze_dispatch.register(frozenset)
def _(
    obj: frozenset[Any],
    config: Config,
    tabu: Dict[int, Tuple[int, int]],
    depth: int,
    index: int,
) -> Tuple[Hashable, bool, Optional[int]]:
    return freeze_sequence(obj, True, False, config, tabu, depth)


@freeze_dispatch.register(list)
def _(
    obj: list[Any],
    config: Config,
    tabu: Dict[int, Tuple[int, int]],
    depth: int,
    index: int,
) -> Tuple[Hashable, bool, Optional[int]]:
    return freeze_sequence(obj, False, True, config, tabu, depth)


@freeze_dispatch.register(tuple)
def _(
    obj: Tuple[Any],
    config: Config,
    tabu: Dict[int, Tuple[int, int]],
    depth: int,
    index: int,
) -> Tuple[Hashable, bool, Optional[int]]:
    return freeze_sequence(obj, True, True, config, tabu, depth)


@freeze_dispatch.register(types.MappingProxyType)
def _(
    obj: types.MappingProxyType[Hashable, Any],
    config: Config,
    tabu: Dict[int, Tuple[int, int]],
    depth: int,
    index: int,
) -> Tuple[Hashable, bool, Optional[int]]:
    return freeze_sequence(
        obj.items(),
        True,
        not config.ignore_dict_order,
        config,
        tabu,
        depth,
    )


@freeze_dispatch.register(dict)
def _(
    obj: Dict[Hashable, Any],
    config: Config,
    tabu: Dict[int, Tuple[int, int]],
    depth: int,
    index: int,
) -> Tuple[Hashable, bool, Optional[int]]:
    return freeze_sequence(
        obj.items(),
        False,
        not config.ignore_dict_order,
        config,
        tabu,
        depth,
    )


@freeze_dispatch.register
def _(
    obj: types.ModuleType,
    config: Config,
    tabu: Dict[int, Tuple[int, int]],
    depth: int,
    index: int,
) -> Tuple[Hashable, bool, Optional[int]]:
    name = obj.__name__
    version = get_version(name)
    file = pathlib.Path(getattr(obj, "__file__", None) or "/").resolve()
    if name in config.stdlib_modules:
        return freeze_sequence((name, *sys.version_info), True, True, config, tabu, depth)
    elif version and config.use_version and name not in config.use_version_exceptions:
        return freeze_sequence((name, version), True, True, config, tabu, depth)
    elif any(
        ancestor in config.ignore_files
        for ancestor in file.parents
    ):
        return freeze_sequence(
            (file, config.hasher(file.read_bytes())),
            True,
            True,
            config,
            tabu,
            depth
        )
    else:
        attrs = {
            attr_name: getattr(obj, attr_name, None)
            for attr_name in dir(obj)
            if hasattr(obj, attr_name)
            and attr_name not in config.ignore_module_attrs
            and (name, attr_name) not in config.ignore_globals
        }
        return freeze_attrs(attrs, True, True, config, tabu, depth)


# pylint: disable=unused-argument
@freeze_dispatch.register
def _(
    obj: memoryview,
    config: Config,
    tabu: Dict[int, Tuple[int, int]],
    depth: int,
    index: int,
) -> Tuple[Hashable, bool, Optional[int]]:
    if config.use_hash:
        return config.hasher(obj.tobytes()), False, None
    return obj.tobytes(), False, None


@freeze_dispatch.register
def _(
    obj: logging.Logger,
    config: Config,
    tabu: Dict[int, Tuple[int, int]],
    depth: int,
    index: int,
) -> Tuple[Hashable, bool, Optional[int]]:
    # The client should be able to change the logger without changing the computation.
    # But the _name_ of the logger specifies where the side-effect goes, so it should matter.
    if config.use_hash:
        return config.hasher(obj.name.encode()), True, None
    return obj.name, True, None


@freeze_dispatch.register(re.Match)
def _(
    obj: re.Match[str],
    config: Config,
    tabu: Dict[int, Tuple[int, int]],
    depth: int,
    index: int,
) -> Tuple[Hashable, bool, Optional[int]]:
    return freeze_attrs(
        {
            "regs": obj.regs,
            "string": obj.string,
            "re": obj.re,
        },
        is_immutable=True,
        write_attrs=False,
        config=config,
        tabu=tabu,
        depth=depth,
    )


@freeze_dispatch.register
def _(
    obj: io.BytesIO,
    config: Config,
    tabu: Dict[int, Tuple[int, int]],
    depth: int,
    index: int,
) -> Tuple[Hashable, bool, Optional[int]]:
    if config.use_hash:
        return config.hasher(obj.getvalue()), False, None
    return obj.getvalue(), False, None


@freeze_dispatch.register
def _(
    obj: io.StringIO,
    config: Config,
    tabu: Dict[int, Tuple[int, int]],
    depth: int,
    index: int,
) -> Tuple[Hashable, bool, Optional[int]]:
    if config.use_hash:
        return config.hasher(obj.getvalue().encode()), False, None
    return obj.getvalue(), False, None


@freeze_dispatch.register
def _(
    obj: ssl.SSLContext,
    config: Config,
    tabu: Dict[int, Tuple[int, int]],
    depth: int,
    index: int,
) -> Tuple[Hashable, bool, Optional[int]]:
    if config.use_hash:
        return config.hasher(b"ssl.SSLContext"), False, None
    return "ssl.SSLContext", False, None
