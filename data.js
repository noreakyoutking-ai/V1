/* ============================================================
   MOCK CATALOG
   Shape mirrors your V3 database.py rows (id, type, name, price,
   desc, stock, warranty_days, image) so this can be swapped for a
   real fetch('/api/items') call once webapp_server.py is wired up.
   ============================================================ */
const CATALOG = [
  {
    id: "acc-001",
    kind: "account",
    category: "Blox Fruits + Evade + Rival Account",
    name: "Full Bundle Account — Dragon Awakened",
    desc: "Blox Fruits (Awakened Dragon, max stats), Evade & Rival progress included. Fresh email, warranty starts at delivery.",
    price: 42,
    currency: "USD",
    stock: 1,
    warranty_days: 14,
    tags: ["Awakened", "Max Melee", "Rare Fruit"]
  },
  {
    id: "acc-002",
    kind: "account",
    category: "Blox Fruits + Evade + Rival Account",
    name: "Starter Bundle Account — Buddha V2",
    desc: "Blox Fruits Buddha V2, Evade unlocked characters, Rival rank Gold+. Great entry-level account.",
    price: 18,
    currency: "USD",
    stock: 1,
    warranty_days: 14,
    tags: ["Buddha V2", "Gold Rank"]
  },
  {
    id: "trd-101",
    kind: "trade",
    category: "MM2",
    name: "Chroma Seer",
    desc: "Trade-only stock item, instant delivery after payment confirmation.",
    price: 6,
    currency: "USD",
    stock: 14,
    warranty_days: 0,
    tags: ["Chroma", "Godly"]
  },
  {
    id: "trd-102",
    kind: "trade",
    category: "Blade Ball",
    name: "Mythic Skin Bundle",
    desc: "3x mythic skins + 500 tickets, delivered to your account via trade.",
    price: 9,
    currency: "USD",
    stock: 22,
    warranty_days: 0,
    tags: ["Mythic", "Tickets"]
  },
  {
    id: "trd-103",
    kind: "trade",
    category: "Gamepass / Fruit",
    name: "Dragon Fruit (Physical, Blox Fruits)",
    desc: "In-game physical fruit trade, delivered same server within 10 minutes.",
    price: 14,
    currency: "USD",
    stock: 7,
    warranty_days: 0,
    tags: ["Physical", "Fast Delivery"]
  },
  {
    id: "trd-104",
    kind: "trade",
    category: "Gamepass / Fruit",
    name: "2x Fruit Storage Gamepass",
    desc: "Gamepass gifted directly to your Roblox account via group funds / gift flow.",
    price: 5,
    currency: "USD",
    stock: 40,
    warranty_days: 0,
    tags: ["Gamepass", "Gifted"]
  }
];

/* ---------- mock purchased orders (would come from /api/orders) ---------- */
const ORDERS = [
  {
    id: "UCH-88213",
    item_name: "Full Bundle Account — Dragon Awakened",
    kind: "account",
    price: 42,
    purchased_at: "2026-08-14T10:32:00Z",
    warranty_days: 14,
    warranty_status: "active", // active | reduced | void
    delivery: {
      login: "uchiro_dragon882",
      password: "Xk9!vLp22Q",
      auth_secret_demo: "JBSWY3DPEHPK3PXP", // demo secret, base32 — backend should store real one encrypted
      email: "uchiro.dragon882@protonmail.com"
    }
  },
  {
    id: "UCH-88190",
    item_name: "MM2 — Chroma Seer",
    kind: "trade",
    price: 6,
    purchased_at: "2026-08-10T18:05:00Z",
    warranty_days: 0,
    warranty_status: "n/a",
    delivery: null
  }
];

/* ---------- coupon codes (would come from /api/coupons) ---------- */
const COUPONS = [
  { code: "UCHIRO10",  type: "percent", value: 10, active: true,  uses: 34, max_uses: 200, expires: "2026-09-30" },
  { code: "WELCOME5",  type: "fixed",   value: 5,  active: true,  uses: 112, max_uses: null, expires: null },
  { code: "FRUIT20",   type: "percent", value: 20, active: false, uses: 18, max_uses: 50,  expires: "2026-08-01" }
];

/* ---------- mock traffic stats (would come from a real analytics
   table populated by webapp_server.py on each page view) ---------- */
const TRAFFIC = {
  today_visitors: 214,
  today_unique: 168,
  week_visitors: [120, 145, 98, 210, 180, 240, 214],
  week_labels: ["Mon","Tue","Wed","Thu","Fri","Sat","Sun"],
  top_pages: [
    { path: "/products.html", views: 402 },
    { path: "/index.html", views: 388 },
    { path: "/checkout.html", views: 121 },
    { path: "/help.html", views: 76 }
  ],
  sources: [
    { name: "Telegram channel", pct: 54 },
    { name: "Direct", pct: 28 },
    { name: "Google", pct: 12 },
    { name: "Other", pct: 6 }
  ]
};

const STORE_INFO = {
  name: "Uchiro Store",
  telegramChannel: "https://t.me/uchirostore",
  telegramAccount: "https://t.me/noreakyout",
  storeBotUsername: "UchiroStoreBot",
  adminBotUsername: "UchiroAdminBot",
  storefrontNote: "Physical storefront verified — walk-in trades available by appointment via Telegram."
};
