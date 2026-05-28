from uuid import uuid4

import pytest

from mp_api.client.contribs.errors import APIError
from mp_api.client.contribs.models.project import ContribsProject

# pytestmark = pytest.mark.integration

NEW_PROJECT_NAME = ("pytest_project_" + str(uuid4())[0:10]).replace("-", "_")


@pytest.fixture
def new_project():
    return {
        "name": NEW_PROJECT_NAME,
        "title": "Pytest Project",
        "authors": "Fake Author",
        "owner": "google:random@gmail.com",
        "description": "Fake description",
        "references": [{"label": "RefLabel", "url": "https://fake.com"}],
        "long_title": "Long Fake Title",
        "is_public": True,
        "is_approved": True,
        "unique_identifiers": True,
        "license": "CCA4",
        "other": {},
    }


PROJECT_NAMES = ["carrier_transport", "riken_trip_magnets_database"]
ALL_FIELDS = set(ContribsProject.model_fields.keys())


class TestGetProject:
    @pytest.mark.parametrize("name", PROJECT_NAMES)
    def test_get_project_returns_model(self, client, name):
        """No fields → full ContribsProject model."""
        project = client.get_project(name=name)
        assert isinstance(project, ContribsProject)
        assert project.name == name

    @pytest.mark.parametrize("name", PROJECT_NAMES)
    @pytest.mark.parametrize(
        "fields",
        [["name"], ["name", "description"]],
        ids=["one", "two"],
    )
    def test_get_project_returns_dict_with_fields(self, client, name, fields):
        """Fields specified → dict containing only those fields."""
        project = client.get_project(name=name, fields=fields)
        assert isinstance(project, ContribsProject)
        assert project.model_fields_set == set(fields)
        assert project.name == name

    @pytest.mark.parametrize("fields", [[], ["_all"]], ids=["empty_list", "all_token"])
    def test_get_project_returns_all_fields(self, client, fields: list[str]):
        project = client.get_project(name="carrier_transport", fields=fields)
        assert project.model_fields_set == ALL_FIELDS

    # Brendan TODO: Currently the API accepts arbitrary fields and silently ignores them. We should potentially be louder than that
    def test_get_project_ignores_wrong_fields(self, client):
        project = client.get_project(
            name="carrier_transport", fields=["this-field-is-nonexistant"]
        )
        assert project.model_fields_set == set()

    def test_get_project_errors_on_name(self, client):
        project_name = "fake_name_123"
        with pytest.raises(APIError) as exc_info:
            client.get_project(project_name)
        assert project_name in str(exc_info.value)
        assert exc_info.value.response.status_code == 404


class TestQueryProject:
    def test_query_projects_empty(self, client):
        projects = client.query_projects()
        assert isinstance(projects, list)
        # We init the projects with 2 entries, but may have made more by repeating full suite testing
        assert len(projects) >= 2
        assert isinstance(projects[0], ContribsProject)
        assert projects[0].model_fields_set == ALL_FIELDS

    @pytest.mark.parametrize(
        "query",
        [
            {"name": "carrier_transport"},
            {"name__in": "carrier_transport"},
            {"name__in": ["carrier_transport", "riken_trip_magnets_database"]},
            {
                "name__in": ["carrier_transport", "riken_trip_magnets_database"],
                "project__endswith": "transport",
            },
        ],
        ids=["single_name", "str_name__in", "list_name__in", "composite_query"],
    )
    def test_query_projects_with_query(self, client, query):
        projects = client.query_projects(query=query)
        assert isinstance(projects, list)
        assert len(projects) >= 1

    def test_query_projects_with_fake_key(self, client):
        projects = client.query_projects(query={"fake__key": "some random"})
        assert isinstance(projects, list)
        assert len(projects) >= 2
        assert projects[0].model_fields_set == ALL_FIELDS

    def test_queryt_projects_with_composite_fake_key(self, client):
        projects = client.query_projects(
            query={
                "name__in": ["carrier_transport"],
                "fake__key": "transport",
            }
        )
        assert isinstance(projects, list)
        assert len(projects) >= 1
        assert projects[0].name == "carrier_transport"

    def test_query_projects_with_wrong_value(self, client):
        projects = client.query_projects(query={"name__in": "carrier_t"})
        assert isinstance(projects, list)
        assert len(projects) == 0

    @pytest.mark.parametrize(
        "query",
        [
            {"name": "fake_name_123"},
            {
                "name__in": ["carrier_tranport"],
                "name": "fake_name_123",
            },
        ],
        ids=["single", "composite"],
    )
    def test_query_projects_wrong_name_error(self, client, query):
        with pytest.raises(APIError) as exc_info:
            client.query_projects(query=query)
        assert "fake_name_123" in str(exc_info.value)
        assert exc_info.value.response.status_code == 404

    def test_query_projects_with_fields(self, client):
        projects = client.query_projects(
            query={"name": "carrier_transport"}, fields=["name"]
        )
        assert isinstance(projects, list)
        assert projects[0].model_fields_set == set(["name"])

    def test_query_projects_with_sort(self, client):
        projects_1 = client.query_projects(sort="+title")
        projects_2 = client.query_projects(sort="-title")
        # assert len(projects_1) == len(projects_2)
        assert projects_1[0].name == projects_2[-1].name

    # Term leads to a deprecated endpoint: /projects/search
    # def test_query_project_with_term(self, client, term):
    #     projects = client.query_projects(term="temperature")


class TestCreateProject:
    # Brendan TODO:
    # SMTP is required for getting a return from POST, needs fix server-side
    def test_create_project(self, client, new_project):
        try:
            _ = client.create_project(**new_project)
        except:
            pass
        assert True


class TestUpdateProject:
    # Note: had to use riken_trip_magnets_database because the API server cannot handle special characters (ie. delta) in the object to update.
    def test_update_project(self, client):
        new_title = str(uuid4())[:20]
        resp = client.update_project(
            {"title": new_title}, name="riken_trip_magnets_database"
        )
        assert resp.name == "riken_trip_magnets_database"
        assert resp.title == new_title

    def test_update_project_name_with_contribs(self, client):
        new_name = "riken_trip_magnets_database_2"
        resp = client.update_project(
            {"name": new_name}, name="riken_trip_magnets_database"
        )
        assert resp.name == "riken_trip_magnets_database"


class TestDeleteProject:
    # Brendan TODO:
    # Fails because of SMTP error - SMTP_USERNAME and SMTP_PASSWORD not set on dev instance of api
    # - need to decouple on server-side
    def test_delete_project(self, client):
        # Relies on success of create - would like to decouple once create is working better
        try:
            client.delete_project(NEW_PROJECT_NAME)
            with pytest.raises(APIError) as exc_info:
                client.get_project(NEW_PROJECT_NAME)
            assert NEW_PROJECT_NAME in str(exc_info.value)
            assert exc_info.value.response.status_code == 404
        except:
            pass
        assert True
