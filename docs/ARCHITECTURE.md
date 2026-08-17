# Architecture

## Processing flow

```text
Feishu user
  -> Feishu bot / app
  -> Feishu WebSocket event
  -> FeishuAdapter (protocol parsing and reply delivery)
  -> FeatureRouter (feature selection)
  -> DemoAccountFeature (validation and conversation state)
  -> AdminClient (HTTP and service authentication)
  -> models-layer-backend
```

The bot opens one outbound WebSocket connection to Feishu, so no public callback
URL or additional gateway service is required. The Admin backend remains the only
component that writes account data.

## Responsibilities

- `feishu_adapter.py`: Feishu SDK integration, event deduplication, per-conversation
  ordering and message delivery. It contains no account business rules.
- `router.py`: routes a message to the active or newly matched feature.
- `features/demo_account.py`: deterministic state machine, validation, authorization,
  confirmation and user-facing responses.
- `conversation_store.py`: short-lived in-memory conversation state and event dedup.
- `admin_client.py`: authenticated Admin API call and error classification.
- `config.py`: fail-fast environment configuration.
- `health.py`: process liveness endpoint for deployment probes.

## Adding another deterministic feature

1. Implement the `Feature` protocol in `features/base.py`.
2. Keep the feature's state and validation inside its own module.
3. Register it in `main.py` when constructing `FeatureRouter`.
4. Add feature-level tests; the Feishu adapter and Admin client do not need changes.

## Adding an Agent later

An Agent is not required for account creation. If natural-language capabilities are
needed later, add an `AgentFeature` as a fallback after all deterministic features.
It can call an external Agent service over HTTP, or use an in-process model client.
The account feature should remain deterministic so passwords, authorization,
confirmation and idempotency never depend on model output.

## State and scaling boundary

The first release stores state in process memory. This is sufficient for one
instance. Before running multiple replicas, replace the conversation store and
message deduplicator with Redis implementations behind the same interfaces. No
business-flow rewrite is required.

Passwords exist only in short-lived conversation memory and outbound Admin request
bodies. They must never be logged, echoed in confirmation messages, or persisted by
this service.
