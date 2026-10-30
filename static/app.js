import { UploadSlot } from '/static/upload-slot.mjs';

const $ = id => document.getElementById(id);
let outputDir = '';
let namingVersion = 0;
let namingTimer;
let timeValue = '日期时间';
let busy = false;
const previewURLs = {};
const slots = {};

function selectedValue(id) {
  const customId = 'custom' + id[0].toUpperCase() + id.slice(1);
  return $(id).value === 'custom' ? $(customId).value.trim() : $(id).value;
}

function requestUpload(file, kind, progress) {
  const xhr = new XMLHttpRequest();
  const promise = new Promise((resolve, reject) => {
    xhr.open('PUT', kind === 'motion' ? '/api/motion-upload' : '/api/upload');
    xhr.setRequestHeader('X-Filename', encodeURIComponent(file.name));
    xhr.upload.onprogress = event => {
      if (event.lengthComputable) progress(Math.round(event.loaded / event.total * 100));
    };
    xhr.onload = () => {
      try {
        const data = JSON.parse(xhr.responseText);
        if (xhr.status !== 200) throw Error(data.error || '上传失败');
        resolve(data);
      } catch (error) {
        reject(error);
      }
    };
    xhr.onerror = () => reject(Error('上传连接中断，请重新选择'));
    xhr.onabort = () => reject(Error('上传已取消'));
    xhr.send(file);
  });
  return { promise, abort: () => xhr.abort() };
}

function renderSlot(key, slot) {
  const label = $(key + 'Name');
  if (!slot.file) {
    label.textContent = key === 'motion' ? '可选：尚未选择 Motion CSV' : '尚未选择文件';
  } else if (slot.error) {
    label.textContent = slot.file.name + ' · 上传失败：' + slot.error;
  } else if (slot.data) {
    label.textContent = slot.file.name + ' · 已读取';
  } else {
    label.textContent = slot.file.name + ' · 上传 ' + slot.progress + '%';
  }
  if (key !== 'motion') scheduleNaming();
}

for (const key of ['first', 'third', 'motion']) {
  slots[key] = new UploadSlot(
    (file, progress) => requestUpload(file, key, progress),
    slot => renderSlot(key, slot)
  );
  $(key).onchange = () => {
    if (busy) return;
    const file = $(key).files[0];
    if (key !== 'motion') {
      timeValue = '日期时间';
      $('captureTime').textContent = '正在读取视频信息…';
      $('timeSource').textContent = '';
      $(key + 'Drop').classList.toggle('has-video', !!file);
      $(key + 'Replace').hidden = !file;
      if (previewURLs[key]) URL.revokeObjectURL(previewURLs[key]);
      $(key + 'Preview').style.display = file ? 'block' : 'none';
      if (file) {
        previewURLs[key] = URL.createObjectURL(file);
        $(key + 'Preview').src = previewURLs[key];
      }
    }
    slots[key].select(file);
  };
  if (key !== 'motion') $(key + 'Replace').onclick = () => $(key).click();
}

function showNames(name, path, motionPath) {
  $('namePreview').textContent = name + '.mp4';
  $('motionNamePreview').textContent = name + '_motion.csv';
  $('destination').textContent = '服务器目标：' + path;
  $('motionDestination').textContent = '服务器 CSV：' + motionPath;
  $('copyTask').value = name.replace(/_firstthird(?=（\d+）$|$)/, '');
  for (const [id, suffix] of [['copyFirst', '_first.mp4'], ['copyThird', '_third.mp4'], ['copyCombined', '.mp4']]) {
    $(id).value = new URL('/videos/' + encodeURIComponent(name + suffix), location.origin).href;
  }
  $('copyStatus').textContent = '';
}

function scheduleNaming() {
  ++namingVersion; // Invalidate in-flight previews immediately, including during debounce.
  clearTimeout(namingTimer);
  const name = `${timeValue}_${selectedValue('role') || '角色'}_${selectedValue('content') || '内容'}_firstthird`;
  showNames(name, `${outputDir}/${name}.mp4`, `${outputDir}/${name}_motion.csv`);
  namingTimer = setTimeout(updateName, 250);
}

async function updateName() {
  const version = namingVersion;
  if (!slots.first.data || !slots.third.data) return;
  try {
    const data = await post('/api/naming', {
      first: slots.first.data.token,
      third: slots.third.data.token,
      role: selectedValue('role'),
      content: selectedValue('content'),
    });
    if (version !== namingVersion) return;
    timeValue = data.time.value;
    $('captureTime').textContent = data.time.display;
    $('timeSource').textContent = '来源：' + data.time.source;
    showNames(data.name, data.path, data.motion_path);
  } catch (error) {
    if (version !== namingVersion) return;
    $('captureTime').textContent = '无法自动命名';
    $('timeSource').textContent = error.message;
  }
}

for (const id of ['role', 'content']) {
  const custom = $('custom' + id[0].toUpperCase() + id.slice(1));
  $(id).onchange = () => {
    custom.hidden = $(id).value !== 'custom';
    scheduleNaming();
  };
  custom.oninput = scheduleNaming;
}
$('syncServer').onchange = () => { $('serverPassword').hidden = !$('syncServer').checked; };
fetch('/api/config').then(response => response.json()).then(data => {
  outputDir = data.output;
  scheduleNaming();
}).catch(() => { $('destination').textContent = '读取保存位置失败，请刷新页面'; });

