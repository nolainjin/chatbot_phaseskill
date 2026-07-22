from __future__ import annotations


class RuntimeProviderError(RuntimeError):
    pass


class RuntimeProviderUnavailable(RuntimeProviderError):
    pass


class RuntimeProviderTimeout(RuntimeProviderError):
    pass


class RuntimeLocalOnlyViolation(RuntimeProviderError):
    pass


class RuntimeAudioError(ValueError):
    pass
