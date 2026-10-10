#!/usr/bin/env python3
"""Offline handbook checks; not a RAG runtime or security certification."""
import argparse
import ast
import re
import subprocess
import sys
import xml.etree.ElementTree as ET
from pathlib import Path
from urllib.parse import unquote, urlsplit

TEXT_SUFFIXES = {'.md', '.mmd', '.svg', '.py', '.yaml', '.yml', '.json', '.mjs', '.txt'}
# Deliberately heuristic: review still must assess rights, images and claims.
HAZARDS = {
    'personal home path': r'/(?:Users|home)/[A-Za-z0-9_.-]+/',
    'private IPv4 address': r'\b(?:10(?:\.\d{1,3}){3}|192\.168(?:\.\d{1,3}){2}|172\.(?:1[6-9]|2\d|3[01])(?:\.\d{1,3}){2})\b',
    'private hostname': r'\b[\w-]+\.(?:local|internal)\b',
    'access token': r'\b(?:gh[pousr]_[A-Za-z0-9]{20,}|github_pat_[A-Za-z0-9_]{20,})\b',
    'private key': r'-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----',
}


def repository_files(root):
    result = subprocess.run(['git', 'ls-files', '-z', '--cached', '--others', '--exclude-standard'],
                            cwd=root, check=True, capture_output=True)
    return sorted({Path(p.decode()) for p in result.stdout.split(b'\0') if p})


def prose_and_fences(text, language_filter="mermaid"):
    """Return non-fenced prose, Mermaid bodies, and unclosed fence status."""
    prose, diagrams, body = [], [], []
    fence = None
    language = ''
    for line in text.splitlines():
        match = re.match(r'^ {0,3}(`{3,}|~{3,})(.*)$', line)
        if fence is None and match:
            fence, language, body = match[1], match[2].strip(), []
        elif fence and re.fullmatch(r' {0,3}' + re.escape(fence[0]) + '{' + str(len(fence)) + r',}\s*', line):
            if language == language_filter:
                diagrams.append('\n'.join(body))
            fence = None
        elif fence:
            body.append(line)
        else:
            prose.append(line)
    return '\n'.join(prose), diagrams, fence is not None


def anchors(text):
    result, seen = set(), {}
    prose, _, _ = prose_and_fences(text)
    for title in re.findall(r'^ {0,3}#{1,6}\s+(.+?)\s*#*$', prose, re.M):
        slug = re.sub(r'[^\w\- ]', '', title.lower()).replace(' ', '-')
        count = seen.get(slug, 0)
        seen[slug] = count + 1
        result.add(slug if count == 0 else f'{slug}-{count}')
    return result


def links(text):
    # Repository style: inline Markdown and reference definitions; no raw HTML.
    prose, _, _ = prose_and_fences(text)
    return re.findall(r'\]\(<?([^\s)>]+)>?(?:\s+"[^"]*")?\)', prose) + re.findall(
        r'^ {0,3}\[[^\]]+\]:\s*<?([^\s>]+)>?', prose, re.M)


def validate(root, paths, syntax=True):
    errors = []
    root = root.resolve()
    path_set = set(paths)
    for relative in paths:
        file = root / relative
        if file.is_symlink():
            errors.append(f'{relative}: symlinks are not publication inputs')
            continue
        if not file.is_file():
            errors.append(f'{relative}: missing file')
            continue
        if file.suffix not in TEXT_SUFFIXES:
            continue
        try:
            text = file.read_text(encoding='utf-8')
        except UnicodeError:
            errors.append(f'{relative}: invalid UTF-8')
            continue
        for name, pattern in HAZARDS.items():
            if re.search(pattern, text, re.I):
                errors.append(f'{relative}: publication hazard: {name}')
        if file.suffix == '.md':
            _, _, unclosed = prose_and_fences(text)
            if unclosed:
                errors.append(f'{relative}: unclosed code fence')
            for target in links(text):
                url = urlsplit(target)
                if url.scheme in {'https', 'http', 'mailto'}:
                    continue
                if url.scheme or url.netloc:
                    errors.append(f'{relative}: unsupported link scheme: {target}')
                    continue
                destination = (file.parent / unquote(url.path)).resolve() if url.path else file
                if not destination.is_relative_to(root):
                    errors.append(f'{relative}: link escapes repository: {target}')
                elif not destination.is_file() or destination.relative_to(root) not in path_set:
                    errors.append(f'{relative}: missing/unpublished target: {target}')
                elif url.fragment and destination.suffix == '.md':
                    if unquote(url.fragment) not in anchors(destination.read_text()):
                        errors.append(f'{relative}: missing heading: {target}')
            if relative.parts[0] == 'docs' and relative != Path('docs/README.md'):
                if '[Documentation index](../README.md)' not in text:
                    errors.append(f'{relative}: missing return navigation')
                index = root / 'docs/README.md'
                if index.exists() and relative.relative_to('docs').as_posix() not in index.read_text():
                    errors.append(f'{relative}: not listed in documentation index')
        if syntax:
            try:
                if file.suffix == '.md':
                    for language in ('yaml', 'yml'):
                        for block in prose_and_fences(text, language)[1]:
                            import yaml
                            list(yaml.safe_load_all(block))
                elif file.suffix == '.py':
                    ast.parse(text, filename=str(relative))
                elif file.suffix in {'.yaml', '.yml'}:
                    import yaml
                    list(yaml.safe_load_all(text))
                elif file.suffix == '.svg':
                    ET.fromstring(text)
            except (SyntaxError, ValueError, ET.ParseError) as exc:
                errors.append(f'{relative}: syntax: {exc}')
            except ImportError:
                errors.append(f'{relative}: install PyYAML to validate YAML')
            except Exception as exc:
                errors.append(f'{relative}: parser: {type(exc).__name__}: {exc}')
    canonical = root / 'diagrams/rag-query-path.png'
    compatibility = root / 'diagrams/sample-query-path-vcf-aos.png'
    if canonical.exists() and compatibility.exists() and canonical.read_bytes() != compatibility.read_bytes():
        errors.append('diagrams: compatibility PNG differs from canonical PNG')
    return errors


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', type=Path, default=Path(__file__).resolve().parents[1])
    args = parser.parse_args()
    paths = repository_files(args.root)
    errors = validate(args.root, paths)
    for error in errors:
        print(error, file=sys.stderr)
    print(f'Documentation checks: {len(paths)} files, {len(errors)} errors')
    return bool(errors)


if __name__ == '__main__':
    sys.exit(main())
