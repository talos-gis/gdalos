from enum import Enum, auto
from pathlib import Path
from typing import Union, List, Tuple

SequanceNotString = Union[List, Tuple]
FileName = Union[str, Path]


def enum_to_str(enum_or_str):
    return enum_or_str.name if isinstance(enum_or_str, Enum) else str(enum_or_str)