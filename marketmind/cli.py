"""
MarketMind CLI
==============

Command-line interface for MarketMind.

Entry point registered in pyproject.toml as `marketmind`.

Usage
-----
    marketmind --help
    marketmind info
    marketmind config show

Phase 1 implements only infrastructure commands.
Research and pipeline commands are added in later phases.
"""

from __future__ import annotations

import sys

import click

from marketmind import __version__


@click.group()
@click.version_option(version=__version__, prog_name="MarketMind")
def main() -> None:
    """
    MarketMind — Quantitative Research Platform.

    A platform for discovering, validating, and monitoring
    statistically meaningful trading signals.
    """


@main.command()
def info() -> None:
    """Display platform version and active configuration."""
    from marketmind.config.settings import get_settings
    from marketmind.logging import configure_from_settings

    configure_from_settings()
    settings = get_settings()

    click.echo(f"MarketMind v{__version__}")
    click.echo(f"Environment : {settings.environment}")
    click.echo(f"Database    : {settings.database.url}")
    click.echo(f"Log level   : {settings.logging.level}")
    click.echo(f"Protocol    : v{settings.research.protocol_version}")


@main.group()
def config() -> None:
    """Configuration management commands."""


@config.command("show")
def config_show() -> None:
    """Print the active configuration as YAML."""
    import yaml

    from marketmind.config.settings import get_settings

    settings = get_settings()
    click.echo(yaml.dump(settings.model_dump(), default_flow_style=False))


@config.command("validate")
def config_validate() -> None:
    """Validate the active configuration and report any problems."""
    try:
        from marketmind.config.settings import get_settings

        get_settings()
        click.secho("✓ Configuration is valid.", fg="green")
    except Exception as e:
        click.secho(f"✗ Configuration error: {e}", fg="red", err=True)
        sys.exit(1)


if __name__ == "__main__":
    main()
