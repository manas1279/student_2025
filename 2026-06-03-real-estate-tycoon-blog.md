---
layout: post
title: Real Estate Tycoon — Sprint 9 Final Project Blog
description: >
  CS 113 capstone blog: architecture, data structures, algorithms, and OOP design
  decisions behind Real Estate Tycoon — a full-featured browser game on OCS GameEnginev1.1.
author: manas1279
date: 2026-06-03
permalink: /real-estate-tycoon/blog
toc: true
comments: true
category: Real Estate Tycoon
---

## Overview

**Real Estate Tycoon** is a browser-based investment simulation game built on the OCS GameEnginev1.1 framework. Players start with $500,000 in capital and must grow their net worth to $5,000,000 by buying, upgrading, and selling properties across three tiers — Residential, Commercial, and Luxury.

The game is the most architecturally complete project I built in this course. It features a clean MVC separation, five distinct game levels, three model singletons, custom data structure implementations (Queue, Set, binary search, Comparator-style sorting, Graph), and full `localStorage` persistence for leaderboards and portfolio state.

**Assigned to:** manas1279  
**Project source:** `_projects/games/real-estate-tycoon/`  
**Live game:** [/real-estate-tycoon](/real-estate-tycoon)

---

## Expected Goals ✅

- [x] MVC architecture with three model singletons (`PortfolioManager`, `MarketEngine`, `PropertyDatabase`)
- [x] Five game levels (Market Hub, Residential, Commercial, Luxury, Win Screen)
- [x] Real-time market simulation (Brownian motion + 10 economic event types)
- [x] Negotiation battle system (HP bar, lasers, inspection coins, shields)
- [x] Full financial CRUD: buy, sell, upgrade, take loans, collect rent
- [x] Progression gate system (Commercial unlocks at 3 properties; Luxury at 6)
- [x] Leaderboard with localStorage persistence (top 10, cross-session)
- [x] Win screen with Canvas market history chart and stat breakdown
- [x] 10 custom SVG character sprites and 4 background scenes

## Stretch Goals 🚀

- [x] Market Influence Graph: directed graph models price spillover across categories
- [x] FIFO EventQueue: structured deck-based event scheduling instead of pure random
- [x] Binary search for properties by price range (`searchByPriceRange`)
- [x] Comparator-style sorting on portfolio and property catalog (`sortBy`, `sortPortfolio`)
- [x] Set-based owned-type tracking (`getOwnedTypes`) and O(1) membership tests
- [x] Algorithm complexity analysis documented in code comments (Big-O throughout)
- [ ] Spring Boot backend leaderboard (REST API + JPA — planned for v2.1)
- [ ] JUnit tests for model logic (planned for v2.1)
- [ ] Docker + nginx deployment (planned for v2.1)

---

## My Contributions

### 1. MVC Architecture & Model Layer

Designed three model singletons that power all game logic without any view-layer coupling:

**`PortfolioManager.js`** — Financial CRUD with `localStorage` persistence. Handles buying/selling/upgrading properties, prorated rent collection (1 real minute = 1 game day), loan management (max 65% of net worth at 6.5% APR), and net worth calculation (cash + property values × market multipliers − debt). The transaction log is structured as a push-only stack so history is naturally ordered and `peekLastTransaction()` runs in O(1).

**`MarketEngine.js`** — Live market simulation via Brownian motion with mean-reversion (prices drift randomly but are pulled 0.1% per tick back toward 1.0x). On initialize, a shuffled `EventQueue` deck is pre-loaded so the 10 market events fire in pseudo-random order without repeating until all events have been seen once. When an event fires, a one-hop graph traversal applies spillover to neighboring market categories via `INFLUENCE_GRAPH`.

**`PropertyDatabase.js`** — Static catalog of 17 properties across 3 types and 3 price tiers. The full catalog is pre-sorted on load (O(n log n) once) into `ALL_SORTED` so `searchByPriceRange` can use binary search. The `getUnowned` method was refactored to build a `Set` from owned IDs, converting repeated O(n) `includes()` calls to O(1) `Set.has()` checks.

### 2. Data Structures Implemented

| Structure | Where | Complexity |
|-----------|-------|------------|
| **Array / List** | `properties[]`, `transactions[]`, price history ring buffer | push O(1), read O(n) |
| **Set** | `getOwnedTypes()`, `getUnowned()` ID membership | O(n) build, O(1) has() |
| **Stack** | Transaction log (LIFO — push via buy/sell, peek via `peekLastTransaction`) | O(1) push/peek |
| **Queue (FIFO)** | `EventQueue` for market event scheduling | O(1) enqueue, O(n) dequeue* |
| **Dictionary/Map** | `_mult` object (category → multiplier), `INFLUENCE_GRAPH` adjacency map | O(1) key lookup |
| **Graph** | `INFLUENCE_GRAPH` directed adjacency map (3 nodes, 6 edges) | O(V+E) traversal |

*Dequeue uses `Array.shift()` which is O(n); with n≤10 this is negligible. A linked-list implementation would give O(1) dequeue if the event set grew.

### 3. Algorithms Implemented

