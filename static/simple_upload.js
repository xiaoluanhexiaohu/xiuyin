const token = localStorage.getItem('xiuyin_token');
if (!token) {
  window.location.href = '/login';
}
const form = document.getElementById('uploadForm');
const statusText = document.getElementById('statusText');
const progress = document.getElementById('progress');
const warningText = document.getElementById('warningText');
const links = document.getElementById('downloadLinks');
const startButton = document.getElementById('startButton');

const referenceAudioInput = document.getElementById('referenceAudioInput');
const userAudioInput = document.getElementById('userAudioInput');
const referenceSearchQuery = document.getElementById('referenceSearchQuery');
const referenceSearchSource = document.getElementById('referenceSearchSource');
const referenceSearchButton = document.getElementById('referenceSearchButton');
const referenceSearchStatus = document.getElementById('referenceSearchStatus');
const referenceSearchResults = document.getElementById('referenceSearchResults');
const selectedReferenceAudioBox = document.getElementById('selectedReferenceAudio');
let selectedReferenceAudio = null;

const recordStart = document.getElementById('recordStart');
const recordStop = document.getElementById('recordStop');
const recordReset = document.getElementById('recordReset');
const recordPreview = document.getElementById('recordPreview');
const recordStatus = document.getElementById('recordStatus');
let mediaRecorder = null;
let recordedChunks = [];
let recordStartedAt = 0;
let recordTimer = null;
const maxRecordingMs = 10 * 60 * 1000;
const maxRecordingBytes = 20 * 1024 * 1024;

if (referenceSearchButton) {
  referenceSearchButton.addEventListener('click', searchReferenceMusic);
  referenceSearchQuery.addEventListener('keydown', (event) => {
    if (event.key === 'Enter') {
      event.preventDefault();
      searchReferenceMusic();
    }
  });
}

if (referenceAudioInput) {
  referenceAudioInput.addEventListener('change', () => {
    if (referenceAudioInput.files.length > 0) {
      clearImportedReference('已切换为本地上传原唱音频。');
    }
  });
}

if (recordStart) {
  recordStart.addEventListener('click', startRecording);
  recordStop.addEventListener('click', stopRecording);
  recordReset.addEventListener('click', resetRecording);
}

async function searchReferenceMusic() {
  const query = referenceSearchQuery.value.trim();
  const source = referenceSearchSource.value;
  referenceSearchResults.replaceChildren();
  if (!query) {
    referenceSearchStatus.textContent = '请输入歌曲名或歌手名。';
    return;
  }
  referenceSearchButton.disabled = true;
  referenceSearchStatus.textContent = '正在搜索…';
  try {
    const response = await fetch('/api/v1/reference/search', {
      method: 'POST',
      headers: { Authorization: `Bearer ${token}`, 'Content-Type': 'application/json' },
      body: JSON.stringify({ source, query, page: 1, page_size: 10 })
    });
    const data = await response.json().catch(() => ({}));
    if (!response.ok) {
      throw new Error(readApiError(data, '搜索失败'));
    }
    const items = data.items || data.results || [];
    renderReferenceResults(items);
    referenceSearchStatus.textContent = items.length ? `找到 ${items.length} 条结果。` : '没有找到结果，请更换关键词或来源。';
  } catch (err) {
    referenceSearchStatus.textContent = `搜索失败：${err.message}`;
  } finally {
    referenceSearchButton.disabled = false;
  }
}

