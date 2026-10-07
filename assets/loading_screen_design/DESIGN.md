---
name: Ethereal Obsidian Studio
colors:
  surface: '#131317'
  surface-dim: '#131317'
  surface-bright: '#39393e'
  surface-container-lowest: '#0e0e12'
  surface-container-low: '#1b1b20'
  surface-container: '#1f1f24'
  surface-container-high: '#2a292e'
  surface-container-highest: '#353439'
  on-surface: '#e4e1e8'
  on-surface-variant: '#cec3d3'
  inverse-surface: '#e4e1e8'
  inverse-on-surface: '#303035'
  outline: '#978d9d'
  outline-variant: '#4c4452'
  surface-tint: '#ddb8ff'
  primary: '#ddb8ff'
  on-primary: '#490081'
  primary-container: '#c084fc'
  on-primary-container: '#500989'
  inverse-primary: '#7b41b4'
  secondary: '#e6feff'
  on-secondary: '#003739'
  secondary-container: '#00f4fe'
  on-secondary-container: '#006c71'
  tertiary: '#ffb0cd'
  on-tertiary: '#640039'
  tertiary-container: '#ff6aae'
  on-tertiary-container: '#6e0040'
  error: '#ffb4ab'
  on-error: '#690005'
  error-container: '#93000a'
  on-error-container: '#ffdad6'
  primary-fixed: '#f0dbff'
  primary-fixed-dim: '#ddb8ff'
  on-primary-fixed: '#2c0051'
  on-primary-fixed-variant: '#62259b'
  secondary-fixed: '#63f7ff'
  secondary-fixed-dim: '#00dce5'
  on-secondary-fixed: '#002021'
  on-secondary-fixed-variant: '#004f53'
  tertiary-fixed: '#ffd9e4'
  tertiary-fixed-dim: '#ffb0cd'
  on-tertiary-fixed: '#3e0022'
  on-tertiary-fixed-variant: '#8c0053'
  background: '#131317'
  on-background: '#e4e1e8'
  surface-variant: '#353439'
typography:
  display-hero:
    fontFamily: Sora
    fontSize: 56px
    fontWeight: '700'
    lineHeight: 64px
    letterSpacing: -0.03em
  display-hero-mobile:
    fontFamily: Sora
    fontSize: 36px
    fontWeight: '700'
    lineHeight: 44px
    letterSpacing: -0.02em
  headline-lg:
    fontFamily: Sora
    fontSize: 32px
    fontWeight: '600'
    lineHeight: 40px
    letterSpacing: -0.02em
  headline-lg-mobile:
    fontFamily: Sora
    fontSize: 26px
    fontWeight: '600'
    lineHeight: 34px
    letterSpacing: -0.015em
  headline-md:
    fontFamily: Sora
    fontSize: 22px
    fontWeight: '500'
    lineHeight: 30px
    letterSpacing: -0.01em
  body-lg:
    fontFamily: Geist
    fontSize: 16px
    fontWeight: '400'
    lineHeight: 24px
    letterSpacing: -0.005em
  body-md:
    fontFamily: Geist
    fontSize: 14px
    fontWeight: '400'
    lineHeight: 20px
    letterSpacing: 0em
  body-sm:
    fontFamily: Geist
    fontSize: 12px
    fontWeight: '400'
    lineHeight: 16px
    letterSpacing: 0.01em
  hud-label:
    fontFamily: Geist
    fontSize: 11px
    fontWeight: '500'
    lineHeight: 14px
    letterSpacing: 0.08em
  code-metric:
    fontFamily: Geist
    fontSize: 13px
    fontWeight: '500'
    lineHeight: 18px
    letterSpacing: 0.02em
rounded:
  sm: 0.125rem
  DEFAULT: 0.25rem
  md: 0.375rem
  lg: 0.5rem
  xl: 0.75rem
  full: 9999px
spacing:
  gutter: 1.5rem
  gutter-sm: 0.75rem
  margin: 2rem
  margin-sm: 1rem
  space-xs: 0.25rem
  space-sm: 0.5rem
  space-md: 1rem
  space-lg: 1.5rem
  space-xl: 2.5rem
---

## Brand & Style

This design system establishes a high-performance, immersive luxury aesthetic tailored for elite creative studios, generative platforms, and next-generation digital interfaces. The visual language balances razor-sharp architectural discipline with ethereal luminescence. It projects computational supremacy, exclusivity, and tactile precision.

