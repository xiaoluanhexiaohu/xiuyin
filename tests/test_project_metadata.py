from pathlib import Path


def test_required_project_files_exist():
    for path in ["AGENTS.md", "README.md", "pyproject.toml", "requirements.txt", "examples/demo_manifest.json"]:
        assert Path(path).exists()
