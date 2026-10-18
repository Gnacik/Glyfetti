import importlib.util
import sys

import pytest

from glyfetti.cli import main
from glyfetti.mcp_server import artifact_path


@pytest.mark.skipif(sys.version_info >= (3, 11) and importlib.util.find_spec('mcp') is not None,
                    reason='MCP is available; the protocol tests exercise startup instead')
def test_cli_reports_optional_runtime_requirement(capsys):
    assert main(['mcp']) == 2
    message = capsys.readouterr().err
    assert 'Python 3.11' in message or 'optional MCP extra' in message


@pytest.mark.parametrize('export_id,filename', [
    ('../outside', 'style.json'), ('a' * 31, 'style.json'), ('A' * 32, 'style.json'),
    ('a' * 32, '../outside.json'), ('a' * 32, 'other.txt'),
])
def test_artifact_paths_reject_unknown_names_and_traversal(tmp_path, export_id, filename):
    with pytest.raises(ValueError, match='Unknown export artifact'):
        artifact_path(tmp_path, export_id, filename)


def test_artifact_paths_require_a_real_export(tmp_path):
    with pytest.raises(ValueError, match='does not exist'):
        artifact_path(tmp_path, 'a' * 32, 'title.png')


def test_export_artifacts_cannot_follow_symlinks_outside_their_folder(tmp_path):
    folder = tmp_path / 'exports' / ('a' * 32)
    folder.mkdir(parents=True)
    outside = tmp_path / 'outside.json'
    outside.write_text('outside export directory', 'utf-8')
    try:
        (folder / 'style.json').symlink_to(outside)
    except OSError:
        pytest.skip('Creating symlinks requires privileges on this system')
    with pytest.raises(ValueError, match='outside the configured'):
        artifact_path(tmp_path / 'exports', 'a' * 32, 'style.json')
