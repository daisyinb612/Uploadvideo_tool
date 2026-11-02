import { UploadSlot } from '/static/upload-slot.mjs';

const $ = id => document.getElementById(id);
let outputDir = '/mnt/skill/mess';
let publicBase = '';
let namingVersion = 0;
let namingTimer;
let timeValue = '日期时间';
let manualTime = false;
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
      if (!manualTime) {
        timeValue = '日期时间';
        $('captureTime').value = '';
        $('timeSource').textContent = '视频上传完成后自动读取，也可手动填写';
      }
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
  $('copyTask').value = name.replace(/_firstthird(?=（\d+）$|_\d+$|$)/, '');
  const marker = name.lastIndexOf('_firstthird');
  const stem = marker < 0 ? name : name.slice(0, marker);
  const duplicate = marker < 0 ? '' : name.slice(marker + '_firstthird'.length);
  for (const [id, filename] of [['copyFirst', stem + '_first' + duplicate + '.mp4'],
                               ['copyThird', stem + '_third' + duplicate + '.mp4'],
                               ['copyCombined', name + '.mp4']]) {
    $(id).value = publicBase && timeValue !== '日期时间'
      ? publicBase + encodeURIComponent(filename) : '';
    $(id).placeholder = '读取拍摄时间并配置命名后生成';
  }
  if (timeValue === '日期时间') $('copyTask').value = '';
  for (const button of document.querySelectorAll('[data-copy], #copyRow')) {
    button.disabled = button.dataset.copy !== 'copyTask' || timeValue === '日期时间';
  }
  $('copyStatus').textContent = '地址为命名预览，上传并通过访问校验后才可复制视频链接';
}

function scheduleNaming() {
  ++namingVersion; // Invalidate in-flight previews immediately, including during debounce.
  clearTimeout(namingTimer);
  if (!busy) syncOption();
  const name = `${timeValue}_${selectedValue('role') || '角色'}_${selectedValue('content') || '内容'}_firstthird`;
  showNames(name, `${outputDir}/${name}.mp4`, `${outputDir}/${name}_motion.csv`);
  for (const button of document.querySelectorAll('[data-copy], #copyRow')) button.disabled = true;
  namingTimer = setTimeout(updateName, 250);
}

async function updateName() {
  const version = namingVersion;
  if (!manualTime && !slots.first.data && !slots.third.data) {
    $('timeSource').textContent = ['first', 'third'].some(key => slots[key].file)
      ? '视频上传完成后自动读取拍摄时间，也可手动填写' : '选择视频后自动读取，也可手动填写';
    return;
  }
  try {
    const data = await post('/api/naming', {
      first: slots.first.data?.token,
      third: slots.third.data?.token,
      ...(manualTime ? { naming_time: inputTime() } : {}),
      role: selectedValue('role'),
      content: selectedValue('content'),
    });
    if (version !== namingVersion) return;
    timeValue = data.time.value;
    if (!manualTime) {
      const stamp = data.time.value;
      $('captureTime').value = `${stamp.slice(0,4)}-${stamp.slice(4,6)}-${stamp.slice(6,8)}T${stamp.slice(9,11)}:${stamp.slice(11,13)}:${stamp.slice(13,15)}`;
    }
    $('timeSource').textContent = '来源：' + data.time.source;
    showNames(data.name, data.path, data.motion_path);
    // Use the same backend filenames used by the exporter and server upload.
    $('copyTask').value = data.task_name;
    $('copyFirst').value = data.video_first;
    $('copyThird').value = data.video_third;
    $('copyCombined').value = data.video_first_third;
  } catch (error) {
    if (version !== namingVersion) return;
    for (const id of ['copyTask', 'copyFirst', 'copyThird', 'copyCombined']) $(id).value = '';
    for (const button of document.querySelectorAll('[data-copy], #copyRow')) button.disabled = true;
    if (!manualTime) {
      timeValue = '日期时间';
      $('captureTime').value = '';
    }
    $('timeSource').textContent = error.message + '；可在上方手动填写日期时间';
  }
}

function inputTime() {
  const value = $('captureTime').value;
  if (!value || !$('captureTime').validity.valid) return '';
  const parts = value.split('T');
  return parts[0].replaceAll('-', '') + '_' + parts[1].replaceAll(':', '').padEnd(6, '0');
}
$('captureTime').oninput = () => {
  manualTime = true;
  timeValue = inputTime() || '日期时间';
  scheduleNaming();
};
$('readTime').onclick = () => {
  manualTime = false;
  timeValue = '日期时间';
  $('captureTime').value = '';
  scheduleNaming();
};

for (const id of ['role', 'content']) {
  const custom = $('custom' + id[0].toUpperCase() + id.slice(1));
  $(id).onchange = () => {
    custom.hidden = $(id).value !== 'custom';
    scheduleNaming();
  };
  custom.oninput = scheduleNaming;
}
function syncOption() {
  $('serverLinkStatus').textContent = '地址预览（尚未验证可访问）· 保存目录：/mnt/skill/mess · 访问入口：' + publicBase;
}
syncOption();
fetch('/api/config').then(response => response.json()).then(data => {
  outputDir = data.output;
  publicBase = data.public_base;
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
  for (const button of document.querySelectorAll('[data-copy], #copyRow')) button.disabled = !job.links_verified;
  if (!job.links_verified) {
    for (const id of ['copyFirst', 'copyThird', 'copyCombined']) $(id).value = '';
    for (const button of document.querySelectorAll('[data-copy], #copyRow')) button.disabled = true;
  }
  $('copyStatus').textContent = job.links_verified ? '服务器视频访问校验通过' : '链接未通过验证，请查看保存错误';
  $('output').src = job.url;
  const messages = ['本次临时结果：' + job.path];
  if (job.motion_path) messages.push('CSV：' + job.motion_path);
  if (job.server_paths) messages.push('服务器：' + job.server_paths.join('，'));
  if (job.sync_error) messages.push('服务器同步失败：' + job.sync_error);
  if (!job.server_synced) messages.push('尚未同步到服务器，复制的公网链接暂不可访问');
  $('serverLinkStatus').textContent = job.links_verified
    ? '已保存到服务器 /mnt/skill/mess，以上为服务器访问链接'
    : '未同步到服务器：以上为目标链接，文件上传成功后才可访问';
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
        ' · ' + job.details.duration.toFixed(1) + ' 秒' +
        (job.details.synchronization ? ' · ' + job.details.synchronization.accuracy_note : '');
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
    const infoText = ['first', 'third'].map(key => {
      const info = slots[key].data.info;
      return (key === 'first' ? '第一视角：' : '第三视角：') + (info.capture_time || info.creation_time || '未找到');
    });
    $('timestamps').textContent = infoText.join('；');
    const autoDownload = $('downloadTogether').checked;
    const check = await post('/api/check-existing', {
      first: slots.first.data.token, third: slots.third.data.token,
      role: selectedValue('role'), content: selectedValue('content'),
      ...(manualTime ? { naming_time: inputTime() } : {}),
    });
    if (check.existing && !window.confirm('这个任务已上传过，是否重新上传？新版本将使用 _1、_2 编号，不覆盖旧文件。')) {
      status('已取消重新上传', 0);
      return;
    }
    const result = await post('/api/jobs', {
      confirm_reupload: check.existing,
      first: slots.first.data.token, third: slots.third.data.token,
      motion: slots.motion.data?.token,
      role: selectedValue('role'), content: selectedValue('content'),
      ...(manualTime ? { naming_time: inputTime() } : {}),
      align: $('align').value, sync_server: true,
    });
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
