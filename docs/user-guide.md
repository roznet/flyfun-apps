# FlyFun European Aviation Portal – User Guide (Work in Progress)

## Table of Contents

- [Introduction](#introduction)
  - [What is FlyFun trying to do?](#what-is-flyfun-trying-to-do)
- [Quick Start](#quick-start)
  - [The Interface](#the-interface)
- [Use Cases (Examples, Not Guarantees)](#use-cases-examples-not-guarantees)
  - [1. Finding Airports Near a Location](#1-finding-airports-near-a-location)
  - [2. Using the Legend to Explore Data](#2-using-the-legend-to-explore-data)
  - [3. Using Filters for Narrowing Things Down](#3-using-filters-for-narrowing-things-down)
  - [4. Route Planning Experiments](#4-route-planning-experiments)
  - [5. Short-Notice Flying – A Realistic Scenario](#5-short-notice-flying--a-realistic-scenario)
  - [6. Comparing Rules Between Countries (Experimental)](#6-comparing-rules-between-countries-experimental)
  - [7. Browsing Rules in the Data Tab](#7-browsing-rules-in-the-data-tab)
  - [8. GA Friendliness Scores & Personas (Very Much WIP)](#8-ga-friendliness-scores--personas-very-much-wip)
- [Tips and Shortcuts](#tips-and-shortcuts)
- [Common Workflows (How It *Might* Be Used)](#common-workflows-how-it-might-be-used)
- [Feedback & Contributions](#feedback--contributions)
- [Data Sources and Limitations](#data-sources-and-limitations)
  - [Data Sources](#data-sources)
  - [Known Limitations](#known-limitations)
  - [Disclaimer](#disclaimer)

---

## Introduction

FlyFun is an **experimental** European aviation project exploring a simple question:

> *Can large language models and modern UI tooling actually help General Aviation pilots deal with the messy, fragmented reality of European flying?*

This repository (and the app it powers) is **very much a work in progress**. Some parts work reasonably well, some are rough, and some are still ideas that haven’t fully proven themselves yet.

The goal is not to claim a finished product, but to **learn**, iterate, and hopefully get feedback from other pilots and builders along the way.

### What is FlyFun trying to do?

Anyone who has planned a GA flight across European borders knows the pain points:

- Customs and border rules vary by country (and sometimes by airport)
- Notification and PPR requirements are often buried in AIPs
- Airport “friendliness” is subjective, undocumented, and experience-based
- Information is fragmented across PDFs, websites, forums, and hearsay

FlyFun is an attempt to:
- Collect *some* of this information in a structured way
- Experiment with letting an LLM help explore it
- See whether a map‑based UI plus chat can reduce friction
- Learn where this approach completely falls apart 😄

Nothing here should be treated as authoritative or complete — it’s an ongoing experiment.

---

## Quick Start

### The Interface

The current UI is split into three main areas:

- **Left Panel** – A chat interface where you can ask questions in plain language  
- **Center** – An interactive map showing European airports  
- **Right Panel** – Tabs with airport details, extracted AIP data, rules, and relevance scoring  

Expect rough edges. Things will change.

---

## Use Cases (Examples, Not Guarantees)

The sections below describe **intended or hoped-for usage**, not promises. Results depend heavily on data quality and interpretation.

### 0. List of prompt ideas to try:

- Find airports along the route from EGTF to LFMD that have customs facilities
- Find airports near Etretat with AVGAS fuel
- What are the details for airport LFQA?
- Which airport have less than 24h notice near Etretat
- What are the aviation rules for France?
- Compare customs rules between France and UK
- Show me airports in Germany
- Route from Geneva to Barcelona
- Show me airports near Lyon with AVGAS and instrument approaches
- What should i know about use of Transponder in Germany
- How is the IFR routing philosophy: route availability, and how hard the system is on validation in France
- Anything to know about Restricted zone if i go to France?
- Tell me about IFR/VFR transition differences between Germany, UK and Belgium


### 1. Finding Airports Near a Location

**Using the Chatbot (best-effort):**
```
Show me airports near Lyon
```

```
Find airports within 30nm of Nice
```

**Using the UI:**
1. Type a location or ICAO code in the search box
2. Center the map
3. Optionally apply a radius filter

This generally works, but edge cases exist.

---

### 2. Using the Legend to Explore Data

The legend (bottom-left) lets you color airports using different datasets:

| Mode | What It Tries to Show |
|-----|----------------------|
| **Notification** | Estimated notice / PPR friction |
| **Procedure** | Presence of IFR procedures |
| **Border Entry** | Customs / entry points |
| **Country** | Simple country grouping |
| **Relevance** | GA friendliness score (experimental) |

This is meant for **exploration**, not decision-making.

---

### 3. Using Filters for Narrowing Things Down

Filters let you reduce clutter and focus on what *might* matter:

- Country
- Runway surface / length
- IFR availability
- Fuel types
- Border entry status
- Approximate notification requirements
- Nearby hospitality

Filters reflect parsed data — not real-time truth.

---

### 4. Route Planning Experiments

One of the main experiments in FlyFun is corridor-based search.

**Example:**
```
Find airports between EGTF and LFMD with customs
```

The idea is to:
- Define a rough route
- Look for “interesting” or “useful” airports along it
- Reduce manual scanning of charts and lists

This is one of the areas where feedback is especially welcome.

---

### 5. Short-Notice Flying – A Realistic Scenario

**Scenario:** You want to fly somewhere nice tomorrow, with limited notice.

```
Show me airports near Etretat with less than 24h notification
```

This combines:
- Geographic filtering
- Parsed notification rules
- A healthy amount of optimism

Always double-check before acting.

---

### 6. Comparing Rules Between Countries (Experimental)

Another experiment is using the LLM to *compare* structured rule data.

```
Compare notification requirements between Switzerland and Italy
```

This can be helpful for spotting differences, but:
- Rules are simplified
- Nuances are often lost
- Interpretation errors are possible

Treat this as a starting point, not an answer.

---

### 7. Browsing Rules in the Data Tab

If you don’t trust the chatbot (fair), you can browse the raw-ish data:

1. Click an airport
2. Open the **Rules** tab
3. Browse country-level rules by category

This reflects the current state of data extraction and structuring.

---

### 8. GA Friendliness Scores & Personas (Very Much WIP)

This is probably the most speculative part of FlyFun.

The idea:
- Airports feel very different depending on your mission
- “GA friendly” means different things to different pilots

Personas attempt to weight things like:
- Cost
- Bureaucracy
- IFR/VFR usability
- Hospitality
- Subjective “fun”

These scores are **not objective**, **not validated**, and mostly here to see whether this concept is even useful.

---

## Tips and Shortcuts

| Action | Shortcut |
|------|----------|
| Expand / collapse chat | `Ctrl+E` |
| Send message | `Enter` |
| New line | `Shift+Enter` |
| Clear chat | Button in chat |
| Center map on airport | Click marker |

---

## Common Workflows (How It *Might* Be Used)

### Weekend Trip Planning
- Explore airports visually
- Apply a persona
- Narrow down by food, fuel, and hassle
- Verify everything elsewhere 😉

### Cross-Border Prep
- Identify potential entry points
- Look at notification patterns
- Read raw rules

### Weather Backup Thinking
- Find IFR-capable alternates
- Prefer low-notice airports
- Keep expectations realistic

---

## Feedback & Contributions

Feedback is the whole point of this project.

If you find:
- Wrong data
- Misleading interpretations
- UI friction
- Ideas that don’t work at all

…that’s extremely useful.

This is an exploration, not a product launch.

---

## Data Sources and Limitations

### Data Sources

FlyFun pulls from a mix of:
- European AIPs
- Parsed procedure data
- Community reviews (where available)
- Manual structuring and experimentation

Update cadence and completeness vary widely.

---

### Known Limitations

- Data may be incomplete, outdated, or misinterpreted
- Notification rules are especially tricky
- Small airfields are underrepresented
- GA friendliness scoring is subjective
- The LLM can be confidently wrong

---

### Disclaimer

FlyFun is a **learning and exploration tool**.

It is **not**:
- Flight planning software
- A legal reference
- A substitute for official sources

Always verify information with:
- National AIPs
- NOTAMs
- Airports directly

If FlyFun helps you think or explore more easily, great.
If it exposes how hard this problem really is, that’s also a success.