| Algorithm | Location | Complexity |
|-----------|----------|------------|
| **Binary search** (`searchByPriceRange`) | `PropertyDatabase.js` | O(log n + k) |
| **Comparator sort** (`sortBy`, `sortPortfolio`) | `PropertyDatabase.js`, `PortfolioManager.js` | O(n log n) |
| **Fisher-Yates shuffle** (`getDealSelection`, `EventQueue.refill`) | `PropertyDatabase.js`, `MarketEngine.js` | O(n) |
| **Brownian motion with mean-reversion** (`tick`) | `MarketEngine.js` | O(1) per tick |
| **BFS-style one-hop graph traversal** (spillover in `triggerEvent`) | `MarketEngine.js` | O(V+E) |
| **Linear search** (`getById`, `EVENTS.find`) | `PropertyDatabase.js`, `MarketEngine.js` | O(n) |
| **Prorated rent formula** (`collectRent`) | `PortfolioManager.js` | O(k) properties |

### 4. OOP Design Patterns

**Inheritance & Polymorphism** — `GameLevelPropertyDeal` is the abstract base class for all three deal levels. It holds the shared battle state (HP, shields, lasers, coin system) and defines the lifecycle methods. `GameLevelResidential`, `GameLevelCommercial`, and `GameLevelLuxury` each call `super(gameEnv, config)` with overridden config values (seller HP, shield count, fire rate, background image) — a classic template-method + constructor-injection pattern.

**Singleton** — `PortfolioManager` and `MarketEngine` are both exported as `export default new ClassName()`, ensuring a single shared instance across all levels and preventing state fragmentation.

**Encapsulation** — All portfolio mutations go through `PortfolioManager`'s public API; raw data is never written directly by levels. Internal fields (`_cache`, `_mult`, `_eventQueue`) are name-prefixed private and `_persist()` is called by every mutating method automatically.

**Abstraction** — `PropertyDatabase` hides whether a lookup is linear or binary-searched behind the same method signature. Callers of `searchByPriceRange` do not need to know that `ALL_SORTED` exists or that a lower-bound binary search is in play.

### 5. Market Hub & Real-Time Systems

`GameLevelMarketHub.js` runs six concurrent systems:
1. **Portfolio HUD** — real-time net worth, cash, monthly income, debt, and per-category market multipliers updated every animation frame.
2. **Market ticker** — horizontally scrolling price feed and event announcements pulled from `MarketEngine.getTickerText()`.
3. **Event banner** — full-width animated notification fired when the `MarketEngine` emits an `'event'` notification.
4. **Rent coins** — floating coins spawning every 2.5s from each owned property; collecting triggers `PortfolioManager.collectRent()`.
5. **NPC interaction** — five brokers with context-aware callbacks; Commercial/Luxury gates call `getOwnedTypes()` (Set check) before entering a deal level.
6. **Win condition** — polls `PortfolioManager.getNetWorth()` each frame; transitions to `GameLevelWinScreen` at $5M.

---

## Software Engineering Practices

- **MVC separation**: All game state is owned by the model layer. Levels are views that query models and call model APIs — they never write directly to localStorage.
- **Iterative development**: Built in four layers — models first, hub level, battle levels, win screen — with a playable milestone at each step.
- **GitHub workflow**: Feature branch → atomic commits per subsystem → PR with design-notes doc for review.
- **Defensive coding**: All `localStorage` access is wrapped in try/catch with graceful defaults for private/incognito sessions.
- **SDLC documentation**: `docs/game.md` (user guide) and `docs/REAL-ESTATE-TYCOON.md` (architecture) maintained throughout development.
- **Algorithm complexity analysis**: Big-O annotations in JSDoc comments on every method with non-trivial complexity (`PropertyDatabase.js`, `PortfolioManager.js`, `MarketEngine.js`).

---

## Technical Concepts Applied

| CS 113 Area | Implementation in Real Estate Tycoon |
|---|---|
| **Lists** | `properties[]` and `transactions[]` arrays with add/remove/iterate operations |
| **Stacks** | Transaction log as LIFO stack; `peekLastTransaction()` O(1) stack peek |
| **Queues** | `EventQueue` FIFO class; shuffled deck of market events dequeued in order |
| **Sets** | `getOwnedTypes()` returns `new Set`; `getUnowned()` uses Set for O(1) membership |
| **Dictionaries/Maps** | `_mult` map (category → float), `INFLUENCE_GRAPH` adjacency map |
| **Graphs** | `INFLUENCE_GRAPH` directed graph (3 nodes, 6 weighted edges); one-hop traversal in `triggerEvent` models economic spillover |
| **Searching** | Binary search in `searchByPriceRange`; linear search in `getById` |
| **Sorting** | Comparator-style `sortBy(field, ascending)` and `sortPortfolio(field)` using Array.sort |
| **Algorithm Analysis** | O(log n), O(n log n), O(1), O(V+E) annotations in JSDoc throughout models |
| **OOP — Inheritance** | `GameLevelPropertyDeal` → `GameLevelResidential` / `Commercial` / `Luxury` |
| **OOP — Polymorphism** | All three subclasses override config via constructor injection; same `classes` interface consumed by `GameControl` |
| **OOP — Encapsulation** | Private `_field` convention; all mutations via public API; `_persist()` called internally |
| **OOP — Abstraction** | `searchByPriceRange` hides binary search; `getMultiplier` hides Brownian state |
| **Design Patterns** | Singleton (PortfolioManager, MarketEngine), MVC, Observer (event listeners), Template Method (PropertyDeal subclasses) |
| **Event-Driven Programming** | `MarketEngine.addListener` / `removeListener` pub/sub; NPC `interact()` callbacks; coin collision handlers |
| **Canvas / Rendering** | Win-screen market history chart via HTML5 Canvas 2D API (axis labels, legend, three price lines) |
| **Storage / Persistence** | `localStorage` with versioned keys and 5-min TTL cache invalidation |
| **Deployment** | Jekyll Notebook page at `/real-estate-tycoon`; ES module imports via `@assets` alias |

