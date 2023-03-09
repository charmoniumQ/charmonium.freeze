import copyreg
from typing import Any, Callable, Dict, Hashable, Mapping, Optional, Tuple, cast

from .config import Config
from .lib import UnfreezableTypeError, freeze_attrs, freeze_dispatch, freeze_sequence

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
        # Returning None tells the caller "we don't know how to do this"
        return None

    if isinstance(reduced, str):
        if config.use_hash:
            return config.hasher(reduced.encode()), True, None
        else:
            return reduced, True, None
    elif isinstance(reduced, tuple) and 2 <= len(reduced) <= 5:
        attrs: Dict[str, Any] = {}
        # pylint: disable=comparison-with-callable
        if reduced[0] == copyreg.__newobj__:  # type: ignore
            attrs["constructor"] = b"copyreg.__newobj__"
        else:
            attrs["constructor"] = reduced[0]
        attrs["args"] = tuple(reduced[1])
        # reduced may only have two items, or the third one may be None or empty containers.
        if len(reduced) > 2 and reduced[2]:
            if isinstance(reduced[2], dict):
                attrs["attrs"] = {
                    var: val
                    for var, val in reduced[2].items()
                    if (obj.__module__, obj.__class__.__name__, var)
                    not in config.ignore_attributes
                }
            else:
                attrs["attrs"] = reduced[2]
        if len(reduced) > 3 and reduced[3]:
            attrs["list_items"] = list(reduced[3])
        if len(reduced) > 4 and reduced[4]:
            attrs["dict_items"] = dict(reduced[4])
        # NOTE: assumed that objects do not get "new" attributes (although attribtues could change their current values).
        # Assess this assumption.
        # This is the "True" parameter in freeze_attrs
        return freeze_attrs(
            attrs,
            is_immutable=True,
            write_attrs=False,
            config=config,
            tabu=tabu,
            depth=depth,
        )
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
        return freeze_sequence(
            (type(obj), getfrozenstate()),
            is_immutable=True,
            order_matters=True,
            config=config,
            tabu=tabu,
            depth=depth,
        )

    pickle_data = freeze_pickle(obj, config, tabu, depth, index)
    # Otherwise, we may be able to use the Pickle protocol.
    if pickle_data is not None:
        return pickle_data

    # Otherwise, give up.
    raise UnfreezableTypeError("not implemented")
