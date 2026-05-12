from mp_api.client.contribs.client import ContribsClient


class ProjectClient:
    def __init__(self, client: ContribsClient):
        """Client for Project-related requests.

        Args:
            client (ContribsClient): the parent client to manage connections
        """
        self.client = client
