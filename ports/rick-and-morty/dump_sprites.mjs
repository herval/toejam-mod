// Runs Schwifty Jam's own sprite code (vendor/schwifty-pix.js) against a tiny fake canvas
// and writes every sprite out as RGBA PNG-ready JSON, so the ROM port uses identical art.
//   node dump_sprites.mjs [out/sprites.json]
import fs from "node:fs";
import path from "node:path";
import vm from "node:vm";
import { fileURLToPath } from "node:url";

const here = path.dirname(fileURLToPath(import.meta.url));

function fakeCanvas() {
  const c = { width: 0, height: 0, data: null, mirror: false };
  c.getContext = () => ({
    createImageData: (w, h) => ({ width: w, height: h, data: new Uint8ClampedArray(w * h * 4) }),
    putImageData: (img) => { c.data = img.data; },
    translate() {},
    scale(sx) { if (sx < 0) c.mirror = true; },
    drawImage(src) {
      const w = src.width, h = src.height, out = new Uint8ClampedArray(w * h * 4);
      for (let y = 0; y < h; y++) for (let x = 0; x < w; x++) {
        const sx = c.mirror ? w - 1 - x : x;
        out.set(src.data.subarray((y * w + sx) * 4, (y * w + sx) * 4 + 4), (y * w + x) * 4);
      }
      c.data = out;
    },
  });
  return c;
}

const ctx = { window: {}, document: { createElement: () => fakeCanvas() }, Math, Object, Array };
vm.createContext(ctx);
// Expose the raw grids too (they're consts inside pix.js's IIFE), for new poses.
const src = fs.readFileSync(path.join(here, "vendor/schwifty-pix.js"), "utf8")
  .replace(/\}\)\(\);\s*$/, "SJ.raw = { PAL, OUT, RICK, MORTY };\n})();");
vm.runInContext(src, ctx);
const lib = ctx.window.SJ.pix.build();

const pack = (s) => ({ w: s.c.width, h: s.c.height, ax: s.ax, ay: s.ay, rgba: Buffer.from(s.c.data).toString("base64") });
const out = {};
for (const [name, v] of Object.entries(lib)) {
  if (Array.isArray(v)) out[name] = v.map(pack);
  else if (v && v.c) out[name] = pack(v);
  else if (v && typeof v === "object") {
    out[name] = {};
    for (const [k, s] of Object.entries(v)) out[name][k] = Array.isArray(s) ? s.map(pack) : s && s.c ? pack(s) : undefined;
  }
}
out.__raw = JSON.parse(JSON.stringify(ctx.window.SJ.raw));
const dest = process.argv[2] ?? path.join(here, "out", "sprites.json");
fs.mkdirSync(path.dirname(path.resolve(dest)), { recursive: true });
fs.writeFileSync(dest, JSON.stringify(out));
console.log("wrote", Object.keys(out).join(", "));
