'use client';

import { useEffect, useRef } from 'react';

/*
  <AuroraField /> — interactive WebGL smoke background for Next.js.

  Drop it once near the top of your layout/page. It renders a fixed,
  full-viewport canvas behind everything (pointer-events: none), so your
  content stays fully clickable while the smoke still reacts to the cursor.

  Props (all optional):
    heatColor      string  hex the click flare cools toward / hover tint   '#ff5e1a'
    heatIntensity  number  hover + click strength (0–2)                     1.0
    speed          number  idle drift speed (0–2)                           1.0
    scale          number  smoke feature scale (0.5–2)                      1.0
    warmth         number  0 = whiter cores, 1 = oranger                    0.45
    grain          number  film grain amount (0–1)                          0.5
    interactive    boolean track cursor / clicks                            true
    renderScale    number  internal res multiplier — lower = faster/softer  0.6
    className/style passthrough for the canvas element
*/

const VERT = `
attribute vec2 aPos;
void main(){ gl_Position = vec4(aPos, 0.0, 1.0); }
`;

const FRAG = `
precision highp float;

uniform vec2  uResolution;
uniform float uTime;
uniform vec2  uMouse;
uniform vec2  uVel;
uniform float uHover;
uniform vec3  uClicks[10];
uniform float uSpeed;
uniform float uScale;
uniform float uWarmth;
uniform float uGlow;
uniform float uGrain;
uniform vec3  uAccent;

float hash(vec2 p){
  p = fract(p * vec2(123.34, 456.21));
  p += dot(p, p + 45.32);
  return fract(p.x * p.y);
}
vec2 hash2(vec2 p){
  p = vec2(dot(p, vec2(127.1, 311.7)), dot(p, vec2(269.5, 183.3)));
  return fract(sin(p) * 43758.5453123) * 2.0 - 1.0;
}
float noise(vec2 p){
  vec2 i = floor(p);
  vec2 f = fract(p);
  vec2 u = f * f * f * (f * (f * 6.0 - 15.0) + 10.0);
  float n = mix(
    mix(dot(hash2(i + vec2(0.0,0.0)), f - vec2(0.0,0.0)),
        dot(hash2(i + vec2(1.0,0.0)), f - vec2(1.0,0.0)), u.x),
    mix(dot(hash2(i + vec2(0.0,1.0)), f - vec2(0.0,1.0)),
        dot(hash2(i + vec2(1.0,1.0)), f - vec2(1.0,1.0)), u.x),
    u.y);
  return 0.5 + 0.5 * n;
}
const mat2 M = mat2(1.58, 1.12, -1.12, 1.58);
float fbm(vec2 p){
  float v = 0.0;
  float a = 0.5;
  for (int i = 0; i < 6; i++){ v += a * noise(p); p = M * p; a *= 0.47; }
  return v;
}

void main(){
  vec2 uv = gl_FragCoord.xy / uResolution.xy;
  float aspect = uResolution.x / uResolution.y;

  vec2 p = uv;
  p.x *= aspect;
  vec2 m = uMouse; m.x *= aspect;
  float md = distance(p, m);

  float t = uTime * 0.04 * uSpeed;

  float stir = exp(-md * md * 7.0);
  vec2 sp = p * (1.05 * uScale) + uVel * stir * 0.9;

  vec2 q = vec2(fbm(sp + t), fbm(sp + vec2(5.2, 1.3) - t));
  vec2 r = vec2(
    fbm(sp + 0.9 * q + vec2(1.7, 9.2) + 0.14 * t),
    fbm(sp + 0.9 * q + vec2(8.3, 2.8) - 0.11 * t));
  float f = fbm(sp + 1.0 * r);

  float cloud = clamp(f + 0.42 * (r.x - 0.5) + 0.04, 0.0, 1.0);
  float dens = smoothstep(0.33, 0.74, cloud);
  float haze = smoothstep(0.34, 0.92, fbm(sp * 0.5 + r * 0.5 + 0.05 * t));

  vec3 base  = vec3(0.014, 0.010, 0.020);
  vec3 ember = vec3(0.97, 0.38, 0.08);
  vec3 hot   = mix(vec3(1.0, 0.94, 0.86), vec3(1.0, 0.74, 0.36), uWarmth);

  vec3 col = base;
  col += ember * haze * 0.20;
  col += ember * dens * 1.5;
  col += hot   * pow(max(dens - 0.46, 0.0), 1.4) * 1.8;
  col += ember * 0.06 * dens * (0.6 + 0.4 * sin(t + r.y * 6.2831));

  // hover: heat bloom
  float glow = exp(-md * md * 9.0);
  float halo = exp(-md * md * 2.6);
  float heat = uHover * uGlow * (glow + 0.25 * halo);
  vec3 white = vec3(1.0, 0.95, 0.88);
  col += col * heat * 1.5;
  col += mix(uAccent, white, 0.55) * heat * (0.3 + 0.95 * dens) * 1.25;

  // click: ignition flare
  for (int i = 0; i < 10; i++){
    vec3 c = uClicks[i];
    if (c.z < 0.0) continue;
    float age = uTime - c.z;
    if (age < 0.0 || age > 1.7) continue;
    vec2 cp = c.xy; cp.x *= aspect;
    float cd = distance(p, cp);
    float spread = 0.045 + age * 0.17;
    float burst = exp(-cd * cd / (spread * spread));
    float life = exp(-age * 3.0);
    vec3 core = mix(uAccent, vec3(1.0, 0.97, 0.92), clamp(life * 1.4, 0.0, 1.0));
    col += core * burst * life * 2.5 * uGlow;
    float rim = exp(-pow((cd - age * 0.5) * 10.0, 2.0)) * life;
    col += vec3(1.0, 0.88, 0.66) * rim * 0.55 * uGlow;
  }

  float gr = hash(gl_FragCoord.xy + fract(uTime) * 311.7) * 2.0 - 1.0;
  col += gr * uGrain * 0.04;

  col = col / (1.0 + col * 0.22);
  col *= 1.16;

  float vig = smoothstep(1.35, 0.25, length(uv - 0.5));
  col *= mix(0.7, 1.0, vig);

  col = clamp(col, 0.0, 1.0);
  gl_FragColor = vec4(col, 1.0);
}
`;