function renderReferenceResults(items) {
  referenceSearchResults.replaceChildren();
  items.forEach((item) => {
    const row = document.createElement('li');
    row.className = 'reference-result-card';

    const title = document.createElement('h3');
    title.textContent = item.title || '未命名歌曲';
    row.appendChild(title);

    const meta = document.createElement('dl');
    meta.className = 'reference-meta';
    addMeta(meta, '歌手', item.artist || '未知');
    addMeta(meta, '时长', formatDuration(item.duration_sec));
    addMeta(meta, '授权', item.license || '未提供');
    addMeta(meta, '来源', item.source || '未知');
    addMeta(meta, '可导入', item.can_download ? '是' : '否');
    row.appendChild(meta);

    if (item.authorization_notes) {
      const note = document.createElement('p');
      note.className = item.can_download ? 'hint' : 'warning';
      note.textContent = item.authorization_notes;
      row.appendChild(note);
    }
    if (['spotify', 'youtube'].includes(item.source)) {
      const compliance = document.createElement('p');
      compliance.className = 'warning';
      compliance.textContent = '该平台仅支持搜索展示，不支持后台导入音频。请使用本地上传作为原唱音频。';
      row.appendChild(compliance);
    }

    const actions = document.createElement('div');
    actions.className = 'reference-result-actions';
    if (item.preview_url) {
      const preview = document.createElement('a');
      preview.href = item.preview_url;
      preview.target = '_blank';
      preview.rel = 'noopener noreferrer';
      preview.className = 'button-link secondary';
      preview.textContent = '试听';
      actions.appendChild(preview);
    }
    if (item.external_url) {
      const external = document.createElement('a');
      external.href = item.external_url;
      external.target = '_blank';
      external.rel = 'noopener noreferrer';
      external.className = 'external-link';
      external.textContent = '外部链接';
      actions.appendChild(external);
    }
    if (item.can_download && !['spotify', 'youtube'].includes(item.source)) {
      const importButton = document.createElement('button');
      importButton.type = 'button';
      importButton.textContent = '导入作为原唱';
      importButton.addEventListener('click', () => importReferenceMusic(item, importButton));
      actions.appendChild(importButton);
    }
    row.appendChild(actions);
    referenceSearchResults.appendChild(row);
  });
}

function addMeta(container, label, value) {
  const term = document.createElement('dt');
  term.textContent = label;
  const description = document.createElement('dd');
  description.textContent = value;
  container.appendChild(term);
  container.appendChild(description);
}

function formatDuration(duration) {
  if (duration === null || duration === undefined || Number.isNaN(Number(duration))) {
    return '未知';
  }
  const total = Math.round(Number(duration));
  const minutes = Math.floor(total / 60);
  const seconds = String(total % 60).padStart(2, '0');
  return `${minutes}:${seconds}`;
}

async function importReferenceMusic(item, button) {
  button.disabled = true;
  const originalText = button.textContent;
  button.textContent = '正在导入…';
  referenceSearchStatus.textContent = '正在导入并转换原唱音频…';
  try {
    const response = await fetch('/api/v1/reference/import', {
      method: 'POST',
      headers: { Authorization: `Bearer ${token}`, 'Content-Type': 'application/json' },
      body: JSON.stringify({ source: item.source, track_id: item.track_id })
    });
    const data = await response.json().catch(() => ({}));
    if (!response.ok) {
      throw new Error(readApiError(data, '导入失败'));
    }
    selectedReferenceAudio = {
      audio_id: data.audio_id,
      normalized_path: data.normalized_path,
      title: data.title || item.title || '已导入原唱',
      artist: data.artist || item.artist || '',
      source: data.source || item.source
    };
    referenceAudioInput.required = false;
    referenceAudioInput.value = '';
    renderSelectedReferenceAudio();
    referenceSearchStatus.textContent = '导入成功，已作为当前原唱音频。';
  } catch (err) {
    referenceSearchStatus.textContent = `导入失败：${err.message}`;
  } finally {
    button.disabled = false;
    button.textContent = originalText;
  }
}

function renderSelectedReferenceAudio() {
  selectedReferenceAudioBox.replaceChildren();
  if (!selectedReferenceAudio) {
    selectedReferenceAudioBox.hidden = true;
    return;
  }
  const text = document.createElement('p');
  text.textContent = `当前原唱：${selectedReferenceAudio.title}${selectedReferenceAudio.artist ? ` - ${selectedReferenceAudio.artist}` : ''}（${selectedReferenceAudio.source}，audio_id=${selectedReferenceAudio.audio_id}）`;
  const path = document.createElement('p');
  path.className = 'hint';
  path.textContent = `normalized_path: ${selectedReferenceAudio.normalized_path}`;
  const clear = document.createElement('button');
  clear.type = 'button';
  clear.className = 'secondary-button';
  clear.textContent = '改用本地上传';
  clear.addEventListener('click', () => clearImportedReference('已取消导入原唱，请使用本地上传。'));
  selectedReferenceAudioBox.append(text, path, clear);
  selectedReferenceAudioBox.hidden = false;
}

