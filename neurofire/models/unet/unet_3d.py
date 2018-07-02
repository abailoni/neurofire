import torch.nn as nn
from inferno.extensions.layers import ConvELU3D
from torch import nn as nn

from .base import UNetSkeleton, Xcoder, XcoderResidual
from inferno.extensions.layers.convolutional import ConvELU3D, Conv3D, BNReLUConv3D
from inferno.extensions.layers.sampling import AnisotropicPool, AnisotropicUpsample


class Encoder(Xcoder):
    def __init__(self, in_channels, out_channels, kernel_size, scale_factor=2, conv_type=ConvELU3D):
        assert isinstance(scale_factor, (int, list, tuple))
        if isinstance(scale_factor, (list, tuple)):
            assert len(scale_factor) == 3
            # we need to make sure that the scale factor conforms with the single value
            # that AnisotropicPool expects
            assert scale_factor[0] == 1
            assert scale_factor[1] == scale_factor[2]
            sampler = AnisotropicPool(downscale_factor=scale_factor[1])
        else:
            sampler = nn.MaxPool3d(kernel_size=1 + scale_factor,
                                   stride=scale_factor,
                                   padding=1)
        super(Encoder, self).__init__(in_channels, out_channels, kernel_size,
                                      conv_type=conv_type,
                                      pre_output=sampler)


class Decoder(Xcoder):
    def __init__(self, in_channels, out_channels, kernel_size, scale_factor=2, conv_type=ConvELU3D):
        assert isinstance(scale_factor, (int, list, tuple))
        if isinstance(scale_factor, (list, tuple)):
            assert len(scale_factor) == 3
            # we need to make sure that the scale factor conforms with the single value
            # that AnisotropicPool expects
            assert scale_factor[0] == 1
            assert scale_factor[1] == scale_factor[2]
            sampler = AnisotropicUpsample(scale_factor=scale_factor[1])
        else:
            sampler = nn.Upsample(scale_factor=scale_factor)
        super(Decoder, self).__init__(in_channels, out_channels, kernel_size,
                                      conv_type=conv_type,
                                      pre_output=sampler)


class Base(Xcoder):
    def __init__(self, in_channels, out_channels, kernel_size, conv_type=ConvELU3D):
        super(Base, self).__init__(in_channels, out_channels, kernel_size,
                                   conv_type=conv_type,
                                   pre_output=None)





class EncoderResidual(XcoderResidual):
    def __init__(self, in_channels, out_channels, kernel_size, scale_factor=2, conv_type=ConvELU3D):
        assert isinstance(scale_factor, (int, list, tuple))
        if isinstance(scale_factor, (list, tuple)):
            assert len(scale_factor) == 3
            # we need to make sure that the scale factor conforms with the single value
            # that AnisotropicPool expects
            assert scale_factor[0] == 1
            assert scale_factor[1] == scale_factor[2]
            sampler = AnisotropicPool(downscale_factor=scale_factor[1])
        else:
            sampler = nn.MaxPool3d(kernel_size=1 + scale_factor,
                                   stride=scale_factor,
                                   padding=1)
        super(EncoderResidual, self).__init__(in_channels, out_channels, kernel_size,
                                              conv_type=conv_type,
                                              pre_output=sampler)


class DecoderResidual(XcoderResidual):
    def __init__(self, in_channels, out_channels, kernel_size, scale_factor=2, conv_type=ConvELU3D):
        assert isinstance(scale_factor, (int, list, tuple))
        if isinstance(scale_factor, (list, tuple)):
            assert len(scale_factor) == 3
            # we need to make sure that the scale factor conforms with the single value
            # that AnisotropicPool expects
            assert scale_factor[0] == 1
            assert scale_factor[1] == scale_factor[2]
            sampler = AnisotropicUpsample(scale_factor=scale_factor[1])
        else:
            sampler = nn.Upsample(scale_factor=scale_factor)
        super(DecoderResidual, self).__init__(in_channels, out_channels, kernel_size,
                                              conv_type=conv_type,
                                              pre_output=sampler)



