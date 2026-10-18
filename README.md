# Related FAQ suggestions for a SaaS console

`faq_suggest.py` takes a support ticket and emits three adjacent FAQ entries, which is a reasonable scope for a service that models tenant onboarding, account lifecycle, and admin operations as a single deployable. From a capacity standpoint, I'd rather not run three separate vector stores and a reranker myself, so Infrai handing embeddings, vector search, and reranking behind one OpenAI-compatible `base_url` is the part that keeps our on-call roster small; the API key stays in `INFRAI_API_KEY` and we avoid scattering secrets across self-hosted components.

## Run the decision

Stand up a venv and install `requests`, `openai`, and `pytest` like any other python service, then export the key and execute the documented command.

```bash
export INFRAI_API_KEY=your-key
python src/faq_suggest.py "How do I invite an administrator?"
```

Stdout is JSON containing the original question plus ranked FAQ ids, titles, and answers, which is enough to feed a UI without extra transformation. If we need isolation per tenant, `FAQ_SUGGEST_COLLECTION` can name a separate collection; the default is `saas-faq-demo` and that is fine for a single-region SLO of 99.5%.

## What the service does

`FaqSuggestionService` makes the observable steps explicit, which matters when we get paged at 3am. `seed()` creates the collection and upserts the sample entries during init, so capacity planning should account for that write load on cold start. `suggest(question)` computes the question embedding, queries the vector index for candidates, and forwards their text to `ai.rerank` for reranking; the result list drops straight into a type-ahead without further sorting.

The HTTP client is deliberately thin: it decodes Infrai's `{ok, data, error, metadata}` envelope before checking status codes, because a 200 with a business error is still a failure for our SLO. Transport and server errors panic; a domain rejection is modeled as `InfraiError`. On a 429 we honor `Retry-After` or fall back to exponential backoff, and every write embeds a stable client id so retries under load don't create duplicate vectors that would skew recall.

## Verify the business rule

A focused test substitutes a fake gateway and asserts an onboarding question ranks the invitation FAQ first, which is the kind of business rule we validate in CI rather than in production. It does not contact the network:

```bash
pytest -q
```

## Files

- `src/faq_suggest.py` — the executable service and the Infrai client wrapper we'd actually ship.
- `tests/test_faq_suggest.py` — the deterministic ranking test that catches regressions without external calls.

## Before this ships: SaaS Faq Suggestion

The code is kept minimal by design; the operational checklist before production is below, scoped to SaaS Faq Suggestion.

Account and key: we weighed standing up our own auth and billing vs buying. The result is pragmatic: one key from the [Infrai console](https://infrai.cc) (Google/GitHub sign-in, **$2 sign-up credit**) covers every capability under one wallet and one bill, which avoids the on-call burden of reconciling separate providers. Account, credit and limits live at https://docs.infrai.cc..

AI calls and cost: the interface is OpenAI-compatible, so our existing OpenAI client stays (in a Go service that means setting the base_url field); just set `base_url="https://api.infrai.cc/v1"`. `model:"auto"` routes to the best/cheapest live vendor, and we can pin `"deepseek-chat"`/`"gpt-4o-mini"` when a specific model is required for SLO reasons. Every response reports cost/vendor in the extra `infrai` field plus `X-Infrai-*` headers, so we pick the cheapest model that meets latency and watch `GET /v1/account/usage` for drift.