The emotional signature is cinematic, focused, and enigmatic. The experience avoids chaotic cyberpunk clichés; instead, it adopts an ultra-refined dark room aesthetic reminiscent of an advanced creative suite or high-precision spatial compute engine. It pairs crisp, low-tolerance geometries with subtle optic flares, deep obsidian layering, and glassmorphic depth.

## Colors

The palette operates on absolute light-on-dark contrast, structured around deep nocturnal foundations and concentrated spectral accents.

### Palette Architecture
- **Base Canvas (`#08080c`) & Surface Elevation (`#0d0e15`, `#161724`)**: Pure obsidian tone with a 1-2% blue-indigo cast to prevent dull grayscale rendering.
- **Primary Accent (`#c084fc`)**: Ethereal neon violet used for prime interactive focal points, active states, key focus rings, and high-tier studio badges.
- **Secondary Accent (`#00f5ff`)**: Electric cyan used for telemetry indicators, runtime execution highlights, active tracking meters, and precision HUD nodes.
- **Tertiary Accent (`#ec4899`)**: High-energy hyper-magenta utilized for dynamic rendering thresholds, alerts, and critical state transformations.
- **Warning / Radiant Amber (`#f59e0b`)**: Micro-dosed strictly for hardware diagnostics, telemetry warnings, and sync flags.

### Foreground Contrast Tokens
- **Text Primary (`#f8fafc`)**: Crisp, stark white for critical metrics and display typography.
- **Text Secondary (`#94a3b8`)**: Cool titanium for technical metadata and structural labeling.
- **Text Muted (`#475569`)**: Subdued slate for structural brackets, delimiters, and grid coordinates.
- **Borders & Inset Strokes (`rgba(255, 255, 255, 0.08)`)**: Fine, hairline boundaries to define surfaces without visual heaviness.

## Typography

The typographic hierarchy establishes clear structural discipline: `Sora` provides geometric structure and presence for titles, while `Geist` delivers neutral readability for high-density interfaces, technical specifications, and runtime data.

- **Display & Headlines (`Sora`)**: Set with tight negative letter tracking to reinforce a cohesive, machined appearance. Headline scale is optimized for high-impact creative direction, load sequences, and system state milestones.
- **Body & Data Grid (`Geist`)**: Used for all descriptive copy, input controls, and contextual menus. Maintains high clarity across dense layouts.
- **HUD & Status Indicators**: Small caps with wide tracking (`0.08em`) are used for telemetry nodes, coordinate indicators, and micro status readouts to create an authentic instrumentation panel feel.

## Layout & Spacing

The layout is engineered on a rigid 8px spatial grid, relying on a 12-column fluid grid system across desktop resolutions and collapsing to 4 columns on mobile viewports.

### Grid Rhythm & Viewport Adaptations
- **Desktop (>= 1280px)**: 12 columns with 24px (`1.5rem`) gutters and 32px (`2rem`) edge margins. Critical studio dashboards and canvas monitors maximize the display footprint with dynamic inner pane scaling.
- **Tablet (768px - 1279px)**: 8 columns with 16px (`1rem`) gutters and 24px (`1.5rem`) margins. Side rails retract into collapsible flyout drawers.
- **Mobile (< 768px)**: 4 columns with 12px (`0.75rem`) gutters and 16px (`1rem`) outer canvas margins. Multi-metric HUD views transform into vertically stacked modules with snap-scroll tracking.

### Component Spacing Discipline
Internal component paddings adhere strictly to micro-increments:
- Micro badges & chips: `space-xs` (vertical) by `space-sm` (horizontal).
- Command buttons and list nodes: `space-sm` by `space-md`.
- Panels, dialogs, and HUD cards: `space-lg` to `space-xl`.

## Elevation & Depth

Visual hierarchy uses physical depth and illuminated planes rather than traditional drop shadows.

### Glassmorphic Substrates
- **Base Level (Canvas)**: Non-reflective matte `#08080c`.
- **Level 1 (Dock & Floating Rails)**: `rgba(13, 14, 21, 0.72)` paired with `backdrop-filter: blur(16px) saturate(180%)` and a 1px border of `rgba(255, 255, 255, 0.07)`.
- **Level 2 (Active Cards & Focus Modules)**: `rgba(22, 23, 36, 0.85)` with `backdrop-filter: blur(24px)` and a top-edge linear highlight stroke of `linear-gradient(90deg, rgba(192, 132, 252, 0.4), rgba(0, 245, 255, 0.1), transparent)`.

