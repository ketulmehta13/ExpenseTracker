import httpx
import pytest
from fastapi.testclient import TestClient

from app.config import Settings
from app.main import create_app
from tests.conftest import SUPABASE_URL, TEST_USER

FOOD = {"id": 1, "name": "Food", "user_id": None}
TRAVEL = {"id": 2, "name": "Travel", "user_id": None}
DINING = {"id": 10, "name": "Dining Out", "user_id": TEST_USER["id"]}


@pytest.fixture
def categorize(client, supabase, auth_headers):
    supabase.tables["categories"] = [FOOD, TRAVEL, DINING]
    supabase.tables["transactions"] = [
        {"title": "Swiggy order 8812", "category_id": 10},
        {"title": "UPI/SWIGGY/1234/Pay", "category_id": 10},
    ]

    def post(**body):
        response = client.post("/v1/categorize", json=body, headers=auth_headers)
        assert response.status_code == 200, response.text
        return response.json()

    return post


def test_requires_a_token(client):
    assert client.post("/v1/categorize", json={"title": "swiggy"}).status_code == 401


def test_the_users_history_comes_first(categorize):
    result = categorize(title="swiggy")
    assert result["suggestion"] == {
        "category_id": 10,
        "category_name": "Dining Out",
        "label": None,
        "confidence": 1.0,
        "source": "history",
    }


def test_a_different_title_falls_through_to_the_model(categorize):
    # "swiggy dinner" shares a word with the past "swiggy" but is not the same title
    assert categorize(title="SWIGGY dinner order")["suggestion"]["source"] == "model"


def test_history_matches_through_typos(categorize):
    assert categorize(title="swigy")["suggestion"]["category_id"] == 10


def test_model_suggestion_maps_onto_the_users_category(categorize):
    result = categorize(title="Uber ride to airport", amount=640, type="EXPENSE")
    assert result["suggestion"]["source"] == "model"
    assert result["suggestion"]["label"] == "travel"
    assert result["suggestion"]["category_id"] == 2
    assert result["model_version"] == "test-model"


def test_model_prefers_the_users_own_category(categorize):
    result = categorize(title="zomato order", amount=380)
    assert (result["suggestion"]["label"], result["suggestion"]["category_id"]) == ("food", 10)


def test_label_without_a_matching_category_is_returned_without_an_id(categorize):
    result = categorize(title="apollo pharmacy medicines", amount=560)
    assert result["suggestion"]["label"] == "health"
    assert result["suggestion"]["category_id"] is None
    assert result["suggestion"]["category_name"] == "Health"


def test_low_confidence_gives_no_suggestion(categorize, client):
    client.app.state.categorizer.threshold = 1.01  # nothing is ever confident enough
    assert categorize(title="zomato order")["suggestion"] is None


def test_history_and_categories_are_cached_per_user(categorize, supabase):
    categorize(title="swiggy")
    calls = supabase.rest_calls
    categorize(title="zomato")
    categorize(title="uber")
    assert supabase.rest_calls == calls


def test_works_without_a_model(supabase, auth_headers, tmp_path):
    supabase.tables["categories"] = [DINING]
    supabase.tables["transactions"] = [{"title": "swiggy", "category_id": 10}]
    settings = Settings(supabase_url=SUPABASE_URL, supabase_anon_key="anon-key", model_dir=tmp_path)
    with TestClient(create_app(settings, transport=httpx.MockTransport(supabase.handler))) as client:
        history = client.post("/v1/categorize", json={"title": "swiggy"}, headers=auth_headers).json()
        unknown = client.post("/v1/categorize", json={"title": "zomato"}, headers=auth_headers).json()
    assert history["suggestion"]["source"] == "history" and history["model_version"] is None
    assert unknown == {"suggestion": None, "model_version": None}


@pytest.mark.parametrize("body", [{"title": ""}, {"title": "x" * 201}, {"title": "rent", "type": "TRANSFER"},
                                  {"title": "rent", "amount": -5}])
def test_rejects_invalid_input(client, auth_headers, body):
    assert client.post("/v1/categorize", json=body, headers=auth_headers).status_code == 422
