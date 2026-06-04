---
layout: post
title: Real Estate Tycoon - Architecture and Design Notes
description: Technical architecture document covering system design, data flow, and implementation decisions for the Real Estate Tycoon browser game built on OCS GameEnginev1.1.
category: Projects
breadcrumb: true
permalink: /real-estate-tycoon/docs
---

## Overview

Real Estate Tycoon is the most architecturally complete game I built in this course. It runs entirely in the browser with no server dependency beyond static file hosting, and combines a full MVC separation, real-time market simulation, a negotiation battle mechanic for property acquisition, and a complete financial management layer backed by `localStorage` persistence.

The game starts the player with $500,000 in capital. The win condition is reaching $5,000,000 in net worth by buying, upgrading, and selling properties across three market tiers. Properties are acquired through negotiation battles against broker NPCs — each battle determines the purchase discount the player receives. Market prices shift continuously via Brownian motion and periodic economic events that ripple across categories through a directed influence graph.

```mermaid
graph TB
    subgraph "Player Journey"
        Start["Start — $500K cash"] --> Hub
        Hub["Market Hub\nWalk around, interact with NPCs"]
        Hub --> R["Residential Deal\nSarah — 10 HP, 4 shields"]
        Hub --> C["Commercial Deal\nMarcus — 15 HP, 3 shields\nrequires 3+ properties"]
        Hub --> L["Luxury Deal\nVictoria — 20 HP, 2 shields\nrequires 6+ properties"]
        R & C & L --> Hub
        Hub -->|"net worth >= $5M"| Win["Win Screen\nStats + Chart + Leaderboard"]
    end

    subgraph "Always Running"
        ME["MarketEngine\nBrownian motion + events + graph"]
        PM["PortfolioManager\nCRUD + localStorage"]
    end

    Hub -.->|reads + writes| ME
    Hub -.->|reads + writes| PM
```

---

## Directory Structure

```
_projects/real-estate-tycoon/
├── Makefile
├── levels/
│   ├── GameLevelMarketHub.js      # Main game world
│   ├── GameLevelPropertyDeal.js   # Base negotiation battle class
│   ├── GameLevelResidential.js    # Residential tier deals
│   ├── GameLevelCommercial.js     # Commercial tier deals
│   ├── GameLevelLuxury.js         # Luxury tier deals
│   └── GameLevelWinScreen.js      # Victory screen + leaderboard
├── model/
│   ├── PortfolioManager.js        # Financial state + localStorage
│   ├── MarketEngine.js            # Live market simulation
│   └── PropertyDatabase.js        # 17-property catalog + search/sort
├── images/
│   ├── city_background.svg        # Main city skyline
│   ├── bg_residential.svg         # Residential deal background
│   ├── bg_commercial.svg          # Commercial deal background
│   ├── bg_luxury.svg              # Luxury deal — sunset beach
│   ├── player_investor.svg        # Player character sprite
│   ├── broker_residential.svg     # Sarah NPC
│   ├── broker_commercial.svg      # Marcus NPC
│   ├── broker_luxury.svg          # Victoria NPC
│   ├── bank_manager.svg           # Bank NPC
│   └── property_manager.svg       # Alex NPC
└── docs/
    └── REAL-ESTATE-TYCOON.md
```

```mermaid
graph LR
    subgraph "levels/"
        Hub["GameLevelMarketHub"]
        Base["GameLevelPropertyDeal\nbase class"]
        Res["GameLevelResidential"]
        Com["GameLevelCommercial"]
        Lux["GameLevelLuxury"]
        Win2["GameLevelWinScreen"]
        Base --> Res & Com & Lux
    end

    subgraph "model/"
        PM2["PortfolioManager\nsingleton"]
        ME2["MarketEngine\nsingleton"]
        PD["PropertyDatabase\nstatic catalog"]
    end

    Hub -->|"imports"| PM2 & ME2 & PD
    Res & Com & Lux -->|"imports"| PM2
    Win2 -->|"imports"| PM2 & ME2
```

---

## Game Systems

### Market Engine — MarketEngine.js

The market engine is a singleton that drives all price simulation in the game. It runs on the browser's animation frame loop, called by the hub level's `update()` method every frame. Three market categories — residential, commercial, luxury — each maintain a price multiplier that the engine continuously adjusts.

