/**
 * background.js — Service Worker (MV3)
 *
 * Обрабатывает:
 *   - startTryon: вызов POST /tryon, сохранение job_id
 *   - getState:   отдаёт текущее состояние из chrome.storage
 *
 * Polling делается в popup.js пока попап открыт.
 * Для production можно добавить chrome.alarms.
 */

const API_BASE = 'http://116.203.138.149';

// ── Helpers ────────────────────────────────────────────────────────────────

async function getStorage(keys) {
  return new Promise(resolve =>
    chrome.storage.local.get(keys, resolve)
  );
}

async function setStorage(data) {
  return new Promise(resolve =>
    chrome.storage.local.set(data, resolve)
  );
}

async function apiPost(path, body) {
  const res = await fetch(`${API_BASE}${path}`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  });
  if (!res.ok) {
    const text = await res.text();
    throw new Error(`HTTP ${res.status}: ${text.slice(0, 200)}`);
  }
  return res.json();
}

// ── Message handler ────────────────────────────────────────────────────────

chrome.runtime.onMessage.addListener((msg, _sender, sendResponse) => {
  if (msg.action === 'startTryon') {
    handleStartTryon(msg.imageUrl)
      .then(result => sendResponse(result))
      .catch(err => sendResponse({ ok: false, error: err.message }));
    return true; // async response
  }

  if (msg.action === 'getState') {
    getStorage(['session_id', 'job_id', 'job_status', 'video_url', 'has_photo'])
      .then(data => sendResponse({ ok: true, ...data }))
      .catch(err => sendResponse({ ok: false, error: err.message }));
    return true;
  }

  if (msg.action === 'clearJob') {
    chrome.storage.local.remove(['job_id', 'job_status', 'video_url'], () =>
      sendResponse({ ok: true })
    );
    return true;
  }
});

// ── Start Try-on ───────────────────────────────────────────────────────────

async function handleStartTryon(imageUrl) {
  const { session_id } = await getStorage(['session_id']);

  if (!session_id) {
    return { ok: false, error: 'No photo uploaded yet. Open the extension popup to upload your photo.' };
  }

  // Запустить примерку
  const data = await apiPost('/tryon', {
    session_id,
    clothing_image_url: imageUrl,
  });

  // Сохранить job
  await setStorage({
    job_id:     data.job_id,
    job_status: 'pending',
    video_url:  null,
  });

  return { ok: true, job_id: data.job_id };
}
