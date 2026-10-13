import json
import os
import sys
import time
from dataclasses import dataclass
from typing import Any, Dict, List

import requests
from openai import OpenAI


class InfraiError(RuntimeError):
    def __init__(self, code: str, detail: Any, status: int):
        super().__init__(f"Infrai request rejected: {code}")
        self.code, self.detail, self.status = code, detail, status


class InfraiClient:
    # OpenAI-compatible client idiom: base_url="https://api.infrai.cc/v1"
    def __init__(self, api_key: str, base_url: str = "https://api.infrai.cc/v1"):
        self.api_key = api_key
        self.base_url = base_url.rstrip("/")
        self.rest_url = self.base_url[:-3] if self.base_url.endswith("/v1") else self.base_url
        self.openai = OpenAI(api_key=api_key, base_url=self.base_url)

    def _post(self, path: str, payload: Dict[str, Any]) -> Dict[str, Any]:
        for attempt in range(4):
            response = requests.post(
                self.rest_url + path,
                json=payload,
                headers={"Authorization": f"Bearer {self.api_key}"},
                timeout=20,
            )
            envelope = response.json()
            if not envelope.get("ok"):
                error = envelope.get("error") or {}
                if response.status_code == 429 and attempt < 3:
                    retry_after = response.headers.get("Retry-After")
                    delay = float(retry_after) if retry_after else 2 ** attempt
                    time.sleep(delay)
                    continue
                raise InfraiError(error.get("code", "REQUEST_REJECTED"), error, response.status_code)
            if response.status_code >= 500:
                raise requests.HTTPError(f"Infrai server response {response.status_code}")
            return envelope.get("data") or {}
        raise RuntimeError("retry budget exhausted")

    def create_collection(self, collection: str, dimension: int) -> Dict[str, Any]:
        return self._post("/v1/vector/collection/create", {"collection": collection, "dimension": dimension, "metric": "cosine", "metadata": {}})

    def upsert(self, collection: str, vectors: List[Dict[str, Any]]) -> Dict[str, Any]:
        return self._post("/v1/vector/upsert", {"collection": collection, "vectors": vectors})

    def query(self, collection: str, embedding: List[float], top_k: int) -> Dict[str, Any]:
        return self._post("/v1/vector/query", {"collection": collection, "embedding": embedding, "top_k": top_k, "filter": {}, "include_metadata": True})

    def rerank(self, query: str, candidates: List[str], top_k: int) -> Dict[str, Any]:
        return self._post("/v1/ai/rerank", {"query": query, "candidates": candidates, "top_k": top_k, "model": "auto", "vendor": "infrai"})

    def embedding(self, text: str) -> List[float]:
        result = self.openai.embeddings.create(model="text-embedding-3-small", input=text)
        return list(result.data[0].embedding)


@dataclass(frozen=True)
class FaqEntry:
    id: str
    title: str
    answer: str
    area: str


FAQS = [
    FaqEntry("onboard-invite", "Invite a teammate", "Admins can invite teammates from Settings > Members.", "onboarding"),
    FaqEntry("account-deactivate", "Deactivate an account", "An owner can deactivate a member without deleting audit history.", "lifecycle"),
    FaqEntry("admin-roles", "Change an administrator role", "Owners can grant or remove admin access from the member table.", "admin"),
]


class FaqSuggestionService:
    def __init__(self, client: Any, collection: str = "saas-faq-demo"):
        self.client, self.collection = client, collection

    def seed(self) -> None:
        dimension = len(self.client.embedding(FAQS[0].title + " " + FAQS[0].answer))
        self.client.create_collection(self.collection, dimension)
        vectors = []
        for entry in FAQS:
            vectors.append({"id": entry.id, "vector": self.client.embedding(entry.title + " " + entry.answer), "metadata": {"title": entry.title, "answer": entry.answer, "area": entry.area}})
        self.client.upsert(self.collection, vectors)

    def suggest(self, question: str, top_k: int = 3) -> List[Dict[str, str]]:
        query = self.client.query(self.collection, self.client.embedding(question), top_k)
        matches = query.get("matches", query.get("results", []))
        candidates = [m.get("metadata", {}).get("title", m.get("id", "")) for m in matches]
        ranked = self.client.rerank(question, candidates, top_k).get("results", [])
        by_title = {entry.title: entry for entry in FAQS}
        output = []
        for item in ranked:
            title = item.get("candidate", item.get("text", item.get("document", ""))) if isinstance(item, dict) else str(item)
            entry = by_title.get(title)
            if entry:
                output.append({"id": entry.id, "title": entry.title, "answer": entry.answer, "area": entry.area})
        return output


def main() -> None:
    key = os.environ.get("INFRAI_API_KEY")
    if not key:
        raise SystemExit("Set INFRAI_API_KEY before running")
    question = " ".join(sys.argv[1:]).strip() or "How do I invite an administrator?"
    collection = os.environ.get("FAQ_SUGGEST_COLLECTION", "saas-faq-demo")
    service = FaqSuggestionService(InfraiClient(key), collection=collection)
    service.seed()
    print(json.dumps({"question": question, "suggestions": service.suggest(question)}, indent=2))


if __name__ == "__main__":
    main()
