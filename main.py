"""POLARIS command line interface."""

from __future__ import annotations

import glob
import sys
from pathlib import Path

import click
from rich.console import Console
from rich.progress import Progress, SpinnerColumn, TextColumn
from rich.table import Table

from engine.gap_detector import DEFAULT_THRESHOLD, detect_gaps, load_framework
from engine.policy_loader import load_policy
from engine.policy_rewriter import rewrite_policy
from engine.roadmap_generator import generate_roadmap
from engine.scorecard import calculate_maturity, generate_scorecard
from output.report_generator import build_report_payload, export_json, export_pdf


console = Console()

FRAMEWORKS = {
    "nist_csf": Path("data/frameworks/nist_cis_controls.json"),
    "iso27001": Path("data/frameworks/iso27001_controls.json"),
    "soc2": Path("data/frameworks/soc2_controls.json"),
}

SAMPLE_POLICIES = {
    "ISMS": Path("data/sample_policies/isms_policy.txt"),
    "Data Privacy": Path("data/sample_policies/data_privacy_policy.txt"),
    "Patch Management": Path("data/sample_policies/patch_management_policy.txt"),
    "Risk Management": Path("data/sample_policies/risk_management_policy.txt"),
}


@click.command(context_settings={"help_option_names": ["-h", "--help"]})
@click.option("--policy", "policy_patterns", multiple=True, help="Policy path or glob pattern. Can be provided more than once.")
@click.option("--framework", default="nist_csf", show_default=True, help="Framework key or JSON file path.")
@click.option("--output", type=click.Path(), help="Optional output path. Defaults to outputs/<policy>_<timestamp>.")
@click.option("--format", "output_format", type=click.Choice(["terminal", "json", "pdf"]), default="terminal", show_default=True)
@click.option("--threshold", default=DEFAULT_THRESHOLD, show_default=True, type=float, help="Semantic similarity threshold.")
@click.option("--all", "run_all", is_flag=True, help="Run all bundled sample policies.")
@click.option("--verbose", is_flag=True, help="Show match-level details.")
def cli(policy_patterns: tuple[str, ...], framework: str, output: str | None, output_format: str, threshold: float, run_all: bool, verbose: bool):
    """Run offline cybersecurity policy gap analysis."""

    if not run_all and not policy_patterns:
        click.echo(cli.get_help(click.Context(cli)))
        return

    framework_path = resolve_framework(framework)
    framework_data = load_framework(framework_path)
    policies = resolve_policy_paths(policy_patterns, run_all)

    for policy_name, policy_path in policies:
        payload = analyze_policy(policy_name, policy_path, framework_path, framework_data["framework"], threshold, verbose)
        if output_format == "json":
            path = export_json(payload, resolve_multi_output(output, policy_path, len(policies), "json"))
            console.print(f"[green]JSON report saved:[/green] {path}")
        elif output_format == "pdf":
            path = export_pdf(payload, resolve_multi_output(output, policy_path, len(policies), "pdf"))
            console.print(f"[green]PDF report saved:[/green] {path}")
        else:
            render_terminal_report(payload, verbose)


def resolve_framework(framework: str) -> Path:
    candidate = FRAMEWORKS.get(framework, Path(framework))
    if not candidate.exists():
        valid = ", ".join(FRAMEWORKS)
        raise click.ClickException(f"Framework not found: {framework}. Use one of: {valid}, or pass a JSON path.")
    return candidate


def resolve_policy_paths(policy_patterns: tuple[str, ...], run_all: bool) -> list[tuple[str, Path]]:
    if run_all:
        return list(SAMPLE_POLICIES.items())

    paths: list[Path] = []
    for pattern in policy_patterns:
        matches = [Path(match) for match in glob.glob(pattern)]
        paths.extend(matches or [Path(pattern)])

    unique_paths = []
    seen = set()
    for path in paths:
        resolved = path.resolve()
        if resolved not in seen:
            seen.add(resolved)
            unique_paths.append(path)

    missing = [str(path) for path in unique_paths if not path.exists()]
    if missing:
        raise click.ClickException(f"Policy file(s) not found: {', '.join(missing)}")

    return [(path.stem.replace("_", " ").title(), path) for path in unique_paths]


