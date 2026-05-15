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
