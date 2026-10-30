```text
video-tool/
├── app.py                  # 启动入口
├── config.py               # 路径与可选服务器配置
├── web.py                  # HTTP 接口、视频与 ZIP 下载
├── services/
│   ├── __init__.py
│   ├── jobs.py             # 内存状态、命名、任务编排
│   ├── media.py            # 元数据、时间对齐、黑边检测
│   ├── processing.py       # 三视角导出与元数据保存
│   ├── motion.py           # Motion CSV 同步裁切
│   └── storage.py          # 可选 SSH 保存
├── static/
│   ├── index.html          # 页面结构
│   ├── style.css           # 页面样式
│   ├── app.js              # 页面交互与结果复制
│   └── upload-slot.mjs     # 单文件上传状态控制
├── tests/
│   ├── test_local.py       # 本地处理流程验证
│   └── upload-slot.test.mjs # 上传竞态验证
├── uploads/                # 上传暂存，不入 Git
└── outputs/                # 视频、Motion CSV、元数据，不入 Git
```
