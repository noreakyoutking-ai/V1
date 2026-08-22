/* ============================================================
   UCHIRO STORE — Telegram Mini App logic
   ============================================================ */

const tg = window.Telegram ? window.Telegram.WebApp : null;

/* ---------- 1. Telegram WebApp bootstrap ---------- */
function initTelegram(){
  if(!tg){
    // Running outside Telegram (plain browser preview) — no-op fallback.
    document.getElementById('tg-user').textContent = 'preview mode';
    return;
  }
  tg.ready();
  tg.expand();
  applyTelegramTheme();
  tg.onEvent('themeChanged', applyTelegramTheme);

  const user = tg.initDataUnsafe && tg.initDataUnsafe.user;
  document.getElementById('tg-user').textContent = user ? ('@' + (user.username || user.first_name)) : 'guest';

  tg.BackButton.onClick(closeSheet);
}

function applyTelegramTheme(){
  if(!tg || !tg.themeParams) return;
  const p = tg.themeParams;
  const root = document.documentElement.style;
  // Only override if Telegram actually supplied values — keeps our brand
  // look intact when it doesn't (e.g. desktop preview).
  if(p.bg_color) root.setProperty('--void', p.bg_color);
  if(p.secondary_bg_color) root.setProperty('--surface', p.secondary_bg_color);
  if(p.text_color) root.setProperty('--ivory', p.text_color);
  if(p.hint_color) root.setProperty('--slate', p.hint_color);
  if(tg.setHeaderColor) tg.setHeaderColor('secondary_bg_color');
  if(tg.setBackgroundColor) tg.setBackgroundColor(p.bg_color || '#0a0b0e');
}

function haptic(type){
  if(tg && tg.HapticFeedback) tg.HapticFeedback.impactOccurred(type || 'light');
}
function notify(type){
  if(tg && tg.HapticFeedback) tg.HapticFeedback.notificationOccurred(type);
}

/* ---------- 2. Tab navigation ---------- */
function switchTab(tab){
  document.querySelectorAll('.screen').forEach(s => s.classList.add('hidden'));
  document.getElementById('screen-' + tab).classList.remove('hidden');
  document.querySelectorAll('.tab-btn').forEach(b => b.classList.toggle('active', b.dataset.tab === tab));
  haptic('light');
  window.scrollTo(0,0);
}

/* ---------- 3. Catalog rendering ---------- */
let activeCategory = 'all';

function pcardHTML(item){
  const isAccount = item.category === 'Account';
  const badge = isAccount
    ? `<span class="badge badge-account">🛡️ ${item.warranty_days}d</span>`
    : `<span class="badge badge-trade">🔄 ${item.quantity} left</span>`;
  return `
    <div class="pcard" onclick="openProduct(${item.id})">
      <div class="pcard-media">${badge}${item.category}</div>
      <div class="pcard-body">
        <h3>${item.name}</h3>
        <div class="pcard-foot">
          <span class="price">$${item.price}</span>
          <span class="stock">${isAccount ? 'x1' : 'x'+item.quantity}</span>
        </div>
      </div>
    </div>`;
}

function renderCatalog(){
  const grid = document.getElementById('product-grid');
  const items = CATALOG.filter(i => i.published && (activeCategory === 'all' || i.category === activeCategory));
  grid.innerHTML = items.length ? items.map(pcardHTML).join('') :
    `<div class="empty-state" style="grid-column:1/-1;">Nothing here yet — check back soon.</div>`;
}

function renderChips(){
  const row = document.getElementById('chip-row');
  const cats = ['all', ...CATEGORIES];
  row.innerHTML = cats.map(c => `<button class="chip ${c===activeCategory?'active':''}" onclick="setCategory('${c}')">${c==='all'?'All':c}</button>`).join('');
}
function setCategory(c){
  activeCategory = c;
  renderChips();
  renderCatalog();
  haptic('light');
}

/* ---------- 4. Product detail sheet ---------- */
let currentItem = null;
let appliedCoupon = null;

function openSheet(id){
  document.getElementById(id).classList.add('open');
  document.getElementById('backdrop').classList.add('open');
  if(tg) tg.BackButton.show();
}
function closeSheet(){
  document.querySelectorAll('.sheet.open').forEach(s => s.classList.remove('open'));
  document.getElementById('backdrop').classList.remove('open');
  if(tg){ tg.BackButton.hide(); tg.MainButton.hide(); }
}

