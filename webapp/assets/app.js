/* ============================================================
   Mock data — field names match your real database.py rows
   exactly, so swapping for fetch('/api/items') / fetch('/api/orders')
   later is a drop-in, not a rewrite.
   items: id, category, name, price, description, quantity,
          warranty_days, published, totp_secret (admin-only)
   ============================================================ */
const CATEGORIES = ["Account", "MM2", "Blade Ball", "Gamepass", "Fruit"];

const CATALOG = [
  { id: 1, category: "Account", name: "Full Bundle — Dragon Awakened", description: "Blox Fruits Dragon Awakened + Evade + Rival progress. Fresh email.", price: 42, quantity: 1, warranty_days: 14, published: 1 },
  { id: 2, category: "Account", name: "Starter Bundle — Buddha V2", description: "Blox Fruits Buddha V2, Evade unlocked, Rival Gold+.", price: 18, quantity: 1, warranty_days: 14, published: 1 },
  { id: 3, category: "MM2", name: "Chroma Seer", description: "Instant trade delivery after payment confirms.", price: 6, quantity: 14, warranty_days: 0, published: 1 },
  { id: 4, category: "Blade Ball", name: "Mythic Skin Bundle", description: "3x mythic skins + 500 tickets.", price: 9, quantity: 22, warranty_days: 0, published: 1 },
  { id: 5, category: "Fruit", name: "Dragon Fruit (Physical)", description: "In-game trade, same server, ~10 min delivery.", price: 14, quantity: 7, warranty_days: 0, published: 1 },
  { id: 6, category: "Gamepass", name: "2x Fruit Storage", description: "Gifted directly to your account.", price: 5, quantity: 40, warranty_days: 0, published: 1 }
];

/* mirrors get_orders_by_buyer() join shape */
const ORDERS = [
  {
    id: 88213, item_id: 1, item_name: "Full Bundle — Dragon Awakened", item_category: "Account",
    status: "approved", price: 42, final_price: 42, created_at: "2026-08-14T10:32:00Z",
    warranty_days: 14,
    delivery: { login: "uchiro_dragon882", password: "Xk9!vLp22Q", totp_secret_demo: "JBSWY3DPEHPK3PXP" }
  },
  {
    id: 88190, item_id: 3, item_name: "MM2 — Chroma Seer", item_category: "MM2",
    status: "approved", price: 6, final_price: 6, created_at: "2026-08-10T18:05:00Z",
    warranty_days: 0, delivery: null
  }
];

const COUPONS = [
  { code: "UCHIRO10", discount_type: "percent", amount: 10, active: 1, used_count: 34, max_uses: 200 },
  { code: "WELCOME5", discount_type: "fixed", amount: 5, active: 1, used_count: 112, max_uses: 500 }
];

const STORE_INFO = {
  name: "Uchiro Store",
  telegramChannel: "https://t.me/uchirostore",
  telegramAccount: "https://t.me/noreakyout",
  storeBotUsername: "UchiroStoreBot"
};
