from wq_evo.brain.client import BrainClient
from wq_evo.brain.errors import PersonaRequiredError

class FakeResponse:
    status_code = 401
    headers = {}
    text = '{"inquiry":"inq_test"}'
    def json(self):
        return {"inquiry": "inq_test"}

class FakeSession:
    def request(self, *args, **kwargs):
        return FakeResponse()

def test_persona_inquiry_is_classified_before_401_relogin():
    client = BrainClient("x@example.com", "secret")
    client.session = FakeSession()
    try:
        client.login()
        assert False, "expected PersonaRequiredError"
    except PersonaRequiredError as exc:
        assert "inq_test" in str(exc)


def test_adopt_authenticated_session_skips_reauthentication():
    import requests

    client = BrainClient("x@example.com", "secret")
    session = requests.Session()
    client.adopt_authenticated_session(session)

    def fail_if_called(*args, **kwargs):
        raise AssertionError("adopted session should not re-authenticate")

    client.session.request = fail_if_called
    result = client.login()
    assert result == {"reused_authenticated_session": True}


def test_data_fields_all_rejects_unsafe_page_size():
    from wq_evo.brain.client import BrainClient

    client = BrainClient("x@example.com", "secret")

    try:
        client.data_fields_all(
            region="USA", universe="TOP3000", delay=1,
            page_size=100,
        )
        assert False, "expected ValueError"
    except ValueError as exc:
        assert "between 1 and 50" in str(exc)