function openProduct(id){
  currentItem = CATALOG.find(i => i.id === id);
  if(!currentItem) return;
  const isAccount = currentItem.category === 'Account';
  document.getElementById('product-sheet-body').innerHTML = `
    <div class="sheet-media">${currentItem.category}</div>
    <h2>${currentItem.name}</h2>
    <div class="desc">${currentItem.description}</div>
    <div class="tag-row">
      <span class="tag">${currentItem.category}</span>
      ${isAccount ? `<span class="tag">🛡️ ${currentItem.warranty_days}-day warranty</span>` : `<span class="tag">${currentItem.quantity} in stock</span>`}
    </div>
    <div class="row-between">
      <span class="mono" style="font-size:22px; font-weight:700;">$${currentItem.price}</span>
      <span class="muted" style="font-size:12px;">Delivered ${isAccount ? 'to your order history' : 'in-game, ~10 min'}</span>
    </div>
  `;
  openSheet('product-sheet');
  if(tg){
    tg.MainButton.setText('Buy now — $' + currentItem.price);
    tg.MainButton.show();
    tg.MainButton.offClick(goToCheckout);
    tg.MainButton.onClick(goToCheckout);
  }
  haptic('medium');
}

/* ---------- 5. Checkout (KHQR) ---------- */
function goToCheckout(){
  closeSheet();
  appliedCoupon = null;
  document.getElementById('coupon-input').value = '';
  document.getElementById('coupon-msg').textContent = '';
  renderCheckout();
  openSheet('checkout-sheet');
  if(tg){
    tg.MainButton.setText('I\'ve paid — confirm');
    tg.MainButton.show();
    tg.MainButton.offClick(goToCheckout);
    tg.MainButton.onClick(confirmPayment);
  }
  startCheckoutTimer();
}

function renderCheckout(){
  const total = appliedCoupon
    ? (appliedCoupon.discount_type === 'percent' ? currentItem.price * (1 - appliedCoupon.amount/100) : Math.max(currentItem.price - appliedCoupon.amount, 0))
    : currentItem.price;
  document.getElementById('checkout-item-name').textContent = currentItem.name;
  document.getElementById('checkout-total').textContent = '$' + total.toFixed(2);
  document.getElementById('checkout-ref').textContent = 'UCH-' + (10000 + currentItem.id * 137 % 90000);
}

function applyCoupon(){
  const code = document.getElementById('coupon-input').value.trim().toUpperCase();
  const msg = document.getElementById('coupon-msg');
  const coupon = COUPONS.find(c => c.code === code);
  if(!coupon || !coupon.active || coupon.used_count >= coupon.max_uses){
    msg.textContent = 'Invalid or expired code.';
    msg.style.color = 'var(--ember)';
    appliedCoupon = null;
    notify('error');
  } else {
    appliedCoupon = coupon;
    msg.textContent = `Applied — ${coupon.discount_type === 'percent' ? coupon.amount+'% off' : '$'+coupon.amount+' off'}`;
    msg.style.color = 'var(--mint)';
    notify('success');
  }
  renderCheckout();
}

let checkoutInterval;
function startCheckoutTimer(){
  clearInterval(checkoutInterval);
  let seconds = 600;
  const el = document.getElementById('checkout-timer');
  const bar = document.getElementById('checkout-bar');
  checkoutInterval = setInterval(() => {
    seconds--;
    if(seconds <= 0){ clearInterval(checkoutInterval); el.textContent = 'Expired'; return; }
    el.textContent = `${String(Math.floor(seconds/60)).padStart(2,'0')}:${String(seconds%60).padStart(2,'0')}`;
    bar.style.width = (seconds/600*100) + '%';
  }, 1000);
}

function confirmPayment(){
  clearInterval(checkoutInterval);
  document.getElementById('checkout-pending').classList.add('hidden');
  document.getElementById('checkout-success').classList.remove('hidden');
  if(tg) tg.MainButton.hide();
  notify('success');
  haptic('heavy');
  // On the real server this is a webhook from your KHQR provider firing
  // db.set_order_approved(order_id) — here we just simulate the wait.
}

function finishCheckout(){
  closeSheet();
  document.getElementById('checkout-pending').classList.remove('hidden');
  document.getElementById('checkout-success').classList.add('hidden');
  switchTab('orders');
}

