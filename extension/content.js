/**
 * content.js — инжектирует кнопку «Try on me» рядом с крупными
 * изображениями одежды (naturalWidth ≥ 300 и naturalHeight ≥ 300).
 *
 * Работает на любом сайте, поддерживает SPA через MutationObserver.
 */

const MIN_SIZE = 300;
const MARKER   = 'data-tryon-injected';

// ── Inject button ──────────────────────────────────────────────────────────

function injectButton(img) {
  if (img.hasAttribute(MARKER)) return;
  if (img.naturalWidth < MIN_SIZE || img.naturalHeight < MIN_SIZE) return;

  // Не добавлять на svg, data:, blob: или уже помеченные
  const src = img.src || '';
  if (!src || src.startsWith('data:') || src.startsWith('blob:')) return;

  img.setAttribute(MARKER, '1');

  // Делаем родителя relative чтобы позиционировать кнопку
  const parent = img.parentElement;
  if (!parent) return;
  parent.classList.add('tryon-img-parent');

  const wrapper = document.createElement('div');
  wrapper.className = 'tryon-btn-wrapper';

  const btn = document.createElement('button');
  btn.className = 'tryon-btn';
  btn.innerHTML = '<span class="tryon-btn-icon">👗</span> Try on me';

  btn.addEventListener('click', (e) => {
    e.preventDefault();
    e.stopPropagation();
    onTryOnClick(img, btn);
  });

  wrapper.appendChild(btn);
  parent.appendChild(wrapper);
}

function onTryOnClick(img, btn) {
  btn.classList.add('loading');
  btn.innerHTML = '<span class="tryon-btn-icon">⏳</span> Preparing…';

  chrome.runtime.sendMessage(
    { action: 'startTryon', imageUrl: img.src },
    (response) => {
      if (response && response.ok) {
        btn.innerHTML = '<span class="tryon-btn-icon">✨</span> Processing…';
        // Открыть попап чтобы пользователь видел прогресс
        chrome.runtime.sendMessage({ action: 'openPopup' });
      } else {
        btn.classList.remove('loading');
        btn.innerHTML = '<span class="tryon-btn-icon">👗</span> Try on me';
        const msg = response && response.error ? response.error : 'Error — open extension popup';
        alert('Try on Me: ' + msg);
      }
    }
  );
}

// ── Scan page ──────────────────────────────────────────────────────────────

function scanImages() {
  document.querySelectorAll('img:not([data-tryon-injected])').forEach((img) => {
    if (img.complete && img.naturalWidth > 0) {
      injectButton(img);
    } else {
      img.addEventListener('load', () => injectButton(img), { once: true });
    }
  });
}

// ── MutationObserver — следим за динамически добавляемым контентом ─────────

const observer = new MutationObserver((mutations) => {
  let hasNew = false;
  for (const m of mutations) {
    for (const node of m.addedNodes) {
      if (node.nodeType === 1) {
        hasNew = true;
        break;
      }
    }
    if (hasNew) break;
  }
  if (hasNew) scanImages();
});

observer.observe(document.body, { childList: true, subtree: true });

// ── Init ───────────────────────────────────────────────────────────────────

// Первичный скан при загрузке страницы
scanImages();

// Повторный скан через 1.5 сек для lazy-load изображений
setTimeout(scanImages, 1500);

// Сброс кнопок при SPA-навигации
let lastUrl = location.href;
setInterval(() => {
  if (location.href !== lastUrl) {
    lastUrl = location.href;
    // Убрать все маркеры и обёртки с предыдущей страницы
    document.querySelectorAll('[data-tryon-injected]').forEach(el => {
      el.removeAttribute(MARKER);
    });
    document.querySelectorAll('.tryon-btn-wrapper').forEach(el => el.remove());
    setTimeout(scanImages, 800);
  }
}, 1000);
