import pytest

from pypodcontrol.image import PixelFormat, decode_image, encode_image, row_size
from pypodcontrol.lingo import Artwork

Image = pytest.importorskip("PIL.Image")


def test_row_size_padded_to_32_bits():
    assert row_size(PixelFormat.RGB565_LE, 3) == 8
    assert row_size(PixelFormat.MONO_2BPP, 5) == 4
    assert row_size(PixelFormat.MONO_2BPP, 16) == 4


def test_decode_rgb565_le_with_padding():
    # Red, green in row 0, blue, black in row 1, 2 padding bytes per row
    data = bytes.fromhex("00 f8 e0 07 aa bb  1f 00 00 00 cc dd")
    image = decode_image(PixelFormat.RGB565_LE, 2, 2, 6, data)

    assert image.mode == "RGB"
    assert [image.getpixel((x, y)) for y in range(2) for x in range(2)] == [
        (255, 0, 0),
        (0, 255, 0),
        (0, 0, 255),
        (0, 0, 0),
    ]


def test_decode_rgb565_be():
    image = decode_image(PixelFormat.RGB565_BE, 1, 1, 4, bytes.fromhex("f8 00 00 00"))
    assert image.getpixel((0, 0)) == (255, 0, 0)


def test_decode_mono():
    # Levels 0 (off) to 3 (black)
    image = decode_image(PixelFormat.MONO_2BPP, 4, 1, 4, bytes([0b00011011, 0, 0, 0]))

    assert image.mode == "L"
    assert [image.getpixel((x, 0)) for x in range(4)] == [255, 170, 85, 0]


@pytest.mark.parametrize("pixel_format", list(PixelFormat))
def test_round_trip(pixel_format):
    colors = [(255, 0, 0), (0, 255, 0), (0, 0, 255), (255, 255, 255), (0, 0, 0)]
    if pixel_format == PixelFormat.MONO_2BPP:
        colors = [(v, v, v) for v in (255, 170, 85, 0, 255)]

    image = Image.new("RGB", (5, 2))
    for x, color in enumerate(colors):
        image.putpixel((x, 0), color)
        image.putpixel((x, 1), color)

    stride, data = encode_image(image, pixel_format)
    assert stride == row_size(pixel_format, 5)
    assert len(data) == stride * 2

    decoded = decode_image(pixel_format, 5, 2, stride, data).convert("RGB")
    assert [decoded.getpixel((x, 1)) for x in range(5)] == colors


def test_artwork_to_image_crop_inset():
    stride, data = encode_image(Image.new("RGB", (4, 4), (255, 0, 0)), PixelFormat.RGB565_LE)
    artwork = Artwork(PixelFormat.RGB565_LE, 4, 4, (1, 1, 2, 2), stride, data)

    assert artwork.to_image().size == (4, 4)
    assert artwork.to_image(crop_inset=True).size == (2, 2)
