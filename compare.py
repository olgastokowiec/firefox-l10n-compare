#!/usr/bin/env python3
"""Firefox L10n completeness dashboard generator."""

import argparse
import json
import re
import subprocess
import sys
import tomllib
import webbrowser
from collections import defaultdict
from datetime import datetime
from pathlib import Path

import plotly.graph_objects as go
from jinja2 import Environment, FileSystemLoader

GITHUB_SOURCE_BASE = "https://github.com/mozilla-l10n/firefox-l10n-source/blob/main"


# ---------------------------------------------------------------------------
# Repo management
# ---------------------------------------------------------------------------

def clone_or_update(url: str, dest: Path, no_fetch: bool) -> None:
    if dest.exists():
        if not no_fetch:
            print(f"  Updating {dest.name}...")
            subprocess.run(
                ["git", "-C", str(dest), "pull", "--ff-only", "--quiet"],
                check=True,
            )
        else:
            print(f"  Using cached {dest.name}")
    else:
        print(f"  Cloning {url}...")
        dest.parent.mkdir(parents=True, exist_ok=True)
        subprocess.run(
            ["git", "clone", "--depth=1", "--quiet", url, str(dest)],
            check=True,
        )


# ---------------------------------------------------------------------------
# Source inventory
# ---------------------------------------------------------------------------

def load_inventory(source_repo: Path, channel: str) -> dict[str, list[str]]:
    """Return {filepath: [string_id, ...]} for all translatable strings in the channel."""
    data_file = source_repo / "_data" / f"{channel}.json"
    with open(data_file) as f:
        data = json.load(f)
    # FTL terms (IDs starting with -) are brand names and are never translated
    return {
        filepath: [sid for sid in ids if not sid.startswith("-")]
        for filepath, ids in data.items()
        if any(not sid.startswith("-") for sid in ids)
    }


# ---------------------------------------------------------------------------
# File parsing
# ---------------------------------------------------------------------------

def parse_source_file(path: Path, ext: str) -> dict[str, tuple[int, str]]:
    """Return {string_id: (line_number, english_value)} for a source file."""
    result: dict[str, tuple[int, str]] = {}
    try:
        lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
    except FileNotFoundError:
        return result

    if ext == "ftl":
        i = 0
        while i < len(lines):
            line = lines[i]
            m = re.match(r"^([a-zA-Z][a-zA-Z0-9_-]*)\s*=\s*(.*)", line)
            if m:
                msg_id = m.group(1)
                line_num = i + 1
                parts = [m.group(2)]
                i += 1
                # Collect indented continuation lines (value body + attributes)
                while i < len(lines) and (lines[i].startswith("    ") or lines[i].startswith("\t")):
                    stripped = lines[i].strip()
                    if stripped and not stripped.startswith("#"):
                        attr_m = re.match(r"^\.[a-zA-Z][a-zA-Z0-9-]*\s*=\s*(.*)", stripped)
                        if attr_m:
                            # Attribute value (e.g. .label = Close tab)
                            parts.append(attr_m.group(1))
                        elif not stripped.startswith("."):
                            parts.append(stripped)
                    i += 1
                result[msg_id] = (line_num, " ".join(p for p in parts if p))
            else:
                i += 1

    elif ext == "properties":
        # Keys can be alphanumeric (including pure-numeric like "1", "2")
        for i, line in enumerate(lines, 1):
            m = re.match(r"^([a-zA-Z0-9][a-zA-Z0-9_.-]*)\s*=\s*(.*)", line)
            if m:
                result[m.group(1)] = (i, m.group(2).strip())

    elif ext == "ini":
        # Inventory uses Section.Key notation, so we track the current section
        current_section = ""
        for i, line in enumerate(lines, 1):
            sec_m = re.match(r"^\[([^\]]+)\]", line)
            if sec_m:
                current_section = sec_m.group(1)
                continue
            kv_m = re.match(r"^([a-zA-Z][a-zA-Z0-9_.]*)\s*=\s*(.*)", line)
            if kv_m:
                key = f"{current_section}.{kv_m.group(1)}" if current_section else kv_m.group(1)
                result[key] = (i, kv_m.group(2).strip())

    return result


def parse_locale_ids(path: Path, ext: str) -> set[str]:
    """Return the set of string IDs present in a locale file."""
    ids: set[str] = set()
    try:
        lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
    except FileNotFoundError:
        return ids

    if ext == "ftl":
        for line in lines:
            m = re.match(r"^([a-zA-Z][a-zA-Z0-9_-]*)\s*=", line)
            if m:
                ids.add(m.group(1))
    elif ext == "properties":
        for line in lines:
            m = re.match(r"^([a-zA-Z0-9][a-zA-Z0-9_.-]*)\s*=", line)
            if m:
                ids.add(m.group(1))
    elif ext == "ini":
        current_section = ""
        for line in lines:
            sec_m = re.match(r"^\[([^\]]+)\]", line)
            if sec_m:
                current_section = sec_m.group(1)
                continue
            kv_m = re.match(r"^([a-zA-Z][a-zA-Z0-9_.]*)\s*=", line)
            if kv_m:
                key = f"{current_section}.{kv_m.group(1)}" if current_section else kv_m.group(1)
                ids.add(key)

    return ids


