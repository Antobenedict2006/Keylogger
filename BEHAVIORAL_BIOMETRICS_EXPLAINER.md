# How the System Knows It’s You

## Simple answer first

The system learns who you are by watching how you behave at the keyboard and mouse, not just what you type.

It monitors:

1. How you type: rhythm, speed, pauses, and key hold time
2. How you move the mouse: curvature, speed, acceleration, tremor, and click habits
3. What applications you normally use: Chrome, VS Code, Outlook, Spotify, Steam, and others
4. When you use your computer: your morning, afternoon, and evening patterns are different
5. How consistent your behavior is: humans vary naturally; bots and automation are unnaturally precise

Just as handwriting is unique to a person, the timing pattern behind typing and mouse movement is also unique.

---

## The complete picture

Traditional security asks:

> “Are you the right person?”

It usually checks a password, token, or device signature.

This system asks a stronger question:

> “Are you behaving like the right person?”

It continuously compares live behavior to a learned baseline built from:

- keyboard rhythm
- mouse movement and click behavior
- process usage patterns
- time-of-day habits
- natural variability versus bot-like precision

Even if someone knows your password, they cannot easily fake your behavioral fingerprint.

---

## Privacy guarantee

The project is designed to protect privacy while still detecting anomalies.

The documentation explicitly states:

- The system does not record screen images, screenshots, or typed text content
- Keyboard data is reduced to timing information such as dwell time and flight time
- Mouse tracking focuses on movement speed, acceleration, path curvature, click hold duration, and zone distribution
- JSON exports include SHA-256 integrity hashes
- Timestamps can be anonymized into relative offsets for privacy-safe forensic review

This means the system is looking for behavioral patterns, not the contents of your work.

---

## What is actually measured

### 1. Keyboard biometrics
The keyboard layer captures timing events around each key press and release.

Metrics tracked include:

- Typing speed (WPM)
- Dwell time: how long a key is held before release
- Flight time: time between a key release and the next key press
- Consistency: standard deviation of intervals
- Burst dynamics: how long and how often the user types continuously
- Error-correction behavior, such as backspace frequency and correction latency

These metrics are combined into a keyboard profile that reflects a user’s typical habits.

### 2. Mouse biometrics
The mouse layer tracks movement and interaction patterns in real time.

Metrics tracked include:

- movement speed in pixels per second
- acceleration and deceleration patterns
- path curvature index
- micro-movements and hand tremor
- click duration and double-click timing
- click-to-move latency
- pause frequency and movement idle gaps
- screen-zone heatmap distribution (3x3 grid)

This gives the system a unique motion signature for each user.

### 3. Process and context behavior
The system also learns what applications a user normally runs and when.

Typical profile examples include:

- Morning: Chrome, Outlook, VS Code
- Afternoon: Chrome, VS Code, Spotify, Slack
- Evening: Steam, Discord, VLC

This is important because a user who suddenly behaves like a different worker or automation pattern may not match their learned context.

---

## Layered detection model

### Layer 1: Keyboard behavior

Each keystroke is a timing event. The system records:

- key press timestamp
- key release timestamp
- hold duration
- gap between keys
- rhythm across sequences of letters and words

A human typist does not type with perfect mechanical regularity. Their rhythm naturally varies.

Example:

- typical dwell time: around 85 ms
- typical flight time: around 145 ms
- natural variation: 15–30 ms

A replay tool or automated script often shows:

- identical dwell times
- fixed gaps between keys
- near-zero variance
- unnatural speed consistency

### Five keyboard signals the system uses

#### 1. Typing speed (WPM)
The user’s normal range is learned over time.

If the current speed is far outside the baseline, it may indicate a different user or suspicious automation.

#### 2. Dwell time
This measures how long the user holds down a key before releasing it.

Different people show different hold habits. A sudden shift often signals a different user or automation.

#### 3. Flight time
This is the interval between one key release and the next key press.

Humans vary their gaps naturally. Perfectly regular timing is suspicious.

#### 4. Timing consistency
Humans are naturally inconsistent. Their timing fluctuates.

Bots tend to have extremely low volatility, which is a red flag.

#### 5. Typing bursts and pauses
Humans type in bursts and pause to think, read, or correct mistakes. Bots often type continuously without natural interruptions.

---

## Layer 2: Mouse behavior

Mouse behavior adds a second biometric layer that is very hard to fake.

The system can measure:

