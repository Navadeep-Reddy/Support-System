---
name: Support demo
description: A clear community noticeboard for a fictional support experience.
colors:
  primary: "#253E5A"
  primary-hover: "#172C43"
  highlight: "#e8a84a"
  neutral-bg: "#EDF3F2"
  surface: "#FFFFFF"
  rail: "#E1EEEB"
  ink: "#253E5A"
  muted: "#526A70"
  border: "#CFDEDB"
  success: "#2D7651"
  warning: "#8B5B16"
  danger: "#AD4237"
typography:
  display:
    fontFamily: "Nunito Sans, Segoe UI, sans-serif"
    fontSize: "clamp(32px, 4vw, 45px)"
    fontWeight: 850
    lineHeight: 1.08
  headline:
    fontFamily: "Nunito Sans, Segoe UI, sans-serif"
    fontSize: "20px"
    fontWeight: 850
  body:
    fontFamily: "Nunito Sans, Segoe UI, sans-serif"
    fontSize: "14px"
    lineHeight: 1.5
  label:
    fontFamily: "Nunito Sans, Segoe UI, sans-serif"
    fontSize: "11px"
    fontWeight: 700
rounded:
  control: "8px"
  panel: "10px"
  pill: "999px"
spacing:
  sm: "8px"
  md: "12px"
  lg: "16px"
  xl: "24px"
components:
  button-primary:
    backgroundColor: "{colors.primary}"
    textColor: "{colors.surface}"
    rounded: "{rounded.control}"
  button-primary-hover:
    backgroundColor: "{colors.primary-hover}"
    textColor: "{colors.surface}"
    rounded: "{rounded.control}"
  card:
    backgroundColor: "{colors.surface}"
    textColor: "{colors.ink}"
    rounded: "{rounded.panel}"
---

# Design System: Support demo

## Overview

**Creative North Star: "The Community Noticeboard"**

A deep blue navigation shell frames cool, pale support surfaces. White conversation and reading areas stay visually central; amber highlights the selected destination and lends emphasis to approval states. The result is distinctive but familiar to operate.

**Key Characteristics:**
- Deep blue navigation and primary controls
- Pale blue-green supporting regions and white reading surfaces
- Lime selection and clearly labelled approval states
- Humanist typography and concise, scannable groupings

## Colors

Deep blue provides the main ink, navigation, and primary controls. Cool pale greens separate supporting areas from white working surfaces. Amber marks the selected navigation and supports the framed approval treatment. Semantic green, amber, and red communicate success, waiting, and failure with explicit text.

## Typography

Nunito Sans, with Segoe UI and sans-serif fallbacks, is used throughout. Conversation copy is 14px; headings and labels establish a compact hierarchy. Tabular numerals help account amounts and timestamps scan consistently.

## Layout

The desktop shell uses a navigation rail beside the main workspace. Chat places conversation history, the active conversation, and account context in separate columns. Below 1260px account context yields space; at 900px the navigation becomes a drawer; at 680px conversation history stacks above the conversation. Knowledge and account views also collapse to fit narrow screens.

## Elevation & Depth

Tonal surfaces and fine borders do most of the separation. Soft shadows distinguish the main work surface, profile menu, and login shell without strong visual elevation.

## Shapes

Panels and controls use modest rounded corners and fine borders. Status badges remain pill-shaped, while avatars are circular.

## Components

Primary buttons use deep blue with white text; secondary buttons use a white background and border. Focus has a visible amber outline. The selected navigation item uses an amber background and dark text. Approval cards use a full green border, explanatory text, and explicit controls; a local approval is not represented as execution. Source labels remain separate from assistant content. Raw Markdown HTML is skipped.

## Do's and Don'ts

### Do:
- **Do** keep the selected customer, preview status, and conversation easy to identify.
- **Do** use explicit labels alongside state colors.
- **Do** preserve readable conversation content and responsive navigation.
- **Do** distinguish local approvals from executed reset requests.

### Don't:
- **Don't** let supporting regions obscure the conversation.
- **Don't** present a simulated link as operational or a local approval as an executed action.
- **Don't** render raw Markdown HTML.
