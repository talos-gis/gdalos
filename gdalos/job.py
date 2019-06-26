from __future__ import annotations

from abc import ABC, abstractmethod
from itertools import chain
from os import PathLike
from os.path import getsize
from typing import Optional, Any, Dict, Union, Set, Mapping, Sequence, Iterable, Tuple, Callable

import logging
from enum import Enum
from pathlib import Path

import gdal

from gdalos import GeoRectangle
from gdalos.__util__ import has_implementors, with_param_dict, AutoPath, DestinationCRS
from gdalos.gdal_helper import OpenDS, get_band_types, get_image_structure_metadata, apply_gdal_config, ds_name, \
    get_ovr_count, get_raster_band

DsLike = Union[gdal.Dataset, PathLike, str]


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


OVERVIEW_COUNT_DEFAULT = 10


@has_implementors
class OvrType(ABC):
    @abstractmethod
    def __call__(self, job):
        pass


@OvrType.instance('single')
@OvrType.factory()
def single(depth=OVERVIEW_COUNT_DEFAULT, resampling_alg: str = None, expand_rgb: bool = False, compression: str = None):
    def _(job):
        job.spawns_post.add(
            OvrMakeSingle(job.output_path, owner=job, overview_count=depth, resampling_alg=resampling_alg,
                          expand_rgb=expand_rgb, compression=compression))

    return _


@OvrType.instance('multi')
@OvrType.factory()
def multi(depth=OVERVIEW_COUNT_DEFAULT, resampling_alg: str = None, expand_rgb: bool = False, compression: str = None):
    def _(job):
        job.spawns_post.add(
            OvrMakeMulti(job.output_path, owner=job, overview_count=depth, resampling_alg=resampling_alg,
                         expand_rgb=expand_rgb, compression=compression))

    return _


@OvrType.instance('embed')
@OvrType.factory()
def embed(depth=OVERVIEW_COUNT_DEFAULT, resampling_alg: str = None, expand_rgb: bool = False, compression: str = None):
    def _(job):
        job.spawns_post.add(
            OvrEmbedJob(job.output_path, owner=job, overview_count=depth, resampling_alg=resampling_alg,
                        expand_rgb=expand_rgb, compression=compression))

    return _


MAX_OVR_SIZE = 1 * (1024 ** 3)  # 1 GB


@OvrType.instance('external')
@OvrType.factory()
def external(depth=OVERVIEW_COUNT_DEFAULT, resampling_alg: str = None, expand_rgb: bool = False,
             compression: str = None):
    def _(job):
        job.spawns_post.add(
            OvrMakeAuto(job.output_path, owner=job, overview_count=depth, resampling_alg=resampling_alg,
                        expand_rgb=expand_rgb, compression=compression))

    return _


@OvrType.instance('auto')
@OvrType.factory()
def auto(depth=OVERVIEW_COUNT_DEFAULT, *args, **kwargs):
    def _(job):
        ovr_count = get_ovr_count(job.src)
        if ovr_count >= depth:
            t = OvrType.MorphExisting
        else:
            t = OvrType.External
        ovr_type = t(depth=depth, *args, **kwargs)
        return ovr_type(job)

    return _


@OvrType.implementor()
def copy(job):
    job.prog_args['creationOptions'].append('COPY_SRC_OVERVIEWS=YES')


@OvrType.instance('morph_existing')
@OvrType.factory()
def morph_existing(depth=OVERVIEW_COUNT_DEFAULT):
    def _(job):
        raise NotImplementedError  # todo
        # as far as i can tell, this operation is not fully supported in original gdalos


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
    def __init__(self, src: DsLike, dst: Union[PathLike, type(...)] = ...,
                 *, owner: Optional[Job], **kwargs):
        super().__init__(dst, owner=owner, **kwargs)
        self.src = src

    def auto_path(self) -> PathLike:
        return AutoPath(self.src)

    def is_auto_dest(self):
        return self.dst is ...


n_y = ('NO', 'YES')
CRS_Coercable = Union[str, int, float]