- cursor position
- movement speed
- direction changes
- acceleration and deceleration
- path curvature
- micro-jitter and hand tremor
- click hold duration
- double-click timing
- click-to-move latency
- pause frequency
- spatial heatmap across screen zones

### Why mouse movement matters

Humans move the mouse along slightly curved, imperfect paths. Their movement usually includes:

- small micro-adjustments
- natural tremor
- hesitation before a click
- deceleration near the target
- pause patterns while reading or deciding

Bots and remote-control tools usually behave differently:

- very straight paths
- near-zero jitter
- instant acceleration and abrupt stops
- little pause behavior
- very consistent movement geometry

### The 3x3 zone distribution

The system records where the user spends time on-screen, creating a spatial heatmap.

This provides another personalization signal, because the same user tends to favor certain regions of the screen more than others.

---

## Multi-modal behavioral scoring

The project combines keyboard and mouse data into a single decision engine.

The documentation defines the overall similarity score as:

$$
\text{Overall Similarity} = (0.40 \times \text{KB Score}) + (0.40 \times \text{Mouse Score}) + (0.20 \times \text{Pattern Score})
$$

This weighted fusion improves detection accuracy from roughly 70–80% with keyboard-only models to 90–95% in the combined setup.

It also includes cross-modal correlation, such as:

- typing bursts vs mouse pause behavior
- switching latency between keyboard and mouse
- whether input streams look synchronized and natural

---

## Multi-modal bot classification

The system distinguishes between multiple bot architectures using behavioral signatures.

| Bot type | Signature | Trigger condition |
|---|---|---|
| Keyboard Macro | Uniform keystrokes, no human mouse movement | Keystroke std-dev < 5 ms and mouse events < 100 |
| Remote Control | Straight geometric cursor paths and no hand tremor | Curvature < 1.05 and jitter < 1.0 px |
| Replay Attack | Identical replay of recorded timing sequence | Exact timing sequence repetition without variance |
| Hybrid Automation | Uncoordinated keyboard and mouse streams | Correlation < 0.30 and unnatural switch latency |

This is one of the strongest parts of the design: the system does not only ask “Is this speed unusual?” It also asks “Does this input look like a machine?”

---

## Why bots trigger immediate alerts

Humans are naturally variable. Bots are usually too perfect.

A bot may show:

- fixed 50 ms key holds
- exact repeated gaps
- zero jitter
- perfectly straight cursor paths
- no natural pauses
- no human hesitation

This is a critical detection clue because a truly human typing rhythm always contains some natural irregularity.

The system can flag bot behavior immediately when timing consistency sits below a threshold or when the movement pattern is geometrically impossible for a human hand.

---

## How training works

### Phase 1: Observation
The system watches the user over time and collects baseline statistics.

It records:

- typing speed variations across the day
- average dwell and flight times
- mouse speed and acceleration patterns
- click hold behavior
- process usage habits and time-of-day context

### Phase 2: Baseline profile
The system calculates a statistical profile with:

- mean value
- standard deviation
- normal range
- percentiles
- variance and consistency values

A profile is created for:

- keyboard behavior
- mouse behavior
- combined behavioral profile
- time-of-day and app-context patterns

### Phase 3: Real-time comparison
The system checks current behavior against baseline values every few seconds or minutes.

It asks:

> Does this behavior still look like the user I know?

It compares current telemetry to:

- z-scores
- similarity percentage
- consistency thresholds
- process pattern mismatch checks

---

## Z-scores and similarity scoring

The system compares live behavior to a personalized baseline using statistical deviation.

Example:

- current typing speed: 92 WPM
- baseline: 65 WPM with std dev 8
- z-score = (92 - 65) / 8 = 3.4

This is a large deviation and may be suspicious.

The system can compute a final similarity score using multiple metrics such as:

- typing speed deviation
- dwell time deviation
- flight time deviation
- mouse speed deviation
- mouse curvature deviation
- process mismatch

Typical logic:

- 85%+ similarity: likely the same user
- 70–84%: probably still the same user, but watch closely
- 50–69%: suspicious or inconsistent
- below 50%: likely not the same person or likely automation

---

## Real-world examples

### Scenario 1: Friend uses your computer
A different user types more slowly, holds keys longer, moves the mouse differently, and prefers different screen zones.

The system sees multiple mismatches and lowers the similarity score.

### Scenario 2: Replay attack
Someone replays a previous recording of your keystrokes.