def analyze_policy(policy_name: str, policy_path: Path, framework_path: Path, framework_name: str, threshold: float, verbose: bool) -> dict:
    with Progress(SpinnerColumn(), TextColumn("[progress.description]{task.description}"), console=console, transient=not verbose) as progress:
        task = progress.add_task(f"Scanning {policy_path.name}", total=None)
        policy_text = load_policy(policy_path)
        findings = detect_gaps(policy_text, framework_path, threshold=threshold)
        roadmap = generate_roadmap(findings)
        scorecard, _ = generate_scorecard(findings)
        improvements = rewrite_policy(findings)
        progress.update(task, description=f"Completed {policy_path.name}")

    return build_report_payload(
        policy_name=policy_name,
        framework=framework_name,
        findings=findings,
        roadmap=roadmap,
        scorecard=scorecard,
        improvements=improvements,
    )


def render_terminal_report(payload: dict, verbose: bool = False) -> None:
    maturity = payload["maturity"]
    color = maturity_color(maturity["level"])
    console.rule(f"[bold]POLARIS Analysis: {payload['policy_name']}[/bold]")
    console.print(f"Framework: [bold]{payload['framework']}[/bold]")
    console.print(f"Maturity: [{color}]{maturity['percent']}% - {maturity['level']}[/{color}]")

    gap_table = Table(title="Gap Analysis")
    gap_table.add_column("Control", style="bold")
    gap_table.add_column("Function")
    gap_table.add_column("Score", justify="right")
    gap_table.add_column("Missing Clauses")
    for finding in payload["findings"]:
        score_style = "green" if finding["score"] == 3 else "yellow" if finding["score"] else "red"
        gap_table.add_row(
            finding["control"],
            finding["function"],
            f"[{score_style}]{finding['score']}[/{score_style}]",
            ", ".join(finding.get("missing", [])) or "[green]None[/green]",
        )
    console.print(gap_table)

    score_table = Table(title="Function Coverage Matrix")
    score_table.add_column("Function")
    score_table.add_column("Total", justify="right")
    score_table.add_column("Covered", justify="right")
    score_table.add_column("Missing", justify="right")
    score_table.add_column("Coverage", justify="right")
    for function, data in payload["scorecard"].items():
        covered = data["fully_covered"] + data["partially_covered"]
        score_table.add_row(function, str(data["total"]), str(covered), str(data["missing"]), f"{data['coverage_percent']}%")
    console.print(score_table)

    roadmap_table = Table(title="Improvement Roadmap")
    roadmap_table.add_column("Phase")
    roadmap_table.add_column("Actions")
    for phase, items in payload["roadmap"].items():
        roadmap_table.add_row(phase, "\n".join(items) or "No action required.")
    console.print(roadmap_table)

    if verbose:
        console.print("[bold]LLM-Enhanced Policy Improvements[/bold]")
        console.print(payload["policy_improvements"])


def maturity_color(level: str) -> str:
    return {
        "Initial": "red",
        "Developing": "orange3",
        "Defined": "yellow3",
        "Managed": "green3",
        "Optimized": "green",
    }.get(level, "white")


def resolve_multi_output(output: str | None, policy_path: Path, policy_count: int, extension: str) -> str | None:
    if not output:
        return None
    path = Path(output)
    if policy_count == 1:
        return str(path)
    return str(path.with_name(f"{path.stem}_{policy_path.stem}.{extension}"))


if __name__ == "__main__":
    try:
        cli()
    except KeyboardInterrupt:
        console.print("[red]Interrupted.[/red]")
        sys.exit(130)
