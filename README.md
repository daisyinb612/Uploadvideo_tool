# ViewPair 双视角视频工具

本地网页：分别上传第一、第三视角和可选的 Motion CSV，按时间对齐、去黑边、并排合成，支持下载 MP4、同步 CSV、元数据 JSON 和完整 ZIP。测试时默认只在本机导出和下载，不同步服务器。没有飞书登记环节。

## 运行

需要 Python 3.11+、FFmpeg、FFprobe，无第三方 Python 依赖。

```sh
python3 app.py --port 8765
```

打开 http://127.0.0.1:8765 。`--output-dir` 可以指定本地输出目录，默认 `outputs/`。网页中的 `/mnt/skill/mess` 是之前约定的可选服务器目标，处理完成后显示实际保存结果。

## 处理方式

- Rokid 从原始 `vid-YYYYMMDD-HHMMSS-*.MP4` 文件名读取开始时间，按北京时间解释，不用可能表示录制结束的内部 creation_time。iPhone 从拍摄元数据读取带时区的时间。
- 自动对齐裁去较早视频的起始差，只输出共同时间范围。“已对齐”模式则从两条视频起点开始。当前是设备时钟初步对齐，没有音频校正。
- 默认裁黑边：在四个时间位置采样，取可见区域并集；保持比例并排，统一高度不超过 720px，输出 H.264 / AAC、30fps。音频优先第一视角，没有时用第三视角。
- Motion CSV 使用 UTF-8 和 `sample_time_iso8601` 绝对时间列，时间需包含时区并有序。按共同时间范围 `[start,end)` 截取，保留原始列并新增 `video_time_s`。绝对时间优先以第三视角时钟为锚点；覆盖不完整会提示。暂不支持 XLSX。
- 名称为 `YYYYMMDD_HHMMSS_角色_内容_firstthird.mp4`。CSV 为同前缀 `_motion.csv`，元数据为 `.metadata.json`；重名整组递增 `（1）`、`（2）`。
- 元数据保留两机原始文件名、FFprobe 信息、裁剪与时间处理参数。HDR、空间音频、传感器轨道不会原样保留，原始文件请单独归档。

## 上传与任务状态

三个上传位使用同一个上传状态控制器，更换文件会中止旧请求，旧回调不能覆盖当前选择。处理中暂时锁定输入，确保视频、CSV、命名及下载选项属于同一次操作。

任务状态和上传元数据仅存在内存，不持久化。重启后旧任务链接失效，但导出文件保留。成功上传的文件暂存在 `uploads/`，同一会话可重复导出，无需重传；关闭服务后可手动清理 `uploads/`。没有固定文件大小限制，受磁盘空间约束。一次只处理一个任务。

## 可选服务器副本

保留原有 SSH 保存能力，默认关闭。手动勾选后会把 MP4、Motion CSV（如有）和 JSON 保存到既有服务器 `/mnt/skill/mess`，目标配置集中在 `config.py`。需要可信主机记录、账号和 sudo 权限。密码仅本次处理使用，不写入任务状态或配置。远端同名文件仍拒绝覆盖；失败会显示错误，本地结果保留。本项目当前整理仅针对本地，不包含服务器部署。

## 目录

```text
app.py                 启动入口
config.py              本地路径、可选服务器目标
web.py                 HTTP、文件下载和 ZIP
services/
  jobs.py              内存状态、元数据缓存、命名及任务编排
  media.py             元数据、拍摄时间、对齐、黑边检测
  processing.py        FFmpeg 合成与元数据导出
  motion.py            CSV 时间裁切
  storage.py           既有 SSH 副本保存
static/
  index.html           页面结构
  style.css            页面样式
  app.js               页面交互
  upload-slot.mjs      单文件上传状态机
  ...
tests/                 回归验证
uploads/               本地暂存（不入 Git）
outputs/               导出结果（不入 Git）
```

## 验证

```sh
python3 -m unittest discover -s tests -v
node --test tests/upload-slot.test.mjs
```

测试覆盖 Motion 截取、命名冲突、元数据缓存、完整视频导出和 ZIP 下载，以及 Motion 旧上传完成/失败/进度不能覆盖新选择。测试不连接服务器。