**Brownian motion with mean-reversion** — Each tick, the engine adds a random delta in [-0.02, +0.02] to the category multiplier, then applies a 0.1% pull back toward 1.0. Without mean-reversion, prices drift to extremes over time; without the random delta, they converge to exactly 1.0 and stay there. Hard clamps at [0.55, 2.2] prevent runaway values.

**Event scheduling via FIFO queue** — Instead of triggering events randomly each time, the engine pre-fills an `EventQueue` with a Fisher-Yates shuffle of all 10 event types. Events dequeue in that shuffled order, so every event fires exactly once before any can repeat. The queue auto-refills when empty.

**Market influence graph** — When an event fires on one category, a one-hop traversal of `INFLUENCE_GRAPH` applies weighted spillover to adjacent categories. A residential boom nudges commercial; commercial growth lifts luxury demand. This models real cross-sector market behavior without hardcoding per-event cross-effects.

```mermaid
graph LR
    subgraph "INFLUENCE_GRAPH — Weighted Directed Edges"
        R["Residential"]
        C["Commercial"]
        L["Luxury"]

        R -->|"0.25"| C
        C -->|"0.35"| L
        L -->|"0.20"| C
        C -->|"0.15"| R
        R -->|"0.10"| L
        L -->|"0.05"| R
    end
```

The edge weights were calibrated through playtesting. The first attempt used weights around 0.5–0.8, which caused compounding spikes that hit the 2.2x ceiling almost immediately. The final weights keep cross-category effects noticeable but not dominant — a residential housing boom is felt in commercial prices, but not so strongly that it overrides commercial's own random walk.

**Price history buffer** — The engine maintains a ring buffer of up to 60 data points per category. This history is consumed by the Win Screen's Canvas chart to draw the three-line price history graph.

**localStorage caching** — Market state (current multipliers, event queue position, price history) is written to `localStorage` with a 5-minute TTL. Refreshing the page mid-game restores market state rather than resetting it.

```mermaid
flowchart TD
    Tick["tick() — each animation frame"] --> Delta["Add random delta ±0.02"]
    Delta --> Revert["Apply 0.1% mean-reversion toward 1.0"]
    Revert --> Clamp["Clamp to 0.55 – 2.20"]
    Clamp --> Buffer["Append to priceHistory ring buffer"]
    Buffer --> Check{"Event timer elapsed?"}
    Check -- "No" --> Tick
    Check -- "Yes" --> Dequeue["EventQueue.dequeue()"]
    Dequeue --> Empty{"Queue empty?"}
    Empty -- "Yes" --> Refill["refill() — Fisher-Yates shuffle"]
    Refill --> Apply
    Empty -- "No" --> Apply["Apply event delta to primary category"]
    Apply --> Spillover["INFLUENCE_GRAPH one-hop traversal\nApply weighted delta to neighbors"]
    Spillover --> Emit["Emit 'event' notification to listeners"]
    Emit --> Tick
```

---

### Portfolio Manager — PortfolioManager.js

PortfolioManager is the sole source of truth for all financial state. It is the only class that reads from or writes to `localStorage` for portfolio data. All level code accesses financial state through this singleton's public API.

**Starting capital:** $500,000

| Operation | What it does | Complexity |
|-----------|-------------|------------|
| `buyProperty(id, price)` | Deducts cash, adds property to portfolio array | O(1) |
| `sellProperty(id)` | Returns market-adjusted price, removes from portfolio | O(n) search |
| `upgradeProperty(id)` | Level up to 3; costs 15–45% of purchase price; rent +30% | O(n) search |
| `takeLoan(amount)` | Adds cash, adds debt. Hard cap: 65% of net worth at 6.5% APR | O(1) |
| `collectRent()` | Prorated by elapsed time — 1 real minute equals 1 game day | O(k) properties |
| `getNetWorth()` | Cash + sum(price × multiplier) − totalDebt | O(k) properties |
| `getLeaderboard()` | Top-10 array sorted by score from localStorage | O(1) |

**Net worth formula:**

```
netWorth = cash
         + sum( property.purchasePrice × market.getMultiplier(property.type) )
           for each property in portfolio
         − totalDebt
```