---

## Key Challenges

**1. Sub-level HUD teardown** — Entering a deal level from the hub left the portfolio HUD, ticker, and rent coins rendering on top of the battle screen. Fixed by implementing `_setUiVisible(false/true)` that hides all hub DOM elements on sub-level entry and restores them via the `parentControl.resume` hook when returning.

**2. Brownian motion stability** — An unclamped random walk caused prices to drift to extreme values within minutes. Added mean-reversion (each tick pulls the multiplier 0.1% back toward 1.0) and hard clamps at [0.55, 2.2] to keep the market plausible.

**3. Set vs. Array for ownership checks** — The original `getUnowned()` called `Array.includes()` inside a filter — O(n²) for large portfolios. Refactored to build a `Set` from owned IDs first (O(k)), then use `Set.has()` inside the filter (O(1) per check), making the overall operation O(n + k).

**4. Graph spillover calibration** — The first `INFLUENCE_GRAPH` weights were too high: a residential boom would overshoot the luxury multiplier cap. Tuned weights iteratively (residential → commercial: 0.25; commercial → luxury: 0.35) until cross-category effects felt economically plausible without hitting the 2.2× ceiling during compounding events.

**5. Progression gate UX** — Players needed clear feedback when Marcus or Victoria were locked. Implemented `_showToast()` — a temporary overlay message — to surface the lock reason without an intrusive modal.

---

## What I Learned

The biggest lesson was that data structure choice is visible to users even in a game. Replacing `Array.includes()` with `Set.has()` in `getUnowned()` is an O(n²) → O(n) improvement that's imperceptible at 17 properties but would matter at scale — and documenting *why* the Set exists makes the code easier to extend later.

The market influence graph was the most creative design decision. Modeling economic spillover as a directed weighted graph — rather than hardcoding per-event cross-category adjustments — means adding a new event type only requires editing the `EVENTS` array, not touching spillover logic. The graph is data, not control flow.

Building the `EventQueue` exposed a real tradeoff: `Array.shift()` is O(n), and a linked list would be O(1). For 10 events it's irrelevant, but writing the comment explaining *why* the simpler implementation is acceptable here (and when it wouldn't be) is a skill I'll carry into larger projects.

---

## Future Goals

- **Spring Boot leaderboard backend**: Replace `localStorage` leaderboard with a REST API (POST score on win, GET top-10 on load) backed by Spring Boot + JPA/Hibernate, making high scores publicly visible and cross-device.
- **JUnit test suite**: Unit tests for `PortfolioManager` CRUD, binary search edge cases (min = 0, max = ∞), and `EventQueue` enqueue/dequeue behavior.
- **Docker + nginx deployment**: Containerize the Spring Boot backend with a `Dockerfile` and `docker-compose.yml`; configure nginx as reverse proxy so `/api/leaderboard` routes to the JVM service.
- **AI advisor NPC**: Integrate the Claude API to add a financial advisor NPC that analyzes the player's portfolio composition and current market multipliers, recommending buy/sell actions with confidence scores.

---

## Overall Conclusions

1. **MVC pays off immediately** — isolating all financial logic in `PortfolioManager` meant adding loan repayment and property upgrade mechanics required zero changes to any rendering code.

2. **Data structure choice is a design decision** — switching from `Array.includes()` to `Set.has()` in `getUnowned()` improved asymptotic complexity and made the code's intent clearer. The choice of *which* structure you use communicates the expected access pattern to the next reader.

3. **Graphs aren't just for social networks** — modeling market category influence as a directed weighted adjacency map let me add economic realism (commercial booms lift luxury demand) without hardcoding relationships into every event definition. The graph is the configuration; the traversal is the engine.

4. **The `parentControl.resume` handshake was the hardest bug** — getting hub UI to tear down cleanly when entering a sub-level, and restore exactly when returning, required understanding the engine's lifecycle at a level the docs didn't cover. Reading source code was the only way through.

5. **Polish is engineering** — the gap between "it works" and "it feels right" (animated tickers, floating coins, spillover market events, event banners) is where most of the final engineering time goes. That polish is what makes users understand what the code is doing without reading it.
