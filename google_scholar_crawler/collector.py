#!/usr/bin/env python3
"""Collect a public Scholar profile; only replace the cache after a complete fetch."""

from datetime import datetime, timezone
import re
import time
from urllib.parse import parse_qs, urlencode, urlsplit
from urllib.request import Request, urlopen

from bs4 import BeautifulSoup



def integer(text):
    text = text.strip().replace(',', '')
    if not re.fullmatch(r'\d+', text):
        raise ValueError(f'Invalid citation number: {text!r}')
    return int(text)


def parse_page(html, scholar_id):
    soup = BeautifulSoup(html, 'html.parser')
    name = soup.select_one('#gsc_prf_in')
    if name is None:
        raise ValueError('Scholar profile is unavailable (possibly a blocked request).')
    summary = {}
    metric_names = {'Citations': 'total_citations', 'h-index': 'h_index', 'i10-index': 'i10_index'}
    for row in soup.select('#gsc_rsb_st tbody tr'):
        label = row.select_one('td')
        cells = row.select('.gsc_rsb_std')
        if label and label.get_text(strip=True) in metric_names and cells:
            summary[metric_names[label.get_text(strip=True)]] = integer(cells[0].get_text())
    if set(summary) != set(metric_names.values()):
        raise ValueError('Missing Scholar summary metrics; refusing an incomplete snapshot.')
    papers = {}
    for row in soup.select('#gsc_a_b .gsc_a_tr'):
        title = row.select_one('.gsc_a_at')
        count = row.select_one('.gsc_a_ac')
        year = row.select_one('.gsc_a_y')
        if title is None or count is None:
            raise ValueError('Incomplete publication row.')
        params = parse_qs(urlsplit(title.get('href', '')).query)
        key = params.get('citation_for_view', [''])[0]
        if not key.startswith(scholar_id + ':') or not key.split(':', 1)[1]:
            raise ValueError('Publication belongs to a different Scholar profile.')
        # Scholar renders an empty citation cell for a verified zero-citation paper.
        raw_count = count.get_text(strip=True).replace('*', '').strip()
        papers[key] = {
            'title': title.get_text(' ', strip=True),
            'year': year.get_text(strip=True) if year else '',
            'citations': integer(raw_count) if raw_count else 0,
        }
    more = soup.select_one('#gsc_bpf_more')
    if more is None or not papers:
        raise ValueError('Missing publications or pagination control.')
    return name.get_text(' ', strip=True), summary, papers, not more.has_attr('disabled')


def fetch_citations(scholar_id, fetch=None, pause=time.sleep):
    if fetch is None:
        def fetch(url):
            request = Request(url, headers={'User-Agent': 'Mozilla/5.0', 'Accept-Language': 'en-US,en;q=0.9'})
            with urlopen(request, timeout=20) as response:
                return response.read()
    papers = {}
    name = None
    for start in range(0, 1000, 100):
        url = 'https://scholar.google.com/citations?' + urlencode({
            'user': scholar_id, 'hl': 'en', 'cstart': start, 'pagesize': 100,
        })
        page_name, summary, batch, has_more = parse_page(fetch(url), scholar_id)
        if name is not None and page_name != name:
            raise ValueError('Scholar profile changed during pagination.')
        if papers.keys() & batch.keys():
            raise ValueError('Repeated publication page; refusing a partial snapshot.')
        name = page_name
        papers.update(batch)
        if not has_more:
            return {
                'metadata': {
                    'scholar_user_id': scholar_id,
                    'author_name': name,
                    'source_url': 'https://scholar.google.com/citations?' + urlencode({'user': scholar_id, 'hl': 'en'}),
                    'last_updated': datetime.now(timezone.utc).date().isoformat(),
                    'fetched_at': datetime.now(timezone.utc).isoformat(timespec='seconds'),
                    'publication_count': len(papers),
                },
                'summary': summary,
                'papers': papers,
            }
        pause(2)
    raise ValueError('Pagination limit reached; existing data was not replaced.')

