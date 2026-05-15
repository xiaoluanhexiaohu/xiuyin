from pathlib import Path


def test_reference_search_module_is_above_reference_upload():
    html = Path("templates/simple_upload.html").read_text(encoding="utf-8")
    assert "搜索原唱音乐" in html
    assert 'placeholder="输入歌曲名或歌手名"' in html
    assert html.index("搜索原唱音乐") < html.index("原唱音频")
    for source in ["jamendo", "freesound", "spotify", "youtube"]:
        assert f'value="{source}"' in html


def test_reference_search_javascript_calls_only_compliant_apis():
    js = Path("static/simple_upload.js").read_text(encoding="utf-8")
    assert "/api/v1/reference/search" in js
    assert "/api/v1/reference/import" in js
    assert "该平台仅支持搜索展示，不支持后台导入音频" in js
    assert "导入作为原唱" in js
    forbidden = ["yt-dlp", "youtube-dl", "pytube", "spotify download"]
    lowered = js.lower()
    for term in forbidden:
        assert term not in lowered


def test_reference_search_fetch_omits_bearer_token():
    js = Path("static/simple_upload.js").read_text(encoding="utf-8")
    search_block = js[js.index("async function searchReferenceMusic"):js.index("function renderReferenceResults")]
    assert "/api/v1/reference/search" in search_block
    assert "Authorization" not in search_block
    assert "CONFIG_MISSING" in js
    assert "第三方音乐 API 未配置，请检查 .env 配置" in js
    assert "REFERENCE_SEARCH_FAILED" in js
    assert "音乐搜索失败，请稍后重试" in js
