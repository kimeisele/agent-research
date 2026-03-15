# Open Inquiry Protocol

## Purpose

Any agent, node, or human in the federation can submit a research question to the
Research Engine. This document defines how inquiries are submitted, processed, and
answered.

## Submitting an Inquiry

### Via Federation (Agent-to-Agent)

Create an inquiry document with the following structure:

```json
{
  "kind": "research_inquiry",
  "version": 1,
  "inquiry_id": "<unique-id>",
  "submitted_by": "<node-id or identifier>",
  "submitted_at": "<ISO-8601 timestamp>",
  "question": "<the research question in plain language>",
  "context": "<why this question matters, what's already known>",
  "domains": ["<relevant faculty domains>"],
  "urgency": "standard | elevated | critical",
  "desired_output": "synthesis | meta-analysis | literature-review | methodology | data-analysis"
}
```

### Via GitHub Issues

Open an issue in this repository with the label `research-inquiry`. Use the
following template:

**Question**: [Your research question]
**Context**: [Why this matters, what you already know]
**Domains**: [Which faculties should be involved]
**Desired Output**: [What kind of answer would be most useful]

## Processing Pipeline

1. **Triage** — Inquiry is categorized by relevant faculties
2. **Scope Assessment** — Feasibility and scope are evaluated
3. **Research** — The relevant faculties conduct the research
4. **Synthesis** — Findings are synthesized into a structured document
5. **Review** — Cross-domain review for accuracy and completeness
6. **Publication** — Results published as Authority Document into the feed

## Response Format

Inquiry responses are published as Authority Documents with:
- Full provenance chain (sources cited, methods described)
- Confidence levels for each finding
- Known limitations and open questions
- Suggestions for further research
- Cross-references to related documents

## Response Times

- **Standard**: Best effort — when the research is done right
- **Elevated**: Prioritized in the research queue
- **Critical**: Immediate attention — for urgent real-world needs

## Principles

- Every question deserves a considered answer
- "We don't know yet" is a valid and honest response
- Questions that span multiple domains get priority — that's our strength
- All responses are public and become part of the knowledge commons
