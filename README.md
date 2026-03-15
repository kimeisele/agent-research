# agent-template

Use this repository as a GitHub template for a new federation node.

## What you get

- `.well-known/agent-federation.json` descriptor
- automatic descriptor sync workflow
- reusable authority-feed publish workflow
- minimal example authority export script

## Quick start

1. Click **Use this template** on GitHub.
2. Give the new repository the topic `agent-federation-node`.
3. Push your own authority documents into `docs/authority/`.
4. Trigger `Publish Authority Feed` or push to `main`.

The template will:

- regenerate `.well-known/agent-federation.json`
- publish `authority-feed/latest-authority-manifest.json`
- become discoverable by `agent-internet`

## Default files

- `docs/authority/charter.md` → canonical authority document
- `scripts/render_federation_descriptor.py` → writes the well-known descriptor
- `scripts/export_authority_feed.py` → writes a valid authority feed bundle

Replace the example content, keep the workflow wiring, and you have a live node.