# xiuyin 中文极简上传式一键修音 Web 系统

xiuyin 是一个离线批处理的一键修音 MVP。Web 版面向普通中文用户：登录后只需要上传两个音频文件——原唱音频和我的录音——点击“开始修音”，后端会自动完成格式转换、可选原唱人声分离、F0/特征分析、局部对齐、按音节近似修音、渲染、混音和打包下载。

处理完成后会生成并打包下载：

- `corrected_vocal.wav`
- `mix.wav`
- `report.json`
- `bundle.zip`

> 重要说明：如果服务器没有安装 Rubber Band / pyrubberband，系统会保守回退为占位渲染：**“仅生成修音计划，未做真实变调。”** 页面和 `report.json` 都会显示该提示。

## Web 版用户流程

1. 打开中文登录页。
2. 输入用户名和密码登录。
3. 上传：
   - 原唱音频
   - 我的录音
4. 点击“开始修音”。
5. 页面轮询任务状态。
6. 完成后自动下载 `bundle.zip`，同时提供三个单独下载链接。

## 安装

```bash
python3.11 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

## 系统依赖

必需：

- Redis：后台队列。
- ffmpeg / ffprobe：处理 mp3、m4a，并统一转工作 wav。

可选：

- Demucs：原唱人声/伴奏分离；不可用时任务不会失败，会提示“Demucs 不可用，已跳过原唱人声分离。”
- Rubber Band + pyrubberband：真实分段变调；不可用时提示“仅生成修音计划，未做真实变调。”
- torchcrepe：可选 F0 后端；否则使用 `librosa.pyin`。

## 登录配置

MVP 默认通过环境变量配置管理员用户，不要把明文密码写入代码。

```bash
export XIUYIN_JWT_SECRET='请替换为随机长密钥'
export XIUYIN_ADMIN_USERNAME='admin'
export XIUYIN_ADMIN_PASSWORD_HASH='sha256$<密码的 sha256 hex，仅建议本地测试>'
```

生产环境建议使用 `pbkdf2_sha256$iterations$salt$hex_digest` 格式。以后可以把 `app/users.py` 替换为数据库用户存储。

## Redis 启动方式

```bash
redis-server
```

默认 Redis 地址：

```bash
export XIUYIN_REDIS_URL=redis://localhost:6379/0
```

## Worker 启动方式

```bash
python -m jobs.worker
```

如果 Redis 不可用，worker 会输出清晰错误并退出。

## FastAPI 启动方式

```bash
uvicorn app.main:app --reload
```

然后访问：

- `GET /login`：中文登录页。
- `GET /`：中文极简上传页。
- `GET /health`：健康检查。

## 上传限制

- 单文件最大：100MB。
- 最大音频时长：10 分钟。
- 支持格式：`wav`、`mp3`、`m4a`、`flac`。
- mp3/m4a 必须通过 ffmpeg 规范化。如果服务器未安装 ffmpeg，会返回中文错误：
  - “服务器未安装 ffmpeg，无法处理 mp3/m4a，请上传 wav 或联系管理员。”

## 下载有效期

处理完成后 1 小时内可以下载。过期后接口返回 410：

> 下载链接已过期，请重新提交任务。

过期清理可以手动运行：

```bash
python -m jobs.cleanup
```

## Web API 概览

- `POST /auth/token`：OAuth2 Password Flow，返回 Bearer JWT。
- `POST /upload`：上传原唱和我的录音，JWT 必填，立即返回 job_id。
- `GET /status/{job_id}`：轮询中文任务状态，JWT 必填且校验 owner。
- `GET /result/{job_id}`：获取下载链接，JWT 必填且校验 owner。
- `GET /download/{job_id}/{artifact}`：下载白名单文件，JWT 必填且校验 owner。
- `GET /health`：健康检查。

## 运行命令示例

```bash
pip install -r requirements.txt
redis-server
python -m jobs.worker
uvicorn app.main:app --reload
```

## 算法概览

1. 上传文件统一规范化为工作 wav。
2. 可选尝试 Demucs 原唱人声分离。
3. 提取 F0、voiced flag、voiced probability、onset strength、RMS、chroma。
4. 对用户录音和原唱进行整体或局部 DTW 对齐。
5. 使用保守 correction plan：低置信度、无声、呼吸声、齿音区域不强修。
6. 默认使用 `conservative` 按音节近似分段。
7. Rubber Band 可用时按段近似变调并做短 crossfade。
8. Rubber Band 不可用时输出占位 `corrected_vocal.wav` 并写入中文 warning。
9. 生成 `mix.wav`、`report.json`、`bundle.zip`。

## 旧 CLI

仓库仍保留旧离线 manifest CLI，便于本地回归：

```bash
python -m jobs.batch_export --manifest examples/demo_manifest.json
```

## 测试

```bash
pytest -q
```

## License Risk Notes

商业分发前需要重新检查依赖和模型许可证。Rubber Band 可能涉及 GPL/商业授权；Demucs/Spleeter 代码与模型权重也需要单独审查。