function clearImportedReference(message = '') {
  selectedReferenceAudio = null;
  referenceAudioInput.required = true;
  selectedReferenceAudioBox.hidden = true;
  selectedReferenceAudioBox.replaceChildren();
  if (message) {
    referenceSearchStatus.textContent = message;
  }
}

async function startRecording() {
  if (!navigator.mediaDevices || !window.MediaRecorder) {
    recordStatus.textContent = '当前浏览器不支持直接录音，请上传音频文件。';
    return;
  }
  try {
    const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
    const mimeType = pickRecordingMimeType();
    mediaRecorder = new MediaRecorder(stream, mimeType ? { mimeType } : undefined);
    recordedChunks = [];
    recordStartedAt = Date.now();
    mediaRecorder.addEventListener('dataavailable', (event) => {
      if (event.data && event.data.size > 0) {
        recordedChunks.push(event.data);
      }
    });
    mediaRecorder.addEventListener('stop', () => finalizeRecording(stream, mimeType || 'audio/webm'));
    mediaRecorder.start(1000);
    recordStart.disabled = true;
    recordStop.disabled = false;
    recordReset.disabled = true;
    recordStatus.textContent = '正在录音…';
    recordTimer = setTimeout(() => {
      if (mediaRecorder && mediaRecorder.state === 'recording') {
        stopRecording();
      }
    }, maxRecordingMs);
  } catch (err) {
    const messages = {
      NotAllowedError: '麦克风权限被拒绝，请允许浏览器使用麦克风。',
      NotFoundError: '未找到可用麦克风，请连接输入设备。',
      OverconstrainedError: '当前麦克风不满足录音约束，请更换输入设备。'
    };
    recordStatus.textContent = messages[err.name] || `录音启动失败：${err.message}`;
  }
}

function stopRecording() {
  if (mediaRecorder && mediaRecorder.state === 'recording') {
    mediaRecorder.stop();
  }
}

function resetRecording() {
  recordedChunks = [];
  if (recordPreview.src) {
    URL.revokeObjectURL(recordPreview.src);
  }
  recordPreview.hidden = true;
  recordPreview.removeAttribute('src');
  userAudioInput.value = '';
  recordStart.disabled = false;
  recordStop.disabled = true;
  recordReset.disabled = true;
  recordStatus.textContent = '已重置，可重新录音。';
}

function finalizeRecording(stream, mimeType) {
  clearTimeout(recordTimer);
  stream.getTracks().forEach((track) => track.stop());
  const blob = new Blob(recordedChunks, { type: mimeType });
  if (blob.size > maxRecordingBytes) {
    recordStatus.textContent = '录音超过 20MB，请缩短时长后重录。';
    resetRecording();
    return;
  }
  const extension = mimeType.includes('mp4') ? 'mp4' : 'webm';
  const file = new File([blob], `recording.${extension}`, { type: mimeType });
  const transfer = new DataTransfer();
  transfer.items.add(file);
  userAudioInput.files = transfer.files;
  recordPreview.src = URL.createObjectURL(blob);
  recordPreview.hidden = false;
  recordStart.disabled = false;
  recordStop.disabled = true;
  recordReset.disabled = false;
  const seconds = Math.round((Date.now() - recordStartedAt) / 1000);
  recordStatus.textContent = `录音完成（约 ${seconds} 秒），已填入“我的录音”。`;
}

function pickRecordingMimeType() {
  const candidates = ['audio/webm;codecs=opus', 'audio/webm', 'audio/mp4'];
  return candidates.find((item) => MediaRecorder.isTypeSupported(item)) || '';
}

const stageText = {
  upload: '正在上传',
  normalize: '正在转换音频格式',
  separate: '正在分析原唱',
  analyze: '正在分析你的录音',
  align: '正在匹配原唱片段',
  segment: '正在按音节生成修音计划',
  render: '正在渲染修音后音频',
  mix: '正在混音',
  package: '正在打包下载文件',
  completed: '处理完成'
};

