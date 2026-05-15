# xiuyin 中文极简上传式一键修音 Web 系统

xiuyin 是一个离线批处理的一键修音 MVP。Web 版面向普通中文用户：登录后可以上传原唱/参考音频、上传或录制用户人声，一键生成 `corrected_vocal.wav`、`mix.wav`、`report.json` 和 `bundle.zip`。

本次升级保留原有 `/upload` 双文件上传流程，同时新增 API v1：统一音频上传/录音入口、第三方参考搜索、自动片段定位、AI 辅助接口预留、任务化修音接口，以及不依赖 Rubber Band 的真实音高校正 renderer。

## 安装依赖

```bash
python3.11 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

系统依赖：

- Redis：旧 Web 队列默认使用。
- ffmpeg / ffprobe：处理 `mp3`、`m4a`、`webm`、`mp4` 并统一转 WAV。
- 可选 Demucs、torchcrepe、Rubber Band；基础流程不强制安装大型模型。

## 配置 `.env`

复制示例并填写密钥：

```bash
cp .env.example .env
```

关键环境变量：

```bash
export XIUYIN_JWT_SECRET='请替换为随机长密钥'
export XIUYIN_ADMIN_USERNAME='admin'
export XIUYIN_ADMIN_PASSWORD_HASH='sha256$<密码 sha256 hex，仅建议本地测试>'
export JAMENDO_CLIENT_ID=''
export FREESOUND_API_KEY=''
export SPOTIFY_CLIENT_ID=''
export SPOTIFY_CLIENT_SECRET=''
export YOUTUBE_API_KEY=''
```

不要把 API key、client secret 或明文密码写入代码。

## 启动项目

```bash
redis-server
python -m jobs.worker
uvicorn app.main:app --reload
```

本地开发也可使用：

```bash
export XIUYIN_QUEUE_MODE=inline
uvicorn app.main:app --reload
```

## 旧 Web 上传流程（兼容保留）

- `POST /auth/token`：OAuth2 Password Flow，返回 Bearer JWT。
- `POST /upload`：一次性上传原唱音频和我的录音。
- `GET /status/{job_id}`：轮询任务状态。
- `GET /result/{job_id}`：获取下载链接。
- `GET /download/{job_id}/{artifact}`：下载白名单文件。

## API v1：上传参考音频或用户录音

`POST /api/v1/audio/upload`，Bearer JWT 必填，multipart 字段：

- `file`: `webm` / `mp4` / `wav` / `mp3` / `m4a` / `flac`
- `kind`: `user_vocal` 或 `reference_audio`
- `source`: `upload` 或 `recording`

返回：`audio_id`、`duration_sec`、`sample_rate`、`channels`、`normalized_path`/`storage_key`、`warnings`。

前端录音接入建议：使用 `getUserMedia + MediaRecorder`，优先 `audio/webm;codecs=opus`，其次 `audio/mp4`；处理 `NotAllowedError`、`NotFoundError`、`OverconstrainedError`；限制单次录音 10 分钟或 20MB；停止后把 Blob 作为 `source=recording&kind=user_vocal` 上传。

## API v1：第三方参考音频搜索

`POST /api/v1/reference/search`：

```json
{"source":"jamendo","query":"acoustic vocal","page":1,"page_size":10}
```

支持 `jamendo`、`freesound`、`spotify`、`youtube`。返回字段包括 `source`、`track_id`、`title`、`artist`、`duration_sec`、`preview_url`、`stream_url`、`download_url`、`license`、`can_download`、`external_url`、`authorization_notes`。

合规边界：Spotify / YouTube 只做搜索元数据展示和跳转，不做后台音频抓取、下载或缓存；Jamendo / Freesound 导入必须遵守对应授权和条款。

## API v1：创建一键修音任务

先上传参考音频和用户录音得到两个 `audio_id`，然后调用：

`POST /api/v1/pitch-correction/jobs`

```json
{
  "reference_audio_id": "REFERENCE_AUDIO_ID",
  "user_audio_id": "USER_AUDIO_ID",
  "options": {
    "auto_locate_segment": true,
    "correction_strength": 0.75,
    "keep_vibrato_ratio": 0.6,
    "max_shift_cents": 300,
    "separation": false,
    "ai_assist": false
  }
}
```

查询任务：

```bash
curl -H "Authorization: Bearer $TOKEN" http://127.0.0.1:8000/api/v1/pitch-correction/jobs/$JOB_ID
curl -H "Authorization: Bearer $TOKEN" http://127.0.0.1:8000/api/v1/pitch-correction/jobs/$JOB_ID/artifacts
```

任务状态包括 `queued`、`running`、`needs_confirmation`、`succeeded`、`failed`。当自动定位片段置信度低时返回 `needs_confirmation`，前端应提示用户手动确认片段。

## 算法与模块概览

1. `core/pitch_renderer.py`：读取 `CorrectionPlan` 的 `target_f0_hz` / `shift_cents` / `low_confidence_frames`，仅对可信 voiced 区域做真实 pitch shift，并输出 `actual_pitch_shift_applied`、`mean_abs_shift_cents`、`skipped_frames`、`render_time_ms`、`warnings`。
2. `core/renderer.py`：保持旧调用兼容，委托给真实 pitch renderer。
3. `core/segment_locator.py`：用户只唱一小段时，用 VAD + chroma/RMS/onset + DTW 自动定位参考原曲片段。
4. `services/intelligent_assist.py`：AI 辅助编排层，当前使用轻量 fallback，预留 Silero、webrtcvad、torchcrepe、RMVPE、Basic Pitch、Demucs 接口。
5. `services/reference_providers/*`：统一第三方搜索 provider；Spotify / YouTube 禁止 import/download。
6. `app/routers/*`：API v1 路由，只做认证、上传持久化、搜索编排和任务编排，不放核心算法。

## 当前版本限制

- 第一版是 DSP / 算法辅助修音，不是完整神经网络 APC。
- AI 辅助模块第一版以接口和可替换 backend 为主，不强制安装大型模型。
- 自训练 APC 是长期规划，见 `docs/apc_training_plan.md`。
- 用户录音默认只用于本次任务，不自动进入训练集。
- 真实 renderer 是保守分段/帧计划驱动 DSP，后续仍需接入更高质量的专业 time/pitch 引擎。

## 旧 CLI

```bash
python -m jobs.batch_export --manifest examples/demo_manifest.json
```

## 测试

```bash
pytest -q
```

## License Risk Notes

商业分发前需要重新检查依赖、二进制和模型许可证。Rubber Band 可能涉及 GPL/商业授权；Demucs/Spleeter 代码与模型权重也需要单独审查。
