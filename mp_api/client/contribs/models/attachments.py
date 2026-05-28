from __future__ import annotations

from mp_api.client.contribs.models.base import ContributionsSupplemental


class Attachment(ContributionsSupplemental):
    mime: str
    # content: int
