# firefox-l10n-compare

Generates an HTML dashboard showing translation completeness for Firefox localizations. For each configured locale it reports string and word-level coverage, a breakdown by component, and a list of missing strings with links to the English source on GitHub.

## How it works

The tool clones (or updates) two Mozilla repos:
- [firefox-l10n-source](https://github.com/mozilla-l10n/firefox-l10n-source) — the English source strings
- [firefox-l10n](https://github.com/mozilla-l10n/firefox-l10n) — the translated files for all locales

It then compares string IDs present in the source against those in each target locale and renders an HTML report with Plotly charts.

## Setup

Requires Python 3.11+ and [uv](https://github.com/astral-sh/uv).

```
uv sync
```

## Configuration

Edit `config.toml` to set the locales and release channel:

```toml
[comparison]
channel = "release"           # main | beta | release | esr140 | esr115
target_locales = ["bn", "de", "pl"]
```

## Run

```
uv run compare
```

The report is written to `output/report.html` and opened in your browser automatically.

To skip re-fetching the repos (use cached copies):

```
uv run compare --no-fetch
```
