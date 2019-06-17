from abc import ABC, abstractmethod

from gdalos.__util__ import builtin_container, has_implementors, implementor


@has_implementors
class OvrType(ABC):
    @abstractmethod
    def populate_spawn(self, job):
        pass

    @staticmethod
    @implementor
    def
