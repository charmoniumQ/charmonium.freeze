from os import PathLike
from typing import IO, AnyStr, Optional, Union

class Figure:
    def savefig(
        self,
        fname: Union[str, PathLike[AnyStr], IO[bytes]],
        format: Optional[str] = None,
    ) -> None: ...
