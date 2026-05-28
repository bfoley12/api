from uuid import uuid4

import pytest

from mp_api.client.contribs.errors import APIError
from mp_api.client.contribs.models.contributions import Contribution

CONTRIB_IDS = ["5f8a3d9583a19cc44d02246b", "5f8a3d9783a19cc44d02247d"]

ALL_FIELDS = set(Contribution.model_fields.keys())


class TestGetContribution:
    @pytest.mark.parametrize("cid", CONTRIB_IDS)
    def test_get_contribution_returns_model(self, client, cid):
        """No fields → full ContribsProject model."""
        contrib = client.get_contribution(cid=cid)
        assert isinstance(contrib, Contribution)
        assert contrib.id == cid

    @pytest.mark.parametrize("cid", CONTRIB_IDS)
    @pytest.mark.parametrize(
        "fields",
        [["id"], ["id", "formula"]],
        ids=["one", "two"],
    )
    def test_get_contribution_returns_dict_with_fields(self, client, cid, fields):
        """Fields specified → dict containing only those fields."""
        contrib = client.get_contribution(cid=cid, fields=fields)
        assert isinstance(contrib, Contribution)
        assert contrib.model_fields_set == set(fields)
        assert contrib.id == cid

    @pytest.mark.parametrize("fields", [[], ["_all"]], ids=["empty_list", "all_token"])
    def test_get_contribution_returns_all_fields(self, client, fields: list[str]):
        contrib = client.get_contribution(cid="5f8a3d9583a19cc44d02246b", fields=fields)
        assert contrib.model_fields_set == ALL_FIELDS

    # Brendan TODO: Currently the API accepts arbitrary fields and silently ignores them. We should potentially be louder than that
    def test_get_contribution_ignores_wrong_fields(self, client):
        contrib = client.get_contribution(
            cid="5f8a3d9583a19cc44d02246b", fields=["this-field-is-nonexistant"]
        )
        assert contrib.model_fields_set == set()

    @pytest.mark.parametrize(
        "cid",
        ["wrong-id", "z" * 24, "z" * 12],
        ids=["too-short", "wrong-hex", "non-existent-12-bytes"],
    )
    def test_get_contribution_errors_on_improper_cid(self, client, cid):
        with pytest.raises(APIError) as exc_info:
            client.get_contribution(cid)
        assert cid in str(exc_info.value)
        assert exc_info.value.response.status_code == 400

    def test_get_contribution_errors_on_name(self, client):
        cid = "ffffffffffffffffffffffff"  # Does not exist
        with pytest.raises(APIError) as exc_info:
            client.get_contribution(cid)
        assert cid in str(exc_info.value)
        assert exc_info.value.response.status_code == 404

class TestQueryContribution:
    pass

class TestUpdateContribution:
    pass

class TestSubmitContribution:
    pass

class TestDeleteContributions:
    def test_delete_contributions(self, client):