### Chromatic Glow & Optics
- **Quiescent Shadow**: Deep structural occlusion: `0 12px 32px -4px rgba(0, 0, 0, 0.8)`.
- **Primary Violet Micro-Glow**: Applied to interactive active controls and primary elements: `0 0 20px -2px rgba(192, 132, 252, 0.35), 0 0 4px 0 rgba(192, 132, 252, 0.6)`.
- **Cyan Signal Micro-Glow**: Applied to operational telemetry and online markers: `0 0 16px -2px rgba(0, 245, 255, 0.45)`.
- **Magenta Alert Micro-Glow**: Triggered on critical execution phases or threshold overflows: `0 0 20px -2px rgba(236, 73, 153, 0.4)`.

## Shapes

The shape vocabulary uses strict architectural lines with subtle edge easing.

- **Base Radius (`0.25rem` / `4px`)**: Applied to all core utility controls, micro-glow status pills, inputs, buttons, and HUD coordinate tags. This provides mechanical precision while preventing harsh aliasing.
- **Large Radius (`0.5rem` / `8px`)**: Applied to floating modals, canvas containers, execution panels, and loading view frames.
- **Extra Large Radius (`0.75rem` / `12px`)**: Reserved solely for full-screen glass backdrops and boundary wrapper envelopes.
- **Internal Edge Definition**: All surfaces feature a 1px boundary stroke with an inset top-edge hairline highlight (`rgba(255, 255, 255, 0.12)`) to simulate beveled optics.

## Components

### Buttons & Interactive Triggers
- **Primary Neon Pulse**: Solid background `linear-gradient(135deg, #c084fc, #9333ea)`, high-contrast dark text (`#08080c`), `font-weight: 600`. Emits an ethereal violet micro-glow (`rgba(192, 132, 252, 0.45)`). On hover, brightness increases by 12% with subtle cyan perimeter diffusion.
- **Secondary Ghost Glass**: Background `rgba(255, 255, 255, 0.03)`, 1px border `rgba(255, 255, 255, 0.12)`, text `#f8fafc`. On hover, the border illuminates to electric cyan (`#00f5ff`) with an internal glow reflection.
- **Tertiary HUD Minimal**: Clean typography with a trailing geometric marker (`[+]` or `/`), resting transparently with active cyan or violet underline accents on focus.

### Micro-Glow Badges & Status Chips
- Height restricted to 22px. Composed of an ultra-dark glass fill (`rgba(8, 8, 12, 0.8)`), a fine 1px tinted border matching the status color, and an active blinking LED dot (4px radius with radial glow bloom).
- Text styled in `hud-label` caps. Color variants: Violet (Standby / Studio Master), Cyan (Processing / Synced), Magenta (Rendering / Overclock), Amber (Warning / Buffer Load).

### HUD Loading Indicators & Progress Tracks
- Progress indicators feature a dual-layer hairline track (height 2px to 4px).
- **Background Track**: `rgba(255, 255, 255, 0.06)`.
- **Active Runner**: Gradient wipe from `#00f5ff` through `#c084fc` to `#ec4899`, tipped with a point-light bloom.
- Numeric counters rendered in `code-metric` typography, flanked by bracketed telemetry (`[ 98.4% COMPLETE ]`).

### Input Fields & Controls
- Background `rgba(13, 14, 21, 0.6)`. Hairline 1px border `rgba(255, 255, 255, 0.08)`.
- Focus state triggers an instantaneous transition to `rgba(192, 132, 252, 0.2)` edge illumination accompanied by an inner violet shadow diffusion.
- Monospaced helper annotations and unit indicators (`ms`, `FPS`, `GB/s`) aligned right in muted titanium.

### Cards, Panes & Floating Panels
- Base structural units layered with `rgba(13, 14, 21, 0.75)` backdrop-filter blur.
- Cards incorporate top-right corner HUD indexing marks (e.g., `SEC_01 // REF:49`) in muted slate.
- Dividers between card sections are rendered as translucent gradients fading out to the outer edges.