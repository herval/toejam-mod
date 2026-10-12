// ROM helpers for the web player: unzip, identify and patch, all inside the browser.
// The page never uploads the ROM anywhere; these functions only see bytes the user picked.

export const REV02_SHA1 = "85e8d0a4fac591b25b77c35680ac4175976f251b";

export async function sha1(bytes) {
  const digest = await crypto.subtle.digest("SHA-1", bytes);
  return [...new Uint8Array(digest)].map((b) => b.toString(16).padStart(2, "0")).join("");
}

const ROM_NAME = /\.(md|gen|bin|smd)$/i;

async function inflateRaw(data) {
  const stream = new Blob([data]).stream().pipeThrough(new DecompressionStream("deflate-raw"));
  return new Uint8Array(await new Response(stream).arrayBuffer());
}

// The ROM inside a .zip (first .md/.gen/.bin/.smd entry, stored or deflated).
// Anything that isn't a zip comes back unchanged.
export async function unzip(bytes) {
  const v = new DataView(bytes.buffer, bytes.byteOffset, bytes.byteLength);
  if (bytes.length < 22 || v.getUint32(0, true) !== 0x04034b50) return bytes;
  // Sizes in local headers can be zero (streamed zips), so walk the central directory.
  let end = bytes.length - 22;
  while (end >= 0 && v.getUint32(end, true) !== 0x06054b50) end--;
  if (end < 0) throw new Error("This zip file looks damaged.");
  let p = v.getUint32(end + 16, true);
  for (let n = v.getUint16(end + 10, true); n > 0; n--) {
    if (v.getUint32(p, true) !== 0x02014b50) throw new Error("This zip file looks damaged.");
    const method = v.getUint16(p + 10, true), size = v.getUint32(p + 20, true);
    const nameLen = v.getUint16(p + 28, true), extraLen = v.getUint16(p + 30, true), noteLen = v.getUint16(p + 32, true);
    const local = v.getUint32(p + 42, true);
    const name = new TextDecoder().decode(bytes.subarray(p + 46, p + 46 + nameLen));
    p += 46 + nameLen + extraLen + noteLen;
    if (!ROM_NAME.test(name)) continue;
    const start = local + 30 + v.getUint16(local + 26, true) + v.getUint16(local + 28, true);
    const data = bytes.subarray(start, start + size);
    if (method === 0) return data.slice();
    if (method === 8) return inflateRaw(data);
    throw new Error(`Can't unpack ${name} (zip method ${method}). Unzip it and load the ROM itself.`);
  }
  throw new Error("No Genesis ROM (.md, .gen, .bin, .smd) inside this zip.");
}

// Applies an IPS patch (as written by tjmod.py: plain and RLE records, growth allowed).
export function applyIps(rom, ips) {
  if (new TextDecoder().decode(ips.subarray(0, 5)) !== "PATCH") throw new Error("Not an IPS patch.");
  let out = rom.slice();
  const fit = (n) => {
    if (n <= out.length) return;
    const grown = new Uint8Array(n);
    grown.set(out);
    out = grown;
  };
  let p = 5;
  for (;;) {
    if (p + 3 > ips.length) throw new Error("The patch is truncated.");
    if (ips[p] === 0x45 && ips[p + 1] === 0x4f && ips[p + 2] === 0x46) break; // "EOF"
    const off = (ips[p] << 16) | (ips[p + 1] << 8) | ips[p + 2];
    const size = (ips[p + 3] << 8) | ips[p + 4];
    p += 5;
    if (size) {
      fit(off + size);
      out.set(ips.subarray(p, p + size), off);
      p += size;
    } else {
      const count = (ips[p] << 8) | ips[p + 1];
      fit(off + count);
      out.fill(ips[p + 2], off, off + count);
      p += 3;
    }
  }
  return out;
}
