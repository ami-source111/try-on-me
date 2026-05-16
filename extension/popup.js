/**
 * popup.js — управляет UI попапа расширения.
 *
 * Состояния:
 *   no-photo   → загрузить фото
 *   uploading  → идёт upload
 *   idle       → фото есть, ждём нажатия на кнопку
 *   processing → идёт генерация (polling)
 *   done       → видео готово
 *   error      → что-то пошло не так
 */

const API_BASE = 'http://116.203.138.149';
const POLL_INTERVAL_MS = 5000;

// ── DOM refs ───────────────────────────────────────────────────────────────
const states = {
  noPhoto:    document.getElementById('state-no-photo'),
  uploading:  document.getElementById('state-uploading'),
  idle:       document.getElementById('state-idle'),
  processing: document.getElementById('state-processing'),
  done:       document.getElementById('state-done'),
  error:      document.getElementById('state-error'),
};

const fileInput       = document.getElementById('file-input');
const uploadTrigger   = document.getElementById('upload-trigger');
const uploadBtn       = document.getElementById('upload-btn');
const changePhotoBtn  = document.getElementById('change-photo-btn');
const statusLabel     = document.getElementById('status-label');
const resultVideo     = document.getElementById('result-video');
const tryAgainBtn     = document.getElementById('try-again-btn');
const downloadBtn     = document.getElementById('download-btn');

let pollTimer = null;

// ── State display ──────────────────────────────────────────────────────────

function showState(name, errorMsg = '') {
  Object.values(states).forEach(el => el.classList.add('hidden'));
  if (states[name]) states[name].classList.remove('hidden');
  if (name === 'error') states.error.textContent = errorMsg;
}

function setStatusLabel(status) {
  const labels = {
    pending:           'In queue…',
    processing_tryon:  '👗 Generating try-on photo…',
    processing_video:  '🎬 Generating video…',
    done:              '✅ Done!',
    failed:            '❌ Failed',
  };
  statusLabel.textContent = labels[status] || status;
}

// ── Storage helpers ────────────────────────────────────────────────────────

function getStorage(keys) {
  return new Promise(resolve => chrome.storage.local.get(keys, resolve));
}
function setStorage(data) {
  return new Promise(resolve => chrome.storage.local.set(data, resolve));
}
function removeStorage(keys) {
  return new Promise(resolve => chrome.storage.local.remove(keys, resolve));
}

// ── API ────────────────────────────────────────────────────────────────────

async function uploadPhoto(file) {
  const formData = new FormData();
  formData.append('file', file);

  const { session_id } = await getStorage(['session_id']);
  const url = session_id
    ? `${API_BASE}/sessions/photo?session_id=${session_id}`
    : `${API_BASE}/sessions/photo`;

  const res = await fetch(url, { method: 'POST', body: formData });
  if (!res.ok) throw new Error(`Upload failed: ${res.status}`);
  return res.json();
}

async function pollJob(jobId) {
  const res = await fetch(`${API_BASE}/tryon/${jobId}`);
  if (!res.ok) throw new Error(`Poll failed: ${res.status}`);
  return res.json();
}

// ── Init ───────────────────────────────────────────────────────────────────

async function init() {
  const data = await getStorage(['session_id', 'has_photo', 'job_id', 'job_status', 'video_url']);

  if (data.job_id && data.job_status === 'done' && data.video_url) {
    // Видео готово
    showDone(data.video_url);
  } else if (data.job_id && data.job_status !== 'done' && data.job_status !== 'failed') {
    // Идёт генерация
    showState('processing');
    setStatusLabel(data.job_status || 'pending');
    startPolling(data.job_id);
  } else if (data.session_id && data.has_photo) {
    // Фото загружено, ждём нажатия
    showState('idle');
  } else {
    // Нет фото
    showState('noPhoto');
  }
}

// ── Photo upload ───────────────────────────────────────────────────────────

function triggerFileInput() {
  fileInput.click();
}

async function handleFileSelected(file) {
  if (!file) return;
  showState('uploading');
  try {
    const data = await uploadPhoto(file);
    await setStorage({
      session_id: data.session_id,
      has_photo: true,
    });
    showState('idle');
  } catch (e) {
    showState('error', 'Failed to upload photo. Check your connection and try again.\n' + e.message);
  }
}

uploadTrigger.addEventListener('click', triggerFileInput);
uploadBtn.addEventListener('click', triggerFileInput);
fileInput.addEventListener('change', () => handleFileSelected(fileInput.files[0]));
changePhotoBtn.addEventListener('click', triggerFileInput);

// ── Drag & drop on upload area ─────────────────────────────────────────────

uploadTrigger.addEventListener('dragover', e => {
  e.preventDefault();
  uploadTrigger.style.borderColor = '#6366f1';
});
uploadTrigger.addEventListener('dragleave', () => {
  uploadTrigger.style.borderColor = '';
});
uploadTrigger.addEventListener('drop', e => {
  e.preventDefault();
  uploadTrigger.style.borderColor = '';
  const file = e.dataTransfer.files[0];
  if (file && file.type.startsWith('image/')) handleFileSelected(file);
});

// ── Polling ────────────────────────────────────────────────────────────────

function startPolling(jobId) {
  stopPolling();
  pollTimer = setInterval(() => checkJob(jobId), POLL_INTERVAL_MS);
  // Первая проверка сразу
  checkJob(jobId);
}

function stopPolling() {
  if (pollTimer) {
    clearInterval(pollTimer);
    pollTimer = null;
  }
}

async function checkJob(jobId) {
  try {
    const data = await pollJob(jobId);
    await setStorage({ job_status: data.status, video_url: data.video_url });

    setStatusLabel(data.status);

    if (data.status === 'done' && data.video_url) {
      stopPolling();
      showDone(data.video_url);
    } else if (data.status === 'failed') {
      stopPolling();
      await removeStorage(['job_id', 'job_status', 'video_url']);
      showState('error', 'Generation failed: ' + (data.error_message || 'Unknown error'));
    }
  } catch (e) {
    console.error('Poll error:', e);
  }
}

// ── Done state ─────────────────────────────────────────────────────────────

function showDone(videoUrl) {
  resultVideo.src = videoUrl;
  showState('done');

  downloadBtn.onclick = () => {
    const a = document.createElement('a');
    a.href = videoUrl;
    a.download = 'try-on.mp4';
    a.click();
  };
}

tryAgainBtn.addEventListener('click', async () => {
  await removeStorage(['job_id', 'job_status', 'video_url']);
  showState('idle');
});

// ── Cleanup on close ───────────────────────────────────────────────────────

window.addEventListener('unload', stopPolling);

// ── Start ──────────────────────────────────────────────────────────────────

init();