function hexToRgb(hex) {
  const h = (hex || '#ff5e1a').replace('#', '');
  const n = parseInt(h.length === 3 ? h.split('').map((c) => c + c).join('') : h, 16);
  return [((n >> 16) & 255) / 255, ((n >> 8) & 255) / 255, (n & 255) / 255];
}

function compile(gl, type, src) {
  const s = gl.createShader(type);
  gl.shaderSource(s, src);
  gl.compileShader(s);
  if (!gl.getShaderParameter(s, gl.COMPILE_STATUS)) {
    console.error('AuroraField shader error:', gl.getShaderInfoLog(s));
  }
  return s;
}

export default function AuroraField({
  heatColor = '#ff5e1a',
  heatIntensity = 1.0,
  speed = 1.0,
  scale = 1.0,
  warmth = 0.45,
  grain = 0.5,
  interactive = true,
  renderScale = 0.6,
  className,
  style,
}) {
  const canvasRef = useRef(null);
  // latest props, read live by the render loop without re-initialising WebGL
  const cfg = useRef({});
  cfg.current = { heatColor, heatIntensity, speed, scale, warmth, grain, interactive, renderScale };

  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    const gl = canvas.getContext('webgl', { antialias: false, alpha: false, powerPreference: 'high-performance' });
    if (!gl) { console.error('AuroraField: WebGL unavailable'); return; }

    const prog = gl.createProgram();
    gl.attachShader(prog, compile(gl, gl.VERTEX_SHADER, VERT));
    gl.attachShader(prog, compile(gl, gl.FRAGMENT_SHADER, FRAG));
    gl.linkProgram(prog);
    gl.useProgram(prog);

    const buf = gl.createBuffer();
    gl.bindBuffer(gl.ARRAY_BUFFER, buf);
    gl.bufferData(gl.ARRAY_BUFFER, new Float32Array([-1, -1, 3, -1, -1, 3]), gl.STATIC_DRAW);
    const aPos = gl.getAttribLocation(prog, 'aPos');
    gl.enableVertexAttribArray(aPos);
    gl.vertexAttribPointer(aPos, 2, gl.FLOAT, false, 0, 0);

    const U = {};
    ['uResolution','uTime','uMouse','uVel','uHover','uClicks','uSpeed','uScale','uWarmth','uGlow','uGrain','uAccent']
      .forEach((n) => { U[n] = gl.getUniformLocation(prog, n); });

    let W = 0, H = 0;
    function resize() {
      const rs = cfg.current.renderScale || 0.6;
      const dpr = Math.min(window.devicePixelRatio || 1, 1.4);
      W = Math.max(2, Math.floor(window.innerWidth * dpr * rs));
      H = Math.max(2, Math.floor(window.innerHeight * dpr * rs));
      canvas.width = W; canvas.height = H;
      gl.viewport(0, 0, W, H);
    }
    resize();
    window.addEventListener('resize', resize);

    const mouse = { tx: 0.5, ty: 0.5, x: 0.5, y: 0.5, hover: 0, hoverT: 0 };
    const vel = { x: 0, y: 0, lx: 0.5, ly: 0.5 };
    const clicks = new Float32Array(30).fill(-1);
    let clickPtr = 0;
    const startT = performance.now() / 1000;

    function onMove(e) {
      if (!cfg.current.interactive) return;
      mouse.tx = e.clientX / window.innerWidth;
      mouse.ty = 1 - e.clientY / window.innerHeight;
      mouse.hoverT = 1;
    }
    function onDown(e) {
      if (!cfg.current.interactive) return;
      onMove(e);
      clicks[clickPtr * 3 + 0] = mouse.tx;
      clicks[clickPtr * 3 + 1] = mouse.ty;
      clicks[clickPtr * 3 + 2] = performance.now() / 1000 - startT;
      clickPtr = (clickPtr + 1) % 10;
    }
    function onLeave() { mouse.hoverT = 0; }
    window.addEventListener('pointermove', onMove);
    window.addEventListener('pointerdown', onDown);
    window.addEventListener('pointerleave', onLeave);

    let raf;
    function frame() {
      const c = cfg.current;
      const now = performance.now() / 1000 - startT;

      mouse.x += (mouse.tx - mouse.x) * 0.12;
      mouse.y += (mouse.ty - mouse.y) * 0.12;
      mouse.hover += (mouse.hoverT - mouse.hover) * 0.10;

      const aspect = W / H;
      const vx = (mouse.x - vel.lx) * aspect;
      const vy = (mouse.y - vel.ly);
      vel.lx = mouse.x; vel.ly = mouse.y;
      vel.x = (vel.x * 0.85 + vx * 4.0) * 0.9;
      vel.y = (vel.y * 0.85 + vy * 4.0) * 0.9;

      gl.uniform2f(U.uResolution, W, H);
      gl.uniform1f(U.uTime, now);
      gl.uniform2f(U.uMouse, mouse.x, mouse.y);
      gl.uniform2f(U.uVel, vel.x, vel.y);
      gl.uniform1f(U.uHover, mouse.hover);
      gl.uniform3fv(U.uClicks, clicks);
      gl.uniform1f(U.uSpeed, c.speed);
      gl.uniform1f(U.uScale, c.scale);
      gl.uniform1f(U.uWarmth, c.warmth);
      gl.uniform1f(U.uGlow, c.heatIntensity);
      gl.uniform1f(U.uGrain, c.grain);
      gl.uniform3fv(U.uAccent, hexToRgb(c.heatColor));

      gl.drawArrays(gl.TRIANGLES, 0, 3);
      raf = requestAnimationFrame(frame);
    }
    frame();

    return () => {
      cancelAnimationFrame(raf);
      window.removeEventListener('resize', resize);
      window.removeEventListener('pointermove', onMove);
      window.removeEventListener('pointerdown', onDown);
      window.removeEventListener('pointerleave', onLeave);
      gl.getExtension('WEBGL_lose_context')?.loseContext();
    };
  }, []);

  return (
    <canvas
      ref={canvasRef}
      aria-hidden="true"
      className={className}
      style={{
        position: 'fixed',
        inset: 0,
        width: '100vw',
        height: '100vh',
        display: 'block',
        zIndex: -1,
        pointerEvents: 'none',
        background: '#050407',
        ...style,
      }}
    />
  );
}
