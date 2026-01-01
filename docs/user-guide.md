# FlyFun European Aviation Portal - User Guide

## Table of Contents

- [Introduction](#introduction)
  - [What problem does FlyFun solve?](#what-problem-does-flyfun-solve)
- [Quick Start](#quick-start)
  - [The Interface](#the-interface)
- [Use Cases](#use-cases)
  - [1. Finding Airports Near a Location](#1-finding-airports-near-a-location)
  - [2. Using the Legend to Quickly Identify Airports](#2-using-the-legend-to-quickly-identify-airports)
  - [3. Using Filters for Precise Searches](#3-using-filters-for-precise-searches)
  - [4. Route Planning - Finding Airports Between Two Locations](#4-route-planning---finding-airports-between-two-locations)
  - [5. Short-Notice Flying - Example: Airports Near Etretat](#5-short-notice-flying---example-airports-near-etretat)
  - [6. Understanding Rules - Comparing Regulations Between Countries](#6-understanding-rules---comparing-regulations-between-countries)
  - [7. Exploring Rules in the Data Tab](#7-exploring-rules-in-the-data-tab)
  - [8. GA Friendliness Scores and Personas](#8-ga-friendliness-scores-and-personas)
- [Tips and Shortcuts](#tips-and-shortcuts)
- [Common Workflows](#common-workflows)
  - [Weekend Trip Planning](#weekend-trip-planning)
  - [Cross-Border Flight Preparation](#cross-border-flight-preparation)
  - [Weather Diversion Planning](#weather-diversion-planning)
- [Need Help?](#need-help)
- [Feedback](#feedback)
- [Data Sources and Limitations](#data-sources-and-limitations)
  - [Data Sources](#data-sources)
  - [Known Limitations](#known-limitations)
  - [Disclaimer](#disclaimer)

---

## Introduction

FlyFun is a European aviation portal designed to help General Aviation pilots navigate the complex landscape of aviation regulations, airport facilities, and flight planning requirements across 40+ European countries.

### What problem does FlyFun solve?

Planning a cross-border flight in Europe often means:
- Checking customs and border crossing requirements for each country
- Finding airports with the right facilities (fuel, procedures, landing fees)
- Understanding notification and PPR (Prior Permission Required) rules
- Cross-referencing multiple data sources (AIPs, NOTAMs, local regulations)

FlyFun consolidates this information into a single, searchable interface with:
- **Airport Database**: Facilities, procedures, fuel availability, and GA-friendliness scores from Euro AIP data
- **Country Regulations**: Customs rules, notification requirements, border crossing procedures
- **Smart Search**: Natural language queries via an AI chatbot
- **Visual Exploration**: Interactive map with color-coded legends

---

## Quick Start

### The Interface

The portal has three main areas:
- **Left Panel**: Chat interface for natural language queries
- **Center**: Interactive map of European airports
- **Right Panel**: Details, AIP data, Rules, and Relevance tabs

---

## Use Cases

### 1. Finding Airports Near a Location

**Using the Chatbot:**
```
Show me airports near Lyon
```

```
Find airports within 30nm of Nice
```

**Using the UI:**
1. Click the search box at the top
2. Type a location name or ICAO code
3. Use the "Locate" feature to set a radius search

---

### 2. Using the Legend to Quickly Identify Airports

The map legend (bottom-left) lets you color airports by different criteria:

| Legend Mode | What it Shows |
|------------|---------------|
| **Notification** | Customs/PPR easiness - Green = H24 (no notice), Red = 48h+ notice required |
| **Procedure** | IFR capability - Which airports have instrument approaches |
| **Border Entry** | Points of Entry - Where you can clear customs |
| **Country** | Airports colored by country |
| **Relevance** | GA-friendliness score based on your selected persona |

**Example: Finding Border Entry Points**
1. Click the Legend selector
2. Choose "Border Entry"
3. Airports with customs facilities will be highlighted
4. Click any airport to see details in the right panel

**Example: Finding Airports with Low Notification Requirements**
1. Select "Notification" legend mode
2. Green airports = H24 or very short notice
3. Yellow/Orange = moderate advance notice
4. Red = long advance notice (48h+)

---

### 3. Using Filters for Precise Searches

The filter panel lets you narrow down airports by specific criteria:

**Available Filters:**
- **Country**: ISO country code (FR, DE, GB, etc.)
- **Runway**: Hard surface, minimum length
- **IFR**: Has procedures, procedure type
- **Fuel**: AVGAS, Jet-A availability
- **Border**: Point of entry status
- **Hospitality**: Hotels, restaurants nearby
- **Notification**: Maximum hours notice required

**Example: Airports with IFR Procedures and AVGAS**
1. Open the Filters panel
2. Enable "Has Procedures"
3. Enable "Has AVGAS"
4. Map updates to show matching airports

---

### 4. Route Planning - Finding Airports Between Two Locations

One of FlyFun's most powerful features is finding suitable airports along a route.

**Using the Chatbot:**
```
Find airports between EGTF and LFMD with customs
```

```
Show me airports along a route from London to Nice with AVGAS and restaurants
```

**What you can search for along a route:**
- Customs clearance points (for border crossing)
- Fuel stops (AVGAS or Jet-A)
- Restaurants and hotels
- Airports with specific notification requirements
- IFR-capable airports for weather diversions

**Example: Planning a UK to South of France Trip**
```
Find airports between EGLL and LFMD with:
- Border entry (for customs)
- AVGAS
- Less than 24h notification
- Restaurant
```

The chatbot will return airports in the corridor between your origin and destination that match your criteria.

---

### 5. Short-Notice Flying - Example: Airports Near Etretat

**Scenario:** You want to fly to the Etretat cliffs in Normandy but can only give less than 24 hours notice.

**Chatbot Query:**
```
Show me airports near Etretat with less than 24 hours notification required
```

**Using Filters:**
1. Search for "Etretat" to center the map
2. Open Filters
3. Set "Max Notification Hours" to 24
4. Set a radius if needed
5. Review the results - green notification markers indicate easy access

**Results might include:**
- LFOH (Le Havre) - Easy access, commercial airport
- LFOS (St-Valery) - Small airfield, check notification requirements
- LFOP (Rouen) - Larger airport with procedures

---

### 6. Understanding Rules - Comparing Regulations Between Countries

**Scenario:** You're planning an IFR flight from Germany that will terminate VFR in France. What are the differences in IFR-to-VFR transition rules?

**Chatbot Query:**
```
What are the differences for IFR to VFR transitions between Germany and France?
```

The chatbot will:
1. Search regulations for both countries
2. Compare the relevant rules
3. Highlight key differences

**Other Rules Questions You Can Ask:**
```
What are the customs requirements for entering France from the UK?
```

```
Compare notification requirements between Switzerland and Italy
```

```
What documents do I need for a private flight to Spain?
```

---

### 7. Exploring Rules in the Data Tab

For deeper exploration of country regulations:

1. Click on any airport in a country
2. Open the **Rules** tab in the right panel
3. Browse all regulations for that country organized by category:
   - Customs & Border Crossing
   - Notifications & PPR
   - Fuel & Oil
   - Special Restrictions
   - Facilities & Services

**Pro Tip:** The Rules tab shows the empirical, consolidated rules from official sources. Use this to verify chatbot answers or explore regulations you didn't know to ask about.

---

### 8. GA Friendliness Scores and Personas

FlyFun includes a sophisticated "GA Friendliness" scoring system that ranks airports based on what matters most to your type of flying. Instead of a one-size-fits-all rating, you can select a **persona** that matches your mission profile.

#### What is GA Friendliness?

GA Friendliness combines multiple signals to score how suitable an airport is for General Aviation:

| Feature | What it Measures |
|---------|------------------|
| **Cost Score** | Landing fees, handling charges, fuel prices |
| **Hassle Score** | Bureaucracy, PPR complexity, customs friction |
| **Operations (IFR)** | IFR procedures quality, approach types available |
| **Operations (VFR)** | VFR friendliness, circuit patterns, noise restrictions |
| **Access Score** | Ease of getting to/from the airport, transport links |
| **Fun Score** | Interesting destination, scenic approaches, activities nearby |
| **Hospitality Score** | Restaurants, hotels at or near the airport |
| **Review Score** | Overall pilot satisfaction from community reviews |

#### Available Personas

Each persona weights these features differently:

**IFR Touring (SR22)** - Default persona
- Prioritizes: IFR capability (25%), Low hassle (20%), Reasonable cost (20%)
- Best for: Cross-country IFR flights, weather flexibility
- Example: Finds airports with good ILS/RNAV approaches and minimal paperwork

**VFR Budget Flyer**
- Prioritizes: Low cost (35%), Low hassle (25%), VFR operations (20%)
- Best for: Day trips, training flights, cost-conscious pilots
- Example: Finds grass strips and small airfields with minimal fees

**Lunch Stop**
- Prioritizes: Hospitality (35%), Fun factor (25%), Cost (15%)
- Best for: Day trips focused on a great meal or destination
- Example: Finds airports with on-field restaurants or nearby attractions

**Training Flight**
- Prioritizes: VFR operations (30%), Low cost (30%), Low hassle (20%)
- Best for: Touch-and-go practice, circuit work, student pilots
- Example: Finds quiet airfields that welcome training traffic

#### Using Personas

**In the UI:**
1. Click the persona selector (top of the page or in relevance panel)
2. Choose your mission type
3. Switch legend to "Relevance" mode
4. Map colors update to show GA-friendliness for your persona

**In the Chatbot:**
```
Show me GA-friendly airports near Munich for a lunch stop
```

```
Find low-hassle training airports within 50nm of London
```

#### Understanding the Relevance Tab

Click any airport and open the **Relevance** tab to see:
- Overall score for your selected persona
- Breakdown of each feature score
- Which features are boosting or hurting the score
- Comparison to other airports in the region

**Example: Comparing Two Airports**

| Feature | LFMD (Cannes) | LFMN (Nice) |
|---------|---------------|-------------|
| Cost Score | 0.3 (expensive) | 0.2 (very expensive) |
| Hassle Score | 0.6 (moderate) | 0.4 (bureaucratic) |
| IFR Operations | 0.9 (excellent) | 0.95 (excellent) |
| Hospitality | 0.8 (great) | 0.7 (good) |
| **IFR Touring Score** | **0.65** | **0.58** |

In this example, Cannes scores higher for IFR touring despite Nice having slightly better procedures, because Cannes is less expensive and less bureaucratic.

#### Where Does the Data Come From?

GA Friendliness scores combine:
1. **Pilot reviews** - Community feedback analyzed with NLP to extract sentiment on cost, hassle, operations, etc.
2. **AIP data** - Official airport information (procedures, facilities, hours)
3. **Fee data** - Landing fee information where available

---

## Tips and Shortcuts

| Action | How |
|--------|-----|
| Expand/collapse chat | `Ctrl+E` |
| Send message | `Enter` |
| New line in chat | `Shift+Enter` |
| Clear conversation | Click the clear button |
| Quick center on airport | Click any airport marker |

---

## Common Workflows

### Weekend Trip Planning
1. Set your persona to match your flying style (e.g., "VFR Day Tripper")
2. Use Legend mode "Relevance" to see GA-friendly airports
3. Filter by facilities you need (fuel, food)
4. Ask chatbot for specific routing advice

### Cross-Border Flight Preparation
1. Use route search to find border entry points
2. Check notification requirements for each country
3. Review customs rules in the Rules tab
4. Note any special restrictions

### Weather Diversion Planning
1. Filter for airports with IFR procedures
2. Check notification requirements (prefer H24 for flexibility)
3. Note fuel availability along your route

---

## Need Help?

The chatbot understands natural language - if you're unsure how to find something, just ask! Examples:
- "How do I find airports with restaurants?"
- "Show me all the airports I can land at without advance notice"
- "What's the easiest way to clear customs flying into France?"

---

## Feedback

If you find incorrect data or have suggestions for improvement, we'd love to hear from you. The rules and airport data are continuously being updated and improved based on pilot feedback.

---

## Data Sources and Limitations

### Data Sources

FlyFun consolidates data from multiple sources:

| Data Type | Source | Update Frequency |
|-----------|--------|------------------|
| **Airport facilities** | Euro AIP (Aeronautical Information Publication) | Periodic sync |
| **IFR procedures** | Euro AIP procedure database | Periodic sync |
| **Country regulations** | Official AIPs, consolidated and structured | Manual updates |
| **GA Friendliness reviews** | Community pilot reviews (airfield.directory, etc.) | Periodic extraction |
| **Landing fees** | Crowdsourced and official sources | When available |
| **Notification requirements** | AIP customs/handling sections, parsed and structured | Periodic updates |

### Known Limitations

**Airport Data:**
- Coverage is focused on **Europe** (40+ countries). Non-European airports are not included.
- Small grass strips and ultra-light fields may be missing or have incomplete data.
- Operating hours may not reflect temporary changes (check NOTAMs before flight).
- Fuel availability is based on AIP data; actual availability may vary.

**Notification Data:**
- Notification requirements are extracted from AIP text which can be ambiguous.
- Some airports have complex rules (weekday vs weekend, Schengen vs non-Schengen) that may be simplified.
- **Always verify** notification requirements directly with the airport before flight.
- H24 status may not account for holidays or seasonal closures.

**GA Friendliness Scores:**
- Scores are based on available reviews - airports with few or no reviews will show as "unknown".
- Review sentiment extraction uses NLP which may occasionally misinterpret context.
- Fee data is incomplete; many airports lack landing fee information.
- Scores reflect community perception which may be outdated if an airport has changed.

**Rules and Regulations:**
- Rules are consolidated from official sources but may not reflect recent amendments.
- Interpretation of complex regulations is simplified for clarity.
- **This is not legal advice** - always consult official sources (national AIPs, NOTAMs) for flight planning.
- Some country-specific exceptions may not be captured.

**Chatbot:**
- The AI chatbot may occasionally provide incorrect or outdated information.
- Complex multi-country comparisons may miss nuances.
- When in doubt, cross-reference with the Rules tab and official sources.

### Disclaimer

FlyFun is a **planning aid**, not a substitute for proper flight preparation. Pilots are responsible for:
- Verifying all information with official sources before flight
- Checking current NOTAMs and weather
- Ensuring compliance with all applicable regulations
- Confirming airport status, fuel availability, and notification requirements

The data provided is offered in good faith but without warranty. Aviation regulations change frequently - when planning actual flights, always use official, current sources.
