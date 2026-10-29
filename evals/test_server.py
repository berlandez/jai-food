"""The /api/pick contract that does not need a live model.

The route is what turns a craving plus up to three known names into the notes
Claude actually sees. Unknown names are dropped on the server. Press reviews
never enter the prompt.
"""

import time

import httpx2
import pytest

import app as jai

pytestmark = pytest.mark.mechanics


class _Block:
    def __init__(self, type_, text=None):
        self.type = type_
        self.text = text


class _Response:
    def __init__(self, text, stop_reason="end_turn"):
        self.stop_reason = stop_reason
        self.content = [_Block("thinking"), _Block("text", text)]


class _Fake:
    def __init__(self):
        self.calls = []
        self.text = "Get the Hot Sailor at Jules. The crust is burnt well done."
        self.stop_reason = "end_turn"
        self.error = None

    def create(self, **kwargs):
        if self.error:
            raise self.error
        self.calls.append(kwargs)
        return _Response(self.text, self.stop_reason)


class _Client:
    def __init__(self, fake):
        self.beta = self
        self.messages = fake


@pytest.fixture
def fake(monkeypatch):
    stub = _Fake()
    monkeypatch.setattr(jai, "client", lambda: _Client(stub))
    jai._cache.clear()
    jai._hits.clear()
    jai._day.update(date=time.strftime("%Y-%m-%d"), count=0)
    yield stub
    jai._cache.clear()
    jai._hits.clear()
    jai._day.update(date=time.strftime("%Y-%m-%d"), count=0)


@pytest.fixture
def client():
    return jai.app.test_client()


def _post(client, query, names, ip="203.0.113.10"):
    return client.post(
        "/api/pick",
        json={"q": query, "names": names},
        environ_base={"REMOTE_ADDR": ip},
    )


def _http_error(status, cls, message):
    request = httpx2.Request("POST", "https://api.anthropic.com/v1/messages")
    response = httpx2.Response(status, request=request)
    return cls(message, response=response, body={"error": {"message": message}})


def test_data_route_serves_the_notebook_files(client):
    response = client.get("/api/data")
    assert response.status_code == 200
    body = response.get_json()
    assert [spot["name"] for spot in body["spots"]] == [spot["name"] for spot in jai.SPOTS]
    assert body["chips"]
    assert body["surprises"]
    assert set(body["reviews"]) <= {spot["name"] for spot in jai.SPOTS}


def test_index_serves_the_page(client):
    response = client.get("/")
    assert response.status_code == 200
    assert b"E.A.T." in response.data


def test_missing_craving_or_unknown_names_are_rejected(client, fake):
    assert _post(client, "", ["Jules"]).status_code == 400
    assert _post(client, "a", ["Jules"]).status_code == 400
    assert _post(client, "  b ", ["Jules"]).status_code == 400
    assert _post(client, "pizza", []).status_code == 400
    assert _post(client, "pizza", ["Nobu", "Not A Real Spot"]).status_code == 400
    assert client.post("/api/pick", data="not-json", content_type="text/plain").status_code == 400
    assert fake.calls == []


def test_prompt_uses_only_the_named_notes(client, fake):
    jules = jai.SPOTS_BY_NAME["Jules"]
    response = _post(client, "pizza night", ["Nobu", "Jules", "Also Fake"])
    assert response.status_code == 200
    assert response.get_json()["text"] == fake.text
    call = fake.calls[0]
    prompt = call["messages"][0]["content"]
    assert call["system"] == jai.SYSTEM
    assert call["model"] == jai.MODEL
    assert 'The reader asked for: "pizza night"' in prompt
    assert jai.notes_for(jules) in prompt
    assert "Nobu" not in prompt
    assert "natural-wine" not in prompt
    assert "Drunken Sailor" not in prompt
    assert "theinfatuation.com" not in prompt
    breadbelly_take = jai.SPOTS_BY_NAME["Breadbelly"]["take"]
    assert breadbelly_take not in prompt


def test_only_the_first_three_names_are_sent(client, fake):
    names = [spot["name"] for spot in jai.SPOTS[:4]]
    response = _post(client, "a big table", names)
    assert response.status_code == 200
    prompt = fake.calls[0]["messages"][0]["content"]
    for name in names[:3]:
        assert jai.notes_for(jai.SPOTS_BY_NAME[name]) in prompt
    assert jai.notes_for(jai.SPOTS_BY_NAME[names[3]]) not in prompt


def test_query_is_trimmed_and_capped_at_200_characters(client, fake):
    response = _post(client, "  " + ("z" * 250) + "  ", ["Jules"])
    assert response.status_code == 200
    prompt = fake.calls[0]["messages"][0]["content"]
    assert '"' + ("z" * 200) + '"' in prompt
    assert "z" * 201 not in prompt


def test_cache_collapses_case_and_skips_a_second_call(client, fake):
    first = _post(client, "Pizza", ["Jules"])
    fake.text = "This should not be served from a second call. It is a different blurb."
    second = _post(client, "pizza", ["Jules"])
    assert first.status_code == second.status_code == 200
    assert second.get_json()["text"] == first.get_json()["text"]
    assert len(fake.calls) == 1


def test_refusal_is_not_cached(client, fake):
    fake.stop_reason = "refusal"
    assert _post(client, "refusal probe", ["Jules"]).status_code == 422
    assert _post(client, "refusal probe", ["Jules"]).status_code == 422
    assert len(fake.calls) == 2


@pytest.mark.parametrize(
    "error, status",
    [
        (_http_error(401, jai.anthropic.AuthenticationError, "nope"), 503),
        (_http_error(429, jai.anthropic.RateLimitError, "slow"), 429),
        (_http_error(500, jai.anthropic.APIStatusError, "down"), 502),
        (jai.anthropic.APIConnectionError(request=httpx2.Request("POST", "https://api.anthropic.com/v1/messages")), 502),
        (TypeError("no credentials"), 503),
    ],
)
def test_model_errors_map_to_status_codes(client, fake, error, status):
    fake.error = error
    response = _post(client, f"error probe {status} {type(error).__name__}", ["Jules"])
    assert response.status_code == status
    assert "error" in response.get_json()


def test_hourly_cap_stops_the_model_call(client, fake):
    ip = "203.0.113.40"
    for _ in range(jai.PER_IP_HOURLY):
        assert jai.over_limit(ip) is False
    response = _post(client, "hourly cap probe", ["Jules"], ip=ip)
    assert response.status_code == 429
    assert fake.calls == []


def test_daily_cap_stops_the_model_call(client, fake):
    jai._day.update(date=time.strftime("%Y-%m-%d"), count=jai.DAILY_CAP)
    response = _post(client, "daily cap probe", ["Jules"], ip="203.0.113.41")
    assert response.status_code == 429
    assert fake.calls == []
