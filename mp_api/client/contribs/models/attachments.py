from __future__ import annotations

from mp_api.client.contribs.models.base import ContributionsSupplemental


class Attachments(ContributionsSupplemental):
    mime: str
    content: int
