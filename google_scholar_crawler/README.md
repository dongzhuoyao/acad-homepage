# Citation collector

The collector on `main` reads the public Google Scholar profile and publishes a
complete snapshot to `google-scholar-stats`. It uses the validated parser from
the Tao Hu website collector and does not require `scholarly` or `bibtexparser`.

The existing endpoints remain compatible:

- `gs_data.json`: `citedby`, `publications[author_pub_id].num_citations`, profile
  details, indices, annual counts, and an `updated` UTC timestamp.
- `gs_data_shieldsio.json`: the original Shields endpoint schema.
- `citations.yml`: the normalized snapshot used by the new website collector.

Run locally from the repository root:

```sh
python3 -m pip install -r google_scholar_crawler/requirements.txt
python3 -m unittest discover -s google_scholar_crawler/tests -v
python3 google_scholar_crawler/main.py --scholar-id EchdyZEAAAAJ
```

The default output directory is `google_scholar_crawler/results/`. Override it
with `--output-dir`. The Scholar ID can also be supplied through the existing
`GOOGLE_SCHOLAR_ID` environment variable; the default is Tao Hu's public ID.

GitHub Actions tests every collector change and collects on pushes to `main`,
manual workflow runs, and the existing daily schedule (16:00 China time).
Pull requests only run the tests. The workflow checks out the existing stats
branch and appends a commit without force pushing. A blocked request, malformed
page, wrong profile, or incomplete pagination fails the run before publication,
so the branch and the previous successful update date remain unchanged.

Scholar can block requests from GitHub runners. This collector does not bypass
CAPTCHAs or use proxies. In that case, a successful local collection can be
committed to the stats branch; do not replace real data with zero counts.
