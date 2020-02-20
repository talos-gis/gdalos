from functools import wraps
from inspect import Parameter, signature
from itertools import chain
from typing import Mapping, Sequence


class CallParamDict:
    def __init__(
        self,
        func,
        args: tuple,
        kwargs: dict,
        pos_param_names: Sequence[str],
        all_params: Mapping[str, Parameter],
    ):
        self.func = func

        self.args = args
        self.kwargs = kwargs

        self.pos_param_names = pos_param_names
        self.all_params = all_params

        self.all_arguments = dict(zip(pos_param_names, args))
        self.all_arguments.update(kwargs)

    def __str__(self):
        return f"""{self.func.__name__}({
            ",".join(chain(
                (repr(a) for a in self.args),
                (f'{k}= {v!r}' for (k,v) in self.kwargs.items()))
            )
        })"""

    def __getitem__(self, item):
        if item in self.all_arguments:
            return self.all_arguments[item]

        p = self.all_params[item]
        if p.default != Parameter.empty:
            return p.default

        raise KeyError(item)

    def __setitem__(self, key, value):
        prev = key in self.all_arguments
        self.all_arguments[key] = value
        if prev:
            # value was default before, nothing more needs changing
            return


def with_param_dict(kwarg_name="_params"):
    def decorator(func):
        all_parameters: Mapping[str, Parameter] = signature(func).parameters
        dest_param = all_parameters.get(kwarg_name)
        if not dest_param or dest_param.kind != Parameter.KEYWORD_ONLY:
            raise NameError(
                "function must contain keyword-only parameter named " + kwarg_name
            )

        pos_names = []
        for n, p in all_parameters.items():
            if p.kind == Parameter.VAR_POSITIONAL:
                raise TypeError(
                    f"with_param_dict can't a variadic argument parameter ({p})"
                )
            if p.kind not in (
                Parameter.POSITIONAL_ONLY,
                Parameter.POSITIONAL_OR_KEYWORD,
            ):
                break
            pos_names.append(n)

        @wraps(func)
        def wrapper(*args, **kwargs):
            if kwarg_name in kwargs:
                raise TypeError(f"{kwarg_name} cannot be specified outside the wrapper")

            params = dict(zip(pos_names, args))
            params.update(kwargs)
            for k, p in all_parameters.items():
                if k == kwarg_name:
                    continue
                params.setdefault(k, p.default)

            kwargs[kwarg_name] = params

            return func(*args, **kwargs)

        return wrapper

    return decorator