form.addEventListener('submit', async (event) => {
  event.preventDefault();
  statusText.textContent = '正在上传';
  warningText.textContent = '';
  links.hidden = true;
  startButton.disabled = true;
  try {
    if (selectedReferenceAudio) {
      await submitImportedReferenceJob();
    } else {
      await submitLegacyUploadJob();
    }
  } catch (err) {
    statusText.textContent = `处理失败：${err.message}`;
    startButton.disabled = false;
  }
});

async function submitLegacyUploadJob() {
  const body = new FormData(form);
  const response = await fetch('/upload', { method: 'POST', headers: { Authorization: `Bearer ${token}` }, body });
  if (!response.ok) {
    const data = await response.json().catch(() => ({}));
    throw new Error(readApiError(data, '上传失败'));
  }
  const data = await response.json();
  statusText.textContent = '排队中';
  pollStatus(data.job_id);
}

async function submitImportedReferenceJob() {
  if (!userAudioInput.files.length) {
    throw new Error('请先上传或录制我的录音。');
  }
  const userAudio = await uploadUserAudioForPitchJob(userAudioInput.files[0]);
  const formData = new FormData(form);
  const response = await fetch('/api/v1/pitch-correction/jobs', {
    method: 'POST',
    headers: { Authorization: `Bearer ${token}`, 'Content-Type': 'application/json' },
    body: JSON.stringify({
      reference_audio_id: selectedReferenceAudio.audio_id,
      user_audio_id: userAudio.audio_id,
      options: {
        auto_locate_segment: true,
        correction_strength: Number(formData.get('correction_strength') || 0.75),
        keep_vibrato_ratio: Number(formData.get('keep_vibrato_ratio') || 0.6),
        max_shift_cents: Number(formData.get('max_shift_cents') || 300),
        separation: false,
        ai_assist: false
      }
    })
  });
  const data = await response.json().catch(() => ({}));
  if (!response.ok) {
    throw new Error(readApiError(data, '创建修音任务失败'));
  }
  statusText.textContent = data.message || '修音任务已创建';
  handlePitchJobStatus(data.job_id, data);
}

async function uploadUserAudioForPitchJob(file) {
  const body = new FormData();
  const isRecording = file.name.startsWith('recording.');
  body.append('file', file);
  body.append('kind', 'user_vocal');
  body.append('source', isRecording ? 'recording' : 'upload');
  const response = await fetch('/api/v1/audio/upload', { method: 'POST', headers: { Authorization: `Bearer ${token}` }, body });
  const data = await response.json().catch(() => ({}));
  if (!response.ok) {
    throw new Error(readApiError(data, '上传我的录音失败'));
  }
  return data;
}

async function pollStatus(jobId) {
  const response = await fetch(`/status/${jobId}`, { headers: { Authorization: `Bearer ${token}` } });
  const data = await response.json();
  progress.value = data.progress || 0;
  statusText.textContent = data.message || stageText[data.stage] || '排队中';
  showWarnings(data.warnings || []);
  if (data.status === 'completed') {
    await loadResult(jobId);
    return;
  }
  if (data.status === 'failed') {
    statusText.textContent = '处理失败';
    startButton.disabled = false;
    return;
  }
  if (data.status === 'expired') {
    statusText.textContent = '下载链接已过期';
    startButton.disabled = false;
    return;
  }
  setTimeout(() => pollStatus(jobId), 2000);
}

async function pollPitchJob(jobId) {
  const response = await fetch(`/api/v1/pitch-correction/jobs/${jobId}`, { headers: { Authorization: `Bearer ${token}` } });
  const data = await response.json();
  handlePitchJobStatus(jobId, data);
}

