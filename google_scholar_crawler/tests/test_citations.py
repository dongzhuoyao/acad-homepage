"""Network-free integrity and endpoint compatibility checks."""
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

import yaml

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import collector
import main

ID = 'EchdyZEAAAAJ'


def page(key='paper', count='12', more=False, author=ID):
    return f'''<div id="gsc_prf_i"><div id="gsc_prf_in">Vincent Tao Hu</div>
    <div class="gsc_prf_il">HUST</div>
    <div id="gsc_prf_ivh">Verified email at lmu.de - <a class="gsc_prf_ila" href="http://taohu.me/">Homepage</a></div>
    <div id="gsc_prf_int"><a>generative modeling</a></div></div>
    <img id="gsc_prf_pup-img" src="https://example.org/profile.png">
    <table id="gsc_rsb_st"><tbody>
    <tr><td>Citations</td><td class="gsc_rsb_std">1,781</td><td class="gsc_rsb_std">1,725</td></tr>
    <tr><td>h-index</td><td class="gsc_rsb_std">18</td><td class="gsc_rsb_std">18</td></tr>
    <tr><td>i10-index</td><td class="gsc_rsb_std">25</td><td class="gsc_rsb_std">24</td></tr></tbody></table>
    <div id="gsc_rsb_cit"><span class="gsc_g_t">2025</span><span class="gsc_g_al">540</span></div>
    <table><tbody id="gsc_a_b"><tr class="gsc_a_tr"><td><a class="gsc_a_at" href="/citations?citation_for_view={author}:{key}">Paper title</a></td>
    <td><a class="gsc_a_ac" href="/scholar?cites=123,456">{count}</a></td><td class="gsc_a_y">2026</td></tr></tbody></table>
    <button id="gsc_bpf_more" {'' if more else 'disabled'}>Show more</button>'''


class CitationTests(unittest.TestCase):
    def test_true_zero_and_comma_separated_total(self):
        data = collector.fetch_citations(ID, fetch=lambda _: page(count=''))
        self.assertEqual(data['summary']['total_citations'], 1781)
        self.assertEqual(data['papers'][ID + ':paper']['citations'], 0)

    def test_wrong_profile_rejected(self):
        with self.assertRaises(ValueError):
            collector.parse_page(page(author='wrong_author'), ID)

    def test_blocked_and_malformed_pages_rejected(self):
        for html in ['<p>Access denied</p>', page().replace('gsc_bpf_more', 'missing'), page(count='unknown')]:
            with self.subTest(html=html), self.assertRaises(ValueError):
                collector.parse_page(html, ID)

    def test_all_pages_collected(self):
        pages = iter([page('first', more=True), page('last')])
        data = collector.fetch_citations(ID, fetch=lambda _: next(pages), pause=lambda _: None)
        self.assertEqual(len(data['papers']), 2)

    def test_repeated_page_rejected(self):
        with self.assertRaises(ValueError):
            collector.fetch_citations(ID, fetch=lambda _: page(more=True), pause=lambda _: None)

    def test_changed_profile_rejected_during_pagination(self):
        pages = iter([page('first', more=True), page('last').replace('Vincent Tao Hu', 'Other Author')])
        with self.assertRaises(ValueError):
            collector.fetch_citations(ID, fetch=lambda _: next(pages), pause=lambda _: None)

    def test_legacy_endpoints_and_normalized_snapshot_agree(self):
        with tempfile.TemporaryDirectory() as directory:
            out = Path(directory)
            snapshot = main.update(ID, out, fetch=lambda _: page())
            author = json.loads((out / 'gs_data.json').read_text())
            badge = json.loads((out / 'gs_data_shieldsio.json').read_text())
            self.assertEqual(author['citedby'], 1781)
            self.assertEqual(author['publications'][ID + ':paper']['num_citations'], 12)
            self.assertEqual(author['publications'][ID + ':paper']['author_pub_id'], ID + ':paper')
            self.assertEqual(author['publications'][ID + ':paper']['cites_id'], ['123', '456'])
            self.assertEqual(author['publications'][ID + ':paper']['bib']['pub_year'], '2026')
            self.assertEqual(badge, {'schemaVersion': 1, 'label': 'citations', 'message': '1781'})
            self.assertEqual(author['updated'], snapshot['metadata']['fetched_at'])
            self.assertEqual(yaml.safe_load((out / 'citations.yml').read_text()), snapshot)

    def test_legacy_profile_fields_preserved(self):
        snapshot = collector.fetch_citations(ID, fetch=lambda _: page())
        author = main.legacy_data(snapshot, [page()])
        self.assertEqual(author['hindex'], 18)
        self.assertEqual(author['i10index'], 25)
        self.assertEqual(author['citedby5y'], 1725)
        self.assertEqual(author['hindex5y'], 18)
        self.assertEqual(author['i10index5y'], 24)
        self.assertEqual(author['cites_per_year'], {'2025': 540})
        self.assertEqual(author['affiliation'], 'HUST')
        self.assertEqual(author['email_domain'], '@lmu.de')
        self.assertEqual(author['homepage'], 'http://taohu.me/')
        self.assertEqual(author['interests'], ['generative modeling'])

    def test_failed_or_partial_refresh_preserves_all_outputs(self):
        cases = [iter(['<p>Access denied</p>']), iter([page(more=True), '<p>Access denied</p>'])]
        for responses in cases:
            with self.subTest(responses=responses), tempfile.TemporaryDirectory() as directory:
                out = Path(directory)
                for name in ['gs_data.json', 'gs_data_shieldsio.json', 'citations.yml']:
                    (out / name).write_text('previous snapshot')
                with self.assertRaises(ValueError):
                    main.update(ID, out, fetch=lambda _: next(responses))
                self.assertTrue(all(p.read_text() == 'previous snapshot' for p in out.iterdir()))

    def test_connection_failure_preserves_output(self):
        with tempfile.TemporaryDirectory() as directory:
            out = Path(directory)
            (out / 'gs_data.json').write_text('previous snapshot')
            def fail(_): raise OSError('network unavailable')
            with self.assertRaises(OSError): main.update(ID, out, fetch=fail)
            self.assertEqual((out / 'gs_data.json').read_text(), 'previous snapshot')

    def test_malformed_history_preserves_output(self):
        with tempfile.TemporaryDirectory() as directory:
            out = Path(directory)
            (out / 'gs_data.json').write_text('previous snapshot')
            with self.assertRaises(ValueError):
                main.update(ID, out, fetch=lambda _: page().replace('gsc_g_al', 'missing'))
            self.assertEqual((out / 'gs_data.json').read_text(), 'previous snapshot')


if __name__ == '__main__':
    unittest.main()
