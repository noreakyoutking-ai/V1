/* ============================================================
   Shared behaviors across all Uchiro Store pages
   ============================================================ */

function initNav(){
  const toggle = document.querySelector('.menu-toggle');
  const links = document.querySelector('.nav-links');
  if(toggle && links){
    toggle.addEventListener('click', ()=>{
      const open = links.style.display === 'flex';
      links.style.display = open ? 'none' : 'flex';
      links.style.cssText += open ? '' : 'display:flex; position:absolute; top:100%; left:0; right:0; flex-direction:column; background:#14161d; padding:20px 28px; border-bottom:1px solid #2a2e3a; gap:18px;';
    });
  }
}

function renderFooter(mount){
  if(!mount) return;
  mount.innerHTML = `
    <div class="wrap">
      <div class="footer-grid">
        <div>
          <div class="brand" style="margin-bottom:14px;">
            <span class="mark">U</span> ${STORE_INFO.name}
          </div>
          <p class="muted" style="font-size:13px; max-width:280px;">${STORE_INFO.storefrontNote}</p>
          <div class="social-row mt-16">
            <a href="${STORE_INFO.telegramChannel}" target="_blank" title="Telegram Channel">TG</a>
            <a href="${STORE_INFO.telegramAccount}" target="_blank" title="Contact Admin">@</a>
          </div>
        </div>
        <div>
          <h4>Shop</h4>
          <a href="products.html">All products</a>
          <a href="products.html#account">Accounts</a>
          <a href="products.html#trade">Trade items</a>
          <a href="checkout.html">Checkout</a>
        </div>
        <div>
          <h4>Account</h4>
          <a href="orders.html">Order history</a>
          <a href="login.html">Login / Register</a>
          <a href="help.html#warranty">Warranty policy</a>
        </div>
        <div>
          <h4>Support</h4>
          <a href="help.html">Help center</a>
          <a href="${STORE_INFO.telegramAccount}" target="_blank">Contact admin</a>
          <a href="${STORE_INFO.telegramChannel}" target="_blank">Telegram channel</a>
          <a href="help.html#relax">Relax radio</a>
        </div>
      </div>
      <div class="footer-bottom">
        <span>&copy; 2026 ${STORE_INFO.name}. Not affiliated with Roblox Corporation.</span>
        <span class="mono">t.me/${STORE_INFO.storeBotUsername}</span>
      </div>
    </div>
  `;
}

/* ---------- warranty countdown ---------- */
function warrantyCountdown(purchasedAtISO, warrantyDays){
  const start = new Date(purchasedAtISO).getTime();
  const end = start + warrantyDays*24*60*60*1000;
  const now = Date.now();
  const remaining = end - now;
  if(remaining <= 0) return {expired:true, text:"Expired"};
  const days = Math.floor(remaining/(24*3600*1000));
  const hours = Math.floor((remaining%(24*3600*1000))/(3600*1000));
  return {expired:false, text:`${days}d ${hours}h remaining`, days, hours};
}

/* ============================================================
   DEMO live authenticator code.
   NOTE: This is a lightweight illustrative ticker, not a real
   TOTP/HMAC implementation. In production, generate the 6-digit
   code server-side (e.g. Python `pyotp.TOTP(secret).now()`) from
   the encrypted secret in your database, and only ever send the
   current code to the authenticated owner of that order.
   ============================================================ */
function startDemoAuthCode(el, secretSeed){
  function tick(){
    const period = 30;
    const epoch = Math.floor(Date.now()/1000);
    const step = Math.floor(epoch/period);
    const secondsLeft = period - (epoch % period);
    let hash = 0;
    const str = secretSeed + step;
    for(let i=0;i<str.length;i++){ hash = (hash*31 + str.charCodeAt(i)) >>> 0; }
    const code = String(hash % 1000000).padStart(6,'0');
    if(el.querySelector('.code')) el.querySelector('.code').textContent = code.slice(0,3)+' '+code.slice(3);
    if(el.querySelector('.bar-fill')) el.querySelector('.bar-fill').style.width = (secondsLeft/period*100)+'%';
  }
  tick();
  return setInterval(tick, 1000);
}

document.addEventListener('DOMContentLoaded', ()=>{
  initNav();
  const footerMount = document.querySelector('[data-footer]');
  if(footerMount) renderFooter(footerMount);
});
