// Schwifty Jam — pixel-art toolkit and sprite data (16-bit Genesis style).
// Sprites are authored as rows of palette letters; outlines are added automatically.
(() => {
'use strict';
const SJ = (window.SJ = window.SJ || {});
const OUT = '#140c1c';

// ---------------------------------------------------------------- palette
const PAL = {
  k: '#140c1c', w: '#ffffff',
  h: '#b4e4f4', H: '#6aaed0',            // Rick hair
  s: '#f4d8bc', S: '#d4a47c',            // skin
  c: '#f4f8fc', C: '#a8b6ca',            // lab coat
  b: '#98d4ec', B: '#5a9cc0',            // Rick shirt
  p: '#8a5a30', P: '#5a381c',            // brown pants
  o: '#3c2818',                          // dark shoes
  g: '#b4e070', m: '#6a2a20',            // drool, mouth
  n: '#7a4420', N: '#542c14',            // Morty hair
  y: '#f8e040', Y: '#c8a818',            // Morty shirt
  u: '#3c6cc8', U: '#28489a',            // Morty pants
  W: '#f2f2f2', V: '#c4ccd6',            // white + shade
  f: '#f4a4ac', F: '#c87080', r: '#6a1020', t: '#fffaf0', // Cronenberg
  i: '#a8c858', I: '#6e9036', e: '#101018', q: '#3464b4', Q: '#1f4080', a: '#f0c830', // Gromflomite
  x: '#9098a8', X: '#5a6070', M: '#ff50d8',
  G: '#a4acbc', T: '#c89060', j: '#9a6840', R: '#d03030', D: '#2e7a30', d: '#6a4a2a',
  L: '#3cc8a0', l: '#1e9070', J: '#8cf0d0', z: '#8a5a7a', Z: '#5a3050', v: '#ff6fae',
  O: '#fff4e0', A: '#e84040', E: '#b02828', K: '#f4ecd8', ',': '#c8b898',
  // deeper ramp steps for the hand-shaded sprites
  1: '#5a8cb4', 2: '#c08a6a', 3: '#96a2bc', 4: '#3e200e', 5: '#a88410', 6: '#8e4458', 7: '#ffd4da',
  8: '#5a8ae0', 9: '#d4ec88', 0: '#9aa2b4', '+': '#10604c',
};
const hexCache = {};
function rgb(hex) {
  if (hexCache[hex]) return hexCache[hex];
  const n = parseInt(hex.slice(1), 16);
  return (hexCache[hex] = [(n >> 16) & 255, (n >> 8) & 255, n & 255]);
}

// ---------------------------------------------------------------- grids
function grid(rows, pal = {}) {
  const h = rows.length, w = Math.max(...rows.map(r => r.length));
  const P = Object.assign({}, PAL, pal), px = new Array(w * h).fill(null);
  for (let y = 0; y < h; y++) for (let x = 0; x < w; x++) {
    const ch = rows[y][x];
    if (ch === undefined || ch === '.' || ch === ' ') continue;
    px[y * w + x] = P[ch] || '#ff00ff';
  }
  return { w, h, px };
}
function blank(w, h) { return { w, h, px: new Array(w * h).fill(null) }; }
function blit(dst, src, ox, oy) {
  for (let y = 0; y < src.h; y++) for (let x = 0; x < src.w; x++) {
    const c = src.px[y * src.w + x];
    const dx = x + ox, dy = y + oy;
    if (c && dx >= 0 && dy >= 0 && dx < dst.w && dy < dst.h) dst.px[dy * dst.w + dx] = c;
  }
}
function put(g, x, y, c) { if (x >= 0 && y >= 0 && x < g.w && y < g.h) g.px[y * g.w + x] = c; }
function rect(g, x, y, w, h, c) { for (let j = 0; j < h; j++) for (let i = 0; i < w; i++) put(g, x + i, y + j, c); }
const hex = ([r, g, b]) => '#' + ((1 << 24) | (Math.round(r) << 16) | (Math.round(g) << 8) | Math.round(b)).toString(16).slice(1);
const mix = (a, b, t) => { const A = rgb(a), B = rgb(b); return hex(A.map((v, i) => v + (B[i] - v) * t)); };
// selective outline ("sel-out"): each edge pixel is a deep, hue-kept version of what it wraps,
// with the ground side left near-black so sprites stay anchored
function outline(g, col = OUT) {
  const o = blank(g.w + 2, g.h + 2);
  blit(o, g, 1, 1);
  const at = (x, y) => (x >= 0 && y >= 0 && x < o.w && y < o.h ? o.px[y * o.w + x] : null);
  const edge = [];
  for (let y = 0; y < o.h; y++) for (let x = 0; x < o.w; x++) {
    if (at(x, y)) continue;
    const n = [at(x, y - 1), at(x - 1, y), at(x + 1, y), at(x, y + 1)].filter(Boolean);
    if (!n.length) continue;
    const below = !!at(x, y - 1) && !at(x, y + 1); // outline under a filled pixel = bottom edge
    edge.push([y * o.w + x, below ? col : mix(n[0], col, 0.72)]);
  }
  for (const [i, c] of edge) o.px[i] = c;
  return o;
}
// rim light from the top-left, soft shade on the bottom-right, applied to the sprite's own edge pixels
function rim(g, lift = 0.22, drop = 0.2) {
  const at = (x, y) => (x >= 0 && y >= 0 && x < g.w && y < g.h ? g.px[y * g.w + x] : null);
  const out = g.px.slice();
  for (let y = 0; y < g.h; y++) for (let x = 0; x < g.w; x++) {
    const c = at(x, y); if (!c) continue;
    if (!at(x, y - 1) || !at(x - 1, y)) out[y * g.w + x] = mix(c, '#ffffff', lift);
    else if (!at(x, y + 1) || !at(x + 1, y)) out[y * g.w + x] = mix(c, '#1a1030', drop);
  }
  return { w: g.w, h: g.h, px: out };
}
function canvasOf(g) {
  const c = document.createElement('canvas'); c.width = g.w; c.height = g.h;
  const cx = c.getContext('2d'), img = cx.createImageData(g.w, g.h);
  for (let i = 0; i < g.px.length; i++) {
    const col = g.px[i]; if (!col) continue;
    const [r, gg, b] = rgb(col);
    img.data[i * 4] = r; img.data[i * 4 + 1] = gg; img.data[i * 4 + 2] = b; img.data[i * 4 + 3] = 255;
  }
  cx.putImageData(img, 0, 0);
  return c;
}
function flipped(c) {
  const f = document.createElement('canvas'); f.width = c.width; f.height = c.height;
  const x = f.getContext('2d'); x.translate(c.width, 0); x.scale(-1, 1); x.drawImage(c, 0, 0);
  return f;
}
// sprite = canvas + anchor (feet, bottom-centre)
function sprite(g, ax, ay) {
  const c = canvasOf(g);
  return { c, f: null, w: g.w, h: g.h, ax: ax ?? Math.floor(g.w / 2), ay: ay ?? g.h - 1 };
}
function S(rows, pal, ol = true) { const g = grid(rows, pal); return sprite(ol ? outline(rim(g)) : g); }

// ---------------------------------------------------------------- characters
// Upper bodies are authored per direction; legs are generated so the walk cycle stays consistent.
const RICK = {
  down: [
    '...h...h...h...',
    '..hhH.hhh.Hhh..',
    'h.hhhhhhhhhhH.1',
    'hhhhhhhhhhhhHH1',
    'hhHssssssssSHH1',
    'hHsHHHHHHHHHSH1',
    'hhsswkwswkwsSH1',
    'hhsswwwswwwsSH1',
    '.hss22sSs22ssh.',
    '..sssssSSsssS..',
    '..ss2mmmmm2sS..',
    '..sssssssssgS..',
    '...SssssssSg...',
    '......2s2......',
    '.cccc3bbb3cccc.',
    'ccccc3bbb3cccC3',
    'ccCcc3bBb3ccC33',
    'ccCcc3bBb3ccC33',
    'ccCcc3bBb3ccC33',
    'ccCcC3bBb3CcC33',
    'scCcc3bBb3ccC3s',
    '.cccccpppccccC.',
    '.CCCCCpPpCCC33.',
  ],
  up: [
    '...h...h...h...',
    '..hhH.hhh.Hhh..',
    'h.hhhhhhhhhhH.1',
    'hhhhhhhhhhhhHH1',
    'hhhhhhhhhhhhHH1',
    'hhhhhhhhhhhhHH1',
    'hhHhhhhhhhhHhH1',
    'hhhHhhhhhhHhhH1',
    '.shhHhhhhHhhHs.',
    '..hhhHhhHhhhH..',
    '..HhhhhhhhhH1..',
    '...HHhhhhhH1...',
    '....2sssss2....',
    '......2s2......',
    '.ccccc333ccccC.',
    'cccccccccccccC3',
    'ccCcccccccccC33',
    'ccCcccc3cccccC3',
    'ccCcccc3cccccC3',
    'ccCcccc3cccccC3',
    'scCcccc3cccccCs',
    '.cccccc3ccccC3.',
    '.CCCCCC3CCCC33.',
  ],
  side: [
    '..h..h.h.......',
    '.hhHhhhhh......',
    'hhhhhhhhhhh....',
    '1Hhhhhhhhhhhh..',
    '.1HhhhhhsssssS.',
    'hHhhhhhHHHHHHs.',
    '1Hhhh2swkwswk..',
    '.11hh2swwwsww..',
    '..1Hs2sssssSsS.',
    '...Hs2sssssssS.',
    '....2ssss2mmmm.',
    '.....2sssssssg.',
    '......2sssss2..',
    '.......2s2.....',
    '.....ccc3bb....',
    '....cccc3bbB...',
    '....ccCc3bbB...',
    '....ccCc3bbB...',
    '....ccCc3bbB...',
    '....ccCc3bbB...',
    '....ccCs3bBB...',
    '....cccc3ppp...',
    '....CCC33ppP...',
  ],
  legs: { len: 4, front: [4, 8], lw: 3, side: 7, pants: ['p', 'P'], shoe: 'o' },
};
const MORTY = {
  down: [
    '...nnnnnnN...',
    '..nnnnnnnnnN.',
    '.nnnnnnnnnnN.',
    '.nnNnnnnnNnN4',
    'nnNnsnNnsnnN4',
    'Nsssssssssss4',
    'sswwwssswwwsS',
    'sswkwssswkwsS',
    'sswwwssswwwsS',
    'Ssssss2ssssS2',
    '.ssssmmmsssS.',
    '..2sssssss2..',
    '....2sss2....',
    '.yyyYsssYyyY.',
    'yyyyyYYYyyyY5',
    'yYyyyyyyyyY55',
    'yYyyyyyyyyY55',
    'yYyyyyyyyyY55',
    'sYyyyyyyyyY5s',
    '.YYYYYYYYY55.',
  ],
  up: [
    '...nnnnnnN...',
    '..nnnnnnnnnN.',
    '.nnnnnnnnnnN.',
    '.nnnnnnnnnnN4',
    'nnnnnnnnnnnN4',
    'nnnnnnnnnnNN4',
    'nNnnnnnnnnNN4',
    'nnNnnnnnnNnN4',
    'snnNnnnnNnnN2',
    'sNnnNnnNnnNN2',
    '.NNnnnnnnNN4.',
    '..4NNNNNNN4..',
    '...2sssss2...',
    '.yyyyyyyyyyY.',
    'yyyyyyyyyyyY5',
    'yYyyyyyyyyY55',
    'yYyyyyyyyyY55',
    'yYyyyyyyyyY55',
    'sYyyyyyyyyY5s',
    '.YYYYYYYYY55.',
  ],
  side: [
    '....nnnnnN...',
    '..nnnnnnnnN..',
    '.nnnnnnnnnnN.',
    'nnnnnnnnnnnnN',
    'NnnnnnnnsnNs.',
    'NnnNn2sssssss',
    '4NnNs2swwwsww',
    '4NNs2sswkwswk',
    '.4Ns2ssswwwsw',
    '..Nsssssssss2',
    '..2ssssmmNm..',
    '...2sssssss..',
    '.....2ss2....',
    '....yyyyyY...',
    '...yyyyyyYY..',
    '...yyy5yyYY..',
    '...yyy5yyYY..',
    '...yyys5yYY..',
    '...YYY55YY5..',
  ],
  legs: { len: 3, front: [3, 7], lw: 3, side: 5, pants: ['u', 'U'], shoe: 'W' },
};
const PICKLE = [
  '...gppp...',
  '..gppppP..',
  '.gHHHHHHP.',
  '.gwkppwkP.',
  '.pwwppwwP.',
  '.gppppppP.',
  '.pkkkkkkP.',
  '.ppwwwwpP.',
  '.gppppppd.',
  '.pPppppPd.',
  '.gppdpppd.',
  '.pppppPpd.',
  '.gPpppppd.',
  '.ppppdPpd.',
  '.gppppppd.',
  '..pPpppd..',
  '..ppppPd..',
  '...dddd...',
];
const PICKLE_PAL = { p: '#70c040', P: '#488828', g: '#a8e070', d: '#2e6018' };

function charFrames(def) {
  const out = {};
  const L = def.legs;
  for (const dir of ['down', 'up', 'side']) {
    const body = grid(def[dir]);
    const frames = [];
    for (let f = 0; f < 4; f++) {
      const g = blank(body.w, body.h + L.len + 2);
      const bob = f % 2 === 0 ? 1 : 0;
      blit(g, body, 0, bob);
      const hip = body.h + bob;
      const [pc, ps] = L.pants.map(k => PAL[k]), sc = PAL[L.shoe];
      if (dir !== 'side') {
        L.front.forEach((lx, i) => {
          const lift = (f === 1 && i === 0) || (f === 3 && i === 1) ? 2 : 0;
          const len = L.len - lift + (bob ? 0 : 1);
          rect(g, lx, hip, L.lw, len, pc); rect(g, lx + L.lw - 1, hip, 1, len, ps);
          rect(g, lx + (i === 0 ? -1 : 0), hip + len, L.lw + 1, 1, sc);
        });
      } else {
        const len = L.len + (bob ? 0 : 1);
        const swing = f === 1 ? 2 : f === 3 ? -2 : 0;
        for (const [sgn, col] of [[-1, ps], [1, pc]]) {
          for (let r = 0; r < len; r++) {
            const off = Math.round((sgn * swing * (r + 1)) / len);
            rect(g, L.side + off, hip + r, L.lw, 1, col);
          }
          const off = sgn * swing;
          rect(g, L.side + off, hip + len, L.lw + 1, 1, sc);
        }
      }
      frames.push(sprite(outline(rim(g, 0.14, 0.14))));
    }
    if (dir === 'side') { out.right = frames; out.left = frames.map(s => ({ ...s, c: flipped(s.c) })); }
    else out[dir] = frames;
  }
  return out;
}

// generic legs for creatures: alternating lift animation
function creature(rows, pal, legs, opts = {}) {
  const body = grid(rows, pal);
  const frames = [];
  for (let f = 0; f < 4; f++) {
    const g = blank(body.w, body.h + legs.len + 1);
    blit(g, body, 0, 0);
    legs.xs.forEach((lx, i) => {
      const lift = (f === 1 && i % 2 === 0) || (f === 3 && i % 2 === 1) ? 1 : 0;
      rect(g, lx, body.h - (legs.overlap || 0), legs.w, legs.len - lift + (legs.overlap || 0), legs.col);
      if (legs.foot) rect(g, lx, body.h + legs.len - lift - 1, legs.w + 1, 1, legs.foot);
    });
    frames.push(sprite(outline(rim(g))));
  }
  return { right: frames, left: frames.map(s => ({ ...s, c: flipped(s.c) })) };
}

// ---------------------------------------------------------------- creatures
const CRONEN = [
  '......f7ff.ff.....',
  '....f77fffffffFf..',
  '..f77wwfffffFwkFF.',
  '.f7ffwkffffffFFfFf',
  '.fwwfffffFwwwfffFF',
  'f7wkffffffFwkwfFFF',
  'fffffffffffwwwFfF6',
  'ffffrrrrrrrrfffFF6',
  'fffrtrtrtrtrrfFFF6',
  'FffrrtrtrtrrrfFF66',
  'FFffrrrrrrrrfFF66.',
  '.6FFffffffffFF666.',
  '..6666666666666...',
];
const GROM = [
  '..9........9..',
  '...i......i...',
  '....8qqqqq....',
  '...88qaqqqQ...',
  '..QQQQQQQQQQ..',
  '..9iiiiiiiiI..',
  '.9eeeiiiieeeI.',
  '.ieweiiiieweI.',
  '.ieeeiiiieeeI.',
  '..iiiIkkIiiI..',
  '...IiIIIIiI...',
  '....8qqqqQ....',
  '..i8qqqqqqQi..',
  '.9i8qaqqqqQxxX',
  '.I.qqqqqqqQxM.',
  '...qqqqqqqQ...',
  '...kkakkkkk...',
  '...QQQQQQQQ...',
];
const DOG = [
  '..............M.....',
  '..............G.....',
  '...........GWGGG....',
  '..........GWGGGGX...',
  '..........XXXXXXXX..',
  '..........WWWkWWWWV.',
  '.V........WWWWWWWkk.',
  'VWV......VWWWWWWWV..',
  '.VWWWWWWWWWWWWWV....',
  '.WWWWWWWWWWWWWWV....',
  '.VWWWWWWWWWWWWVV....',
  '.0VVWWWWWWWWVV0.....',
  '..000000000000......',
];
const TERRY = [
  '....dddddd....',
  '...ddddddd4...',
  '..dddddddd44..',
  '...TTTTTTTj...',
  '..jTwkTTwkTj..',
  '..jTTTTjTTTj..',
  '...Tddddddj...',
  '...TTwtwtwj...',
  '....jTTTTj....',
  '..RRDDRRDDRE..',
  '.RRRDDRRDDREE.',
  'xTRwDDRRDDREjx',
  'xTDDRRDDwRDDjx',
  'x.DDRRDDRRDD.x',
  '..RRDDRRDDEE..',
  '..PPPPPPPPPP..',
];
const POOPY = [
  '....kkkk....',
  '....kkkk....',
  '....RRRE....',
  '..kkkkkkkk..',
  '...ayyyyY...',
  '..ayyyyyyY..',
  '.aywwyywwyY.',
  '.yywkyywkyY.',
  '.yywwyywwyY.',
  '.yyyyyyyyyY.',
  'ayyyykkyyyYY',
  'yyyyykkyyyYY',
  'yyyyyyyyyyYY',
  'YyyyyyyyyyY5',
  '.YyyyyyyyY5.',
  '..55555555..',
];
const MEESEEKS = [
  'm..lmmmmm..m',
  '.mlmmmmmmmM.',
  '.mlwwmmwwmM.',
  '.mmwkmmwkmM.',
  '.mmmmMMmmmM.',
  '.mmmmMMmmMd.',
  '..mmkkkkMd..',
  '...mmmmMd...',
  '...lmmmmM...',
  '..lmmmmmmM..',
  '...mmmmmM...',
  '...mmmmmM...',
  '...MmmmMd...',
  '....dddd....',
];
const MEE_PAL = { m: '#8cd8f8', M: '#58a8d8', l: '#d0f4ff', d: '#3a78b0' };

// ---------------------------------------------------------------- props
const TREE = [
  '.........LLLLLL.........',
  '......LLJJJLLLLLLL......',
  '....LLJJJJJLLLLlLLLL....',
  '...LJJJJLLLLLllLLJJLL...',
  '..LJJJLLLLvLlLLLJJJLLl..',
  '..LJJLLLLLLlLLLLLLLLll..',
  '.LLLLLLLLlllLLLvLLLLlll.',
  '.LLLlllLLLlLLLLLLLLllll.',
  'LLJJLLllLLLLlllLLLLllll+',
  'LJJJLLLLLlLLJJLLlLllll++',
  'LJLLLLvLLLLJJJLLLlllll++',
  '.LLLLLLLLLLLLLLLLllll++.',
  '.lLLLLLlllLLLLLLllll+++.',
  '..llLLLLLLLLvLlllll+++..',
  '...llllLLLLLllll++++++..',
  '.....llllllll+++++++....',
  '.......+++++++++++......',
  '..........zZz...........',
  '..........zZz...........',
  '..........zZz...........',
  '.........zzZzz..........',
  '........zz.Z.zz.........',
];
const TREE_PALS = [
  {},
  { L: '#b068e0', l: '#7038a8', J: '#e0b0ff', v: '#ffe060', '+': '#4a2080' },
  { L: '#70d048', l: '#3c9030', J: '#c0f090', v: '#ff5060', '+': '#246020' },
  { L: '#ff88c8', l: '#c04890', J: '#ffd0ec', v: '#fff6a0', '+': '#8c2c6c' },
];
const SHROOM = [
  '.......AAAAAA.......',
  '.....AAOOOAAAAA.....',
  '...AAAOOOOOAAAAOA...',
  '..AAAAAOOOAAAAAAAA..',
  '.AOOAAAAAAAAAAOOAAE.',
  '.AOOOAAAAAAOOAAAAEE.',
  'AAOOAAAAAAOOOAAAAEEE',
  'EAAAAAAAAAAAAAAAEEEE',
  '.EEEEEEEEEEEEEEEEEE.',
  '...,K,K,K,K,K,K,,...',
  '........KKK,........',
  '........KKK,........',
  '.......KKKK,,.......',
  '.......KKKK,,.......',
  '......KKKKK,,,......',
];
const SHROOM_PALS = [{}, { A: '#9858e8', E: '#6030b0' }, { A: '#3890e0', E: '#2060a8' }, { A: '#f08a3c', E: '#b85a18' }];
const EYEPLANT = [
  '..wwww..',
  '.wwvvww.',
  '.wvkkvw.',
  '.wvkkvw.',
  '.wwvvww.',
  '..wwww..',
  '...LL...',
  '...Ll...',
  '....L...',
  '...lL...',
  'L..L...L',
  'LL.Ll.LL',
  '.LLLLLL.',
  '..LLLL..',
];
const ROCK = [
  '....WWWGG.......',
  '..WWWGGGGGX.....',
  '.WWGGGGGGXXGGX..',
  '.WGGGGGGXXGWGGX.',
  'WGGGGGGXGGWGGGGX',
  'GGGGGGGXGGGGGGXX',
  'XGGGGGGGGGGGGXX#',
  '.XX########XXX#.',
];
const ROCK_PAL = { G: '#a8aabc', W: '#d8dae8', X: '#6c6e84', '#': '#46485c' };
const PRESENT = [
  '...rr..rr...',
  '..r..rr..r..',
  '...rrrrrr...',
  'BBBBBrrBBBBB',
  'bbbbbrrbbbbb',
  '.BBBBrrBBBB.',
  '.BBBBrrBBBB.',
  '.rrrrrrrrrr.',
  '.BBBBrrBBBB.',
  '.BBBBrrBBBB.',
  '.bbbbrrbbbbb',
];
const WRAPS = [
  ['#e8486c', '#b02848'], ['#3ca8e8', '#2070b0'], ['#a060e8', '#6c30b8'], ['#f8b830', '#c88010'], ['#38c878', '#1e9450'],
  ['#ff7a45', '#c85020'], ['#f060b8', '#b83088'], ['#20c0c8', '#108890'], ['#90705e', '#604838'], ['#c0cc30', '#8c9818'],
  ['#6070d0', '#3c48a0'], ['#e85050', '#b02828'], ['#30b0a0', '#187c70'], ['#d8d8e8', '#9898b0'], ['#704098', '#482068'],
  ['#88d840', '#5aa020'], ['#ffa0a0', '#d06868'],
];
const RIBBONS = ['#fff4c8', '#f8e040', '#ff4d6d', '#2c2244', '#b8f2ff'];
const COIN = [
  '..ooo..',
  '.owooo.',
  'owoooOo',
  'ooooOOo',
  'oooOOOo',
  '.oOOOo.',
  '..ooo..',
];
const COIN_PAL = { o: '#f8d048', O: '#c88818', w: '#fff8d0' };
const PARTS = [
  ['.xxxxxxx...', 'xwxxxxxxXX.', 'xxxxxxxxXXM', 'XXXXXXXXXX.', '..XX.......'],
  ['..xxxx..', '.xggggx.', '.xgwggx.', '.xggggx.', '.xggggx.', '..xxxx..'],
  ['..xx..', '.xRRx.', '.xRRx.', '..xx..', '..XX..', '..XX..', '..XX..', '..XX..'],
];
const PART_PAL = { g: '#7cff4f', w: '#e0ffd0' };
const FOOD = {
  sauce: [['wwwwwwww', 'wRRRRRRw', 'wRwRwRRw', 'wRRRRRRw', 'wwwwwwww'], {}],
  cereal: [['.qqqqq.', 'qqqqqqq', 'qaeqaeq', 'qqqqqqq', 'qaaaaaq', 'qqqqqqq', 'qqqqqqq', '.QQQQQ.'], {}],
  pizza: [['aaaaaaaa', 'RyyRyyyy', '.yyyyRy.', '.yRyyy..', '..yyy...', '..yy....', '...y....'], { y: '#f8d060', a: '#c88040' }],
  fleeb: [['..X..', '.MMM.', 'MMMMM', 'MwMMM', 'MMMMM', 'MMMMM', '.MMM.'], { M: '#9848d8', w: '#e0c0ff' }],
};
const VENDING = [
  'RRRRRRRRRRRRRR',
  'RwwRwRwRRwwRwR',
  'RRRRRRRRRRRRRR',
  'XxxxxxxxxxxxxX',
  'XbBbBbBbBxxxxX',
  'XxxxxxxxxxMMxX',
  'XaRaRaRaRxxxxX',
  'XxxxxxxxxxkkxX',
  'XvLvLvLvLxxxxX',
  'XxxxxxxxxxxxxX',
  'XbBaRvLbBxxxxX',
  'XxxxxxxxxxxxxX',
  'XkkkkkkkkkxxxX',
  'XkkkkkkkkkxxxX',
  'XxxxxxxxxxxxxX',
  'XXXXXXXXXXXXXX',
];
const ELEVATOR = [
  '..aaaaaaaaaaaaaaaa..',
  '.aaaaaaaawwaaaaaaaa.',
  'aaaaaaawwwwwwaaaaaaa',
  'aaaaaaaaawwaaaaaaaaa',
  'aaaaaaaaawwaaaaaaaaa',
  'aYYYYYYYYYYYYYYYYYYa',
  'aYxxxxxxxxXxxxxxxxYa',
  'aYxxxxxxxxXxxxxxxxYa',
  'aYxxxxxxxxXxxxxxxxYa',
  'aYxwxxxxxxXxxxxxxxYa',
  'aYxwxxxxxxXxxxxxxxYa',
  'aYxxxxxxxxXxxxxxxxYa',
  'aYxxxxxxxxXxxxxxxxYa',
  'aYxxxxxxxxXxxxxxxxYa',
  'aYxxxxxxxxXxxxxxxxYa',
  'aYxxxxxxxxXxxxxxxxYa',
  'aYxxxxxxxxXxxxxxxxYa',
  'aYxxxxxxxxXxxxxxxxYa',
  'aYxxxxxxxxXxxxxxxxYa',
  'aYXXXXXXXXXXXXXXXXYa',
  'YYYYYYYYYYYYYYYYYYYY',
];
const CRUISER = [
  '........bbbbbb........',
  '......bbwbbbbbb.......',
  '..xxxxxxxxxxxxxxxxxx..',
  'xxwxxxxxxxxxxxxxxxxxxx',
  'XXgXXXaXXXgXXXaXXXgXXX',
  '..XXXXXXXXXXXXXXXXXX..',
];
const CRUISER_PAL = { b: '#b8ecff', g: '#7cff4f' };

// ---------------------------------------------------------------- procedural
function ellipseGrid(w, h, col) {
  const g = blank(w, h), cx = (w - 1) / 2, cy = (h - 1) / 2;
  for (let y = 0; y < h; y++) for (let x = 0; x < w; x++) {
    if (((x - cx) / (w / 2)) ** 2 + ((y - cy) / (h / 2)) ** 2 <= 1) g.px[y * w + x] = col;
  }
  return g;
}
const shadowCache = {};
function shadow(w) {
  if (shadowCache[w]) return shadowCache[w];
  const h = Math.max(3, Math.round(w * 0.4));
  const c = canvasOf(ellipseGrid(w, h, '#000000'));
  return (shadowCache[w] = { c, w, h });
}
function portalFrames(active) {
  const frames = [];
  const w = 22, h = 32;
  for (let f = 0; f < 8; f++) {
    const g = blank(w, h), cx = (w - 1) / 2, cy = (h - 1) / 2;
    for (let y = 0; y < h; y++) for (let x = 0; x < w; x++) {
      const nx = (x - cx) / (w / 2), ny = (y - cy) / (h / 2), r = Math.hypot(nx, ny);
      if (r > 1) continue;
      let col;
      if (r > 0.86) col = active ? '#1e7a2a' : '#4a4e5c';
      else if (!active) col = r < 0.8 && (x + y) % 2 ? '#2a2e38' : '#343846';
      else {
        const v = (((Math.atan2(ny, nx) / (Math.PI * 2) + r * 1.4 - f / 8) % 1) + 1) % 1;
        col = r < 0.16 ? '#f4fff0' : v < 0.33 ? '#d8ffb0' : v < 0.66 ? '#6ae848' : '#2fae3c';
      }
      g.px[y * w + x] = col;
    }
    frames.push(sprite(outline(g)));
  }
  return frames;
}
function hotTub() {
  const w = 40, h = 18, g = blank(w, h + 4);
  const outer = ellipseGrid(w, h, '#a06a38'), inner = ellipseGrid(w - 8, h - 6, '#58c8f0');
  blit(g, outer, 0, 0);
  for (let y = h - 6; y < h + 3; y++) for (let x = 3; x < w - 3; x++) if (y > h / 2) put(g, x, y, y > h ? '#6a4020' : '#8a5a2c');
  blit(g, outer, 0, 0);
  blit(g, inner, 4, 2);
  for (let x = 2; x < w - 2; x += 5) put(g, x, h / 2, '#6a4020');
  return sprite(outline(g));
}

// ---------------------------------------------------------------- font helpers
const FONT = '"Press Start 2P", monospace';
function text(ctx, str, x, y, col = '#fff', o = {}) {
  const size = o.size || 8;
  ctx.font = `${size}px ${FONT}`;
  ctx.textBaseline = 'top';
  ctx.textAlign = o.align || 'left';
  x = Math.round(x); y = Math.round(y);
  if (o.outline !== false) {
    ctx.fillStyle = o.oc || OUT;
    const d = o.thick || 1;
    for (let dy = -d; dy <= d; dy++) for (let dx = -d; dx <= d; dx++) if (dx || dy) ctx.fillText(str, x + dx, y + dy);
  }
  if (o.shadow) { ctx.fillStyle = o.shadow; ctx.fillText(str, x + 1, y + 1 + (o.thick || 1)); }
  ctx.fillStyle = col; ctx.fillText(str, x, y);
}
function wrap(ctx, str, maxW, size = 8) {
  ctx.font = `${size}px ${FONT}`;
  const words = str.split(' '), lines = [];
  let line = '';
  for (const w of words) {
    const t = line ? line + ' ' + w : w;
    if (ctx.measureText(t).width > maxW && line) { lines.push(line); line = w; } else line = t;
  }
  if (line) lines.push(line);
  return lines;
}
function box(ctx, x, y, w, h, fill = '#1c1440', border = '#f8f8f8') {
  x = Math.round(x); y = Math.round(y); w = Math.round(w); h = Math.round(h);
  ctx.fillStyle = OUT; ctx.fillRect(x - 1, y - 1, w + 2, h + 2);
  ctx.fillStyle = border; ctx.fillRect(x, y, w, h);
  ctx.fillStyle = fill; ctx.fillRect(x + 1, y + 1, w - 2, h - 2);
}

// ---------------------------------------------------------------- build library
let LIB = null;
function build() {
  if (LIB) return LIB;
  LIB = {
    rick: charFrames(RICK), morty: charFrames(MORTY),
    pickle: S(PICKLE, PICKLE_PAL),
    cronen: creature(CRONEN, {}, { xs: [2, 6, 10, 14], w: 2, len: 3, col: PAL.F }),
    grom: creature(GROM, {}, { xs: [4, 8], w: 2, len: 5, col: '#243458', foot: '#101018' }),
    dog: creature(DOG, {}, { xs: [2, 5, 10, 13], w: 2, len: 4, col: '#e8ecf0', overlap: 1 }),
    terry: creature(TERRY, {}, { xs: [3, 8], w: 3, len: 4, col: '#3a2a20', foot: '#140c1c' }),
    poopy: creature(POOPY, { a: '#fff29a' }, { xs: [3, 7], w: 1, len: 4, col: '#c8a818' }),
    meeseeks: creature(MEESEEKS, MEE_PAL, { xs: [4, 7], w: 1, len: 5, col: '#58a8d8' }),
    trees: TREE_PALS.map(p => S(TREE, p)),
    shrooms: SHROOM_PALS.map(p => S(SHROOM, p)),
    eyeplant: S(EYEPLANT),
    rock: S(ROCK, ROCK_PAL),
    presents: WRAPS.map((wr, i) => S(PRESENT, { B: wr[0], b: wr[1], r: RIBBONS[i % RIBBONS.length] })),
    coin: [1, 0.72, 0.4, 0.15].map(k => {
      const g = grid(COIN, COIN_PAL), w = Math.max(1, Math.round(g.w * k)), o = blank(w, g.h);
      for (let y = 0; y < g.h; y++) for (let x = 0; x < w; x++) o.px[y * w + x] = g.px[y * g.w + Math.min(g.w - 1, Math.floor(((x + 0.5) / w) * g.w))];
      return sprite(outline(o));
    }),
    parts: PARTS.map(r => S(r, PART_PAL)),
    food: Object.fromEntries(Object.entries(FOOD).map(([k, [r, p]]) => [k, S(r, p)])),
    vending: S(VENDING),
    elevator: S(ELEVATOR),
    cruiser: S(CRUISER, CRUISER_PAL),
    portalOn: portalFrames(true), portalOff: portalFrames(false),
    hottub: hotTub(),
    seed: S(['.g.', 'ggg', '.g.'], { g: '#9cff5a' }),
    bolt: S(['.M.', 'MwM', '.M.']),
    puff: S(['.ww.', 'wwww', 'wwww', '.ww.'], {}, false),
  };
  return LIB;
}
function draw(ctx, spr, x, y, flip = false) {
  ctx.drawImage(spr.c, Math.round(x - spr.ax), Math.round(y - spr.ay));
}
function drawShadow(ctx, x, y, w, alpha = 0.3) {
  const s = shadow(w);
  ctx.globalAlpha = alpha;
  ctx.drawImage(s.c, Math.round(x - s.w / 2), Math.round(y - s.h / 2));
  ctx.globalAlpha = 1;
}

SJ.pix = { PAL, OUT, build, draw, drawShadow, text, wrap, box, WRAPS, RIBBONS, rgb, FONT };
})();
