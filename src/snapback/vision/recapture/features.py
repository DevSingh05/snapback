"""Hand-made image signals that tell a fresh phone photo from a photo of a screen, a printout or
a digitally pasted code. Numpy only, so CI computes them without torch.

- Screens: a pixel grid and moire leave sharp peaks in the spectrum and periodic gradients.
- Prints: few colours, paper tone, softness.
- Pastes: a card with no sensor noise on an otherwise noisy photo, and a JPEG error level that
  does not match the rest of the picture.

DINOv2 features (learning-v2 L1a) can be appended later; v0 stands on these alone.
"""

import io

import numpy as np
from PIL import Image, ImageFilter, ImageOps

SIDE = 512

FEATURE_NAMES = (
    "spectrum_peak",  # log ratio of the strongest mid/high-frequency peak to the band median
    "grid_period",  # strongest autocorrelation of horizontal gradients at lags 2 to 6
    "laplacian_var",  # log variance of the Laplacian (sharpness)
    "noise_median",  # log median of per-block high-pass noise
    "noise_floor_ratio",  # 5th percentile block noise / median: a noise-free pasted patch
    "noise_spread",  # interquartile range of block noise / median
    "colour_count",  # distinct colours at 5 bits per channel, as a share of the maximum
    "saturation_mean",
    "saturation_std",
    "contrast",  # grey std / mean
    "glare",  # share of near-white pixels
    "ela_mean",  # mean error level after re-saving at quality 90
    "ela_block_ratio",  # 99th percentile block error level / median
    "warm_cast",  # mean red minus blue, scaled
)


def _prepare(image: Image.Image) -> Image.Image:
    image = ImageOps.exif_transpose(image).convert("RGB")
    scale = SIDE / max(image.size)
    if scale < 1:
        image = image.resize(
            (round(image.width * scale), round(image.height * scale)), Image.Resampling.BILINEAR
        )
    return image


def _blocks(a: np.ndarray, size: int = 16) -> np.ndarray:
    h, w = (a.shape[0] // size) * size, (a.shape[1] // size) * size
    a = a[:h, :w]
    return a.reshape(h // size, size, w // size, size).swapaxes(1, 2).reshape(-1, size * size)


def features(image: Image.Image) -> np.ndarray:
    image = _prepare(image)
    rgb = np.asarray(image, dtype=np.float32)
    grey = rgb @ np.array([0.299, 0.587, 0.114], dtype=np.float32)
    eps = 1e-6

    # Spectrum: peak to median in the mid/high band.
    spectrum = np.abs(np.fft.fftshift(np.fft.fft2(grey - grey.mean())))
    h, w = grey.shape
    yy, xx = np.mgrid[0:h, 0:w]
    radius = np.hypot((yy - h / 2) / (h / 2), (xx - w / 2) / (w / 2))
    band = spectrum[(radius > 0.15) & (radius < 0.95)]
    spectrum_peak = float(np.log((band.max() + eps) / (np.median(band) + eps)))

    # Periodic gradients (a resampled pixel grid).
    gx = np.abs(np.diff(grey, axis=1)).mean(axis=0)
    gx = gx - gx.mean()
    denom = float((gx * gx).sum()) + eps
    grid_period = max(float((gx[:-lag] * gx[lag:]).sum()) / denom for lag in range(2, 7))

    lap = grey[:-2, 1:-1] + grey[2:, 1:-1] + grey[1:-1, :-2] + grey[1:-1, 2:] - 4 * grey[1:-1, 1:-1]
    laplacian_var = float(np.log(lap.var() + 1.0))

    smooth = np.asarray(
        Image.fromarray(grey.astype(np.uint8)).filter(ImageFilter.BoxBlur(1)), dtype=np.float32
    )
    noise = _blocks(grey - smooth).std(axis=1)
    median = float(np.median(noise)) + eps
    noise_median = float(np.log(median))
    noise_floor_ratio = float(np.percentile(noise, 5)) / median
    q75, q25 = np.percentile(noise, [75, 25])
    noise_spread = float(q75 - q25) / median

    small = np.asarray(image.resize((128, 128)), dtype=np.uint8) >> 3
    codes = (
        (small[..., 0].astype(np.int32) << 10)
        | (small[..., 1].astype(np.int32) << 5)
        | small[..., 2]
    )
    colour_count = len(np.unique(codes)) / (128 * 128)

    maxc, minc = rgb.max(axis=2), rgb.min(axis=2)
    saturation = (maxc - minc) / (maxc + eps)
    contrast = float(grey.std() / (grey.mean() + eps))
    glare = float((grey > 245).mean())

    buffer = io.BytesIO()
    image.save(buffer, format="JPEG", quality=90)
    buffer.seek(0)
    resaved = np.asarray(Image.open(buffer).convert("RGB"), dtype=np.float32)
    ela = np.abs(rgb - resaved).mean(axis=2)
    ela_blocks = _blocks(ela).mean(axis=1)
    ela_mean = float(ela.mean())
    ela_block_ratio = float(np.percentile(ela_blocks, 99) / (np.median(ela_blocks) + eps))

    warm_cast = float((rgb[..., 0] - rgb[..., 2]).mean() / 255.0)

    return np.array(
        [
            spectrum_peak,
            grid_period,
            laplacian_var,
            noise_median,
            noise_floor_ratio,
            noise_spread,
            colour_count,
            float(saturation.mean()),
            float(saturation.std()),
            contrast,
            glare,
            ela_mean,
            ela_block_ratio,
            warm_cast,
        ],
        dtype=np.float64,
    )
