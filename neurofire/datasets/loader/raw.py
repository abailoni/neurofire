from math import ceil, floor
import inferno.io.volumetric as io
from inferno.io.transform import Compose
from inferno.io.transform.volume import AdditiveNoise
from inferno.io.transform.generic import Cast, Normalize
from inferno.io.core.base import SyncableDataset
from inferno.io.core.base import IndexSpec

try:
    import z5py
    WITH_Z5PY = True
except ImportError:
    WITH_Z5PY = False


def read_param(param, name, type_):
    if param is None:
        return None
    if isinstance(param, dict):
        assert name is not None
        assert name in param
        return param[name]
    elif isinstance(param, type_):
        return param
    else:
        raise AttributeError("No such param %s" % name)


class RawVolume(io.HDF5VolumeLoader):
    def __init__(self, path, path_in_file=None,
                 data_slice=None, name=None, dtype='float32',
                 mean=None, std=None, sigma=None, **slicing_config):
        # Init super
        super(RawVolume, self).__init__(path=path, path_in_h5_dataset=path_in_file,
                                        data_slice=data_slice, name=name, **slicing_config)
        # Record attributes
        assert isinstance(dtype, str)
        self.dtype = dtype
        # Make transforms
        self.transforms = self.get_transforms(mean, std, sigma)

    def get_transforms(self, mean, std, sigma):
        if sigma is None:
            transforms = Compose(Cast(self.dtype),
                                 Normalize(mean=mean, std=std))
        else:
            transforms = Compose(Cast(self.dtype),
                                 Normalize(mean=mean, std=std),
                                 AdditiveNoise(sigma=sigma))
        return transforms


class MultiscaleRawVolume(SyncableDataset):
    def __init__(self, path, paths_in_file,
                 name=None, dtype='float32', mean=None, std=None,
                 scale_factors=None, downscale_policy=None, **slicing_config):
        assert WITH_Z5PY
        assert isinstance(paths_in_file, (list, tuple)), type(paths_in_file)
        self.n_scales = len(paths_in_file)
        assert self.n_scales >= 2

        # the downscale policy determines the shape of the
        # volumes returned at lower scales.
        # e.g. if downscale policy == 1, the shape will
        # be the same as downsampling at the original scale
        # if 0.5 it will be half the shape etc.
        # if None, the downscaled volume will not be changed.
        # downscale_policy can also be a tuple, then the
        # second factor will be the required divisor for the shape
        self.downscale_policy = downscale_policy

        # get the downscaling factors
        if scale_factors is None:
            self.scale_factors = [2**i for i in range(self.n_scales)]
        else:
            assert len(scale_factors) == self.n_scales
            self.scale_factors = scale_factors

        self.name = name
        self.dtype = read_param(dtype, name, str)
        self.path = read_param(path, name, str)
        self.paths_in_file = read_param(paths_in_file, name, list)
        # we assume that the slicing config is w.r.t. the volume at highest resolution
        # and that this is the volume at index 0 of `paths_in_dataset`
        # TODO add option to switch between n5, h5 etc.
        self.dataset0 = io.LazyN5VolumeLoader(self.path, self.paths_in_file[0],
                                              name=name, **slicing_config)
        # load the volumes at lower scales
        self.datasets = [z5py.File(self.path)[pid] for pid in self.paths_in_file[1:]]
        # we need offset for proper coordinate transformations.
        # we assume that these are stored as attribute `offset` in the
        # datasets
        self.offsets = [z5py.File(self.path)[pid].attrs['offset']
                        for pid in self.paths_in_file[1:]]
        self.transforms = self.get_transforms(mean, std)
        super().__init__(self.dataset0.base_sequence)

    def get_transforms(self, mean, std):
        transforms = Compose(Cast(self.dtype),
                             Normalize(mean=mean, std=std))
        return transforms

    # get the data at lower scale
    def _get_scale(self, slices, scale):
        scale_factor = self.scale_factors[scale]
        # need to substract 1 when indexing, because we store
        # the dataset for 0th scale differently and don't have offsets
        ds = self.datasets[scale - 1]
        offset = self.offsets[scale - 1]

        # downscale the bounding box defined by slices
        if isinstance(scale_factor, int):
            slices_ = tuple(slice(sl.start // scale_factor + off,
                                  sl.stop // scale_factor + off)
                            for sl, off in zip(slices, offset))
        elif isinstance(scale_factor, (tuple, list)):
            slices_ = tuple(slice(sl.start // sf + off, sl.stop // sf + off)
                            for sl, sf, off in zip(slices, scale_factor, offset))
        else:
            raise NotImplementedError

        # enlarge the bounding box according to our downscale policy
        if self.downscale_policy is not None:
            original_shape = tuple(sl.stop - sl.start for sl in slices)
            scale_shape = tuple(sl.stop - sl.start for sl in slices_)
            if isinstance(self.downscale_policy, int):
                shape_factor = self.downscale_policy
                mandatory_divisor = None
            elif isinstance(self.downscale_policy, tuple):
                shape_factor, mandatory_divisor = self.downscale_policy
            else:
                raise NotImplementedError
            target_shape = tuple(min(int(sh * shape_factor), dsh)
                                 for sh, dsh in zip(original_shape, scale_shape))

            # change the target shape to fit the mandatory divisor if given
            if mandatory_divisor is not None:
                mandatory_divisor = mandatory_divisor if isinstance(mandatory_divisor, (tuple, list)) else\
                    (mandatory_divisor,) * len(target_shape)
                target_shape = tuple(ts if ts % md == 0 else ts + (md - ts % md)
                                     for ts, md in zip(target_shape, mandatory_divisor))

            shape_diff = tuple((os - ts) / 2
                               for os, ts in zip(original_shape, target_shape))
            # FIXME this will not yield the correct size odd target shapes
            slices_ = tuple(slice(sl.start - floor(sd),
                                  sl.stop + ceil(sd)) for sl, sd in zip(slices_,
                                                                        shape_diff))

        return ds[slices_]

    def __getitem__(self, index):
        # first, we load the chunk at original scale
        index = int(index)
        v0 = self.dataset0[index]

        # next, we get the slices at original scale and transform
        # them to the lower scales
        slices = tuple(self.dataset0.base_sequence[index])
        # we need to make sure that the len of slices corresponds to
        # our number of dimensions TODO don't hard-code to 3
        assert len(slices) == 3, str(len(slices))
        volumes = [v0]
        for scale in range(1, self.n_scales):
            volumes.append(self._get_scale(slices, scale))

        if self.transforms is None:
            transformed = volumes
        else:
            transformed = [self.transforms(vol) for vol in volumes]

        return transformed