async function handlePitchJobStatus(jobId, data) {
  progress.value = statusToProgress(data.status);
  statusText.textContent = data.message || stageText[data.stage] || '处理中';
  showWarnings(data.warnings || []);
  if (data.status === 'succeeded') {
    await loadPitchJobArtifacts(jobId, data);
    return;
  }
  if (data.status === 'failed') {
    statusText.textContent = data.message || '处理失败';
    startButton.disabled = false;
    return;
  }
  if (data.status === 'needs_confirmation') {
    statusText.textContent = data.message || '需要确认原唱片段后继续。';
    startButton.disabled = false;
    return;
  }
  setTimeout(() => pollPitchJob(jobId), 2000);
}

function statusToProgress(status) {
  return { queued: 0.05, running: 0.5, needs_confirmation: 0.2, succeeded: 1, failed: 0 }[status] || 0.1;
}

async function loadPitchJobArtifacts(jobId, statusData) {
  let artifacts = statusData.artifacts || {};
  if (!Object.keys(artifacts).length) {
    const response = await fetch(`/api/v1/pitch-correction/jobs/${jobId}/artifacts`, { headers: { Authorization: `Bearer ${token}` } });
    artifacts = await response.json();
  }
  statusText.textContent = '处理完成';
  links.hidden = false;
  links.replaceChildren();
  addDownloadLink(artifacts.corrected_vocal, 'corrected_vocal.wav', '下载修音后人声');
  addDownloadLink(artifacts.mix, 'mix.wav', '下载混音结果');
  addDownloadLink(artifacts.report, 'report.json', '下载处理报告');
  if (artifacts.bundle) {
    addDownloadLink(artifacts.bundle, 'bundle.zip', '下载打包文件');
  }
  startButton.disabled = false;
}

async function loadResult(jobId) {
  const response = await fetch(`/result/${jobId}`, { headers: { Authorization: `Bearer ${token}` } });
  if (response.status === 410) {
    statusText.textContent = '下载链接已过期';
    startButton.disabled = false;
    return;
  }
  const data = await response.json();
  statusText.textContent = '处理完成';
  showWarnings(data.warnings || []);
  if (!data.actual_pitch_shift_applied) {
    warningText.textContent = '仅生成修音计划，未做真实变调。';
  }
  links.hidden = false;
  links.innerHTML = `
    <a href="#" data-url="${data.artifacts.corrected_vocal}" data-name="corrected_vocal.wav">下载修音后人声</a>
    <a href="#" data-url="${data.artifacts.mix}" data-name="mix.wav">下载混音结果</a>
    <a href="#" data-url="${data.artifacts.report}" data-name="report.json">下载处理报告</a>
  `;
  links.querySelectorAll('a').forEach((item) => {
    item.addEventListener('click', (event) => {
      event.preventDefault();
      downloadWithToken(item.dataset.url, item.dataset.name);
    });
  });
  downloadWithToken(data.bundle_url, 'bundle.zip');
  startButton.disabled = false;
}

function addDownloadLink(url, filename, text) {
  if (!url) {
    return;
  }
  const link = document.createElement('a');
  link.href = '#';
  link.dataset.url = url;
  link.dataset.name = filename;
  link.textContent = text;
  link.addEventListener('click', (event) => {
    event.preventDefault();
    downloadWithToken(url, filename);
  });
  links.appendChild(link);
}

function showWarnings(warnings) {
  if (warnings.some((item) => item.includes('仅生成修音计划，未做真实变调'))) {
    warningText.textContent = '仅生成修音计划，未做真实变调。';
  }
}

function readApiError(data, fallback) {
  if (typeof data.detail === 'string') {
    return data.detail;
  }
  if (data.detail && typeof data.detail === 'object') {
    return data.detail.message || data.detail.error_code || fallback;
  }
  return data.message || data.error_code || fallback;
}

async function downloadWithToken(url, filename) {
  const response = await fetch(url, { headers: { Authorization: `Bearer ${token}` } });
  if (response.status === 410) {
    statusText.textContent = '下载链接已过期';
    return;
  }
  if (!response.ok) {
    statusText.textContent = '下载失败';
    return;
  }
  const blob = await response.blob();
  const objectUrl = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = objectUrl;
  a.download = filename;
  document.body.appendChild(a);
  a.click();
  a.remove();
  URL.revokeObjectURL(objectUrl);
}
