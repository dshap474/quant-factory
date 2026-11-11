# sec-edgar-client

Thin client for SEC EDGAR JSON and bulk download endpoints.

## Fund holdings data sets (DERA)

Keyless page scrapes of the SEC DERA structured data set pages. Each family has the
same four methods; `list_*` returns absolute zip URLs newest first, and `download_*`
validates the URL is on the configured SEC HTTPS host before fetching (bytes returned).
Use `download_archive_if_modified(url, last_modified=...)` for conditional GETs.

| Family | Page | Methods |
| --- | --- | --- |
| Form N-PORT (quarterly fund/ETF holdings) | `/data-research/sec-markets-data/form-n-port-data-sets` | `form_nport_data_sets_page_url`, `list_form_nport_data_set_urls`, `latest_form_nport_data_set_url`, `download_form_nport_data_set_zip(url)` |
| Form N-MFP (monthly money market fund holdings) | `/data-research/sec-markets-data/dera-form-n-mfp-data-sets` | `form_nmfp_*` equivalents |
| Form N-CEN (quarterly fund census) | `/data-research/sec-markets-data/form-n-cen-data-sets` | `form_ncen_*` equivalents |

The N-PORT zips are multi-GB. SEC requires a descriptive `User-Agent` with contact
info and caps traffic at 10 requests/second. The default `user_agent` is a placeholder;
pass your own organization and contact address.

```python
from sec_edgar_client import SECEdgarClient

with SECEdgarClient(user_agent="my-org research me@example.com") as sec:
    url = sec.latest_form_nport_data_set_url()
    payload, stamp = sec.download_archive_if_modified(url)
```

Live smoke (lists URLs only): `SEC_LIVE=1 SEC_USER_AGENT="name email@example.com" uv run pytest packages/platform/clients/sec-edgar-client -m live -q`
