"""Checagens do frontend que rodam no Node (pulam se o Node não estiver instalado)."""

import json
import shutil
import subprocess
from pathlib import Path

import pytest

UTIL = (Path(__file__).resolve().parent.parent / 'frontend' / 'static' / 'js' / 'util.js').as_uri()
NODE = shutil.which('node')


def format_text(text):
    script = (
        "globalThis.document = { getElementById: () => null };"
        f"const {{ formatText }} = await import({json.dumps(UTIL)});"
        f"process.stdout.write(formatText({json.dumps(text)}));"
    )
    out = subprocess.run([NODE, '--input-type=module', '-e', script],
                         capture_output=True, text=True, encoding='utf-8', check=True)
    return out.stdout


@pytest.mark.skipif(not NODE, reason='Node não instalado')
def test_curly_quotes_get_dialogue_highlight():
    assert format_text('“oi”') == '<span class="dialogue">“oi”</span>'
    assert format_text('"oi"') == '<span class="dialogue">&quot;oi&quot;</span>'


@pytest.mark.skipif(not NODE, reason='Node não instalado')
def test_curly_quotes_keep_escaping():
    html = format_text('“<img src=x onerror=alert(1)>”')
    assert '<img' not in html and '&lt;img' in html
