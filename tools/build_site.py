#!/usr/bin/env python3
"""Build the public handbook as a sidebar-free GitHub Pages site."""
import html
import posixpath
import re
import shutil
import subprocess
from pathlib import Path
from urllib.parse import urlsplit, urlunsplit

import markdown
from markdown.extensions import Extension
from markdown.treeprocessors import Treeprocessor

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / '_site'
BASE = '/NX-Shield-RAG/'
REPO = 'https://github.com/ipccheng/NX-Shield-RAG/blob/main/'


def page_path(path):
    path = Path(path)
    return path.with_name('index.html') if path.name == 'README.md' else path.with_suffix('.html')


class SiteLinks(Treeprocessor):
    def run(self, root):
        for element in root.iter():
            for attribute in ('href', 'src'):
                value = element.get(attribute)
                if not value:
                    continue
                url = urlsplit(value)
                if url.scheme or url.netloc or not url.path:
                    continue
                target = posixpath.normpath(posixpath.join(self.md.source.parent.as_posix(), url.path))
                if target not in self.md.published:
                    element.set(attribute, REPO + target)
                else:
                    path = page_path(target).as_posix() if target.endswith('.md') else target
                    element.set(attribute, urlunsplit(('', '', BASE + path, url.query, url.fragment)))
        return root


class SiteExtension(Extension):
    def extendMarkdown(self, md):
        md.treeprocessors.register(SiteLinks(md), 'site_links', 5)


STYLE = '''
:root { color-scheme: light dark; --bg:#f8fafc; --fg:#17243b; --muted:#52647a; --line:#dbe3ed; --link:#1559b3; --code:#eaf0f7; }
@media(prefers-color-scheme:dark) { :root { --bg:#101923; --fg:#e5edf7; --muted:#a8b8cc; --line:#33445a; --link:#8bc0ff; --code:#1c2a3b; } }
* { box-sizing:border-box; } body { margin:0; background:var(--bg); color:var(--fg); font:17px/1.75 system-ui,sans-serif; }
header,main,footer { max-width:1000px; margin:auto; padding:24px; } header { border-bottom:1px solid var(--line); }
nav { display:flex; flex-wrap:wrap; gap:12px 24px; align-items:center; } nav strong { margin-right:auto; }
a { color:var(--link); text-underline-offset:3px; } h1,h2,h3 { line-height:1.25; letter-spacing:-.02em; scroll-margin-top:20px; }
h1 { font-size:2.4rem; } h2 { margin-top:2.2em; border-bottom:1px solid var(--line); padding-bottom:.3em; }
img,svg { max-width:100%; height:auto; } pre { overflow:auto; padding:20px; border-radius:8px; background:var(--code); font-size:.88em; }
code { background:var(--code); padding:.12em .3em; border-radius:3px; } pre code { padding:0; }
table { display:block; overflow:auto; border-collapse:collapse; max-width:100%; font-size:.9em; }
th,td { padding:10px 14px; border:1px solid var(--line); text-align:left; } blockquote { border-left:4px solid var(--link); margin-left:0; padding-left:20px; color:var(--muted); }
footer { color:var(--muted); font-size:.85em; border-top:1px solid var(--line); } .skip { position:absolute; left:-9999px; } .skip:focus { left:20px; }
@media(max-width:600px) { h1 { font-size:1.9rem; } header,main,footer { padding:18px; } }
'''


def build():
    tracked = subprocess.check_output(['git', 'ls-files', '-z'], cwd=ROOT).decode().split('\0')
    pages = [Path(p) for p in tracked if p.endswith('.md')]
    assets = [Path(p) for p in tracked if (p.startswith('diagrams/') and Path(p).suffix in {'.png', '.svg', '.mmd'}) or p.startswith('templates/')]
    published = {p.as_posix() for p in pages + assets}
    if OUT.exists():
        shutil.rmtree(OUT)
    OUT.mkdir()
    (OUT / '.nojekyll').touch()
    (OUT / 'style.css').write_text(STYLE)
    for asset in assets:
        dest = OUT / asset
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(ROOT / asset, dest)
    for source in pages:
        text = (ROOT / source).read_text()
        heading = re.search(r'^# (.+)$', text, re.M)
        title = heading.group(1) if heading else source.stem
        md = markdown.Markdown(extensions=['tables', 'fenced_code', 'toc', SiteExtension()])
        md.source, md.published = source, published
        body = md.convert(text)
        body = re.sub(r'<pre><code class="language-mermaid">(.*?)</code></pre>', r'<pre class="mermaid">\1</pre>', body, flags=re.S)
        document = f'''<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>{html.escape(title)} | NX-Shield RAG</title><link rel="stylesheet" href="{BASE}style.css"></head>
<body><a class="skip" href="#content">Skip to content</a><header><nav aria-label="Main navigation">
<strong>NX-Shield RAG</strong><a href="{BASE}">Home</a><a href="{BASE}docs/index.html">Handbook</a><a href="https://github.com/ipccheng/NX-Shield-RAG">GitHub</a>
</nav></header><main id="content">{body}</main><footer>Independent engineering handbook · Not an official Nutanix product or validated design.<br>
<a href="{REPO}{source.as_posix()}">View this page on GitHub</a></footer>
<script type="module">import mermaid from 'https://cdn.jsdelivr.net/npm/mermaid@11.12.0/dist/mermaid.esm.min.mjs'; mermaid.initialize({{startOnLoad:true,securityLevel:'strict'}});</script>
</body></html>'''
        dest = OUT / page_path(source)
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_text(document)
    print(f'Built {len(pages)} pages and {len(assets)} assets in _site')


if __name__ == '__main__':
    build()
