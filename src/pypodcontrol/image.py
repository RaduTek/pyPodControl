"""
Conversion between iPod image data and Pillow images

Used for artwork (RetTrackArtworkData, RetArtworkData) and display images
(SetDisplayImage) of the Extended Interface lingo. Pillow is optional, install
it with `pip install pyPodControl[image]`.
"""

from enum import IntEnum
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from PIL.Image import Image


class PixelFormat(IntEnum):
    """Display pixel formats of images and artwork"""

    MONO_2BPP = 0x01
    """Monochrome, 2 bits per pixel, 0 is off (white) and 3 is black"""
    RGB565_LE = 0x02
    """RGB 565 color, little-endian, 16 bits per pixel"""
    RGB565_BE = 0x03
    """RGB 565 color, big-endian, 16 bits per pixel"""


MONO_LEVELS = (255, 170, 85, 0)
"""Grey value of each 2 bpp monochrome level"""


def _pil():
    try:
        from PIL import Image
    except ImportError:
        raise ImportError(
            "Image conversion needs Pillow, install it with: pip install pyPodControl[image]"
        ) from None

    return Image


def bits_per_pixel(pixel_format: int) -> int:
    """Bits per pixel of a pixel format"""

    return 2 if pixel_format == PixelFormat.MONO_2BPP else 16


def row_size(pixel_format: int, width: int) -> int:
    """Row size (stride) in bytes of an image, rows are padded to 32 bits"""

    row_bits = width * bits_per_pixel(pixel_format)
    return (row_bits + 31) // 32 * 4


def _swap_pairs(data: bytes) -> bytes:
    swapped = bytearray(len(data) - len(data) % 2)
    swapped[0::2] = data[1 : len(swapped) : 2]
    swapped[1::2] = data[0 : len(swapped) : 2]
    return bytes(swapped)


def decode_image(
    pixel_format: int, width: int, height: int, stride: int, data: bytes
) -> "Image":
    """
    Decode iPod image data into a Pillow image

    Returns an "RGB" image for the color formats and an "L" (greyscale) image
    for monochrome. Row padding is skipped.
    """

    Image = _pil()

    needed = stride * height
    if len(data) < needed:
        data = data + bytes(needed - len(data))

    if pixel_format == PixelFormat.MONO_2BPP:
        # L;2 unpacks levels 0-3 to 0, 85, 170, 255, but level 3 is black
        image = Image.frombuffer("L", (width, height), data, "raw", "L;2", stride, 1)
        return image.point(lambda v: 255 - v)

    if pixel_format == PixelFormat.RGB565_BE:
        data = _swap_pairs(data[:needed])
    elif pixel_format != PixelFormat.RGB565_LE:
        raise ValueError(f"Unsupported pixel format 0x{pixel_format:02X}")

    return Image.frombuffer("RGB", (width, height), data, "raw", "BGR;16", stride, 1)


def encode_image(image: "Image", pixel_format: int) -> tuple[int, bytes]:
    """
    Encode a Pillow image into iPod image data

    Returns (row size in bytes, pixel data), rows are zero padded to 32 bits.
    """

    width, height = image.size
    stride = row_size(pixel_format, width)
    out = bytearray(stride * height)

    if pixel_format == PixelFormat.MONO_2BPP:
        pixels = image.convert("L").tobytes()

        for y in range(height):
            row = pixels[y * width : (y + 1) * width]
            base = y * stride
            for x, value in enumerate(row):
                # Nearest of the 4 levels, white is off and black is level 3
                level = (255 - value + 42) // 85
                out[base + x // 4] |= level << (6 - 2 * (x % 4))

        return stride, bytes(out)

    if pixel_format not in (PixelFormat.RGB565_LE, PixelFormat.RGB565_BE):
        raise ValueError(f"Unsupported pixel format 0x{pixel_format:02X}")

    pixels = image.convert("RGB").tobytes()
    big_endian = pixel_format == PixelFormat.RGB565_BE

    for y in range(height):
        base = y * stride
        for x in range(width):
            i = (y * width + x) * 3
            r, g, b = pixels[i], pixels[i + 1], pixels[i + 2]
            value = (r >> 3) << 11 | (g >> 2) << 5 | b >> 3
            out[base + 2 * x : base + 2 * x + 2] = value.to_bytes(
                2, "big" if big_endian else "little"
            )

    return stride, bytes(out)
