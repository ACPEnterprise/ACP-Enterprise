"""Twelve Hats-owned speech model governance and fail-closed engine boundary."""

from .engine import TwelveHatsSpeechEngine
from .genesis import admit_genesis_dataset_for_training

__all__ = ["TwelveHatsSpeechEngine", "admit_genesis_dataset_for_training"]
