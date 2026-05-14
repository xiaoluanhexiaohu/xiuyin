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
