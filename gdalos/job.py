from __future__ import annotations

from abc import ABC, abstractmethod
from itertools import chain
from os import PathLike, makedirs
from typing import Optional, Any, Dict, Union, Set, Iterable, List

import logging
from enum import Enum, auto
from pathlib import Path

import gdal

from gdalos.__util__ import has_implementors, implementor, make_implementor, with_param_dict
from gdalos.gdal_helper import OpenDS, get_band_types

DsLike = Union[gdal.Dataset, PathLike, str]


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


@has_implementors
class OnSpawnFail(ABC):
    @abstractmethod
    def __call__(self, owner: Optional[Job], spawn: Job, error: Exception):
        pass

    @implementor
    @staticmethod
    def raise_(owner: Optional[Job], spawn: Job, error: Exception):
        raise error

    @implementor
    @staticmethod
    def warn(owner: Optional[Job], spawn: Job, error: Exception):
        message = f'spawn {spawn} failed with exception:\n{type(error).__name__}: {str(error)}'
        logging.error(message)

    @implementor
    @staticmethod
    def ask(owner: Optional[Job], spawn: Job, error: Exception):
        print(f'spawn {spawn} failed with exception:\n{type(error).__name__}: {str(error)}')
        answer = input('continue? (y/N)? ')
        if answer.lower() != 'y':
            OnSpawnFail.raise_(owner, spawn, error)
        else:
            OnSpawnFail.warn(owner, spawn, error)


@has_implementors
class OnExists(ABC):
    @abstractmethod
    def __call__(self, job: Job, file: PathLike) -> bool:
        pass

    @implementor
    @staticmethod
    def raise_(job, file):
        raise FileExistsError(file)

    @implementor
    @staticmethod
    def skip(job, file):
        logging.warning(f'job: {job} skips file {file}')
        return False

    @implementor
    @staticmethod
    def overwrite(job, file):
        logging.warning(f'job: {job} overwrites file {file}')
        return True

    @implementor
    @staticmethod
    def ask(job, file):
        print(f'job: {job}, {file} already exists')
        answer = input('what to do? (s)kip/(o)verwrite/(R)aise')
        if not answer:
            answer = 'r'
        else:
            answer = answer[0].lower()

        if answer == 's':
            OnExists.skip(job, file)
        elif answer == 'o':
            OnExists.overwrite(job, file)
        else:
            OnExists.raise_(job, file)


@has_implementors
class SpawnOrder(ABC):
    @abstractmethod
    def __call__(self, spawns: Iterable[Job], owner: Optional[Job]) -> Iterable[Job]:
        pass

    @make_implementor('lightest_first', lambda job: job.weight or 0)
    @make_implementor('heaviest_first', lambda job: -job.weight or 0)
    @staticmethod
    def order(key, owner_place=0, reverse=False):
        def ret(spawns: Iterable[Job], owner: Optional[Job]):
            if owner and owner_place == -1:
                yield owner
            if owner and owner_place == 0:
                spawns = chain(
                    spawns,
                    [owner]
                )
            yield from sorted(spawns, key=key, reverse=reverse)
            if owner and owner_place == 1:
                yield owner

        return ret

@has_implementors
class RasterKind(ABC):
    @abstractmethod
    def resampling_alg(self, expand_rgb=False):
        pass

    @implementor
    @staticmethod
    def photo(self, expand_rgb = False):

    photo = auto()
    pal = auto()
    dtm = auto()

    @classmethod
    def guess(cls, band_types: Union[DsLike, List[gdal.Band]]):
        if not isinstance(band_types, list):
            band_types = get_band_types(band_types)
        if len(band_types) == 0:
            raise Exception('no bands in raster')

        if band_types[0] == 'Byte':
            if len(band_types) in (3, 4):
                return cls.photo
            elif len(band_types) == 1:
                return cls.pal
            else:
                raise Exception("invalid raster band count")
        elif len(band_types) == 1:
            return cls.dtm

        raise Exception('could not guess raster kind')

