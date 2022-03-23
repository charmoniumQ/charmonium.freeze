from typing import Mapping, Union, Iterable


class DataFrame:
    def __init__(
            self,
            data: Mapping[str, Iterable[Union[int, float]]] = ...,
            index: Iterable[int] = ...,
    ) -> None:
        ...
