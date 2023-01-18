import copyreg
from typing import Any, Callable, Dict, Hashable, Mapping, Optional, Tuple, cast

from .config import Config
from .lib import (
    UnfreezableTypeError,
    _freeze,
    combine_frozen,
    freeze_attrs,
    freeze_dispatch,
    freeze_sequence,
)

dispatch_table = cast(
    Mapping[type, Callable[[Any], Any]],
    copyreg.dispatch_table,
)


def freeze_pickle(
    obj: Any, config: Config, tabu: Dict[int, Tuple[int, int]], depth: int, index: int
) -> Optional[Tuple[Hashable, bool, Optional[int]]]:
    reduce_ex_method = getattr(obj, "__reduce_ex__", None)
    reduce_method = getattr(obj, "__reduce__", None)
    if type(obj) in dispatch_table:
        reduced = dispatch_table[type(obj)](obj)
    elif reduce_ex_method:
        reduced = reduce_ex_method(4)
    elif reduce_method:
        reduced = reduce_method()
    else:
        return None

    if isinstance(reduced, str):
        return ((b"pickle", reduced), True, None)
    elif isinstance(reduced, tuple) and 2 <= len(reduced) <= 5:
        ret: Tuple[Hashable, bool, Optional[int]]
        # pylint: disable=comparison-with-callable
        if reduced[0] == copyreg.__newobj__:  # type: ignore
            ret = (b"__newobj__", True, None)
        else:
            ret = _freeze(reduced[0], config, tabu, depth, index)
        ret = combine_frozen(
            ret, freeze_sequence(reduced[1], True, True, config, tabu, depth)
        )
        # reduced may only have two items, or the third one may be None or empty containers.
        if len(reduced) > 2 and reduced[2]:
            if isinstance(reduced[2], dict):
                ret = combine_frozen(
                    ret,
                    freeze_attrs(
                        {
                            var: val
                            for var, val in reduced[2].items()
                            if (obj.__module__, obj.__class__.__name__, var)
                            not in config.ignore_attributes
                        },
                        True,
                        True,
                        config,
                        tabu,
                        depth,
                    ),
                )
                # NOTE: assumed that objects do not get "new" attributes (although attribtues could change their current values).
                # Assess this assumption.
                # This is the "True" parameter in freeze_attrs
            else:
                ret = combine_frozen(ret, _freeze(reduced[2], config, tabu, depth, 1))
        if len(reduced) > 3 and reduced[3]:
            list_items = list(reduced[3])
            if list_items:
                ret = combine_frozen(
                    ret, freeze_sequence(list_items, False, True, config, tabu, depth)
                )
        if len(reduced) > 4 and reduced[4]:
            dict_items = dict(reduced[4])
            if dict_items:
                ret = combine_frozen(
                    ret,
                    freeze_sequence(
                        list(dict_items.items()),
                        False,
                        True,
                        config,
                        tabu,
                        depth,
                    ),
                )
        return ((b"pickle", *ret[0]), ret[1], ret[2])
    else:
        raise RuntimeError("__reduce__ protocol violated.")


@freeze_dispatch.register
def _(
    obj: object,
    config: Config,
    tabu: Dict[int, Tuple[int, int]],
    depth: int,
    index: int,
) -> Tuple[Hashable, bool, Optional[int]]:
    # getfrozenstate is custom-built for charmonium.freeze
    # It should take precedence.
    getfrozenstate = getattr(obj, "__getfrozenstate__", None)
    if getfrozenstate:
        ret = _freeze(type(obj), config, tabu, depth, 0)
        ret = combine_frozen(ret, _freeze(getfrozenstate(), config, tabu, depth, 1))
        return ((b"getfrozenstate", *ret[0]), ret[1], ret[2])

    pickle_data = freeze_pickle(obj, config, tabu, depth, index)
    # Otherwise, we may be able to use the Pickle protocol.
    if pickle_data is not None:
        return pickle_data

    # Otherwise, give up.
    raise UnfreezableTypeError("not implemented")
