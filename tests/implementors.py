from abc import abstractmethod, ABC

from gdalos.__util__ import has_implementors


@has_implementors
class Foo(ABC):
    @abstractmethod
    def bar(self, x):
        pass


@Foo.implementor()
def a(x):
    return x


@Foo.implementor()
def b(x):
    return x * x


@Foo.instance('cb', 3)
@Foo.factory()
def c(p):
    def ret(x):
        return x ** p

    return ret


print(Foo.cb.bar(5))
