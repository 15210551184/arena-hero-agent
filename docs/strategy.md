# Strategy Profile

The default profile optimizes for long-term Core survival and resource accumulation rather than Beacon progress or indiscriminate combat.

## Population Plan

The mature target is:

| Unit | Target | Role |
| --- | ---: | --- |
| Worker | 12 | Harvest, deposit, scout, observe, and recover dropped cargo. |
| Vanguard | 3 | Outer screen, route clearing, and bounded assault reinforcement. |
| Ranger | 4 | Inner Core defense and ranged stationary-target clearing. |
| Total | 19 | Remains below the 20-population resource penalty. |

Production reserves resources between stages and does not build beyond the configured Worker target and defense targets.

## Core Safety

- The Core is the highest-value object and is never intentionally self-destructed.
- With the default `retreat` policy, migration candidates favor directions away from the Beacon and visible threats.
- Guards are distributed around the Core instead of stacking on its cell or blocking Worker routes.
- Visible projected damage, shields, repair resources, migration progress, and destination safety influence repair or cancellation decisions.
- A compatibility marker forces conservative behavior when published rules, the server contract, or the SDK no longer match the tested profile.

## Economy and Scouting

- Resource cells are treated as dynamic observations, not permanent terrain.
- Workers reserve targets, detect repeated entry/harvest blocking, and release stale assignments.
- Scouting prioritizes the least recently observed chunks and avoids sending every Worker through the same corridor.
- Loaded Workers prioritize a legal return route and account for Core movement.
- Recovery mode protects the replacement Worker and dropped cargo after a Core loss.

## Combat Policy

- Active enemy fleets cause spacing, screening, and fighting withdrawal rather than an unconditional stop.
- Confirmed stationary units can be cleared by a small bounded strike group while guards remain with the Core.
- A stationary Core is considered for a raid only after repeated observations and isolation checks. The Worker that exposed it may remain as the designated observer.
- Loss of visibility does not immediately invalidate stationary-target memory, but moving escorts, contradictory observations, age, and risk reduce confidence.
- Loot events, storage capacity, same-Tick Core survival, and return-path cost determine whether a kill was economically useful.

## Current Optimization Priority

The strategy currently has focused unit tests and structured diagnostics for economy stalls, blocking, Core survival, scouting coverage, combat pressure, lifecycle events, and unexplained resource loss. New tuning should be driven by a captured unhealthy window rather than by increasing fleet size or adding a model to the Tick loop.