async function post(url, payload) {
  const response = await fetch(url, {
    method: 'POST', headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  });
  const data = await response.json();
  if (!response.ok) throw Error(data.error || '请求失败');
  return data;
}

function status(text, progress) {
  $('stage').textContent = text;
  $('progress').style.width = progress + '%';
}

function setBusy(value) {
  busy = value;
  for (const input of document.querySelectorAll('input, select, button')) {
    if (!input.closest('.copy-fields')) input.disabled = value;
  }
}

function downloadLink(id, url, filename) {
  $(id).href = url;
  $(id).download = filename;
}

function showResult(jid, job, autoDownload) {
  $('result').style.display = 'block';
  downloadLink('bundleDownload', '/bundle/' + jid, job.filename.replace(/\.mp4$/i, '.zip'));
  downloadLink('download', job.url, job.filename);
  downloadLink('metadataDownload', job.metadata_url, job.filename.replace(/\.mp4$/i, '.metadata.json'));
  $('motionDownload').hidden = !job.motion_url;
  if (job.motion_url) downloadLink('motionDownload', job.motion_url, job.motion_filename);
  $('copyTask').value = job.task_name;
  $('copyFirst').value = new URL(job.video_first, location.origin).href;
  $('copyThird').value = new URL(job.video_third, location.origin).href;
  $('copyCombined').value = new URL(job.video_first_third, location.origin).href;
  $('copyStatus').textContent = '';
  $('output').src = job.url;
  const messages = ['本地已保存：' + job.path];
  if (job.motion_path) messages.push('CSV：' + job.motion_path);
  if (job.server_paths) messages.push('服务器：' + job.server_paths.join('，'));
  if (job.sync_error) messages.push('服务器同步失败：' + job.sync_error);
  if (job.motion_info && !job.motion_info.coverage_complete) messages.push('注意：Motion 未覆盖完整视频时段');
  $('saved').textContent = messages.join('；');
  if (autoDownload) $('bundleDownload').click();
}

async function waitForJob(jid) {
  while (true) {
    const response = await fetch('/api/jobs/' + jid);
    const job = await response.json();
    if (!response.ok) throw Error(job.error || '读取任务状态失败');
    status(job.stage + ' · ' + job.progress + '%', job.progress);
    if (job.details) {
      $('detail').textContent = job.details.size + ' · 起始裁切 ' +
        job.details.starts.map(value => value.toFixed(3) + 's').join(' / ') +
        ' · ' + job.details.duration.toFixed(1) + ' 秒';
    }
    if (job.status === 'error') throw Error(job.error);
    if (job.status === 'done') return job;
    await new Promise(resolve => setTimeout(resolve, 1000));
  }
}

$('start').onclick = async () => {
  if (busy) return;
  setBusy(true);
  $('status').style.display = 'block';
  $('result').style.display = 'none';
  $('stage').className = '';
  $('detail').textContent = '';
  try {
    status('准备视频信息', 0);
    await Promise.all(Object.values(slots).map(slot => slot.pending));
    if (!slots.first.data || !slots.third.data) throw Error('请先选择并成功上传两个视频');
    if (slots.motion.file && !slots.motion.data) throw Error('Motion CSV 上传未成功');
    if ($('syncServer').checked && !$('serverPassword').value) throw Error('请填写服务器密码，或取消同时保存到服务器');
    const infoText = ['first', 'third'].map(key => {
      const info = slots[key].data.info;
      return (key === 'first' ? '第一视角：' : '第三视角：') + (info.capture_time || info.creation_time || '未找到');
    });
    $('timestamps').textContent = infoText.join('；');
    const autoDownload = $('downloadTogether').checked;
    let result;
    try {
      result = await post('/api/jobs', {
        first: slots.first.data.token, third: slots.third.data.token,
        motion: slots.motion.data?.token,
        role: selectedValue('role'), content: selectedValue('content'),
        align: $('align').value, sync_server: $('syncServer').checked,
        server_password: $('serverPassword').value,
      });
    } finally {
      $('serverPassword').value = '';
    }
    const job = await waitForJob(result.id);
    showResult(result.id, job, autoDownload);
    // Keep the completed task's name and links until the user changes the configuration.
  } catch (error) {
    $('stage').textContent = error.message;
    $('stage').className = 'error';
  } finally {
    setBusy(false);
  }
};

async function copyText(text) {
  try {
    await navigator.clipboard.writeText(text);
    $('copyStatus').textContent = '已复制';
  } catch {
    $('copyStatus').textContent = '复制未成功，请选中内容后手动复制';
  }
}
for (const button of document.querySelectorAll('[data-copy]')) {
  button.onclick = () => copyText($(button.dataset.copy).value);
}
$('copyRow').onclick = () => copyText(
  ['copyTask', 'copyFirst', 'copyThird', 'copyCombined'].map(id => $(id).value).join('\t')
);
$('copyHeader').onclick = () => copyText(
  ['task_name', 'video_first', 'video_third', 'video_first_third'].join('\t')
);
