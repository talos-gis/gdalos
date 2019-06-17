from abc import ABC, ABCMeta
from itertools import chain
from typing import Mapping, Type, Callable

from inspect import signature, Parameter
from functools import wraps, partial


def with_param_dict(kwarg_name='_arguments'):
    def decorator(func):
        all_parameters: Mapping[str, Parameter] = signature(func).parameters
        dest_param = all_parameters.get(kwarg_name)
        if not dest_param or dest_param.kind != Parameter.KEYWORD_ONLY:
            raise NameError('function must contain keyword-only parameter named ' + kwarg_name)

        pos_names = []
        for n, p in all_parameters.items():
            if p.kind == Parameter.VAR_POSITIONAL:
                raise TypeError(f"with_param_dict can't a variadic argument parameter ({p})")
            if p.kind not in (Parameter.POSITIONAL_ONLY, Parameter.POSITIONAL_OR_KEYWORD):
                break
            pos_names.append(n)

        @wraps(func)
        def wrapper(*args, **kwargs):
            if kwarg_name in kwargs:
                raise TypeError(f'{kwarg_name} cannot be specified outside the wrapper')

            params = dict(zip(pos_names, args))
            params.update(kwargs)

            kwargs[kwarg_name] = params

            return func(*args, **kwargs)

        return wrapper

    return decorator


def implementor(func: Callable):
    func.__implementor__ = True
    return func


def make_implementor(name: str, *args, **kwargs):
    def decorator(func):
        if not hasattr(func, '__implementors__'):
            func.__implementors__ = {}
        func.__implementors__[name] = (args, kwargs)
        return func

    return decorator


def has_implementors(cls: Type[ABC]):
    def const_method(const):
        def ret(self):
            return const

        return ret

    am = cls.__abstractmethods__
    if len(am) != 1:
        raise ValueError('class must have exactly 1 abstract method')
    method_name = next(iter(am))

    implementor_instances = {}

    k: str
    for k, v in cls.__dict__.items():
        if k.startswith('_'):
            continue

        if getattr(v, '__implementor__', False):
            subclass = type(
                k.capitalize(), (cls,),
                {
                    method_name: v,
                    '__str__': const_method(k),
                    '__repr__': const_method(f'{cls.__name__}[{k!r}]')
                }
            )
            instance = subclass()
            implementor_instances[k] = instance
        if getattr(v, '__implementors__', False):
            def make_init(v):
                if not callable(v):
                    v = v.__func__

                def __init__(self, name, *args, **kwargs):
                    super(type(self), self).__init__()
                    self.__name__ = name
                    self.__func__ = v(*args, **kwargs)

                return __init__

            subclass = type(
                k.capitalize(), (cls,),
                {
                    '__init__': make_init(v),
                    method_name: lambda self, *a, **k: self.__func__(*a, **k),
                    '__str__': lambda self: self.__name__,
                    '__repr__': lambda self: f'{cls.__name__}[{self.__name__!r}]'
                }
            )
            for name, (args, kwargs) in v.__implementors__.items():
                instance = subclass(name, *args, **kwargs)
                implementor_instances[name] = instance

    cls.__class_getitem__ = lambda i: implementor_instances.get(i, i)

    for k, v in implementor_instances.items():
        if hasattr(cls, k):
            continue
        setattr(cls, k, v)

    return cls


class ShortABCMeta(ABCMeta):
    def __new__(mcs, *args, **kwargs):
        ret = super().__new__(mcs, *args, **kwargs)
        am = ret.__abstractmethods__
        if len(am) != 1:
            raise ValueError('class must have exactly 1 abstract method')
        ret.__abstractmethod__ = next(iter(am))
        ret.__instance_lookup__ = {}

        return ret

    def _register_instance(cls, name, instance):
        if cls.__instance_lookup__.setdefault(name, instance) is not instance:
            raise Exception(f'duplicate name: {name}')

    def register_implementor(cls, name=...):
        def ret(func):
            nonlocal name
            if name is ...:
                name = func.__name__
            subclass = type(
                name.capitalize(), (cls,),
                {
                    cls.__abstractmethod__: staticmethod(func),
                    '__str__': name,
                    '__repr__': f'{cls.__name__}[{name!r}]'
                }
            )
            cls._register_instance(name, subclass())
            return func

        return ret

    def register_instance(cls, name, *args, **kwargs):
        def ret(subclass):
            cls._register_instance(name, subclass(*args, **kwargs))
            return subclass

        return ret

    def register_implementor_class(cls, name=...):
        def ret(func):
            nonlocal name
            if name is ...:
                name = func.__name__

            subclass = type(
                name.capitalize(), (cls,),
                {
                    '__init__': None,
                    cls.__abstractmethod__: lambda self, *a, **k: self.__func__(*a, **k),
                    '__str__': None,
                    '__repr__': None
                }
            )

            def __init__(self, *args, **kwargs):
                super(subclass, self)
                self.args = args
                self.kwargs = kwargs
                self.__func__ = func(*args, **kwargs)
                self.__name__ = None

            def __str__(self):
                return self.__name__ or repr(self)

            def __repr__(self):
                if self.__name__:
                    return f'{cls.__name__}[{self.__name__!r}]'
                return f'{type(self).__name__}({", ".join(chain((repr(a) for a in self.args),(f"{k}={v!r}" for (k, v) in self.kwargs.items())))})'

            subclass.__init__ = __init__
            subclass.__str__ = __str__
            subclass.__repr__ = __repr__

            return subclass
        return ret
