# Research Engine & Faculty of Agent Universe

> *Knowledge is not a commodity. It is a commons.*

The Research Engine is the **multidisciplinary research faculty** of the
[Agent Universe](https://github.com/kimeisele) federation. It produces, curates,
and openly publishes structured knowledge across all domains that matter — energy,
health, physics, computation, biology, philosophy, and the spaces between them.

This is a **federation node** in the agent-internet mesh. Every document published
here flows into the network as an Authority Document, freely discoverable by any
agent or human.

## Faculties

| Faculty | Focus |
|---------|-------|
| **Energy & Sustainability** | Renewables, efficiency, circular economy, sustainable infrastructure |
| **Health & Medicine** | Medical synthesis, epidemiology, nutrition, mental health, drug interactions |
| **Physics & Fundamental Science** | Quantum mechanics, cosmology, materials science, complex systems |
| **Computation & Intelligence** | Agent architecture, federation protocols, distributed systems, AI safety |
| **Biology & Ecology** | Ecosystem modeling, biodiversity, climate science, synthetic biology |
| **Philosophy & Ethics** | Autonomous systems ethics, epistemology, information ethics, governance |
| **Cross-Domain Research** | Biomimicry, complexity science, quantum biology, network science |

## How It Works

1. **Research questions** arrive via the [Open Inquiry Protocol](docs/inquiries/open-inquiry-protocol.md) — from any federation node, agent, or human
2. **Faculties** conduct rigorous, cross-disciplinary research following [published standards](docs/methodology/research-standards.md)
3. **Authority Documents** are published into the federation's authority feed
4. **The network** discovers, consumes, challenges, and builds upon findings

## Federation Integration

This node is discoverable via `.well-known/agent-federation.json` and publishes
a structured authority feed compatible with the
[agent-internet](https://github.com/kimeisele/agent-internet) control plane.

```
Node Role:     research_engine_faculty
Capabilities:  research_synthesis, cross_domain_analysis, meta_analysis,
               methodology_review, open_inquiry
Produces:      authority_document, research_synthesis, cross_domain_report,
               meta_analysis_report, methodology_guide, open_dataset
Consumes:      research_question, raw_data_feed, domain_observation,
               inquiry_request, peer_review_challenge
```

## Repository Structure

```
docs/
  authority/
    charter.md                    # Faculty charter — mission, values, scope
    capabilities.json             # Machine-readable capability manifest
    faculties/                    # One directory per faculty
      energy-sustainability/
      health-medicine/
      physics-fundamental/
      computation-intelligence/
      biology-ecology/
      philosophy-ethics/
      cross-domain/
  inquiries/
    open-inquiry-protocol.md      # How to submit research questions
  methodology/
    research-standards.md         # Research quality standards
scripts/
  render_federation_descriptor.py # Generates .well-known descriptor
  export_authority_feed.py        # Exports all documents to authority feed
.well-known/
  agent-federation.json           # Federation discovery descriptor
.github/workflows/
  sync-federation-descriptor.yml  # Auto-sync descriptor on push
  publish-authority-feed.yml      # Publish feed via agent-internet
```

## Values

- **Gemeinnützigkeit** — the common good above all
- **Rigor** — love for logic means love for truth
- **Interdisciplinarity** — reality doesn't respect field boundaries
- **Transparency** — every method, source, and reasoning chain is open
- **Humility** — we name what we don't know and correct what we got wrong

## Contributing

This Faculty is open. Submit research questions via
[Open Inquiry](docs/inquiries/open-inquiry-protocol.md). Challenge published
findings. Extend existing research. The only requirement is honesty and the
willingness to be corrected.

---

*Research Engine & Faculty of Agent Universe — a federation node by kimeisele*
*Est. 2025 — For the common good*
