"""Scrape CUHK-Shenzhen faculty directories and build an Obsidian vault."""
from __future__ import annotations

import argparse
import json
import pathlib
import sys

from cuhksz_faculty.config import ConfigError, load_config
from cuhksz_faculty.faculty import scrape_faculty
from cuhksz_faculty.fetch import Fetcher
from cuhksz_faculty.sites import crawl_sites
from cuhksz_faculty.vault import build_vault


def _fetcher(args, config) -> Fetcher:
    return Fetcher(args.data / "cache", config.user_agent, config.host_delay, config.legacy_tls_hosts)


def _save(path: pathlib.Path, value) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=1), encoding="utf-8")


def _load_people(args) -> list[dict]:
    path = args.data / "faculty.json"
    if not path.exists():
        raise FileNotFoundError(f"{path} not found. Run the 'faculty' step first.")
    return json.loads(path.read_text(encoding="utf-8"))


def cmd_schools(args, config) -> None:
    for school in config.schools:
        print(f"{school.key:6} {school.name}")


def cmd_faculty(args, config) -> None:
    people = scrape_faculty(_fetcher(args, config), config.select_schools(args.school))
    _save(args.data / "faculty.json", people)
    print(f"Saved {len(people)} professors.")


def cmd_sites(args, config) -> None:
    results = crawl_sites(_fetcher(args, config), _load_people(args), config.max_pages_per_site, config.workers)
    _save(args.data / "sites.json", results)
    print(f"Crawled sites for {len(results)} professors.")


def cmd_build(args, config) -> None:
    if not (args.data / "sites.json").exists():
        raise FileNotFoundError(f"{args.data / 'sites.json'} not found. Run the 'sites' step first.")
    reviews = json.loads(args.review.read_text(encoding="utf-8")) if args.review else {}
    rows = build_vault(args.data, args.vault, config, reviews)
    open_call = sum(row.hire["status"] in ("ra", "undergrad") for row in rows)
    print(f"Wrote {len(rows)} notes to {args.vault}. {open_call} show evidence of taking RAs, interns or undergraduates.")
    if config.themes:
        print("Top matches:")
        for row in rows[:10]:
            print(f"  {row.score:3d}  {row.display}  [{','.join(row.schools)}] [{row.hire['status']}]")


def cmd_run(args, config) -> None:
    cmd_faculty(args, config)
    cmd_sites(args, config)
    cmd_build(args, config)


COMMANDS = {"run": cmd_run, "faculty": cmd_faculty, "sites": cmd_sites, "build": cmd_build, "schools": cmd_schools}


def main(argv: list[str] | None = None) -> int:
    for stream in (sys.stdout, sys.stderr):
        stream.reconfigure(encoding="utf-8", errors="replace")
    parser = argparse.ArgumentParser(prog="cuhksz-faculty", description=__doc__)
    parser.add_argument("command", choices=list(COMMANDS),
                        help="'run' does faculty, sites and build in order; 'schools' lists school keys")
    parser.add_argument("--school", nargs="+", metavar="KEY", help="only these schools, such as: --school sai sds (default: all)")
    parser.add_argument("--data", type=pathlib.Path, default=pathlib.Path("data"), help="cache and JSON output (default: data)")
    parser.add_argument("--vault", type=pathlib.Path, default=pathlib.Path("vault"), help="Obsidian vault folder (default: vault)")
    parser.add_argument("--config", type=pathlib.Path, help="TOML config (default: built-in)")
    parser.add_argument("--review", type=pathlib.Path, help="JSON of hand-reviewed hiring labels")
    args = parser.parse_args(argv)
    try:
        COMMANDS[args.command](args, load_config(args.config))
    except (ConfigError, FileNotFoundError, RuntimeError) as error:
        print(f"error: {error}", file=sys.stderr)
        return 1
    return 0
