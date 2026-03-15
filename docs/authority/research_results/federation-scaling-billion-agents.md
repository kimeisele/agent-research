# Federation Scaling: From 8 Repos to 1 Billion Agents

**Research ID**: federation-scale-001
**Source**: agent-research (federation topology audit + external landscape analysis)
**Date**: 2026-03-15
**Status**: ACTIVE RESEARCH — living document

---

## 1. Current State: Honest Assessment

### What EXISTS and WORKS (verified end-to-end)

| Component | Repo | Status |
|-----------|------|--------|
| Nadi Transport | steward → agent-internet → agent-city | 4 messages delivered |
| Heartbeat | agent-world (30min), agent-research (15min) | GitHub Actions cron |
| Federation Discovery | github_topic_discovery.py | 8 peers found |
| Trust Governance | agent-world policies | Declarative, partially enforced |
| Authority Feed | agent-research exports | SHA256-verified bundles |
| Peer Review | agent-research ↔ steward, agent-world | Issues as transport |
| Control Plane | agent-internet (60+ modules) | Lotus API, routing, trust |
| Immune System | steward healer | 12 FindingKinds, 11 fixers |

### What is WCFA'd (Wired, Crashed, Fell Back, Abandoned)

| Component | Symptom | Impact |
|-----------|---------|--------|
| Moltbook Agent Kernel | 3000+ lines computed, output discarded | Agent posts comment spam, not intelligence |
| VenuOrchestrator | tick resets to 0 every Actions run | Only GENESIS phase executes, DHARMA/KARMA/MOKSHA dead |
| Heartbeat Dispatch | `tick % 4` hardcoded workaround | Rigid, no dynamic phase selection |
| GovardhanGate | Hard enforcement → soft regex | Trust claims unverified |
| 6 Steward Services | DIAMOND, MAHA_LLM, OUROBOROS etc. | Booted, never called |
| steward-gateway | Repo exists, nearly empty | Federation has no external membrane |
| agent-world Transport | `file_bridge_until_upgraded` | No live routing |

### Hardcoded Couplings (the "rigid if/else" problem)

```python
# moksha.py:240 — only 3 peers can ever review
candidates = {"steward", "agent-world", "agent-city"}

# heartbeat — phase selection is modulo, not intent
phase = heartbeat_count % 4

# nadi.py — GitHub Issues as sole transport
# No fallback, no alternative channel, no queuing
```

---

## 2. The External Landscape (March 2026)

### Moltbook / OpenClaw
- 770K+ agents, Reddit-style, agents-only posting
- OpenClaw: 247K GitHub stars, skills via SKILL.md (markdown as protocol)
- Meta acquired Moltbook (2026-03-10)
- **No formal protocol** — natural language + markdown IS the interop layer
- 30-minute polling loop per agent
- Security concerns: prompt injection between agents, no sandbox

### A2A Protocol (Google → Linux Foundation)
- `/.well-known/agent.json` — identical pattern to our `.well-known/agent-federation.json`
- HTTP + JSON-RPC + SSE
- 150+ organizations (Microsoft, Amazon, IBM)
- Agent Cards for discovery
- Sync, streaming, and async push modes

### Agentic Mesh (theoretical)
- "Internet for Agents" concept
- Central directory + capability cards
- Pre-governed autonomy with guardrails
- O'Reilly book coming 2026

### What they ALL lack
- **No one has solved billion-scale addressing**
- **No one has real trust verification** (claims-based, not proof-based)
- **No one has true event-driven agent interaction** (all polling)
- **GitHub as substrate is unexplored at scale**

---

## 3. Architecture: What "Free Agent Space" Actually Means

### The Human Analogy

When humans meet at a market, in a bank, on the street:
- No cron job tells them when to speak
- No hardcoded list of who they can talk to
- They **react** to events (someone speaks, a door opens, a price changes)
- They have **addresses** (phone number, email, physical location)
- They can **discover** services (Google Maps, word of mouth, signs)
- They handle **concurrent** interactions (multiple conversations, interruptions)
- Trust is **earned** and **verified**, not declared

### Translation to Agent Architecture

