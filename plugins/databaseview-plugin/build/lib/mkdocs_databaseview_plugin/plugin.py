from __future__ import annotations

import os
import re
import shutil
import subprocess
from pathlib import Path

from mkdocs.config import config_options
from mkdocs.plugins import BasePlugin


class DBViewPluginConfig(config_options.Config):
    """
    Configuration for the Obsidian Bases -> MkDocs plugin.
    """

    vault_path = config_options.Type(str, default=".")
    vault_name = config_options.Type(str, default="")
    cli_command = config_options.Type(str, default="obsidian")
    timeout = config_options.Type(int, default=60)


class DBViewPlugin(BasePlugin[DBViewPluginConfig]):
    """
    Render Obsidian .base embeds as static MkDocs content.

    Supported Obsidian syntax:

        ![[Needs.base]]

    and:

        ![[Needs.base#Needs]]

    The actual Base is evaluated by Obsidian's CLI, so filters,
    formulas, sorting, grouping, backlinks, and other Base features
    remain the responsibility of Obsidian.
    """

    # Matches:
    #
    # ![[Needs.base]]
    # ![[Templates/Bases/Needs.base]]
    # ![[Templates/Bases/Needs.base#Needs]]
    #
    # Also tolerates spaces inside the wikilink.
    EMBED_PATTERN = re.compile(
        r"!\[\["
        r"(?P<target>[^\]]+?\.base)"
        r"(?:#(?P<view>[^\]]+))?"
        r"\]\]"
    )

    def __init__(self):
        super().__init__()

        self.vault_path: Path | None = None
        self.vault_name: str | None = None
        self.cli_command: str | None = None

    # ------------------------------------------------------------------
    # MkDocs initialization
    # ------------------------------------------------------------------

    def on_config(self, config):
        """
        Initialize and validate the Obsidian vault configuration.
        """

        self.vault_path = Path(
            os.path.expandvars(
                os.path.expanduser(
                    self.config.vault_path
                )
            )
        ).resolve()

        if not self.vault_path.exists():
            raise ValueError(
                f"Obsidian vault does not exist: "
                f"{self.vault_path}"
            )

        if not self.vault_path.is_dir():
            raise ValueError(
                f"Obsidian vault path is not a directory: "
                f"{self.vault_path}"
            )

        # Explicit vault name wins.
        if self.config.vault_name:
            self.vault_name = self.config.vault_name
        else:
            # Usually the vault directory name is also the
            # Obsidian vault name.
            self.vault_name = self.vault_path.name

        self.cli_command = self._find_cli()

        return config

    # ------------------------------------------------------------------
    # MkDocs Markdown processing
    # ------------------------------------------------------------------

    def on_page_markdown(
        self,
        markdown,
        page,
        config,
        files,
    ):
        """
        Replace Obsidian .base embeds with the output produced
        by Obsidian's Base query engine.
        """

        def replace(match):
            base_target = match.group("target").strip()
            view_name = match.group("view")

            if view_name:
                view_name = view_name.strip()

            try:
                base_path = self._resolve_base_path(
                    base_target
                )

                return self._query_base(
                    base_path=base_path,
                    view_name=view_name,
                )

            except Exception as exc:
                raise RuntimeError(
                    f"Could not render Obsidian Base "
                    f"{base_target!r}"
                    + (
                        f" view {view_name!r}"
                        if view_name
                        else ""
                    )
                    + f": {exc}"
                ) from exc

        return self.EMBED_PATTERN.sub(
            replace,
            markdown,
        )

    # ------------------------------------------------------------------
    # Obsidian CLI discovery
    # ------------------------------------------------------------------

    def _find_cli(self) -> str:
        """
        Find the Obsidian CLI executable.
        """

        command = self.config.cli_command

        found = shutil.which(command)

        if found:
            return found

        # Windows sometimes exposes the executable with .exe.
        if not command.lower().endswith(".exe"):
            found = shutil.which(
                f"{command}.exe"
            )

            if found:
                return found

        raise RuntimeError(
            "Could not find the Obsidian CLI. "
            "Make sure Obsidian's command line interface "
            "is enabled and that 'obsidian' is available "
            "in PATH."
        )

    # ------------------------------------------------------------------
    # Base path handling
    # ------------------------------------------------------------------

    def _resolve_base_path(
        self,
        target: str,
    ) -> str:
        """
        Resolve an Obsidian wikilink target to a path relative
        to the vault root.

        Example:

            Templates/Bases/Needs.base

        becomes:

            C:/SuckitUpDocs/docs/Suck It Up/
            Templates/Bases/Needs.base
        """

        if self.vault_path is None:
            raise RuntimeError(
                "Vault path has not been initialized."
            )

        # Normalize Obsidian's forward-slash paths.
        target = target.replace("\\", "/").strip()

        # Remove a leading slash if one exists.
        target = target.lstrip("/")

        base_path = (
            self.vault_path / Path(target)
        ).resolve()

        # Security check: don't allow a Base outside the vault.
        try:
            base_path.relative_to(
                self.vault_path
            )
        except ValueError as exc:
            raise ValueError(
                f"Base path is outside the Obsidian vault: "
                f"{target}"
            ) from exc

        if not base_path.exists():
            raise FileNotFoundError(
                f"Base file does not exist: "
                f"{base_path}"
            )

        if not base_path.is_file():
            raise ValueError(
                f"Base path is not a file: "
                f"{base_path}"
            )

        if base_path.suffix.lower() != ".base":
            raise ValueError(
                f"Expected a .base file: "
                f"{base_path}"
            )

        # Obsidian CLI wants the path relative to the vault.
        relative_path = base_path.relative_to(
            self.vault_path
        )

        return relative_path.as_posix()

    # ------------------------------------------------------------------
    # Query Obsidian
    # ------------------------------------------------------------------

    def _query_base(
        self,
        base_path: str,
        view_name: str | None,
    ) -> str:
        """
        Ask Obsidian to evaluate the Base and return Markdown.

        Using format=md means Obsidian performs all of the actual
        Base work, including:

        - filters
        - formulas
        - sorting
        - grouping
        - linked files
        - backlinks
        - this
        - properties
        - view configuration
        """

        if self.cli_command is None:
            raise RuntimeError(
                "Obsidian CLI has not been initialized."
            )

        if self.vault_name is None:
            raise RuntimeError(
                "Obsidian vault name has not been initialized."
            )

        command = [
            self.cli_command,
            f"vault={self.vault_name}",
            "base:query",
            f"path={base_path}",
        ]

        if view_name:
            command.append(
                f"view={view_name}"
            )

        command.append("format=md")

        try:
            result = subprocess.run(
                command,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=self.config.timeout,
                check=False,
            )

        except subprocess.TimeoutExpired as exc:
            raise RuntimeError(
                f"Obsidian CLI timed out after "
                f"{self.config.timeout} seconds."
            ) from exc

        except OSError as exc:
            raise RuntimeError(
                f"Could not execute Obsidian CLI: "
                f"{exc}"
            ) from exc

        stdout = result.stdout.strip()
        stderr = result.stderr.strip()

        if result.returncode != 0:
            details = stderr or stdout

            raise RuntimeError(
                "Obsidian CLI returned an error"
                + (
                    f": {details}"
                    if details
                    else "."
                )
            )

        if not stdout:
            # An empty Base is a legitimate result.
            return (
                '<div class="databaseview-empty">'
                "No results."
                "</div>"
            )

        return self._clean_cli_output(
            stdout
        )

    # ------------------------------------------------------------------
    # CLI output cleanup
    # ------------------------------------------------------------------

    @staticmethod
    def _clean_cli_output(
        output: str,
    ) -> str:
        """
        Clean harmless CLI output while preserving the Markdown
        table generated by Obsidian.
        """

        lines = output.splitlines()

        # Remove leading/trailing blank lines.
        while lines and not lines[0].strip():
            lines.pop(0)

        while lines and not lines[-1].strip():
            lines.pop()

        return "\n".join(lines)
