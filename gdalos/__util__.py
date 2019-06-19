from abc import ABC, ABCMeta
from itertools import chain
from os import PathLike
from pathlib import Path
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

            for k in ('self', 'cls'):
                params.pop(k, None)

            kwargs[kwarg_name] = params

            return func(*args, **kwargs)

        return wrapper

    return decorator


def has_implementors(cls):
    am = cls.__abstractmethods__
    if len(am) != 1:
        raise ValueError('class must have exactly 1 abstract method')
    cls.__abstractmethod__ = next(iter(am))
    cls.__instance_lookup__ = {}

    def _register_instance(name, instance):
        if hasattr(cls, name) \
                or cls.__instance_lookup__.setdefault(name, instance) is not instance:
            raise Exception(f'duplicate name: {name}')
        setattr(cls, name, instance)

    def _register_subclass(sbcls):
        if hasattr(cls, sbcls.__name__):
            raise Exception(f'duplicate name: {sbcls.__name__}')
        setattr(cls, sbcls.__name__, sbcls)

    def register_implementor(cls, name=...):
        def ret(func):
            nonlocal name
            if name is ...:
                name = func.__name__

            def __str__(self):
                return name

            def __repr__(self):
                return f'{cls.__name__}[{name!r}]'

            subclass = type(
                capitalize(name), (cls,),
                {
                    cls.__abstractmethod__: staticmethod(func),
                    '__str__': __str__,
                    '__repr__': __repr__
                }
            )
            _register_subclass(subclass)
            _register_instance(name, subclass())
            return func

        return ret

    def register_instance(cls, name, *args, **kwargs):
        def ret(subclass):
            inst = subclass(*args, **kwargs)
            inst.__name__ = name
            _register_instance(name, inst)
            return subclass

        return ret

    def register_implementor_factory(cls, name=...):
        def ret(func):
            nonlocal name
            if name is ...:
                name = func.__name__

            subclass = type(
                capitalize(name), (cls,),
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
                args = chain((repr(a) for a in self.args), (f"{k}={v!r}" for (k, v) in self.kwargs.items()))
                return f'{type(self).__name__}({", ".join(args)})'

            subclass.__init__ = __init__
            subclass.__str__ = __str__
            subclass.__repr__ = __repr__

            _register_subclass(subclass)

            return subclass

        return ret

    cls.implementor = classmethod(register_implementor)
    cls.instance = classmethod(register_instance)
    cls.factory = classmethod(register_implementor_factory)
    return cls


class AutoPath(PathLike):
    def __init__(self, base: PathLike):
        self.base = Path(base)
        self.suffixes = []

    def add_suffix(self, *suffixes: str):
        self.suffixes.extend(
            (s if s.startswith('.') else '.' + s)
            for s in suffixes
        )

    def __fspath__(self):
        return str(self.base.with_suffix(''.join(self.suffixes)))


def capitalize(x: str):
    split = x.split('_')
    return ''.join(s.capitalize() for s in split)