```mermaid
flowchart LR
    Cash["Cash\n$500K start"] -->|"buyProperty()"| Deduct["Cash decreases\nProperty added to array"]
    Cash -->|"takeLoan()"| Loan["Cash increases\nDebt increases"]
    Deduct -->|"collectRent()"| Income["Cash increases\nProrated by elapsed time"]
    Income -->|"sellProperty()"| Sale["Cash increases\nProperty removed"]
    Sale -->|"upgradeProperty()"| Upgrade["Cash decreases\nRent value boosted 30%"]

    Loan -->|"getNetWorth()"| NW["Net Worth =\nCash\n+ Σ(price × multiplier)\n− totalDebt"]
    Income --> NW
    Upgrade --> NW
    Sale --> NW
```

**Transaction log** — Every buy, sell, upgrade, and loan is pushed to `_transactions[]`. The array is treated as a LIFO stack: `peekLastTransaction()` returns `_transactions[_transactions.length - 1]` in O(1). The full array is available for history iteration.

**Persistence invariant** — Every mutating method calls `_persist()` as its final step. This means the in-memory state and the localStorage state are always in sync. If the page is refreshed at any point, `_load()` restores the exact state the player had.

```mermaid
stateDiagram-v2
    [*] --> Browsing : game starts, portfolio loaded
    Browsing --> Negotiating : player enters deal level
    Negotiating --> WonDeal : seller HP depleted
    Negotiating --> LostDeal : player shields depleted
    WonDeal --> Browsing : buyProperty() called with discount
    LostDeal --> Browsing : return to hub, no purchase
    Browsing --> Upgrading : player selects owned property
    Upgrading --> Browsing : upgradeProperty() called
    Browsing --> Selling : player selects owned property
    Selling --> Browsing : sellProperty() called
    Browsing --> WinScreen : getNetWorth() >= 5000000
    WinScreen --> [*]
```

---

### Property Database — PropertyDatabase.js

The property database is a static catalog of 17 properties across three market tiers. It is imported as a plain module (not a singleton) since its data never changes at runtime — it only provides querying methods.

| Type | Count | Price Range | Monthly Rent |
|------|-------|-------------|--------------|
| Residential | 6 | $145K – $1.4M | $1,150 – $11,000 |
| Commercial | 6 | $210K – $2.8M | $2,100 – $32,000 |
| Luxury | 5 | $3.2M – $18M | $24,000 – $175,000 |

**Initialization** — On first import, all 17 properties are sorted by price into `ALL_SORTED` via a comparator sort (O(n log n), paid once). This pre-sorted array is never modified at runtime; it is only read.

**`searchByPriceRange(min, max)`** — Runs a lower-bound binary search on `ALL_SORTED` to find the first index where `price >= min` (O(log n)), then walks forward collecting entries while `price <= max` (O(k) where k is the result count). Total complexity: O(log n + k).

**`getUnowned(portfolio)`** — Builds a `Set` of owned property IDs from the portfolio (O(k) where k is portfolio size), then filters the full catalog using `Set.has()` for each entry (O(1) per check). This was refactored from an original O(n²) implementation that called `Array.includes()` inside a filter loop.

```mermaid
flowchart LR
    A["searchByPriceRange(min, max)"] --> B["Binary search on ALL_SORTED\nFind leftmost index: price >= min\nO(log n)"]
    B --> C["Walk forward: collect while price <= max\nO(k results)"]
    C --> D["Return matched properties"]

    E["getUnowned(portfolio)"] --> F["Build Set from owned IDs\nO(k) — k = portfolio size"]
    F --> G["Filter ALL properties:\nSet.has(id) per entry — O(1)"]
    G --> H["Return unowned properties\nTotal: O(n + k)"]
```

---

### Negotiation Battle — GameLevelPropertyDeal.js

The negotiation battle is how players acquire properties. Each deal level subclasses `GameLevelPropertyDeal` with different difficulty parameters.

The framing: the broker NPC (seller) fires counter-offers (red lasers) at the player. The player fires offers (cyan lasers) at the seller to deplete their HP. Inspection documents scattered on the ground give a 1% purchase discount each when collected. When seller HP reaches 0, the deal closes at the total accumulated discount.

**Difficulty scaling by tier:**