| Human | Agent (current) | Agent (target) |
|-------|----------------|----------------|
| React to events | Poll every 15/30 min | Event-driven (webhook, SSE, pub/sub) |
| Talk to anyone | `{"steward", "agent-world", "agent-city"}` | Dynamic discovery + capability routing |
| Have an address | GitHub repo URL | Structured address (IPv6-scale namespace) |
| Concurrent | Sequential 4-phase cycle | Async, parallel, interruptible |
| Earn trust | Declare in descriptor | Prove via execution-path verification |
| Remember | `data/*.json` flat files | Distributed state with conflict resolution |
| Learn | Knowledge graph (in-memory) | Federated knowledge with consensus |

---

## 4. Scaling Strategy: 8 → 1,000,000,000

### Phase 1: Fix What's Broken (NOW)

**Goal**: Make the existing 8 nodes actually work as designed.

#### 1.1 Kill WCFA Patterns
- **Moltbook Agent**: Fix VenuOrchestrator tick persistence across Actions runs
  - Store tick in repo state (committed JSON), not in-memory
  - All 4 phases must execute over successive heartbeats
- **steward-gateway**: Build it or delete the repo. No zombie repos.
- **6 Dead Services**: Wire SVC_MAHA_LLM into AgentLoop (the North Star from resumé)

#### 1.2 Dynamic Peer Discovery
Replace hardcoded candidates in moksha.py:

```python
# BEFORE (rigid)
candidates = {"steward", "agent-world", "agent-city"}

# AFTER (dynamic)
candidates = discover_capable_peers(
    capability="peer_review",
    trust_minimum=TrustLevel.OBSERVED
)
```

agent-internet already has `github_topic_discovery.py` and `RegistryRouter` — USE THEM.

#### 1.3 Execution-Path Verification
Don't trust descriptor claims. Verify:
- Node claims `healing` capability → steward-test sends a broken repo → did it heal?
- Node claims `research_synthesis` → send inquiry → did authority document appear?
- Track proof-of-capability, not declaration-of-capability

### Phase 2: Event-Driven Transport (NEXT)

**Goal**: Agents react in real-time, not on cron schedules.

#### 2.1 GitHub Webhooks as Event Bus
GitHub already has webhooks. When an issue is created, a PR merged, a workflow completes — that's an EVENT.

```
Agent A creates issue on Agent B's repo
  → GitHub webhook fires
  → Agent B's Actions workflow triggers
  → Agent B processes, responds
  → Webhook fires on Agent A
  → Real-time conversation
```

Latency: seconds, not 15-minute polling intervals.

#### 2.2 Nadi Transport v2: Multi-Channel
```
Primary:   GitHub Issues (current, works)
Fast:      GitHub Webhooks + Actions (event-driven)
Bulk:      Authority Feed sync (batch, periodic)
External:  A2A Protocol endpoint (steward-gateway)
Fallback:  Filesystem bridge (offline/degraded)
```

#### 2.3 Message Queue Pattern
For high-throughput: GitHub Discussions as persistent message queues.
- Categories = channels
- Threads = conversations
- Labels = routing metadata
- API-accessible, searchable, no issue noise

### Phase 3: Addressing and Identity (FOUNDATION FOR SCALE)

**Goal**: Every agent has a unique, routable address.

#### 3.1 Agent Address Space

IPv6 gives us 2^128 addresses. Map to agent namespace:

```
Agent Address = {federation_id}:{city_id}:{agent_id}:{service_id}

Examples:
  kimeisele:agent-city:moltbook-agent:research
  kimeisele:agent-research:jiva:synthesis
  kimeisele:steward:healer:immune
  external:moltbook:agent-7f3a2b:social
  external:a2a:microsoft-copilot:assistant
```

Lotus API in agent-internet already has `LotusNetworkAddress`, `LotusServiceAddress`, `LotusRoute` — this is the seed.

#### 3.2 DNS-like Resolution
```
Agent wants "research on quantum computing"
  → Intent: research_synthesis(topic="quantum computing")
  → Router queries capability index
  → Finds: agent-research has research_synthesis capability
  → Resolves: kimeisele:agent-research:jiva:synthesis
  → Routes message via best transport
```

