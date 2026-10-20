"""Exercise the real generated site and every local HTML link."""
import unittest
from html.parser import HTMLParser
from urllib.parse import unquote, urlsplit
import build_site


class Document(HTMLParser):
    def __init__(self, text):
        super().__init__()
        self.links, self.ids, self.tags = [], set(), []
        self.feed(text)

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        self.tags.append(tag)
        if 'id' in attrs:
            self.ids.add(attrs['id'])
        for key in ('href', 'src'):
            if key in attrs:
                self.links.append(attrs[key])


class SiteTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        build_site.build()
        cls.pages = {p: Document(p.read_text()) for p in build_site.OUT.rglob('*.html')}

    def test_navigation_and_no_sidebar(self):
        self.assertTrue((build_site.OUT / 'index.html').exists())
        self.assertTrue((build_site.OUT / 'docs/index.html').exists())
        for page, doc in self.pages.items():
            with self.subTest(page=page):
                self.assertIn('main', doc.tags)
                self.assertIn('nav', doc.tags)
                self.assertNotIn('aside', doc.tags)
                self.assertIn(build_site.BASE + 'docs/index.html', doc.links)

    def test_local_links_and_fragments(self):
        for page, doc in self.pages.items():
            for link in doc.links:
                url = urlsplit(link)
                if url.scheme or url.netloc:
                    continue
                with self.subTest(page=page, link=link):
                    if url.path:
                        self.assertTrue(url.path.startswith(build_site.BASE))
                        target = build_site.OUT / unquote(url.path[len(build_site.BASE):])
                        if target.is_dir():
                            target /= 'index.html'
                    else:
                        target = page
                    self.assertTrue(target.is_file(), str(target))
                    if url.fragment and target in self.pages:
                        self.assertIn(unquote(url.fragment), self.pages[target].ids)

    def test_only_publication_assets(self):
        self.assertFalse((build_site.OUT / '.git').exists())
        self.assertFalse((build_site.OUT / 'tools').exists())
        self.assertTrue((build_site.OUT / 'diagrams/rag-query-path.png').exists())


if __name__ == '__main__':
    unittest.main()