class MorphJob(IOJob):
    @staticmethod
    def _default_callback(pips=20):
        pip_worth = 1 / pips
        next_target = pip_worth

        def ret(progress, *_):
            nonlocal next_target
            pips_to_add = 0
            while progress >= next_target:
                pips_to_add += 1
                next_target += pip_worth
            if pips_to_add:
                print('.' * pips_to_add, end='', flush=True)
            if progress >= 1:
                print('done!')

        return ret

    class Kind(Enum):
        translate = gdal.Translate
        wrap = gdal.Warp

    # these values will only be filled in after resolution
    kind: MorphJob.Kind
    proc_args: Dict[str, Any]
    config_options: Dict[str, Any]

    def _resolve(self, create_info=True, output_format='GTiff', output_auto_extension='tif',
                 tiled: Union[str, bool] = True, big_tiff='IF_SAFER',
                 creation_options: Union[Mapping[str, str], Iterable[str]] = None, config_options=None,
                 extent: GeoRectangle = None, destination_CRS: CRS_Coercable = None, source_ovr=-1,
                 out_resolution: Tuple[float, float] = None, ovr_type: OvrType = OvrType.auto(),
                 kind: RasterKind = None, progress_callback: Callable = ..., open_options = ()):
        ds: gdal.Dataset
        with OpenDS(self.src, *open_options) as ds:
            geo_transform = ds.GetGeoTransform()
            band_res = (geo_transform[1], geo_transform[5])
            sample_band = get_raster_band(ds)
            band_size = (sample_band.XSize, sample_band.YSize)

            ovr_type = OvrType.coerce(ovr_type)
            if kind:
                kind = RasterKind.coerce()
            else:
                kind = RasterKind.guess(ds)
            if progress_callback is ...:
                progress_callback = self._default_callback()

            if progress_callback:
                self.proc_args['callback'] = progress_callback

            self.proc_args['format'] = output_format

            self.kind = self.Kind.wrap if (source_ovr >= 0) or (destination_CRS is not None) else self.Kind.translate

            if config_options:
                self.config_options.update(config_options)

            if creation_options:
                if isinstance(creation_options, Mapping):
                    self.proc_args['creationOptions'].extend(
                        f'{k}={v}' for (k, v) in creation_options.items()
                    )
                else:
                    self.proc_args['creationOptions'].extend(creation_options)
            if destination_CRS:
                destination_CRS = DestinationCRS(destination_CRS)
                if destination_CRS.has_datum():
                    if destination_CRS.is_utm():
                        zone_extent = GeoRectangle.from_points(destination_CRS.zone_extent())
                        if not extent:
                            extent = zone_extent
                        else:
                            extent = zone_extent.crop(extent)
                    self.maybe_add_auto_suffix(str(destination_CRS))
                self.proc_args['dstSRS'] = destination_CRS.proj4

            if not isinstance(tiled, str):
                tiled = n_y[tiled]
            self.proc_args['creationOptions'].append(f'TILED={tiled}')

            self.proc_args['creationOptions'].append(f'BIGTIFF={big_tiff}')

            self.maybe_add_auto_suffix(output_auto_extension)
            if create_info:
                self.spawns_post.add(InfoJob(self.output_path, owner=self))

    def resolve(self):
        self.proc_args = {'creationOptions': []}
        self.config_options = {}
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


def _fill_compression(compression, config, ds):
    if compression is None:
        compression = get_image_structure_metadata(ds, 'COMPRESSION')

    if compression == 'YCbCr JPEG':
        config['COMPRESS_OVERVIEW'] = 'JPEG'
        config['PHOTOMETRIC_OVERVIEW'] = 'YCBCR'
        config['INTERLEAVE_OVERVIEW'] = 'PIXEL'
    else:
        config['COMPRESS_OVERVIEW'] = compression


