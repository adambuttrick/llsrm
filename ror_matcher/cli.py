import asyncio

import click
import yaml

from .config import load_config
from . import extract, query, reconcile, throughput


@click.group()
def main():
    pass


@main.command()
@click.option("--config", required=True, type=click.Path(exists=True), help="Path to YAML config file")
def extract_cmd(config):
    cfg = load_config(config)
    extract.run(cfg)
    click.echo("Extraction complete.")


extract_cmd.name = "extract"


@main.command()
@click.option("--config", required=True, type=click.Path(exists=True), help="Path to YAML config file")
@click.option("--resume", is_flag=True, default=False, help="Resume from checkpoint")
def query_cmd(config, resume):
    cfg = load_config(config)
    asyncio.run(query.run(cfg, resume=resume))
    click.echo("Query complete.")


query_cmd.name = "query"


@main.command()
@click.option("--config", required=True, type=click.Path(exists=True), help="Path to YAML config file")
def reconcile_cmd(config):
    cfg = load_config(config)
    reconcile.run(cfg)
    click.echo("Reconciliation complete.")


reconcile_cmd.name = "reconcile"


@main.command()
@click.option("--config", required=True, type=click.Path(exists=True), help="Path to YAML config file")
def optimize_cmd(config):
    cfg = load_config(config)

    async def _run():
        optimal = await throughput.find_optimal_concurrency(
            cfg.query.base_url,
            timeout=cfg.query.timeout,
        )
        return optimal

    optimal = asyncio.run(_run())
    click.echo(f"\nRecommended concurrency: {optimal}")

    if click.confirm("Update config file with this value?"):
        with open(config) as f:
            raw = yaml.safe_load(f)
        raw["query"]["concurrency"] = optimal
        with open(config, "w") as f:
            yaml.dump(raw, f, default_flow_style=False)
        click.echo(f"Updated {config}")


optimize_cmd.name = "optimize"


@main.command()
@click.option("--config", required=True, type=click.Path(exists=True), help="Path to YAML config file")
@click.option("--optimize", is_flag=True, default=False, help="Run throughput optimization before querying")
@click.option("--resume", is_flag=True, default=False, help="Resume query from checkpoint")
def run_cmd(config, optimize, resume):
    cfg = load_config(config)

    click.echo("Stage 1: Extracting affiliations...")
    extract.run(cfg)
    click.echo("Extraction complete.")

    if optimize:
        click.echo("Optimizing concurrency...")

        async def _optimize():
            return await throughput.find_optimal_concurrency(
                cfg.query.base_url,
                timeout=cfg.query.timeout,
            )

        optimal = asyncio.run(_optimize())
        cfg.query.concurrency = optimal
        click.echo(f"Concurrency set to {optimal}.")

    click.echo("Stage 2: Querying ROR API...")
    asyncio.run(query.run(cfg, resume=resume))
    click.echo("Query complete.")

    click.echo("Stage 3: Reconciling matches...")
    reconcile.run(cfg)
    click.echo("Reconciliation complete.")

    click.echo("Pipeline finished.")


run_cmd.name = "run"
