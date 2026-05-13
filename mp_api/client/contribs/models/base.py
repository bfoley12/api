from __future__ import annotations

from mp_api.client.contribs.models.mpc import MPCLike
from mp_api.client.core.schemas import _DictLikeAccess


# TODO: Find new name: conflicts with BaseContrib
# This might end up being unnecessary
class ContribsBase(_DictLikeAccess, MPCLike):
    pass
