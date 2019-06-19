from abc import ABC, abstractmethod
from itertools import chain
import logging
from os import PathLike

from gdalos.__util__ import has_implementors
from gdalos.gdal_helper import get_band_types


@has_implementors
class OnSpawnFail(ABC):
    @abstractmethod
    def __call__(self, owner, spawn, error: Exception):
        pass


@OnSpawnFail.implementor
def raise_(owner, spawn, error: Exception):
    raise error


@OnSpawnFail.implementor
def warn(owner, spawn, error: Exception):
    message = f'spawn {spawn} failed with exception:\n{type(error).__name__}: {str(error)}'
    logging.error(message)


@OnSpawnFail.implementor
def ask(owner, spawn, error: Exception):
    print(f'spawn {spawn} failed with exception:\n{type(error).__name__}: {str(error)}')
    answer = input('continue? (y/N)? ')
    if answer.lower() != 'y':
        OnSpawnFail.raise_(owner, spawn, error)
    else:
        OnSpawnFail.warn(owner, spawn, error)


@has_implementors
class OnExists(ABC):
    @abstractmethod
    def __call__(self, job, file: PathLike) -> bool:
        pass


@OnExists.implementor
def raise_(job, file):
    raise FileExistsError(file)


@OnExists.implementor
def skip(job, file):
    logging.warning(f'job: {job} skips file {file}')
    return False


@OnExists.implementor
def overwrite(job, file):
    logging.warning(f'job: {job} overwrites file {file}')
    return True


@OnExists.implementor
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
    def __call__(self, spawns, owner):
        pass


@SpawnOrder.instance('lightest_first', lambda job: job.weight or 0)
@SpawnOrder.instance('heaviest_first', lambda job: -job.weight or 0)
@SpawnOrder.factory()
def order(key, owner_place=0, reverse=False):
    def ret(spawns, owner):
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

    @classmethod
    def guess(cls, band_types):
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


@RasterKind.implementor()
def photo(expand_rgb=False):
    return 'cubic'


@RasterKind.implementor()
def pal(expand_rgb=False):
    return 'average' if expand_rgb else 'near'


@RasterKind.implementor()
def dtm(expand_rgb=False):
    return 'average'

@has_implementors
class OvrType(ABC):
    @abstractmethod
    def handle(self, job):
        pass

@OvrType.implementor()
def create_external_single(job):
    job.spawns_post.add()