"""Collect Scholar citations and preserve the existing JSON endpoint contract."""

import argparse
import json
import os
from pathlib import Path
import re
import sys
from urllib.parse import parse_qs, urljoin, urlsplit
from urllib.request import Request, urlopen

from bs4 import BeautifulSoup
import yaml

from collector import fetch_citations, integer


def legacy_data(snapshot, pages):
    """Keep the fields used by AcadHomepage and existing Shields badges."""
    soup = BeautifulSoup(pages[0], 'html.parser')
    metadata, summary = snapshot['metadata'], snapshot['summary']
    data = {
        'container_type': 'Author',
        'filled': ['basics', 'publications', 'indices', 'counts'],
        'scholar_id': metadata['scholar_user_id'],
        'source': 'AUTHOR_PROFILE_PAGE',
        'name': metadata['author_name'],
        'citedby': summary['total_citations'],
        'hindex': summary['h_index'],
        'i10index': summary['i10_index'],
        'updated': metadata['fetched_at'],
        'metadata': metadata,
        'publications': {},
    }
    recent_keys = {'Citations': 'citedby5y', 'h-index': 'hindex5y', 'i10-index': 'i10index5y'}
    for row in soup.select('#gsc_rsb_st tbody tr'):
        label = row.select_one('td').get_text(strip=True)
        cells = row.select('.gsc_rsb_std')
        if label in recent_keys and len(cells) > 1:
            data[recent_keys[label]] = integer(cells[1].get_text())
    picture = soup.select_one('#gsc_prf_pup-img')
    if picture:
        data['url_picture'] = picture.get('src', '')
    affiliation = soup.select_one('#gsc_prf_i > .gsc_prf_il:not([id])')
    data['affiliation'] = affiliation.get_text(' ', strip=True) if affiliation else ''
    data['interests'] = [e.get_text(strip=True) for e in soup.select('#gsc_prf_int a')]
    contact = soup.select_one('#gsc_prf_ivh')
    if contact:
        match = re.search(r'Verified email at ([\w.-]+)', contact.get_text(' ', strip=True))
        data['email_domain'] = '@' + match[1] if match else ''
        homepage = contact.select_one('a.gsc_prf_ila')
        data['homepage'] = homepage.get('href', '') if homepage else ''
    years = soup.select('#gsc_rsb_cit .gsc_g_t')
    counts = soup.select('#gsc_rsb_cit .gsc_g_al')
    if len(years) != len(counts):
        raise ValueError('Incomplete citation history; previous results retained.')
    data['cites_per_year'] = {year.get_text(strip=True): integer(count.get_text())
                              for year, count in zip(years, counts)}
    for html in pages:
        for row in BeautifulSoup(html, 'html.parser').select('#gsc_a_b .gsc_a_tr'):
            title = row.select_one('.gsc_a_at')
            key = parse_qs(urlsplit(title['href']).query)['citation_for_view'][0]
            paper = snapshot['papers'][key]
            publication = {
                'container_type': 'Publication',
                'source': 'AUTHOR_PUBLICATION_ENTRY',
                'bib': {'title': paper['title'], 'pub_year': paper['year']},
                'filled': False,
                'author_pub_id': key,
                'num_citations': paper['citations'],
            }
            href = row.select_one('.gsc_a_ac').get('href', '')
            if href:
                publication['citedby_url'] = urljoin('https://scholar.google.com', href)
                ids = parse_qs(urlsplit(href).query).get('cites', [])
                publication['cites_id'] = ids[0].split(',') if ids else []
            data['publications'][key] = publication
    return data


def update(scholar_id, output, fetch=None):
    pages = []

    def capture(url):
        if fetch is not None:
            html = fetch(url)
        else:
            request = Request(url, headers={'User-Agent': 'Mozilla/5.0', 'Accept-Language': 'en-US,en;q=0.9'})
            with urlopen(request, timeout=20) as response:
                html = response.read()
        pages.append(html)
        return html

    snapshot = fetch_citations(scholar_id, fetch=capture)
    author = legacy_data(snapshot, pages)
    badge = {'schemaVersion': 1, 'label': 'citations', 'message': str(author['citedby'])}
    # Complete and serialize all outputs before touching any previous snapshot.
    payloads = {
        'gs_data.json': json.dumps(author, ensure_ascii=False, indent=2) + '\n',
        'gs_data_shieldsio.json': json.dumps(badge, ensure_ascii=False, indent=2) + '\n',
        'citations.yml': yaml.safe_dump(snapshot, allow_unicode=True, sort_keys=False),
    }
    output.mkdir(parents=True, exist_ok=True)
    for filename, content in payloads.items():
        (output / (filename + '.tmp')).write_text(content, encoding='utf-8')
    for filename in payloads:
        (output / (filename + '.tmp')).replace(output / filename)
    return snapshot


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--scholar-id', default=os.environ.get('GOOGLE_SCHOLAR_ID') or 'EchdyZEAAAAJ')
    parser.add_argument('--output-dir', type=Path, default=Path(__file__).parent / 'results')
    args = parser.parse_args()
    try:
        snapshot = update(args.scholar_id, args.output_dir)
    except Exception as error:
        print(f'Citation refresh failed; existing data retained: {error}', file=sys.stderr)
        return 1
    print(f"Collected {len(snapshot['papers'])} papers for {snapshot['metadata']['author_name']}: "
          f"{snapshot['summary']['total_citations']} total citations.")
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
