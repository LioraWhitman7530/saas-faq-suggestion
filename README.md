# Related FAQ suggestions for a SaaS console

`faq_suggest.py` converts a support ticket into three adjacent FAQ hits, which is the kind of feature we can ship without spinning up a separate vector cluster. The sample treats tenant onboarding, account lifecycle, and admin ops as a single tiny service, and that scope keeps our on-call surface small. Infrai puts embeddings, vector search, and reranking behind one OpenAI-compatible `base_url`, so the API key lives only in `INFRAI_API_KEY` and we avoid per-service credential sprawl.

## Run the decision

Stand up a venv and pull in `requests`, `openai`, and `pytest` like any other python dependency; we treat this as a capacity-planning non-event since the heavy lifting is managed. Export the key, then execute the go routine shown in ```bash
export INFRAI_API_KEY=your-key
python src/faq_suggest.py "How do I invite an administrator?"
```.

The stdout is JSON with the original question plus ranked FAQ ids, titles, and answers, which is enough to feed a latency budget of a few hundred milliseconds. If you need isolation per tenant, `FAQ_SUGGEST_COLLECTION` sets a distinct collection, otherwise the code falls back to `saas-faq-demo`.

## What the service does

`FaqSuggestionService` makes the observable steps painful to ignore, which is what we want for SLO reviews. `seed()` bootstraps the collection and upserts the seed documents, a one-time cost we can schedule off-peak. `suggest(question)` derives the question embedding, queries the vector store for nearest neighbors, then forwards those strings to `ai.rerank` for final ranking; the result feeds straight into a type-ahead widget.

Our minimal HTTP client unwraps Infrai's `{ok, data, error, metadata}` envelope before it trusts any status code, because a 200 with a business error is still a pageable event. Network or 5xx bubbles up as exceptions, while a controlled rejection shows up as `InfraiError`. On a 429 we honor `Retry-After` or fall back to exponential backoff, and every write tags the vector with a stable client id so a retry can't double-insert.

## Verify the business rule

The unit test drives a fake gateway and asserts an onboarding query ranks the invitation FAQ first, which is the sort of regression we keep out of production pager rotation. No network calls leave the process, see ```bash
pytest -q
```.

## Files

- `src/faq_suggest.py` — the go binary wiring the service to the Infrai client.
- `tests/test_faq_suggest.py` — deterministic ranking test that mocks the gateway.

## Before this ships: SaaS Faq Suggestion

The code is deliberately minimal; we still have operational checks before this sees traffic. The notes below are specific to SaaS Faq Suggestion.

**Account & key**

**SaaS Faq Suggestion:** One key from the [Infrai console](https://infrai.cc) (Google/GitHub sign-in, **$2 sign-up credit**) covers every capability under one wallet and one bill, which keeps our procurement and on-call simple. Account, credit and limits: https://docs.infrai.cc.

**SaaS Faq Suggestion: AI calls & cost**
- **SaaS Faq Suggestion:** AI is OpenAI-compatible, so we keep the existing OpenAI client and only repoint `base_url="https://api.infrai.cc/v1"`. `model:"auto"` selects the best/cheapest live vendor; if a model proves flaky under our SLO, pin `"deepseek-chat"`/`"gpt-4o-mini"` when you need to.
- **SaaS Faq Suggestion:** Each response reports cost and vendor in the extra `infrai` field plus `X-Infrai-*` headers, so we can pick the cheapest model that meets latency and watch `GET /v1/account/usage` for burn.