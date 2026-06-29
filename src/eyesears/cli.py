"""ee — command-line interface for the prep + health steps."""
from __future__ import annotations

import json

import typer
from rich.console import Console
from rich.table import Table

from . import doctor, prep
from .config import load_config

app = typer.Typer(add_completion=False, help="Eyes & ears prep for ad videos.")
console = Console()


@app.command()
def doc(ping: bool = typer.Option(False, "--ping", help="Also validate the Groq key live.")):
    """Health check: deps, ffmpeg, config, Groq key (and optional live ping)."""
    cfg = load_config()
    rows = doctor.check(cfg, ping=ping)
    table = Table(title="ads-learnings doctor")
    table.add_column("check")
    table.add_column("ok")
    table.add_column("detail", overflow="fold")
    all_ok = True
    for label, ok, detail in rows:
        all_ok = all_ok and ok
        table.add_row(label, "[green]✓[/]" if ok else "[red]✗[/]", detail)
    console.print(table)
    raise typer.Exit(code=0 if all_ok else 1)


@app.command()
def prep_cmd(
    source: str = typer.Argument(..., help="Local video path OR a TikTok/Meta/YouTube URL."),
    quiet: bool = typer.Option(False, "--quiet", help="Print only the prep.json path."),
):
    """Ingest -> frames -> contact sheets + manifest -> audio. No LLM calls."""
    cfg = load_config()
    out = prep.run(source, cfg)
    workdir = out["workdir"]
    if quiet:
        console.print(f"{workdir}/prep.json")
        return
    console.print(f"[green]✓[/] prepped [bold]{out['slug']}[/]")
    console.print(f"  duration : {out['duration_s']}s | frames: {out['frame_count']} | sheets: {out['sheet_count']}")
    console.print(f"  sheets   : {out['sheets_dir']}")
    console.print(f"  manifest : {out['manifest_path']}")
    console.print(f"  audio    : {out['audio_path']}")
    console.print(f"  prep.json: {workdir}/prep.json")


app.command(name="prep")(prep_cmd)


@app.command()
def show(slug: str = typer.Argument(..., help="Slug under data/out/ to print.")):
    """Print a previously generated prep.json."""
    cfg = load_config()
    path = cfg.out_dir / slug / "prep.json"
    if not path.exists():
        console.print(f"[red]not found:[/] {path}")
        raise typer.Exit(1)
    console.print_json(json.loads(path.read_text()))


def main():
    app()


if __name__ == "__main__":
    main()
