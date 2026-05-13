from __future__ import annotations


# Brendan TODO: flesh out and allow classes to inherit from in order to convert to MPCDict
class MPCLike:
    def to_mpc(self) -> dict[str, str]:
        pass
