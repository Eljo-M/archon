import json

import httpx
import pytest

from archon.agents.model import InferenceModel


async def test_adapter_sends_structured_role_request_and_parses_response():
    async def respond(request):
        body = json.loads(request.content)
        assert request.url.path == "/v1/chat/completions"
        assert body["response_format"] == {"type": "json_object"}
        assert body["model"] == "test-model"
        assert json.loads(body["messages"][1]["content"])["issue"] == "bug"
        return httpx.Response(200, json={"choices": [{"message": {"content": '{"files":["arithmetic.py"]}'}}]})

    model = InferenceModel("http://localhost/v1", "test-model")
    await model.client.aclose()
    model.client = httpx.AsyncClient(base_url="http://localhost/v1/", transport=httpx.MockTransport(respond))
    try:
        assert await model.complete("Architect", {"issue": "bug"}) == {"files": ["arithmetic.py"]}
    finally:
        await model.close()


async def test_model_http_failure_is_not_treated_as_patch():
    model = InferenceModel("http://localhost/v1", "test-model")
    await model.client.aclose()
    model.client = httpx.AsyncClient(base_url="http://localhost/v1/", transport=httpx.MockTransport(
        lambda _: httpx.Response(503)))
    try:
        with pytest.raises(httpx.HTTPStatusError):
            await model.complete("Coder", {})
    finally:
        await model.close()