# ---------------------------------------------------------------------------
# Word counting
# ---------------------------------------------------------------------------

def count_words(text: str) -> int:
    """Count human-readable words in an English source string."""
    text = re.sub(r"\{[^}]*\}", " ", text)   # FTL placeholders: { $var }, { -term }
    text = re.sub(r"<[^>]+>", " ", text)     # HTML tags
    text = re.sub(r"&[a-zA-Z]+;", " ", text) # HTML entities
    text = re.sub(r"\s+", " ", text).strip()
    return len(text.split()) if text else 0


# ---------------------------------------------------------------------------
# Locale analysis
# ---------------------------------------------------------------------------

def analyze_locale(
    locale: str,
    target_repo: Path,
    source_repo: Path,
    inventory: dict[str, list[str]],
) -> dict:
    total_strings = 0
    translated = 0
    missing: list[dict] = []
    by_component: dict[str, dict] = defaultdict(lambda: {"total": 0, "translated": 0})
    total_source_words = 0
    missing_word_count = 0

    for filepath, string_ids in inventory.items():
        component = filepath.split("/")[0]
        ext = filepath.rsplit(".", 1)[-1]

        source_data = parse_source_file(source_repo / filepath, ext)
        locale_ids = parse_locale_ids(target_repo / locale / filepath, ext)

        file_total = len(string_ids)
        total_strings += file_total
        by_component[component]["total"] += file_total

        for sid in string_ids:
            line_num, value_text = source_data.get(sid, (None, ""))
            wc = count_words(value_text)
            total_source_words += wc

            if sid in locale_ids:
                translated += 1
                by_component[component]["translated"] += 1
            else:
                missing_word_count += wc
                github_url = f"{GITHUB_SOURCE_BASE}/{filepath}"
                if line_num:
                    github_url += f"#L{line_num}"
                missing.append({
                    "file": filepath,
                    "string_id": sid,
                    "source_line": line_num,
                    "word_count": wc,
                    "github_url": github_url,
                })

    missing.sort(key=lambda x: (x["file"], x["string_id"]))

    completeness_pct = round(100 * translated / total_strings, 1) if total_strings else 0.0
    translated_words = total_source_words - missing_word_count
    word_completeness_pct = (
        round(100 * translated_words / total_source_words, 1) if total_source_words else 0.0
    )

    return {
        "total_strings": total_strings,
        "translated": translated,
        "missing_count": len(missing),
        "missing": missing,
        "by_component": dict(by_component),
        "total_source_words": total_source_words,
        "missing_word_count": missing_word_count,
        "translated_words": translated_words,
        "completeness_pct": completeness_pct,
        "word_completeness_pct": word_completeness_pct,
    }


# ---------------------------------------------------------------------------
# Chart generation
# ---------------------------------------------------------------------------

def _pct_color(pct: float) -> str:
    if pct >= 90:
        return "#27ae60"
    if pct >= 70:
        return "#f39c12"
    return "#e74c3c"


def make_overall_chart(results: dict, locale_names: dict[str, str]) -> str:
    locales = list(results.keys())
    labels = [locale_names.get(l, l) for l in locales]
    pcts = [results[l]["completeness_pct"] for l in locales]
    missing_pcts = [round(100 - p, 1) for p in pcts]

    fig = go.Figure()
    fig.add_trace(go.Bar(
        name="Translated",
        y=labels,
        x=pcts,
        orientation="h",
        marker_color=[_pct_color(p) for p in pcts],
        text=[f"{p}%" for p in pcts],
        textposition="inside",
        insidetextanchor="middle",
    ))
    fig.add_trace(go.Bar(
        name="Missing",
        y=labels,
        x=missing_pcts,
        orientation="h",
        marker_color="#dfe6e9",
        text=[f"{p}%" if p > 2 else "" for p in missing_pcts],
        textposition="inside",
        insidetextanchor="middle",
    ))
    fig.update_layout(
        barmode="stack",
        title_text="Overall Translation Completeness (string count)",
        xaxis=dict(title="Percentage", range=[0, 100]),
        height=max(200, 80 * len(locales) + 80),
        margin=dict(l=10, r=20, t=50, b=40),
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
        plot_bgcolor="white",
        paper_bgcolor="white",
    )
    return fig.to_html(full_html=False, include_plotlyjs=False)