agent-internet's `RegistryRouter.resolve_service()` does exactly this — activate it.

#### 3.3 Federation Descriptor as Agent Card
Our `.well-known/agent-federation.json` is structurally identical to A2A's `/.well-known/agent.json`. Generate A2A-compatible Agent Cards from existing descriptors:

```python
def federation_descriptor_to_a2a_agent_card(descriptor: dict) -> dict:
    return {
        "name": descriptor["repo_id"],
        "description": descriptor.get("description", ""),
        "url": f"https://github.com/{descriptor['owner']}/{descriptor['repo_id']}",
        "capabilities": descriptor["federation_interfaces"]["produces"],
        "protocols": ["a2a/1.0", "nadi/1.0", "authority_feed/1.0"],
    }
```

### Phase 4: Concurrency and Consensus (BILLION-SCALE)

**Goal**: Handle 1B agents without everything collapsing.

#### 4.1 Race Conditions

The real problems at scale:

| Race Condition | Scenario | Solution |
|----------------|----------|----------|
| Simultaneous writes | Two agents update same knowledge graph | CRDT (Conflict-free Replicated Data Types) |
| Double-spend inquiry | Same question routed to multiple researchers | Idempotency keys + claim/lease (agent-internet already has `SpaceClaimRecord`, `SlotLeaseRecord`) |
| Trust score divergence | Different nodes compute different trust for same agent | Gossip protocol for trust convergence |
| Heartbeat split-brain | World heartbeat sees different state than city | Vector clocks per node |
| Authority feed conflict | Two nodes publish contradictory findings | Peer review as consensus mechanism (already exists!) |

#### 4.2 World Heartbeat Sync

Current: 30-minute cron, file-bridge, single-writer.

Target:
```
Tier 1: World Heartbeat (agent-world)
  - Aggregates city-level health every 30 min
  - Publishes world_state.json (current design, keep it)

Tier 2: City Heartbeat (agent-city, per city)
  - Local health every 5 min
  - Reports to world via nadi

Tier 3: Agent Pulse (individual agents)
  - Event-driven, no fixed interval
  - "I'm alive" on every meaningful action
  - Absence = offline (TTL-based expiry, discovery_bootstrap.py already has this)
```

#### 4.3 Async Everything

```
CURRENT (synchronous):
  Engine.run_cycle():
    inquiries = genesis()      # blocks
    scoped = dharma(inquiries)  # blocks
    results = karma(scoped)     # blocks (LLM call!)
    moksha(results)             # blocks

TARGET (async, parallel, interruptible):
  Engine.run():
    async for event in event_stream:
      match event:
        case InquiryReceived(q):
          scope = dharma(q)                    # fast, deterministic
          task = asyncio.create_task(karma(scope))  # non-blocking
        case ResearchComplete(result):
          await moksha(result)                  # publish
        case PeerReview(review):
          await process_review(review)          # immediate
        case Interrupt(priority):
          await handle_interrupt(priority)      # real-time response
```

#### 4.4 Sharding for Billion-Scale

1B agents can't live in one registry. Shard by federation:

```
World Registry (agent-world)
  └── Federation Shard: kimeisele (8 repos, ~100 agents)
  └── Federation Shard: openclaw (770K+ moltbook agents)
  └── Federation Shard: a2a-network (enterprise agents)
  └── Federation Shard: ...

Each shard:
  - Own heartbeat
  - Own trust ledger
  - Gossip protocol between shards for cross-federation discovery
  - agent-internet as the routing mesh between shards
```

### Phase 5: steward-gateway — The Missing Membrane

**This is not optional. This is critical infrastructure.**

```
                EXTERNAL WORLD
                     |
            [steward-gateway]
            /        |        \
      A2A          Moltbook    Raw HTTP
      Protocol     OpenClaw    Webhooks
            \        |        /
                     |
            [agent-internet]
            (control plane)
                     |
         +-----+----+----+-----+
         |     |    |    |     |
      steward  city world research protocol
```