| Tier | Seller HP | Player Shields | Counter-Offer Interval | Max Discount |
|------|-----------|----------------|------------------------|--------------|
| Residential | 10 | 4 | 1.8 seconds | 5% (5 documents) |
| Commercial | 15 | 3 | 1.3 seconds | 5% (5 documents) |
| Luxury | 20 | 2 | 1.0 seconds | 5% (5 documents) |

```mermaid
sequenceDiagram
    participant P as Player
    participant B as Broker (Seller)
    participant Sys as Battle System
    participant PM as PortfolioManager

    Sys->>Sys: spawn 5 inspection documents
    loop Each battle frame
        P->>B: fire offer laser
        B->>Sys: HP decreases
        B-->>P: fire counter-offer on interval timer
        P-->>Sys: lose shield if hit
        P->>Sys: collect document if in range
        Sys->>Sys: discount += 1%
    end

    alt Seller HP = 0
        Sys->>PM: buyProperty(id, price × (1 − discount%))
        Sys->>Sys: transition back to Market Hub
    else Player shields = 0
        Sys->>Sys: deal failed, transition back to hub
    end
```

The discount accumulates as the player collects documents during the battle. A player who collects all five documents and defeats the seller earns a 5% purchase price reduction on top of whatever the current market multiplier is. This adds a navigation layer to the combat mechanic — players who ignore the documents and just fire at the seller miss out on savings.

---

### Market Hub — GameLevelMarketHub.js

The hub is the main game world. It is the level the player returns to after every deal and spends the most time in. Six systems run concurrently from the same animation frame loop.

```mermaid
graph TB
    GameLoop["Animation Frame Loop"] --> HUD & Ticker & WinPoll

    subgraph "Per-Frame Systems"
        HUD["Portfolio HUD\nNet worth / cash / income / debt\n3 market multipliers"]
        Ticker["Market Ticker\nScrolling animated price feed"]
        WinPoll{"getNetWorth() >= $5M?"}
    end

    subgraph "Event-Driven / Interval Systems"
        Banner["Market Event Banner\nFull-width animated notification\nFires via MarketEngine observer"]
        Coins["Rent Coins\n1 coin per owned property\nevery 2.5 seconds"]
        NPC["NPC Callbacks\nSet-based gate check\nLevel transition on pass"]
    end

    WinPoll -- "Yes" --> WinScreen["GameLevelWinScreen"]
    WinPoll -- "No" --> GameLoop

    MarketEngine -->|"emit 'event'"| Banner
    IntervalTimer["2.5s setInterval"] --> Coins
    PlayerCollision --> Coins
    PlayerNearNPC --> NPC
    NPC -->|"getOwnedTypes() / getPortfolio().length"| GateCheck{"Gate condition met?"}
    GateCheck -- "Yes" --> DealLevel["Enter Deal Level"]
    GateCheck -- "No" --> Toast["_showToast() — 2.5s lock message"]
```

**HUD implementation** — The HUD is a DOM overlay rather than a Canvas element. It is updated by directly writing to pre-built DOM nodes each frame via `innerText`. At 60fps this is fast enough; if the game ever targets 120fps, throttling to every other frame would be worth considering.

**Visibility management** — When the player enters a deal level, `_setUiVisible(false)` sets `display: none` on all HUD and ticker DOM elements. Without this, those elements render on top of the deal level canvas, which was the original bug. When the player returns, `parentControl.resume` fires and `_setUiVisible(true)` restores them.

**NPC gate system** — Marcus (Commercial) and Victoria (Luxury) use `PortfolioManager.getPortfolio().length` to check the total property count. If the gate fails, `_showToast()` renders a temporary message for 2.5 seconds describing the requirement. No modal, no pause — the game keeps running while the toast is visible.

---

## Progression System

```mermaid
flowchart TD
    A["Start: $500,000 cash"] --> B

    B["Buy Residential Properties\nSarah broker\n10 HP seller, 4 player shields"] --> C

    C{"Properties owned >= 3?"}
    C -- "No" --> B
    C -- "Yes" --> D

    D["Commercial Market Unlocked\nMarcus broker\n15 HP seller, 3 player shields"] --> E

    E{"Properties owned >= 6?"}
    E -- "No" --> B & D
    E -- "Yes" --> F

    F["Luxury Market Unlocked\nVictoria broker\n20 HP seller, 2 player shields"] --> G

    G{"Net worth >= $5,000,000?"}
    G -- "No" --> B & D & F
    G -- "Yes" --> H["TYCOON STATUS\nWin Screen"]
```

