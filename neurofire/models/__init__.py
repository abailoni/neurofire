from .cantor.cantor import Cantor

from .unet.unet_2d import UNet2D
from .unet.unet_2p5d import UNet2p5D
from .unet.unet_3d import UNet3D

from .unet_multiscale.unet_2d_multiscale import UNet2DMultiscale
from .unet_multiscale.unet_3d_multiscale import UNet3DMultiscale

from .fcn.fcn import FCN
from .hed.hed import HED
from .hed.fusionhed import FusionHED

# TODO replace hed completely once it is not used for training any longer
from .hed.hed2 import HED as HED2
from .hed.dense_hed import DenseHED
from .hed.m2fcn import M2FCN


def get_model(name):
    assert name in globals(), "Model not found."
    return globals().get(name)