The content may match, but timing is too exact, variation is too low, and the movement pattern may be too perfect.

The system flags the session as a replay attack quickly.

### Scenario 3: Remote control or RAT activity
A remote operator controls the mouse and keyboard with geometric precision.

The movement is too straight and too smooth, with little tremor or natural delay.

The system recognizes this as non-human control behavior.

### Scenario 4: You are simply having a bad day
The system allows for normal variation. A tired or stressed user may type slower or move differently, so the detection engine uses thresholds and persistence checks before escalating to a full alert.

---

## JSON export and integrity guarantees

The repo includes a full JSON-export specification for behavioral data.

Exportable files include:

- keyboard_behavior.json
- mouse_behavior.json
- behavioral_profile.json
- session_[timestamp].json
- comparison_report.json

These exports are useful for:

- baseline benchmarking
- forensic incident review
- comparing live behavior to learned profile
- verifying session integrity

### Privacy properties of exports

- no raw keystroke content is stored
- no screen pixels are captured
- no complete target or text reconstruction is possible
- numerical timing and movement data only
- SHA-256 hash fields are included for integrity validation
- timestamps may be anonymized as relative offsets

This supports security analysis without violating basic privacy expectations.

---

## Live dashboard and streaming integration

The project also supports a live web dashboard that receives real-time scan data from the Python detector.

### What the live bridge does

- Python monitor scans running processes
- the results are pushed to a Flask API
- a Next.js dashboard polls for status and process results
- the app shows safe, suspicious, and malicious entries in real time

### Data flow

```text
Python detector -> Flask API -> Next.js dashboard
```

### Dashboard capabilities

- live metrics cards
- process table with risk badges
- detailed inspection of flagged entries
- health and stale-state indicators
- refresh/pause controls
- real-time rendered results with process name, PID, risk score, and reasons

This extends the behavioral biometric logic into a browser-based operational console without exposing keystroke content.

---

## Mouse optimization and robust tracking

The repository includes a mouse optimization guide because high-frequency mouse events can overwhelm a Python callback loop.

### Problems addressed

- event flood overload
- blocking synchronous math in the OS hook thread
- memory allocation pressure
- thread contention and UI lag

### Solutions implemented

- aggressive event downsampling
- lock-free fast-path capture in the mouse callback
- background worker thread for batch processing
- thread priority tuning for smoother Windows interaction
- smart idle detection and auto-throttling during high-activity periods

### Performance results

The documentation reports impressive optimization:

- average callback latency reduced from about 5.20 ms to 0.0095 ms
- event processing reduced from roughly 500 events/s to 20–24 events/s
- cursor feel remained smooth with no visible lag
- biometric accuracy was preserved

This matters because the system must gather high-quality behavioral data without causing the user interface to stutter or the desktop to lag.

---

## User-facing UI and controls

The product includes a modern desktop dashboard with a menu system and toggles for monitoring behavior.

Features include:

- menu bar with File, View, Tools, and Help sections
- clickable statistics cards used to filter detection history
- live alerts and history tabs
- status bar for monitoring and notification controls
- settings dialog and about dialog
- notification toggle for desktop alerts

The notification feature is important: users can disable popups while still letting the detector log threats and update the dashboard.

---

## Why the system works

This approach is effective because it combines several weak signals into a strong identity model:

- keyboard rhythm is highly personal
- mouse movement is highly personal
- process and time-of-day patterns add context
- timing consistency catches automation
- bot-like precision is usually obvious

The system does not rely on a single metric. Instead, it checks many signals together.

A single odd measurement is not enough to trigger a serious alarm. Multiple conflicting signals together create a high-confidence decision.

---

## Summary

The system knows it’s you by comparing live keyboard, mouse, and process behavior to a learned baseline of your normal habits.

It looks for:

1. Typing rhythm and key timing
2. Mouse motion, curvature, tremor, and click behavior
3. Process and application patterns
4. Time-of-day usage context
5. Human variability versus machine precision

The key insight is simple:

> A human is naturally variable. A bot is unnaturally precise.

Even if an attacker knows your password, they usually cannot reproduce your exact timing profile, mouse geometry, and normal behavioral context.

That is the behavioral DNA the system uses to decide whether the current activity is really you or something else.

---

## One-line version

The system identifies the user by checking whether their live keyboard, mouse, and application behavior still match the learned fingerprint of their normal habits, and it immediately treats overly precise and repetitive input as bot-like or replayed behavior.
