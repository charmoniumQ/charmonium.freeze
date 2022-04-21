from typing import Union, Optional, Protocol, IO, AnyStr
from os import PathLike

class Figure:
    def savefig(
            self,
            fname: Union[str, PathLike[AnyStr], IO[bytes]],
            format: Optional[str] = None, 
    ) -> None:
        ...