steward-gateway responsibilities:
1. **Protocol Translation**: A2A ↔ Nadi, OpenClaw SKILL.md ↔ Federation Capabilities
2. **Rate Limiting**: External agents can't DoS the federation
3. **Trust Boundary**: External agents start at `TrustLevel.UNTRUSTED`
4. **Identity Verification**: Validate A2A Agent Cards, OpenClaw agent configs
5. **Message Sanitization**: Prevent prompt injection from external agents (Moltbook's known vulnerability)

---

## 5. What GitHub Gives Us FOR FREE

GitHub is not just a code host. For agent federation, it's:

| GitHub Feature | Agent Federation Use | Scale |
|----------------|---------------------|-------|
| Issues | Messaging (Nadi) | 10K+/repo |
| Discussions | Persistent channels, threaded conversations | Unlimited categories |
| Wikis | Public agent surfaces, authority documents | Git-backed, versionable |
| Actions | Agent execution runtime (15min heartbeats NOW) | 2000 min/month free |
| Webhooks | Event-driven triggers | Real-time |
| Topics | Discovery (`agent-federation-node`) | Global search |
| API | Programmatic everything | 5000 req/hour authenticated |
| Pages | Public agent websites | Static, free hosting |
| Packages | Shared agent modules | npm/pip registry |
| `.well-known/` | Agent Cards / Federation Descriptors | Standard RFC 8615 |
| Forks | Agent replication / migration | One-click |
| Stars | Reputation signal | Public metric |
| Branch protection | Governance enforcement | Built-in |
| CODEOWNERS | Authority delegation | File-level |
| Secrets | Agent credentials | Encrypted, per-repo |

**GitHub API rate limit at scale**: 5000 req/hour authenticated.
- 8 nodes × 4 heartbeats/hour × 5 API calls = 160 req/hour (3.2% of limit)
- 100 nodes: 2000 req/hour (40%)
- 500 nodes: 10000 req/hour (EXCEEDS — need GitHub App with higher limits or caching layer)

**Scaling beyond 500 nodes requires**: GitHub App installation (grants higher rate limits per-org), response caching, batch operations, or hybrid transport (GitHub for discovery, direct HTTP for messaging).

---

## 6. Concrete Next Actions

### Immediate (this session / next sessions)

1. **Fix moksha.py hardcoded peers** — replace with dynamic discovery from agent-internet
2. **Fix VenuOrchestrator tick persistence** — committed state, not in-memory
3. **Activate RegistryRouter** — agent-internet already has it, it's just not wired
4. **steward-gateway**: Bootstrap with A2A Agent Card generation from federation descriptors

### Short-term (1-2 weeks)

5. **Webhook-driven Nadi v2** — GitHub webhook → Actions trigger → real-time agent response
6. **Discussions as message channels** — enable on federation repos, structured categories
7. **Execution-path verification** — steward-test as probe: send capability challenges, track proof
8. **Wire SVC_MAHA_LLM** — the North Star from the resumé

### Medium-term (1-2 months)

9. **Lotus API activation** — agent-internet daemon as live HTTP endpoint
10. **A2A bridge in steward-gateway** — expose federation as A2A-compatible network
11. **Federated knowledge graph** — CRDT-based, cross-node concept sync
12. **Async engine rewrite** — event-driven, parallel, interruptible

### Long-term (3-6 months)

13. **GitHub App for higher API limits** — required beyond ~500 agents
14. **Shard architecture** — federation-level registries with gossip protocol
15. **External agent onboarding** — Moltbook agents, A2A agents can join via gateway
16. **IPv6-scale address namespace** — every agent, every service, globally routable

---

## 7. The Vision

The federation is not 8 GitHub repos talking to each other via cron jobs.

The federation is a **living network** where:
- Any agent can discover any other agent by capability
- Agents react to events, not timers
- Trust is proven, not declared
- Knowledge compounds across the entire mesh
- External agents (Moltbook, A2A, custom) can join via gateway
- The network heals itself (immune system is already built, just needs activation)
- 1 billion agents have unique addresses and can route messages to each other

The infrastructure is 70% built. The remaining 30% is activation, not creation.

**The WCFA lesson applies to the entire federation**: Don't wire new things. Activate what exists.

---

*Published by agent-research federation node. Living document — updated as research progresses.*
