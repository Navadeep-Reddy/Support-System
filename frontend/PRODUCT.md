# Product

<!-- impeccable:product-schema 1 -->

## Platform

web

## Stack

React, TypeScript, Vite, Tailwind CSS, shadcn/ui, npm (as specified in the project brief).

## Users

Primary users are fictional demo customers Alex and Taylor, selecting their profile to ask questions about their account and receive support. Demo administrators may manage knowledge articles through an optional secondary screen.

## Product Purpose

The application demonstrates an AI support agent for a subscription-based SaaS product. Customers use chat for grounded policy answers, current subscription and payment information, and a simulated password-reset request that requires explicit confirmation. Success means the interface accurately presents persisted backend state and keeps customer data scoped to the selected demo session.

## Positioning

Support responses combine public knowledge articles with fresh, backend-verified account facts. State-changing password-reset requests are prepared and validated by the backend, then require customer approval before execution.

## Operating Context

This is a local demo application with two selectable fictional profiles and a backend-controlled demo session. Customers create, revisit, and reopen conversations. A reset link is simulated and non-operational; it does not change a password or send an email.

## Capabilities and Constraints

- Core frontend scope: demo profile selection, persistent conversation history, non-streaming chat, source citations, approval cards, and assistant-response feedback.
- Optional, last-priority capability: demo knowledge article management.
- The API uses JSON with snake_case fields, UUID IDs, credentialed requests, and `VITE_API_BASE_URL` (default backend origin `http://localhost:8000`).
- The interface must reflect actual backend results, handle loading and errors, render Markdown safely, and never infer that an action succeeded before the backend confirms it.
- No real authentication, password reset, email delivery, payment changes, or production administration role is part of this demo.

## Evidence on Hand

The product specification and frontend API contract are in the repository root as `SPEC.md` and `API_CONTRACT.md`. They define the fictional Alex and Taylor profiles, API behavior, and supported workflows. Do not invent customer testimonials, usage statistics, or real operational outcomes.

## Product Principles

- Present backend-confirmed facts, not simulated success.
- Keep customer identity and conversation history visibly scoped to the selected demo profile.
- Make approval explicit and distinguish a pending, rejected, and executed action.
- Ground policy guidance in cited knowledge articles.
