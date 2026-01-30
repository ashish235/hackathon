"""
Audio load/save using TorchCodec (recommended replacement for deprecated torchaudio.load/save).
Returns tensors in (channels, samples) format, float in [-1, 1].
"""

from pathlib import Path

from torchcodec.decoders import AudioDecoder
from torchcodec.encoders import AudioEncoder
import torch


def load_audio(
    path: str | Path,
    *,
    sample_rate: int | None = None,
    num_channels: int | None = None,
) -> tuple[torch.Tensor, int]:
    """
    Load audio file using TorchCodec AudioDecoder.

    Returns
    -------
    waveform : (C, T) tensor, float [-1, 1]
    sample_rate : int
    """
    path = Path(path)
    if not path.is_file():
        raise FileNotFoundError(f"Audio file not found: {path}")
    kwargs: dict = {}
    if sample_rate is not None:
        kwargs["sample_rate"] = sample_rate
    if num_channels is not None:
        kwargs["num_channels"] = num_channels
    decoder = AudioDecoder(str(path), **kwargs)
    samples = decoder.get_all_samples()
    return samples.data, samples.sample_rate


def save_audio(path: str | Path, waveform: torch.Tensor, sample_rate: int) -> None:
    """
    Save audio to file using TorchCodec AudioEncoder.

    Parameters
    ----------
    path : output file path (e.g. .wav, .mp3)
    waveform : (C, T) or (T,) tensor, float [-1, 1]
    sample_rate : int
    """
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    encoder = AudioEncoder(samples=waveform, sample_rate=sample_rate)
    encoder.to_file(path)
