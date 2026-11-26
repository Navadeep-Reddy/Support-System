---
version: 1
slug: "src-app-tsx"
primary_target: "src/App.tsx"
related_targets: []
---

# Support workspace

## Scope and visitor mode

Operate: a responsive support application spanning demo login/profile switching, conversations and saved history, chat with citations, deterministic password-reset approvals, assistant feedback, and demo knowledge article CRUD.

## Audience and task

Alex and Taylor are fictional demo customers using account-scoped support. They need straightforward, grounded answers, current account context, and clear next steps. Demo administrators can maintain knowledge articles. The first screen must make the support interaction and selected profile immediately legible.

## Content, evidence, and constraints

Use only the contract's fictional profile data and truthful API states. Distinguish a pending approval from an executed reset; state that reset links are simulated. Keep conversation history, citations, and account details in clear separate roles. Build against the complete `API_CONTRACT.md`; use typed fixtures in development and keep live integration behind the API client. No real authentication, payment mutation, reset, or email.

## Direction contract

THESIS: A community noticeboard makes the next support step unmistakable while keeping the conversation central.

OWN-WORLD: Deep blue navigation, cool pale blue-green grounds, crisp white working surfaces, readable humanist typography, and a warm amber highlight for selected navigation and important decisions.

STORY: The selected demo profile opens a familiar support workspace; the customer reads a grounded answer, checks its cited source, and can decide explicitly on any simulated action.

FIRST VIEWPORT: A deep blue navigation rail identifies the support workspace and active demo customer. A pale history rail and compact account column flank a white central conversation with the preview notice, messages, sources and a clearly framed approval. Amber marks the selected navigation; dark blue marks primary actions. On small screens the navigation becomes a drawer and the conversation remains accessible.

FORM: Community noticeboard, fifth grounded direction, selected from the direction board; seed:2be004312a6ae858.

FINISH: unreviewed and undocumented is unfinished; this build ends with the finish review, the verdict, DESIGN.md, and every shipping raster carrying its provenance

## Unresolved decisions

Use responsive web behavior. Connect the API only in a later integration phase; retain typed API methods and explicit development fixtures now. The knowledge-management screen is included in this frontend build.