class BaseResidual(XcoderResidual):
    def __init__(self, in_channels, out_channels, kernel_size, conv_type=ConvELU3D):
        super(BaseResidual, self).__init__(in_channels, out_channels, kernel_size,
                                           conv_type=conv_type,
                                           pre_output=None)


class Output(Conv3D):
    def __init__(self, in_channels, out_channels, kernel_size):
        super(Output, self).__init__(in_channels, out_channels, kernel_size)


CONV_TYPES = {'vanilla': ConvELU3D,
              'conv_bn': BNReLUConv3D}


class UNet3D(UNetSkeleton):
    """
    3D U-Net architecture.
    """
    def __init__(self,
                 in_channels,
                 out_channels,
                 initial_num_fmaps,
                 fmap_growth,
                 scale_factor=2,
                 final_activation='auto',
                 conv_type_key='vanilla',
                 add_residual_connections=False):
        """
        Parameter:
        ----------
        in_channels (int): number of input channels
        out_channels (int): number of output channels
        initial_num_fmaps (int): number of feature maps of the first layer
        fmap_growth (int): growth factor of the feature maps; the number of feature maps
        in layer k is given by initial_num_fmaps * fmap_growth**k
        final_activation:  final activation used
        scale_factor (int or list / tuple): upscale / downscale factor (default: 2)
        final_activation:  final activation used (default: 'auto')
        conv_type_key: convolutin type
        """

        # validate conv-type
        assert conv_type_key in CONV_TYPES, conv_type_key
        conv_type = CONV_TYPES[conv_type_key]

        # validate scale factor
        assert isinstance(scale_factor, (int, list, tuple))
        self.scale_factor = [scale_factor] * 3 if isinstance(scale_factor, int) else scale_factor
        assert len(self.scale_factor) == 3
        # NOTE individual scale factors can have multiple entries for anisotropic sampling
        assert all(isinstance(sfactor, (int, list, tuple))
                   for sfactor in self.scale_factor)

        # Set attributes
        self.in_channels = in_channels
        self.out_channels = out_channels

        conv_type = CONV_TYPES[conv_type_key]
        decoder_type = DecoderResidual if add_residual_connections else Decoder
        encoder_type = EncoderResidual if add_residual_connections else Encoder
        base_type = BaseResidual if add_residual_connections else Base

        # Build encoders with proper number of feature maps
        f0e = initial_num_fmaps
        f1e = initial_num_fmaps * fmap_growth
        f2e = initial_num_fmaps * fmap_growth**2
        encoders = [
            encoder_type(in_channels, f0e, 3, self.scale_factor[0], conv_type=conv_type),
            encoder_type(f0e, f1e, 3, self.scale_factor[1], conv_type=conv_type),
            encoder_type(f1e, f2e, 3, self.scale_factor[2], conv_type=conv_type)
        ]

        # Build base
        # number of base output feature maps
        f0b = initial_num_fmaps * fmap_growth**3
        base = base_type(f2e, f0b, 3, conv_type=conv_type)

        # Build decoders (same number of feature maps as MALA)
        f2d = initial_num_fmaps * fmap_growth**2
        f1d = initial_num_fmaps * fmap_growth
        f0d = initial_num_fmaps
        decoders = [
            decoder_type(f0b + f2e, f2d, 3, self.scale_factor[2], conv_type=conv_type),
            decoder_type(f2d + f1e, f1d, 3, self.scale_factor[1], conv_type=conv_type),
            decoder_type(f1d + f0e, f0d, 3, self.scale_factor[0], conv_type=conv_type)
        ]

        # Build output
        output = Output(f0d, out_channels, 3)
        # Parse final activation
        if final_activation == 'auto':
            final_activation = nn.Sigmoid() if out_channels == 1 else nn.Softmax2d()

        # Build the architecture
        super(UNet3D, self).__init__(encoders=encoders,
                                     base=base,
                                     decoders=decoders,
                                     output=output,
                                     final_activation=final_activation)