class OvrEmbedJob(Job):
    proc_args: Dict[str, Any]
    config_options: Dict[str, Any]

    def __init__(self, ds: DsLike,
                 *, owner: Optional[Job], **kwargs):
        super().__init__(owner=owner, **kwargs)
        self.ds = ds

    def resolve(self):
        self.proc_args = {}
        self.config_options = {}
        super().resolve()

    def _resolve(self, overview_count: int = OVERVIEW_COUNT_DEFAULT, resampling_alg: str = None,
                 kind: RasterKind = None, expand_rgb: bool = False, compression: str = None):
        self.proc_args['overviewlist'] = [2 ** (i + 1) for i in range(overview_count)]
        if not resampling_alg:
            if not kind:
                kind = RasterKind.guess(self.ds)
            resampling_alg = kind.resampling_alg(expand_rgb)
        self.proc_args['resampling'] = resampling_alg

        _fill_compression(compression, self.config_options, self.ds)

    def run_self(self, on_exist: OnExists):
        with apply_gdal_config(self.config_options), \
             OpenDS(self.ds, gdal.GA_Update, wild_options=True) as ds:
            ds.BuildOverviews(**self.proc_args)


class OvrMakeSingle(Job):
    proc_args: Dict[str, Any]
    config_options: Dict[str, Any]

    def __init__(self, ds: DsLike,
                 *, owner: Optional[Job], **kwargs):
        super().__init__(owner=owner, **kwargs)
        self.ds = ds

    def resolve(self):
        self.proc_args = {}
        self.config_options = {}
        super().resolve()

    def _resolve(self, overview_count: int = OVERVIEW_COUNT_DEFAULT, resampling_alg: str = None,
                 kind: RasterKind = None, expand_rgb: bool = False, compression: str = None):
        self.proc_args['overviewlist'] = [2 ** (i + 1) for i in range(overview_count)]
        if not resampling_alg:
            if not kind:
                kind = RasterKind.guess(self.ds)
            resampling_alg = kind.resampling_alg(expand_rgb)
        self.proc_args['resampling'] = resampling_alg

        _fill_compression(compression, self.config_options, self.ds)

    def run_self(self, on_exist: OnExists):
        with apply_gdal_config(self.config_options), \
             OpenDS(self.ds, gdal.GA_ReadOnly, reopen=True) as ds:
            ds.BuildOverviews(**self.proc_args)


class OvrMakeMulti(Job):
    proc_args: Dict[str, Any]
    config_options: Dict[str, Any]

    def __init__(self, ds: DsLike,
                 *, owner: Optional[Job], **kwargs):
        super().__init__(owner=owner, **kwargs)
        self.ds = ds

    def resolve(self):
        self.proc_args = {}
        self.config_options = {}
        super().resolve()

    @with_param_dict()
    def _resolve(self, overview_count: int = OVERVIEW_COUNT_DEFAULT, resampling_alg: str = None,
                 kind: RasterKind = None, expand_rgb: bool = False, compression: str = None, *, _arguments):
        self.proc_args['overviewlist'] = [2]
        if not resampling_alg:
            if not kind:
                kind = RasterKind.guess(self.ds)
            resampling_alg = kind.resampling_alg(expand_rgb)
        self.proc_args['resampling'] = resampling_alg

        _fill_compression(compression, self.config_options, self.ds)

        if overview_count > 1:
            args = {**_arguments, 'overview_count': overview_count - 1}
            dst_path = ds_name(self.ds) + '.ovr'
            self.spawns_post.add(OvrMakeMulti(dst_path, owner=self, **args))

    def run_self(self, on_exist: OnExists):
        with apply_gdal_config(self.config_options), \
             OpenDS(self.ds, gdal.GA_ReadOnly, reopen=True) as ds:
            ds.BuildOverviews(**self.proc_args)


class OvrMakeAuto(Job):
    def __init__(self, ds: DsLike,
                 *, owner: Optional[Job], **kwargs):
        super().__init__(owner=owner, **kwargs)
        self.ds = ds

    def _resolve(self, **kwargs):
        file_size = getsize(ds_name(self.ds))  # bytes
        if file_size > MAX_OVR_SIZE:
            spawn_cls = OvrMakeMulti
        else:
            spawn_cls = OvrMakeSingle

        self.spawns_post.add(
            spawn_cls(self.ds, owner=self, **kwargs)
        )

    def run_self(self, on_exist: OnExists):
        pass