class Job:
    # these values will only be filled in after resolution
    spawns: Set[Job]
    spawns_pre: Set[Job]
    spawns_post: Set[Job]
    # a generic heuristic for how long the job will take/how big the output file is,
    #  a weight of None means the size is unknown
    weight: Optional[float]

    def __init__(self, *, owner: Optional[Job], **kwargs):
        self.owner = owner
        self.kwargs = kwargs

        self._resolved = False

    def is_resolved(self):
        return self._resolved

    @abstractmethod
    def _resolve(self):
        pass

    def resolve(self):
        self.spawns = set()
        self.spawns_pre = set()
        self.spawns_post = set()

        self._resolve(**self.kwargs)

        self._resolved = True


    def _run_spawn(self, spawn, run_args, on_fail):
        try:
            spawn.run(**run_args)
        except Exception as e:
            on_fail(self, spawn, on_fail)

    @with_param_dict()
    def run(self, on_fail: OnSpawnFail = 'raise_', on_exist: OnExists = 'skip',
            order: SpawnOrder = 'lightest_first',
            *, _arguments):
        if not self.is_resolved():
            raise Exception('job is run before being resolved')

        on_fail = OnSpawnFail[on_fail]
        order = SpawnOrder[order]
        on_exist = on_exist

        for job in order(self.spawns_pre, None):
            self._run_spawn(job, _arguments, on_fail)
        for job in order(self.spawns, self):
            if job is self:
                self.run_self(on_exist=on_exist)
            else:
                self._run_spawn(job, _arguments, on_fail)
        for job in order(self.spawns_post, None):
            self._run_spawn(job, _arguments, on_fail)

    @abstractmethod
    def run_self(self, on_exist: OnExists):
        pass


class OutputJob(Job):
    output_path: PathLike

    def __init__(self, dst: Union[PathLike, type(...)],
                 *, owner: Optional[Job], **kwargs):
        super().__init__(owner=owner, **kwargs)
        self.dst = dst

    @abstractmethod
    def auto_path(self) -> PathLike:
        pass

    def resolve(self):
        if self.dst is ...:
            self.output_path = self.auto_path()
        else:
            self.output_path = Path(self.dst)

        super().resolve()

    def is_auto_dest(self):
        return self.dst is ...

    def maybe_add_auto_suffix(self, *suf):
        if isinstance(self.output_path, AutoPath):
            self.output_path.add_suffix(*suf)


class IOJob(OutputJob, ABC):
    def __init__(self, src: DsLike, dst: Union[PathLike, type(...)],
                 *, owner: Optional[Job], **kwargs):
        super().__init__(dst, owner=owner, **kwargs)
        self.src = src

    def auto_path(self) -> PathLike:
        return AutoPath(self.src)

    def is_auto_dest(self):
        return self.dst is ...


class TransJob(IOJob):
    class Kind(Enum):
        translate = gdal.Translate
        wrap = gdal.Warp

    # these values will only be filled in after resolution
    kind: TransJob.Kind
    proc_args: Dict[str, Any]

    def _resolve(self):
        with OpenDS(self.src):
            pass

    def resolve(self):
        self.proc_args = {}
        super().resolve()

    def run_self(self, on_exist: OnExists):
        output = Path(self.output_path)
        if output.exists() and not on_exist(self, self.output_path):
            return
        ret_code = self.kind.value(**self.proc_args)
        if ret_code != 0:
            raise Exception(f'gdal returned non-0 code ({ret_code})')


class InfoJob(IOJob):
    # these values will only be filled in after resolution
    proc_args: Dict[str, Any]

    def _resolve(self):
        self.maybe_add_auto_suffix('.info')

    def resolve(self):
        self.proc_args = {}
        super().resolve()

    def run_self(self, on_exist: OnExists):
        output = Path(self.output_path)
        if output.exists() and not on_exist(self, self.output_path):
            return

        with OpenDS(self.src) as ds:
            info = gdal.Info(ds, **self.proc_args)
        Path(self.output_path).write_text(info)


class VrtJob(OutputJob):
    proc_args: Dict[str, Any]

    def __init__(self, *sources: Union[str, PathLike], dest, owner=None, **kwargs):
        super().__init__(dest, owner=owner, **kwargs)
        self.sources = sources

    def auto_path(self) -> PathLike:
        return AutoPath(self.sources[0])

    def _resolve(self, resampling_alg=None):
        self.maybe_add_auto_suffix('.vrt')
        self.proc_args['resampleAlg'] = resampling_alg

    def resolve(self):
        self.proc_args = {}
        super().resolve()

    def run_self(self, on_exist: OnExists):
        output = Path(self.output_path)
        if output.exists() and not on_exist(self, self.output_path):
            return

        output.parent.mkdir(parents=True, exist_ok=True)
        gdal.BuildVRT(output, self.sources, **self.proc_args)

"""
There are basically 2 brands of OVR jobs:
* creating a pyramid embedded in the raster file
* creating/appending a single .ovr file
"""

OVERVIEW_COUNT_DEFAULT = 10

class OvrEmbedJob(Job):
    proc_args: Dict[str, Any]

    def __init__(self, ds: DsLike,
                 *, owner: Optional[Job], **kwargs):
        super().__init__(owner=owner, **kwargs)
        self.ds = ds

    def resolve(self):
        self.proc_args = {}
        super().resolve()

    def _resolve(self, overview_count=OVERVIEW_COUNT_DEFAULT, resampling_alg = None):


