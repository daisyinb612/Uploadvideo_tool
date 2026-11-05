import { UploadSlot } from './upload-slot.mjs';

// Resolve internal routes under the same mount directory as this module.
const siteBase = new URL('../', import.meta.url);
const appURL = path => new URL(/^https?:\/\//i.test(path) ? path : path.replace(/^\/+/, ''), siteBase).href;

const $ = id => document.getElementById(id);
let outputDir = '/mnt/skill/mess';
let coffeeRoles = [];
let publicBase = '';
let namingVersion = 0;
let namingTimer;
let timeValue = '日期时间';
let manualTime = false;
let busy = false;
const previewURLs = {};
const slots = {};

function mode() { return $('uploadMode').value; }
function views() { return mode() === 'first' ? ['first'] : mode() === 'third' ? ['third'] : mode() ? ['first', 'third'] : []; }
function suffix() { return ['first', 'third'].includes(mode()) ? mode() : 'firstthird'; }
function selection() {
  return {mode: mode(), project: $('project').value.trim(),
    ...Object.fromEntries(views().map(key => [key, slots[key].data?.token])),
    ...(mode() === 'both_motion' ? {motion: slots.motion.data?.token} : {}),
    role: selectedValue('role'), content: selectedValue('content'),
    ...(manualTime ? {naming_time: inputTime()} : {})};
}
$('uploadMode').onchange = () => {
  const active = views();
  for (const button of document.querySelectorAll('[data-mode]')) {
    button.setAttribute('aria-pressed', String(button.dataset.mode === mode()));
  }
  $('uploadGrid').hidden = !mode();
  for (const key of ['first', 'third']) $(key+'Card').hidden = !active.includes(key);
  $('motionCard').hidden = mode() !== 'both_motion';
  active.forEach((key, index) => {
    $(key+'Card').querySelector('h2').textContent = `0${index+1} / ${key === 'first' ? '第一视角' : '第三视角'}`;
    $(key+'Card').querySelector('.sub').textContent = active.length === 1 ? '单视角裁边与导出' : (key === 'first' ? '合成画面左侧 · 通常为竖向视频' : '合成画面右侧 · 通常为横向视频');
  });
  $('uploadGrid').style.gridTemplateColumns = `repeat(${active.length + (mode() === 'both_motion' ? 1 : 0)},minmax(0,1fr))`;
  $('alignmentSettings').hidden = active.length !== 2;
  $('viewSuffix').textContent = mode() ? suffix() : '选择模式后自动填充';
  $('start').textContent = active.length === 2 ? '开始合成并导出 ↗' : '开始处理并导出 ↗';
  $('modeHint').textContent = mode() === 'both_motion' ? '请上传两个视频和 Motion CSV。' : active.length === 2 ? '请上传两个视频，自动对齐后合成。' : mode() ? '上传一个视频，自动裁边后导出。' : '先选择模式，再上传对应素材。';
  $('result').style.display = 'none';
  if (!manualTime) {timeValue = '日期时间'; $('captureTime').value = '';}
  scheduleNaming();
};
function renderRoleOptions() {
  const previous = $('role').value;
  const isCoffee = $('project').value.trim().toLowerCase() === 'coffee';
  const choices = isCoffee ? coffeeRoles : [
    {value:'teacher',name:'老师'}, {value:'student',name:'学生'}, {value:'custom',name:'自定义增加'}];
  $('role').replaceChildren(...choices.map(role => {
    const option = document.createElement('option');
    option.value = role.value;
    option.textContent = role.value === 'custom' ? '＋ 自定义增加' : `${role.value} · ${role.name}`;
    return option;
  }));
  if (choices.some(role => role.value === previous)) $('role').value = previous;
  $('customRole').hidden = $('role').value !== 'custom';
}
$('project').oninput = () => { renderRoleOptions(); scheduleNaming(); };

function selectedValue(id) {
  const customId = 'custom' + id[0].toUpperCase() + id.slice(1);
  return $(id).value === 'custom' ? $(customId).value.trim() : $(id).value;
}

function requestUpload(file, kind, progress) {
  const xhr = new XMLHttpRequest();
  const promise = new Promise((resolve, reject) => {
    xhr.open('PUT', appURL(kind === 'motion' ? 'api/motion-upload' : 'api/upload'));
    xhr.setRequestHeader('X-Filename', encodeURIComponent(file.name));
    xhr.timeout = 60 * 60 * 1000;
    xhr.ontimeout = () => reject(Error('上传或服务器响应超过60分钟，请检查网络后重新选择文件'));
    xhr.upload.onprogress = event => {
      const total = event.lengthComputable ? event.total : file.size;
      progress({percent: total ? Math.min(100, Math.round(event.loaded / total * 100)) : null,
        loaded: event.loaded, total, phase: 'uploading'});
    };
    xhr.upload.onload = () => progress({percent: 100, loaded: file.size, total: file.size, phase: 'waiting'});
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
    label.textContent = key === 'motion' ? '尚未选择 Motion CSV' : '尚未选择文件';
  } else if (slot.error) {
    label.textContent = slot.file.name + ' · 上传失败：' + slot.error;
  } else if (slot.data) {
    label.textContent = slot.file.name + ' · 已读取';
  } else {
    const size = n => (n / 1024 / 1024).toFixed(1) + ' MB';
    label.textContent = slot.file.name + (slot.phase === 'waiting'
      ? ' · 已发送，等待服务器接收确认与文件解析…'
      : ' · 正在上传 ' + (slot.progress == null ? '' : slot.progress + '% · ')
        + size(slot.loaded || 0) + ' / ' + size(slot.file.size));
  }
  let meter = $(key + 'UploadProgress');
  if (!meter) {
    meter = document.createElement('progress');
    meter.id = key + 'UploadProgress';
    meter.max = 100;
    meter.className = 'upload-progress';
    meter.setAttribute('aria-label', key === 'motion' ? 'Motion 上传进度' : (key === 'first' ? '第一视角上传进度' : '第三视角上传进度'));
    label.after(meter);
  }
  meter.hidden = !slot.file || !!slot.data || !!slot.error;
  if (slot.phase === 'waiting' || slot.progress == null) meter.removeAttribute('value');
  else meter.value = slot.progress;
  // Naming only depends on the selected file and its result, not every byte sent.
  const state = !slot.file ? 'empty' : slot.error ? 'error' : slot.data ? 'ready' : slot.phase;
  if (key !== 'motion' && slot.namingState !== state) {
    slot.namingState = state;
    scheduleNaming();
  }
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
  $('motionNamePreview').hidden = mode() !== 'both_motion';
  $('destination').textContent = '服务器目标：' + path;
  $('motionDestination').textContent = '服务器 CSV：' + motionPath;
  $('copyTask').value = name.replace(/_(firstthird|first|third)(?=_\d+$|$)/, '');
  const marker = name.lastIndexOf('_' + suffix());
  const stem = marker < 0 ? name : name.slice(0, marker);
  const duplicate = marker < 0 ? '' : name.slice(marker + ('_' + suffix()).length);
  for (const [id, filename] of [['copyFirst', stem + '_first' + duplicate + '.mp4'],
                               ['copyThird', stem + '_third' + duplicate + '.mp4'],
                               ['copyCombined', name + '.mp4']]) {
    const available = id === 'copyCombined' ? views().length === 2 : views().includes(id === 'copyFirst' ? 'first' : 'third');
    $(id).value = available && publicBase && timeValue !== '日期时间'
      ? publicBase + encodeURIComponent(filename) : '';
    $(id).placeholder = '读取拍摄时间并配置命名后生成';
  }
  $('copyMotion').value = mode() === 'both_motion' && publicBase && timeValue !== '日期时间'
    ? publicBase + encodeURIComponent(name + '_motion.csv') : '';
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
  const name = `${$('project').value.trim() || '项目'}_${timeValue}_${selectedValue('role') || '角色'}_${selectedValue('content') || '内容'}_${suffix()}`;
  showNames(name, `${outputDir}/${name}.mp4`, `${outputDir}/${name}_motion.csv`);
  for (const button of document.querySelectorAll('[data-copy], #copyRow')) button.disabled = true;
  namingTimer = setTimeout(updateName, 250);
}

async function updateName() {
  const version = namingVersion;
  const activeSlots = views().map(key => slots[key]);
  const failed = activeSlots.find(slot => slot.error);
  if (!manualTime && failed) {
    $('timeSource').textContent = '视频上传失败：' + failed.error + '；请重新选择文件后再读取时间';
    return;
  }
  if (!manualTime && activeSlots.some(slot => slot.file && !slot.data)) {
    $('timeSource').textContent = activeSlots.some(slot => slot.file && !slot.data && slot.phase === 'waiting')
      ? '文件已发送，等待服务器确认与解析；完成后自动读取拍摄时间'
      : '视频仍在上传，请查看素材卡片的上传进度';
    return;
  }
  if (!mode() || (!manualTime && !views().some(key => slots[key].data))) {
    $('timeSource').textContent = ['first', 'third'].some(key => slots[key].file)
      ? '视频上传完成后自动读取拍摄时间，也可手动填写' : '选择视频后自动读取，也可手动填写';
    return;
  }
  try {
    const data = await post('/api/naming', selection());
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
    $('copyMotion').value = data.motion || '';
  } catch (error) {
    if (version !== namingVersion) return;
    for (const id of ['copyTask', 'copyFirst', 'copyThird', 'copyCombined', 'copyMotion']) $(id).value = '';
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
fetch(appURL('api/config')).then(response => response.json()).then(data => {
  outputDir = data.output;
  publicBase = data.public_base;
  coffeeRoles = data.coffee_roles;
  renderRoleOptions();
  scheduleNaming();
}).catch(() => { $('destination').textContent = '读取保存位置失败，请刷新页面'; });

async function post(url, payload) {
  const response = await fetch(appURL(url), {
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
  $(id).href = appURL(url);
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
  $('copyFirst').value = job.video_first ? appURL(job.video_first) : '';
  $('copyThird').value = job.video_third ? appURL(job.video_third) : '';
  $('copyCombined').value = job.video_first_third ? appURL(job.video_first_third) : '';
  $('copyMotion').value = job.motion ? appURL(job.motion) : '';
  for (const button of document.querySelectorAll('[data-copy], #copyRow')) button.disabled = !job.links_verified;
  if (!job.links_verified) {
    for (const id of ['copyFirst', 'copyThird', 'copyCombined', 'copyMotion']) $(id).value = '';
    for (const button of document.querySelectorAll('[data-copy], #copyRow')) button.disabled = true;
  }
  $('copyStatus').textContent = job.links_verified ? '服务器文件访问校验通过' : '链接未通过验证，请查看保存错误';
  $('output').src = appURL(job.url);
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
    const response = await fetch(appURL('api/jobs/' + jid));
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
    if (!mode()) throw Error('请先选择上传模式');
    if (views().some(key => !slots[key].data)) throw Error('请上传当前模式需要的视频');
    if (mode() === 'both_motion' && !slots.motion.data) throw Error('Motion CSV 上传未成功');
    const infoText = views().map(key => {
      const info = slots[key].data.info;
      return (key === 'first' ? '第一视角：' : '第三视角：') + (info.capture_time || info.creation_time || '未找到');
    });
    $('timestamps').textContent = infoText.join('；');
    const autoDownload = $('downloadTogether').checked;
    const check = await post('/api/check-existing', selection());
    if (check.existing && !window.confirm('这个任务已上传过，是否重新上传？新版本将使用 _1、_2 编号，不覆盖旧文件。')) {
      status('已取消重新上传', 0);
      return;
    }
    const result = await post('/api/jobs', {...selection(), confirm_reupload: check.existing, align: $('align').value, sync_server: true});
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
  ['copyTask', 'copyFirst', 'copyThird', 'copyCombined', 'copyMotion'].map(id => $(id).value).join('\t')
);
$('copyHeader').onclick = () => copyText(
  ['task_name', 'video_first', 'video_third', 'video_first_third', 'motion'].join('\t')
);

for (const button of document.querySelectorAll('[data-mode]')) {
  button.onclick = () => {
    if (busy) return;
    $('uploadMode').value = button.dataset.mode;
    $('uploadMode').onchange();
  };
}
$('uploadMode').onchange();