def make_component_chart(results: dict, locale_names: dict[str, str]) -> str:
    locales = list(results.keys())
    all_components = sorted({
        comp
        for r in results.values()
        for comp in r["by_component"]
    })
    colors = ["#3498db", "#e74c3c", "#2ecc71", "#f39c12", "#9b59b6", "#1abc9c"]

    fig = go.Figure()
    for idx, locale in enumerate(locales):
        label = locale_names.get(locale, locale)
        comp_data = results[locale]["by_component"]
        pcts = []
        for comp in all_components:
            d = comp_data.get(comp, {"total": 0, "translated": 0})
            pct = round(100 * d["translated"] / d["total"], 1) if d["total"] else 0.0
            pcts.append(pct)
        fig.add_trace(go.Bar(
            name=label,
            x=all_components,
            y=pcts,
            marker_color=colors[idx % len(colors)],
            text=[f"{p}%" for p in pcts],
            textposition="outside",
        ))

    fig.update_layout(
        barmode="group",
        title_text="Translation Completeness by Component",
        yaxis=dict(title="% Translated", range=[0, 112]),
        height=480,
        margin=dict(l=10, r=20, t=50, b=80),
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
        plot_bgcolor="white",
        paper_bgcolor="white",
    )
    return fig.to_html(full_html=False, include_plotlyjs=False)


# ---------------------------------------------------------------------------
# HTML rendering
# ---------------------------------------------------------------------------

def render_html(
    results: dict,
    locale_names: dict[str, str],
    config: dict,
    overall_chart: str,
    component_chart: str,
) -> str:
    template_path = Path(__file__).parent / "template.html"
    env = Environment(
        loader=FileSystemLoader(str(template_path.parent)),
        autoescape=False,
    )
    template = env.get_template(template_path.name)
    return template.render(
        results=results,
        locale_names=locale_names,
        config=config,
        overall_chart=overall_chart,
        component_chart=component_chart,
        generated_at=datetime.now().strftime("%Y-%m-%d %H:%M"),
        locales=list(results.keys()),
    )


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(description="Generate Firefox L10n completeness report")
    parser.add_argument("--config", default="config.toml", help="Path to config file")
    parser.add_argument("--no-fetch", action="store_true", help="Skip git pull, use cached repos")
    args = parser.parse_args()

    config_path = Path(args.config)
    if not config_path.exists():
        print(f"Error: config file not found: {config_path}", file=sys.stderr)
        sys.exit(1)

    with open(config_path, "rb") as f:
        config = tomllib.load(f)

    repo_cache = Path(config["output"]["repo_cache_dir"])
    source_repo = repo_cache / "firefox-l10n-source"
    target_repo = repo_cache / "firefox-l10n"

    print("Fetching repositories...")
    clone_or_update(config["repos"]["source"], source_repo, args.no_fetch)
    clone_or_update(config["repos"]["target"], target_repo, args.no_fetch)

    channel = config["comparison"]["channel"]
    target_locales = config["comparison"]["target_locales"]
    locale_names: dict[str, str] = config["comparison"].get("locale_display_names", {})

    print(f"\nLoading source inventory (channel: {channel})...")
    inventory = load_inventory(source_repo, channel)
    total_strings = sum(len(ids) for ids in inventory.values())
    print(f"  {total_strings:,} translatable strings across {len(inventory)} files")

    results: dict[str, dict] = {}
    for locale in target_locales:
        display = locale_names.get(locale, locale)
        print(f"\nAnalyzing {display} ({locale})...")
        results[locale] = analyze_locale(locale, target_repo, source_repo, inventory)
        r = results[locale]
        print(f"  Strings:    {r['completeness_pct']}%  ({r['translated']:,} / {r['total_strings']:,})")
        print(f"  Word vol.:  {r['word_completeness_pct']}%  ({r['translated_words']:,} / {r['total_source_words']:,} words)")
        print(f"  Missing:    {r['missing_count']:,} strings, {r['missing_word_count']:,} words")

    print("\nGenerating charts...")
    overall_chart = make_overall_chart(results, locale_names)
    component_chart = make_component_chart(results, locale_names)

    print("Rendering HTML report...")
    html = render_html(results, locale_names, config, overall_chart, component_chart)

    output_dir = Path(config["output"]["output_dir"])
    output_dir.mkdir(parents=True, exist_ok=True)
    output_file = output_dir / "report.html"
    output_file.write_text(html, encoding="utf-8")
    print(f"\nReport written to {output_file}")
    webbrowser.open(output_file.resolve().as_uri())


if __name__ == "__main__":
    main()
