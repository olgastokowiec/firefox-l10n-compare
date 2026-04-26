# firefox-l10n-compare

Generates an HTML dashboard showing translation completeness for Firefox localizations. For each configured locale it reports string and word-level coverage, a breakdown by component, and a list of missing strings with links to the English source on GitHub.

## How it works

The tool clones (or updates) two Mozilla repos:
- [firefox-l10n-source](https://github.com/mozilla-l10n/firefox-l10n-source) — the English source strings
- [firefox-l10n](https://github.com/mozilla-l10n/firefox-l10n) — the translated files for all locales

It then compares string IDs present in the source against those in each target locale and renders an HTML report with Plotly charts.

## Setup

### 1. Install Git

Git is used to download the project and the Firefox translation files.

- **Mac:** Open Terminal and run `git --version`. If it's not installed, macOS will prompt you to install it.
- **Windows:** Download and install from [git-scm.com](https://git-scm.com/download/win).
- **Linux:** Run `sudo apt install git` (Debian/Ubuntu) or `sudo dnf install git` (Fedora).

### 2. Install uv

uv manages the Python environment for this project.

- **Mac/Linux:** Open Terminal and run:
  ```
  curl -LsSf https://astral.sh/uv/install.sh | sh
  ```
- **Windows:** Open PowerShell and run:
  ```
  powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"
  ```

After installing, close and reopen your terminal.

### 3. Clone this repo

In your terminal, navigate to the folder where you want to keep the project, then run:

```
git clone https://github.com/olgastokowiec/firefox-l10n-compare.git
cd firefox-l10n-compare
```

### 4. Install dependencies

```
uv sync
```

This sets up a local Python environment with everything the tool needs. You only need to do this once.

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
