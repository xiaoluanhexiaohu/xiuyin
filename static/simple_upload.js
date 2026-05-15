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

const userAudioInput = document.getElementById('userAudioInput');
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

if (recordStart) {
  recordStart.addEventListener('click', startRecording);
  recordStop.addEventListener('click', stopRecording);
  recordReset.addEventListener('click', resetRecording);
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
  const body = new FormData(form);
  try {
    const response = await fetch('/upload', { method: 'POST', headers: { Authorization: `Bearer ${token}` }, body });
    if (!response.ok) {
      const data = await response.json().catch(() => ({}));
      throw new Error(data.detail || '上传失败');
    }
    const data = await response.json();
    statusText.textContent = '排队中';
    pollStatus(data.job_id);
  } catch (err) {
    statusText.textContent = `处理失败：${err.message}`;
    startButton.disabled = false;
  }
});

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

function showWarnings(warnings) {
  if (warnings.some((item) => item.includes('仅生成修音计划，未做真实变调'))) {
    warningText.textContent = '仅生成修音计划，未做真实变调。';
  }
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
