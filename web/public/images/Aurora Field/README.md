# AuroraField — Next.js interactive smoke background

A zero-dependency WebGL background component. Soft white/orange smoke that
**heat-blooms** under the cursor and fires an **ignition flare** on click.

## Install

Copy `AuroraField.jsx` into your project, e.g. `components/AuroraField.jsx`.
(No npm packages needed — it's plain WebGL + React.)

## Use it (App Router)

`AuroraField` is a client component. Render it **once**, high in the tree, and
put your content above it.

```jsx
// app/layout.jsx
import AuroraField from '@/components/AuroraField';

export default function RootLayout({ children }) {
  return (
    <html lang="en">
      <body>
        <AuroraField />
        {/* your app — sits above the canvas automatically */}
        <main style={{ position: 'relative', zIndex: 1 }}>{children}</main>
      </body>
    </html>
  );
}
```

The canvas is `position: fixed`, `z-index: -1`, `pointer-events: none`, so it
never intercepts clicks or scroll — the cursor is tracked on `window`, so the
smoke stays interactive *underneath* your fully-usable UI.

## Props

| prop            | default     | what it does                                   |
|-----------------|-------------|------------------------------------------------|
| `heatColor`     | `'#ff5e1a'` | hue the flare cools toward / hover tint        |
| `heatIntensity` | `1.0`       | hover + click strength (0–2)                   |
| `speed`         | `1.0`       | idle drift speed (0–2)                          |
| `scale`         | `1.0`       | smoke feature size (0.5–2)                      |
| `warmth`        | `0.45`      | 0 = whiter cores, 1 = oranger                  |
| `grain`         | `0.5`       | film grain (0–1)                               |
| `interactive`   | `true`      | set `false` to freeze cursor reactions         |
| `renderScale`   | `0.6`       | internal resolution. Lower = faster + softer   |

```jsx
<AuroraField heatColor="#ffae3d" heatIntensity={1.3} warmth={0.3} />
```

## Readability

Bright smoke fights with text. Add a scrim between the canvas and your content:

```jsx
<div style={{
  position: 'fixed', inset: 0, zIndex: 0, pointerEvents: 'none',
  background: 'radial-gradient(120% 120% at 50% 0%, rgba(5,4,7,0) 40%, rgba(5,4,7,0.7) 100%)',
}} />
```

## Performance notes

- Renders a fullscreen fragment shader each frame. It caps DPR at 1.4 and renders
  at `renderScale` of viewport, then the browser upscales (which also gives the
  soft, gaseous look). On low-end mobiles, try `renderScale={0.45}`.
- Browsers auto-pause `requestAnimationFrame` when the tab is hidden.
- To respect reduced motion, gate it: `const reduce = useReducedMotion()` (from
  `framer-motion`) or a `matchMedia('(prefers-reduced-motion: reduce)')` check,
  and pass `speed={0}` / `interactive={false}` or skip rendering entirely.

## TypeScript

Rename to `AuroraField.tsx` and add a props type:

```ts
type AuroraFieldProps = {
  heatColor?: string; heatIntensity?: number; speed?: number; scale?: number;
  warmth?: number; grain?: number; interactive?: boolean; renderScale?: number;
  className?: string; style?: React.CSSProperties;
};
```
Everything else compiles as-is.
```