/* ---------- 6. Orders tab ---------- */
function warrantyCountdown(purchasedAtISO, warrantyDays){
  const start = new Date(purchasedAtISO).getTime();
  const end = start + warrantyDays*24*60*60*1000;
  const remaining = end - Date.now();
  if(remaining <= 0) return {expired:true, text:'Expired'};
  const days = Math.floor(remaining/(864e5));
  const hours = Math.floor((remaining%(864e5))/(36e5));
  return {expired:false, text:`${days}d ${hours}h left`, days};
}

function startDemoAuthCode(el, seed){
  function tick(){
    const period = 30, epoch = Math.floor(Date.now()/1000), step = Math.floor(epoch/period);
    const secondsLeft = period - (epoch % period);
    let hash = 0; const str = seed + step;
    for(let i=0;i<str.length;i++) hash = (hash*31 + str.charCodeAt(i)) >>> 0;
    const code = String(hash % 1000000).padStart(6,'0');
    el.querySelector('.code').textContent = code.slice(0,3) + ' ' + code.slice(3);
    el.querySelector('.bar-fill').style.width = (secondsLeft/period*100) + '%';
  }
  tick();
  setInterval(tick, 1000);
}

function orderCardHTML(o){
  const isAccount = o.item_category === 'Account';
  const date = new Date(o.created_at).toLocaleDateString(undefined,{month:'short',day:'numeric'});
  let deliveryHTML = '';
  if(o.delivery){
    deliveryHTML = `
      <div class="divider"></div>
      <div class="field" style="margin-bottom:8px;">
        <label>Login</label>
        <div class="code-box"><span class="mono" style="font-size:13px;">${o.delivery.login}</span>
          <button class="copy-btn" onclick="navigator.clipboard.writeText('${o.delivery.login}')">Copy</button></div>
      </div>
      <div class="field" style="margin-bottom:8px;">
        <label>Password</label>
        <div class="code-box"><span class="mono" style="font-size:13px;">${o.delivery.password}</span>
          <button class="copy-btn" onclick="navigator.clipboard.writeText('${o.delivery.password}')">Copy</button></div>
      </div>
      <div class="field" style="margin-bottom:0;">
        <label>Live code · refreshes every 30s</label>
        <div class="code-box" id="auth-${o.id}"><div><span class="code">000 000</span><div class="bar" style="margin-top:6px;"><div class="bar-fill"></div></div></div>
          <button class="copy-btn" onclick="copyOrderCode(${o.id})">Copy</button></div>
      </div>`;
  }
  let warrantyBadge = '<span class="pill">🔄 Trade — no warranty</span>';
  if(isAccount){
    const cd = warrantyCountdown(o.created_at, o.warranty_days);
    const dot = cd.expired ? 'status-expired' : (cd.days <= 2 ? 'status-warn' : 'status-live');
    warrantyBadge = `<span class="pill"><span class="status-dot ${dot}"></span>${cd.text}</span>`;
  }
  return `
    <div class="order-card">
      <div class="row-between">
        <div><div class="mono muted" style="font-size:11px;">#${o.id} · ${date}</div>
          <div style="font-weight:600; font-size:13.5px; margin-top:3px;">${o.item_name}</div></div>
        <div style="text-align:right;"><div class="mono" style="font-weight:700;">$${o.final_price}</div>${warrantyBadge}</div>
      </div>
      ${deliveryHTML}
    </div>`;
}
function copyOrderCode(id){
  const el = document.querySelector(`#auth-${id} .code`);
  if(el) navigator.clipboard.writeText(el.textContent.replace(' ',''));
}

function renderOrders(){
  const mount = document.getElementById('orders-list');
  if(ORDERS.length === 0){
    mount.innerHTML = `<div class="empty-state">No orders yet — head to the Shop tab.</div>`;
    return;
  }
  mount.innerHTML = ORDERS.map(orderCardHTML).join('');
  ORDERS.forEach(o => {
    if(o.delivery) startDemoAuthCode(document.getElementById('auth-' + o.id), o.delivery.totp_secret_demo);
  });
}

/* ---------- 7. init ---------- */
document.addEventListener('DOMContentLoaded', () => {
  initTelegram();
  renderChips();
  renderCatalog();
  renderOrders();
  switchTab('shop');
});