Players are not locked out of lower tiers once higher ones unlock. Mixing property types is often the optimal strategy — commercial properties generate significantly higher monthly rent and benefit from residential market event spillover. A player who buys only luxury properties faces higher deal difficulty and loses faster if the luxury multiplier drops.

---

## Win Screen — GameLevelWinScreen.js

The win screen has three main components.

**Stats panel** — Eight stat cards covering final net worth, time elapsed, total properties purchased, total sold, peak net worth during the run, total rent collected, total loans taken, and final debt. All values are read from `PortfolioManager` getter methods.

**Portfolio breakdown** — A table listing each currently owned property with its type, current market-adjusted value, and monthly rent output.

**Top-10 leaderboard** — Scores from `localStorage`, ranked by final net worth. Each entry shows player name, score, and time elapsed. The leaderboard persists across game resets — "Play Again" resets the portfolio but does not wipe the leaderboard.

**Market history chart** — An HTML5 Canvas chart drawn without any external charting library. It reads the 60-point price history ring buffer from `MarketEngine.getPriceHistory()` and renders three polylines (one per market category) with axis labels, tick marks, and a legend. This is the most visually complex piece of the project and required the most Canvas API research.

```mermaid
graph LR
    subgraph "Win Screen Components"
        Stats["8 Stat Cards\nfinal run metrics"]
        Port["Portfolio Table\ncurrent holdings + rent"]
        LB["Top-10 Leaderboard\nlocalStorage — cross-session"]
        Chart["Canvas Market Chart\n3-line price history\nno external library"]
    end

    PM["PortfolioManager"] -->|"getters"| Stats & Port & LB
    ME["MarketEngine"] -->|"getPriceHistory()"| Chart
```

```mermaid
graph TB
    subgraph "Win Screen Layout"
        NW2["Final Net Worth\n$X,XXX,XXX"]
        Time["Time Elapsed\nMM:SS"]
        Peak["Peak Net Worth"]
        Props["Properties Purchased"]
        Sold["Properties Sold"]
        Rent["Total Rent Collected"]
        Loans["Loans Taken"]
        Debt["Final Debt"]
    end

    subgraph "Portfolio Table"
        Row1["Property Name | Type | Value | Monthly Rent"]
        Rows["... one row per owned property"]
    end

    subgraph "Market Chart — Canvas"
        Axis["Axis labels + tick marks"]
        Line1["Residential price line"]
        Line2["Commercial price line"]
        Line3["Luxury price line"]
    end

    subgraph "Leaderboard"
        Rank["Rank | Name | Net Worth | Time\n(top 10, localStorage)"]
    end
```

---

## Data Flow Summary

```mermaid
sequenceDiagram
    participant Player
    participant Hub as Market Hub
    participant ME as MarketEngine
    participant PM as PortfolioManager
    participant PD as PropertyDatabase
    participant LS as localStorage

    Note over ME,LS: On page load
    ME->>LS: load cached multipliers + history (5-min TTL)
    PM->>LS: load portfolio + leaderboard

    Note over Player,Hub: During gameplay
    loop Every animation frame
        ME->>ME: Brownian tick + event check
        Hub->>ME: getMultiplier(category)
        Hub->>PM: getNetWorth() / getCash() / getIncome()
        Hub->>Hub: update DOM HUD elements
    end

    Player->>Hub: interact with NPC
    Hub->>PM: getPortfolio().length — gate check
    Hub->>Hub: enter deal level

    Note over Player,PM: In deal level
    Player->>PM: buyProperty(id, discountedPrice)
    PM->>LS: _persist()
    PM-->>Hub: success, return to hub

    Note over Player,Hub: Win condition
    Hub->>PM: getNetWorth()
    PM-->>Hub: value >= 5000000
    Hub->>Hub: transition to WinScreen
    Hub->>PM: addScore(name, netWorth, time)
    PM->>LS: persist leaderboard
```
