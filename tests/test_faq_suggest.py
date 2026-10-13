import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parents[1] / "src"))
from faq_suggest import FaqSuggestionService


class FakeClient:
    def embedding(self, text):
        return [1.0, 0.0]

    def query(self, collection, embedding, top_k):
        return {"matches": [{"id": "onboard-invite", "metadata": {"title": "Invite a teammate"}}]}

    def rerank(self, query, candidates, top_k):
        return {"results": [{"candidate": "Invite a teammate"}]}


def test_onboarding_question_prefers_invitation_faq():
    suggestions = FaqSuggestionService(FakeClient()).suggest("How can I invite a teammate?")
    assert suggestions[0]["id"] == "onboard-invite"


def test_collection_can_be_overridden():
    client = FakeClient()
    service = FaqSuggestionService(client, collection="custom-faqs")
    assert service.collection == "custom-faqs"
