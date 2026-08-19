from __future__ import annotations

import re
from pathlib import Path
from typing import Any
from urllib.parse import quote, urlparse

import yaml

from mkdocs.plugins import BasePlugin


# ============================================================
# Regular expressions
# ============================================================

BASE_EMBED_RE = re.compile(
    r"!\[\[([^\]#]+?)(?:#([^\]]+))?\]\]"
)

WIKILINK_RE = re.compile(
    r"\[\[([^\]|#]+)(?:#[^\]|]+)?(?:\|([^\]]+))?\]\]"
)


# ============================================================
# Plugin
# ============================================================

class DBViewPlugin(BasePlugin):
    """
    Converts Obsidian .base embeds into static Markdown tables.

    Examples:

        ![[Needs.base]]

        ![[Tasks.base#Needs]]

    The generated result is ordinary Markdown.
    """

    # ========================================================
    # MkDocs hooks
    # ========================================================

    def on_config(self, config):
        self.docs_dir = Path(config["docs_dir"]).resolve()

        self.use_directory_urls = config.get(
            "use_directory_urls",
            True,
        )

        site_url = str(
            config.get("site_url") or ""
        ).strip()

        if site_url:
            parsed = urlparse(site_url)
            self.site_url_path = parsed.path or "/"
        else:
            self.site_url_path = "/"

        if not self.site_url_path.startswith("/"):
            self.site_url_path = "/" + self.site_url_path

        if not self.site_url_path.endswith("/"):
            self.site_url_path += "/"

        print(f"[StaticBases] docs: {self.docs_dir}")

        self.notes: dict[str, dict[str, Any]] = {}
        self.bases: dict[str, Path] = {}

        self._load_notes()
        self._load_bases()

        unique_notes = {
            note["path"]
            for note in self.notes.values()
        }

        print(
            f"[StaticBases] Loaded "
            f"{len(unique_notes)} Markdown notes"
        )

        print(
            f"[StaticBases] Loaded "
            f"{len(self.bases)} .base files"
        )

        return config

    def on_page_markdown(self, markdown, page, config, files):
        page_name = (
            page.file.src_path
            if page.file
            else "UNKNOWN"
        )

        print(
            f"[StaticBases] PROCESSING PAGE: "
            f"{page_name}"
        )

        embeds = list(
            BASE_EMBED_RE.finditer(markdown)
        )

        if embeds:
            for match in embeds:
                print(
                    f"[StaticBases] Embed found: "
                    f"{match.group(0)}"
                )
        else:
            print(
                "[StaticBases] No Obsidian base "
                "embeds found on this page."
            )

        current_file = None

        if page.file and page.file.abs_src_path:
            current_file = Path(
                page.file.abs_src_path
            ).resolve()

        return self._replace_base_embeds(
            markdown,
            current_file,
        )

    # ========================================================
    # Loading Markdown notes
    # ========================================================

    def _load_notes(self):
        """
        Load all Markdown files and their YAML frontmatter.
        """

        for path in self.docs_dir.rglob("*.md"):

            if self._is_conflict_file(path):
                continue

            if self._is_trash(path):
                continue

            try:
                text = path.read_text(
                    encoding="utf-8"
                )
            except Exception as exc:
                print(
                    f"[StaticBases] Could not read "
                    f"{path}: {exc}"
                )
                continue

            frontmatter = self._parse_frontmatter(text)

            note = {
                "path": path.resolve(),
                "name": path.stem,
                "relative_path": path.relative_to(
                    self.docs_dir
                ),
                "frontmatter": frontmatter,
                "tags": self._get_tags(frontmatter),
            }

            self.notes[
                path.as_posix().lower()
            ] = note

            self.notes.setdefault(
                path.stem.lower(),
                note,
            )

    # ========================================================
    # Loading .base files
    # ========================================================

    def _load_bases(self):
        """
        Find all .base files.

        Conflict copies and .trash files are ignored.
        """

        for path in self.docs_dir.rglob("*.base"):

            if self._is_conflict_file(path):
                continue

            if self._is_trash(path):
                continue

            key = path.name.lower()

            existing = self.bases.get(key)

            if existing:
                if self._is_preferred_base(
                    path,
                    existing,
                ):
                    self.bases[key] = path
            else:
                self.bases[key] = path

    def _is_preferred_base(
        self,
        candidate: Path,
        existing: Path,
    ) -> bool:

        candidate_text = candidate.as_posix()
        existing_text = existing.as_posix()

        candidate_preferred = (
            "Templates/Bases" in candidate_text
            or "Templates\\Bases" in candidate_text
        )

        existing_preferred = (
            "Templates/Bases" in existing_text
            or "Templates\\Bases" in existing_text
        )

        if candidate_preferred and not existing_preferred:
            return True

        return False

    # ========================================================
    # Base embed processing
    # ========================================================

    def _replace_base_embeds(
        self,
        markdown: str,
        current_file: Path | None,
    ) -> str:

        def replace(match):

            base_ref = match.group(1).strip()

            view_name = match.group(2)

            if view_name:
                view_name = view_name.strip()

            print(
                f"[StaticBases] Embed: "
                f"{base_ref}"
                f"{'#' + view_name if view_name else ''}"
            )

            base_path = self._find_base(base_ref)

            if base_path is None:

                print(
                    f"[StaticBases] WARNING: "
                    f"Could not find base: "
                    f"{base_ref}"
                )

                return match.group(0)

            try:

                table = self._render_base(
                    base_path,
                    view_name,
                    current_file,
                )

                if table is None:
                    return match.group(0)

                return table

            except Exception as exc:

                print(
                    f"[StaticBases] ERROR rendering "
                    f"{base_ref}: {exc}"
                )

                import traceback

                traceback.print_exc()

                return match.group(0)

        return BASE_EMBED_RE.sub(
            replace,
            markdown,
        )

    # ========================================================
    # Base resolution
    # ========================================================

    def _find_base(
        self,
        base_ref: str,
    ) -> Path | None:

        base_ref = (
            base_ref
            .replace("\\", "/")
            .strip("/")
        )

        exact = self.docs_dir / base_ref

        if exact.is_file():
            print(
                f"[StaticBases] Base resolved exactly: "
                f"{exact}"
            )
            return exact.resolve()

        if not base_ref.lower().endswith(".base"):

            exact_with_extension = (
                self.docs_dir
                / f"{base_ref}.base"
            )

            if exact_with_extension.is_file():
                print(
                    f"[StaticBases] Base resolved: "
                    f"{exact_with_extension}"
                )
                return exact_with_extension.resolve()

        filename = Path(base_ref).name

        if not filename.lower().endswith(".base"):
            filename += ".base"

        key = filename.lower()

        if key in self.bases:

            path = self.bases[key].resolve()

            print(
                f"[StaticBases] Base resolved by "
                f"filename: {path}"
            )

            return path

        matches = [
            p
            for p in self.docs_dir.rglob(filename)
            if not self._is_conflict_file(p)
            and not self._is_trash(p)
        ]

        if not matches:
            return None

        for path in matches:

            normalized = (
                path.as_posix()
                .replace("\\", "/")
            )

            if "/Templates/Bases/" in normalized:
                return path.resolve()

        return matches[0].resolve()

    # ========================================================
    # Render .base
    # ========================================================

    def _render_base(
        self,
        base_path: Path,
        view_name: str | None,
        current_file: Path | None,
    ) -> str | None:

        print(
            f"[StaticBases] Rendering base: "
            f"{base_path}"
        )

        try:

            text = base_path.read_text(
                encoding="utf-8"
            )

            base = yaml.safe_load(text) or {}

        except Exception as exc:

            print(
                f"[StaticBases] ERROR reading "
                f"{base_path}: {exc}"
            )

            return None

        if not isinstance(base, dict):

            print(
                f"[StaticBases] WARNING: "
                f"Invalid .base structure: "
                f"{base_path}"
            )

            return None

        print(
            f"[StaticBases] Base keys: "
            f"{list(base.keys())}"
        )

        views = base.get("views", [])

        if not isinstance(views, list):

            print(
                f"[StaticBases] WARNING: "
                f"'views' is not a list in "
                f"{base_path}"
            )

            return None

        if not views:

            print(
                f"[StaticBases] WARNING: "
                f"No views in "
                f"{base_path}"
            )

            return None

        print(
            f"[StaticBases] Found "
            f"{len(views)} views in "
            f"{base_path}"
        )

        for index, candidate in enumerate(views):

            if isinstance(candidate, dict):

                print(
                    f"[StaticBases] View {index}: "
                    f"name={candidate.get('name')!r}, "
                    f"type={candidate.get('type')!r}"
                )

        view = self._choose_view(
            views,
            view_name,
            base_path,
        )

        if view is None:

            print(
                f"[StaticBases] WARNING: "
                f"Could not find requested view "
                f"'{view_name}' in {base_path}"
            )

            return None

        print(
            f"[StaticBases] Selected view: "
            f"{view.get('name')!r} "
            f"(type={view.get('type')!r})"
        )

        # ----------------------------------------------------
        # Find matching notes
        # ----------------------------------------------------

        matching_notes = []

        seen_paths = set()

        for note in self.notes.values():

            note_path = note["path"]

            if note_path in seen_paths:
                continue

            seen_paths.add(note_path)

            if self._matches_filter(
                view.get("filters"),
                note,
                current_file,
            ):
                matching_notes.append(note)

        print(
            f"[StaticBases] Matching notes: "
            f"{len(matching_notes)}"
        )

        # ----------------------------------------------------
        # Sorting
        # ----------------------------------------------------

        matching_notes = self._sort_notes(
            matching_notes,
            view.get("sort", []),
        )

        # ----------------------------------------------------
        # Columns
        # ----------------------------------------------------

        columns = view.get("order")

        if not columns:

            columns = [
                "file.name",
                "status",
                "teams",
                "features",
            ]

        columns = [
            str(column)
            for column in columns
        ]

        # ----------------------------------------------------
        # Rows
        # ----------------------------------------------------

        rows = []

        for note in matching_notes:

            row = []

            for column in columns:

                value = self._get_column_value(
                    column,
                    note,
                )

                row.append(value)

            rows.append(row)

        # ----------------------------------------------------
        # Title
        # ----------------------------------------------------

        title = view.get(
            "name",
            view_name or base_path.stem,
        )

        return self._markdown_table(
            title,
            columns,
            rows,
        )

    # ========================================================
    # View selection
    # ========================================================

    def _choose_view(
        self,
        views: list[dict[str, Any]],
        view_name: str | None,
        base_path: Path | None = None,
    ):

        if view_name:

            wanted = (
                view_name
                .strip()
                .lower()
            )

            for view in views:

                if not isinstance(view, dict):
                    continue

                name = str(
                    view.get("name", "")
                ).strip().lower()

                if name == wanted:
                    return view

            return None

        if base_path:

            base_name = (
                base_path.stem
                .strip()
                .lower()
            )

            for view in views:

                if not isinstance(view, dict):
                    continue

                name = str(
                    view.get("name", "")
                ).strip().lower()

                if name == base_name:
                    return view

        for view in views:

            if not isinstance(view, dict):
                continue

            if (
                str(
                    view.get("type", "")
                ).lower()
                == "table"
            ):
                return view

        for view in views:

            if isinstance(view, dict):
                return view

        return None

    # ========================================================
    # Filters
    # ========================================================

    def _matches_filter(
        self,
        filter_config,
        note,
        current_file,
    ) -> bool:

        if not filter_config:
            return True

        result = self._evaluate_expression(
            filter_config,
            note,
            current_file,
        )

        return bool(result)

    def _evaluate_expression(
        self,
        expression,
        note,
        current_file,
    ) -> bool:

        # ----------------------------------------------------
        # Boolean literal
        # ----------------------------------------------------

        if isinstance(expression, bool):
            return expression

        # ----------------------------------------------------
        # Lists mean AND in Bases filter syntax.
        # ----------------------------------------------------

        if isinstance(expression, list):

            for item in expression:

                if not self._evaluate_expression(
                    item,
                    note,
                    current_file,
                ):
                    return False

            return True

        # ----------------------------------------------------
        # String expression
        # ----------------------------------------------------

        if isinstance(expression, str):

            expression = expression.strip()

            if not expression:
                return True

            return self._evaluate_string_expression(
                expression,
                note,
                current_file,
            )

        # ----------------------------------------------------
        # Mapping expression
        # ----------------------------------------------------

        if not isinstance(expression, dict):

            print(
                f"[StaticBases] Unknown filter type: "
                f"{type(expression).__name__}"
            )

            return False

        # ----------------------------------------------------
        # AND
        # ----------------------------------------------------

        if "and" in expression:

            values = expression["and"]

            if not isinstance(values, list):
                values = [values]

            for item in values:

                if not self._evaluate_expression(
                    item,
                    note,
                    current_file,
                ):
                    return False

            return True

        # ----------------------------------------------------
        # OR
        # ----------------------------------------------------

        if "or" in expression:

            values = expression["or"]

            if not isinstance(values, list):
                values = [values]

            for item in values:

                if self._evaluate_expression(
                    item,
                    note,
                    current_file,
                ):
                    return True

            return False

        # ----------------------------------------------------
        # file.tags.contains
        # ----------------------------------------------------

        if "file.tags.contains" in expression:

            return self._contains(
                note["tags"],
                expression["file.tags.contains"],
            )

        # ----------------------------------------------------
        # Nested:
        #
        # file:
        #   tags:
        #     contains: needs
        # ----------------------------------------------------

        if "file" in expression:

            value = expression["file"]

            if isinstance(value, dict):

                tags = value.get("tags")

                if isinstance(tags, dict):

                    if "contains" in tags:

                        return self._contains(
                            note["tags"],
                            tags["contains"],
                        )

        print(
            f"[StaticBases] Unknown filter mapping: "
            f"{expression}"
        )

        return False

    # ========================================================
    # String filter parser
    # ========================================================

    def _evaluate_string_expression(
        self,
        expression: str,
        note,
        current_file,
    ) -> bool:

        expression = expression.strip()

        if not expression:
            return True

        # ----------------------------------------------------
        # Strip balanced outer parentheses.
        # ----------------------------------------------------

        expression = self._strip_outer_parentheses(
            expression
        )

        # ----------------------------------------------------
        # OR
        #
        # Must happen before AND because OR has lower
        # precedence.
        # ----------------------------------------------------

        parts = self._split_boolean_operator(
            expression,
            "||",
        )

        if len(parts) > 1:

            return any(
                self._evaluate_string_expression(
                    part,
                    note,
                    current_file,
                )
                for part in parts
            )

        # ----------------------------------------------------
        # AND
        # ----------------------------------------------------

        parts = self._split_boolean_operator(
            expression,
            "&&",
        )

        if len(parts) > 1:

            return all(
                self._evaluate_string_expression(
                    part,
                    note,
                    current_file,
                )
                for part in parts
            )

        # ----------------------------------------------------
        # NOT
        # ----------------------------------------------------

        if expression.startswith("!"):
            return not self._evaluate_string_expression(
                expression[1:].strip(),
                note,
                current_file,
            )

        # ----------------------------------------------------
        # file.name.contains(...)
        # ----------------------------------------------------

        match = re.match(
            r"""
            ^file
            \.name
            \.contains
            \(
                \s*
                ['"]?([^'")]+)['"]?
                \s*
            \)
            $
            """,
            expression,
            re.VERBOSE,
        )

        if match:

            wanted = match.group(1).strip()

            return (
                wanted.lower()
                in note["name"].lower()
            )

        # ----------------------------------------------------
        # file.tags.contains(...)
        # ----------------------------------------------------

        match = re.match(
            r"""
            ^file
            \.tags
            \.contains
            \(
                \s*
                ['"]?([^'")]+)['"]?
                \s*
            \)
            $
            """,
            expression,
            re.VERBOSE,
        )

        if match:

            wanted = match.group(1).strip()

            return self._contains(
                note["tags"],
                wanted,
            )

        # ----------------------------------------------------
        # this.tags.contains(...)
        # ----------------------------------------------------

        match = re.match(
            r"""
            ^this
            \.tags
            \.contains
            \(
                \s*
                ['"]?([^'")]+)['"]?
                \s*
            \)
            $
            """,
            expression,
            re.VERBOSE,
        )

        if match:

            wanted = match.group(1).strip()

            return self._contains(
                note["tags"],
                wanted,
            )

        # ----------------------------------------------------
        # this.hasTag(...)
        # ----------------------------------------------------

        match = re.match(
            r"""
            ^this
            \.hasTag
            \(
                \s*
                ['"]?([^'")]+)['"]?
                \s*
            \)
            $
            """,
            expression,
            re.VERBOSE,
        )

        if match:

            wanted = match.group(1).strip()

            return self._contains(
                note["tags"],
                wanted,
            )

        # ----------------------------------------------------
        # this.inFolder(...)
        # ----------------------------------------------------

        match = re.match(
            r"""
            ^this
            \.inFolder
            \(
                \s*
                ['"]([^'"]+)['"]
                \s*
            \)
            $
            """,
            expression,
            re.VERBOSE,
        )

        if match:

            folder = (
                match.group(1)
                .replace("\\", "/")
                .strip("/")
            )

            relative = (
                note["relative_path"]
                .as_posix()
                .replace("\\", "/")
            )

            relative_folder = (
                str(Path(relative).parent)
                .replace("\\", "/")
            )

            return (
                relative_folder == folder
                or relative_folder.startswith(
                    folder + "/"
                )
            )

        # ----------------------------------------------------
        # property.contains(this)
        #
        # Examples:
        #
        # features.contains(this)
        # teams.contains(this)
        # sprint.contains(this)
        # needs.contains(this)
        # file.backlinks.contains(this)
        # ----------------------------------------------------

        match = re.match(
            r"""
            ^
            ([A-Za-z0-9_. ]+)
            \.contains
            \(
                \s*this\s*
            \)
            $
            """,
            expression,
            re.VERBOSE,
        )

        if match:

            property_name = (
                match.group(1)
                .strip()
            )

            # --------------------------------------------
            # file.backlinks.contains(this)
            # --------------------------------------------

            if property_name == "file.backlinks":

                return self._has_backlink_to(
                    note,
                    current_file,
                )

            # --------------------------------------------
            # Normal property
            # --------------------------------------------

            values = self._property_values(
                note,
                property_name,
            )

            if current_file is None:
                return False

            current_file = current_file.resolve()

            for value in values:

                resolved = self._resolve_link(
                    value
                )

                if resolved:

                    if (
                        resolved["path"].resolve()
                        == current_file
                    ):
                        return True

            return False

        # ----------------------------------------------------
        # Direct property equality.
        #
        # Example:
        #
        # status == [[Complete]]
        #
        # This is intentionally limited/simple.
        # ----------------------------------------------------

        match = re.match(
            r"""
            ^
            ([A-Za-z0-9_. ]+)
            \s*
            (==|=)
            \s*
            (.+)
            $
            """,
            expression,
            re.VERBOSE,
        )

        if match:

            property_name = (
                match.group(1)
                .strip()
            )

            wanted = (
                match.group(3)
                .strip()
            )

            values = self._property_values(
                note,
                property_name,
            )

            for value in values:

                if self._values_equal(
                    value,
                    wanted,
                ):
                    return True

            return False

        # ----------------------------------------------------
        # Unknown expression.
        #
        # IMPORTANT:
        #
        # Unknown expressions now return FALSE.
        #
        # This prevents a broken filter from causing
        # unrelated notes to appear.
        # ----------------------------------------------------

        print(
            f"[StaticBases] Unrecognized filter "
            f"expression: {expression!r} "
            f"for note {note['name']!r}"
        )

        return False

    # ========================================================
    # Boolean parser helpers
    # ========================================================

    def _strip_outer_parentheses(
        self,
        expression: str,
    ) -> str:

        expression = expression.strip()

        while (
            expression.startswith("(")
            and expression.endswith(")")
            and self._parentheses_wrap_entire_expression(
                expression
            )
        ):
            expression = expression[1:-1].strip()

        return expression

    def _parentheses_wrap_entire_expression(
        self,
        expression: str,
    ) -> bool:

        depth = 0
        quote_char = None

        for index, char in enumerate(expression):

            if quote_char:

                if char == quote_char:
                    quote_char = None

                continue

            if char in ("'", '"'):
                quote_char = char
                continue

            if char == "(":
                depth += 1

            elif char == ")":

                depth -= 1

                if depth == 0 and index != len(expression) - 1:
                    return False

        return depth == 0

    def _split_boolean_operator(
        self,
        expression: str,
        operator: str,
    ) -> list[str]:

        parts = []

        depth = 0
        quote_char = None
        start = 0

        index = 0

        while index < len(expression):

            char = expression[index]

            if quote_char:

                if char == quote_char:
                    quote_char = None

                index += 1
                continue

            if char in ("'", '"'):

                quote_char = char
                index += 1
                continue

            if char == "(":

                depth += 1
                index += 1
                continue

            if char == ")":

                depth -= 1
                index += 1
                continue

            if (
                depth == 0
                and expression.startswith(
                    operator,
                    index,
                )
            ):

                parts.append(
                    expression[
                        start:index
                    ].strip()
                )

                index += len(operator)

                start = index
                continue

            index += 1

        if parts:

            parts.append(
                expression[start:].strip()
            )

            return [
                part
                for part in parts
                if part
            ]

        return [expression]

    def _values_equal(
        self,
        value,
        wanted,
    ) -> bool:

        wanted = wanted.strip()

        if (
            len(wanted) >= 2
            and wanted[0] in ("'", '"')
            and wanted[-1] == wanted[0]
        ):
            wanted = wanted[1:-1]

        value_text = str(value).strip()

        if value_text.lower() == wanted.lower():
            return True

        resolved_value = self._resolve_link(
            value
        )

        resolved_wanted = self._resolve_link(
            wanted
        )

        if resolved_value and resolved_wanted:

            return (
                resolved_value["path"].resolve()
                == resolved_wanted["path"].resolve()
            )

        if resolved_value:

            return (
                resolved_value["name"].lower()
                == wanted.lstrip("#").lower()
            )

        return False

    # ========================================================
    # Sorting
    # ========================================================

    def _sort_notes(
        self,
        notes,
        sort_config,
    ):

        if not sort_config:
            return notes

        result = list(notes)

        for sort_rule in reversed(
            sort_config
        ):

            if not isinstance(
                sort_rule,
                dict,
            ):
                continue

            prop = sort_rule.get(
                "property"
            )

            if not prop:
                continue

            direction = sort_rule.get(
                "direction",
                "ASC",
            )

            reverse = (
                str(direction).upper()
                == "DESC"
            )

            result.sort(
                key=lambda note: self._sort_value(
                    prop,
                    note,
                ),
                reverse=reverse,
            )

        return result

    def _sort_value(
        self,
        property_name,
        note,
    ):

        value = self._get_column_value(
            property_name,
            note,
        )

        try:
            return float(str(value))
        except (
            ValueError,
            TypeError,
        ):
            pass

        return str(value).lower()

    # ========================================================
    # Column values
    # ========================================================

    def _get_column_value(
        self,
        column,
        note,
    ):

        column = str(column)

        if column in (
            "file.name",
            "note.file.name",
        ):

            return self._link_to_note(note)

        if column == "file.path":

            return (
                str(
                    note["relative_path"]
                )
                .replace("\\", "/")
            )

        if column in (
            "file.tags",
            "tags",
        ):

            return ", ".join(
                note["tags"]
            )

        if column == "file.folder":

            return str(
                note["relative_path"].parent
            ).replace("\\", "/")

        if column.startswith(
            "formula."
        ):

            formula_name = column[
                len("formula.") :
            ]

            return self._evaluate_formula(
                formula_name,
                note,
            )

        if column.startswith(
            "note."
        ):

            column = column[
                len("note.") :
            ]

        value = note[
            "frontmatter"
        ].get(column)

        return self._format_value(value)

    # ========================================================
    # Formulas
    # ========================================================

    def _evaluate_formula(
        self,
        formula_name,
        note,
    ):

        properties = note["frontmatter"]

        # ----------------------------------------------------
        # Priority
        # ----------------------------------------------------

        if formula_name in (
            "Priority",
            "Status Priority Number",
        ):

            status = properties.get("status")

            status_note = self._resolve_link(
                status
            )

            if status_note:

                priority = (
                    status_note[
                        "frontmatter"
                    ].get("priority")
                )

                priority_note = (
                    self._resolve_link(
                        priority
                    )
                )

                if priority_note:

                    nested = (
                        priority_note[
                            "frontmatter"
                        ].get("priorityVal")
                    )

                    if nested is not None:
                        return str(nested)

                    return priority_note["name"]

                return self._format_value(
                    priority
                )

            return ""

        # ----------------------------------------------------
        # Feature Priority
        # ----------------------------------------------------

        if formula_name == "Feature Priority":

            features = self._property_values(
                note,
                "features",
            )

            if not features:
                return ""

            first = self._resolve_link(
                features[0]
            )

            if not first:
                return ""

            priority = first[
                "frontmatter"
            ].get("priority")

            priority_note = (
                self._resolve_link(priority)
            )

            priority_value = ""

            if priority_note:

                priority_value = (
                    priority_note[
                        "frontmatter"
                    ].get("priorityVal")
                )

                if priority_value is None:
                    priority_value = (
                        priority_note["name"]
                    )

            else:

                priority_value = (
                    self._format_value(
                        priority
                    )
                )

            return (
                f"{priority_value} | "
                f"{first['name']} | "
                f"{self._format_value(priority)}"
            )

        # ----------------------------------------------------
        # FirstFeature
        # ----------------------------------------------------

        if formula_name == "FirstFeature":

            features = self._property_values(
                note,
                "features",
            )

            resolved = []

            for feature in features:

                feature_note = (
                    self._resolve_link(feature)
                )

                if feature_note:

                    priority = (
                        feature_note[
                            "frontmatter"
                        ].get("priority")
                    )

                    resolved.append(
                        (
                            self._priority_sort_key(
                                priority
                            ),
                            feature_note["name"],
                        )
                    )

            resolved.sort(
                key=lambda item: item[0]
            )

            if resolved:

                return self._link_to_note(
                    self._resolve_link_by_name(
                        resolved[0][1]
                    )
                )

            return ""

        # ----------------------------------------------------
        # Feature Parent
        # ----------------------------------------------------

        if formula_name == "Feature Parent":

            features = self._property_values(
                note,
                "features",
            )

            if not features:
                return ""

            first = self._resolve_link(
                features[0]
            )

            if first:
                return first["name"]

            return self._format_value(
                features[0]
            )

        # ----------------------------------------------------
        # Untitled
        # ----------------------------------------------------

        if formula_name == "Untitled":

            features = self._property_values(
                note,
                "features",
            )

            if not features:
                return ""

            first = self._resolve_link(
                features[0]
            )

            if not first:
                return ""

            priority = (
                first[
                    "frontmatter"
                ].get("priority")
            )

            return (
                f"{self._format_value(priority)}"
                f" | {first['name']}"
            )

        # ----------------------------------------------------
        # auto-status
        # ----------------------------------------------------

        if formula_name == "auto-status":

            backlinks = self._find_backlinks(
                note
            )

            statuses = []

            for backlink in backlinks:

                if "task" not in backlink["tags"]:
                    continue

                status = backlink[
                    "frontmatter"
                ].get("status")

                if status:

                    statuses.append(
                        self._format_value(status)
                    )

            return ", ".join(statuses)

        # ----------------------------------------------------
        # FilterHighPriorities
        # ----------------------------------------------------

        if formula_name == "FilterHighPriorities":

            features = self._property_values(
                note,
                "features",
            )

            candidates = []

            for feature in features:

                feature_note = (
                    self._resolve_link(feature)
                )

                if not feature_note:
                    continue

                priority = (
                    feature_note[
                        "frontmatter"
                    ].get("priority")
                )

                candidates.append(
                    (
                        self._priority_sort_key(
                            priority
                        ),
                        feature_note["name"],
                    )
                )

            candidates.sort(
                key=lambda item: item[0]
            )

            if candidates:

                resolved = (
                    self._resolve_link_by_name(
                        candidates[0][1]
                    )
                )

                if resolved:
                    return resolved["name"]

            return ""

        return ""

    def _priority_sort_key(
        self,
        priority,
    ):

        resolved = self._resolve_link(
            priority
        )

        if resolved:

            value = (
                resolved[
                    "frontmatter"
                ].get("priorityVal")
            )

            try:
                return float(value)
            except (
                ValueError,
                TypeError,
            ):
                pass

            return str(
                value or resolved["name"]
            ).lower()

        try:
            return float(priority)
        except (
            ValueError,
            TypeError,
        ):
            pass

        return str(
            priority or ""
        ).lower()

    # ========================================================
    # Markdown table
    # ========================================================

    def _markdown_table(
        self,
        title,
        columns,
        rows,
    ):

        headers = [
            self._column_title(column)
            for column in columns
        ]

        output = []

        if title:

            output.append(
                f"### {title}"
            )

            output.append("")

        output.append(
            "| "
            + " | ".join(headers)
            + " |"
        )

        output.append(
            "| "
            + " | ".join(
                "---"
                for _ in headers
            )
            + " |"
        )

        for row in rows:

            output.append(
                "| "
                + " | ".join(
                    self._escape_table_cell(
                        str(value)
                    )
                    for value in row
                )
                + " |"
            )

        output.append("")

        return "\n".join(output)

    def _column_title(
        self,
        column,
    ):

        column = str(column)

        if column.startswith("formula."):

            column = column[
                len("formula.") :
            ]

        if column.startswith("note."):

            column = column[
                len("note.") :
            ]

        if column == "file.name":
            return "File"

        if column == "file.path":
            return "Path"

        if column == "file.tags":
            return "Tags"

        return (
            column
            .replace("_", " ")
            .replace(".", " ")
            .title()
        )

    def _escape_table_cell(
        self,
        value,
    ):

        return (
            value
            .replace("|", "\\|")
            .replace("\n", " ")
            .replace("\r", "")
        )

    # ========================================================
    # Frontmatter
    # ========================================================

    def _parse_frontmatter(
        self,
        markdown,
    ):

        if not markdown.startswith("---"):
            return {}

        lines = markdown.splitlines()

        if len(lines) < 3:
            return {}

        if lines[0].strip() != "---":
            return {}

        end = None

        for index in range(
            1,
            len(lines),
        ):

            if lines[index].strip() == "---":
                end = index
                break

        if end is None:
            return {}

        raw = "\n".join(
            lines[1:end]
        )

        try:

            data = yaml.safe_load(raw)

            if isinstance(data, dict):
                return data

        except Exception as exc:

            print(
                f"[StaticBases] WARNING: "
                f"Invalid frontmatter: "
                f"{exc}"
            )

        return {}

    # ========================================================
    # Tags
    # ========================================================

    def _get_tags(
        self,
        frontmatter,
    ):

        tags = frontmatter.get(
            "tags",
            [],
        )

        if isinstance(tags, str):
            tags = [tags]

        if not isinstance(tags, list):
            return []

        result = []

        for tag in tags:

            tag = str(tag).strip()

            if tag.startswith("#"):
                tag = tag[1:]

            result.append(
                tag.lower()
            )

        return result

    # ========================================================
    # Property helpers
    # ========================================================

    def _property_values(
        self,
        note,
        property_name,
    ):

        value = note[
            "frontmatter"
        ].get(property_name)

        if value is None:
            return []

        if isinstance(value, list):
            return value

        return [value]

    def _format_value(
        self,
        value,
    ):

        if value is None:
            return ""

        if isinstance(value, list):

            values = []

            for item in value:

                resolved = self._resolve_link(item)

                if resolved:

                    values.append(
                        self._link_to_note(
                            resolved
                        )
                    )

                else:

                    values.append(
                        str(item)
                    )

            return ", ".join(values)

        resolved = self._resolve_link(value)

        if resolved:

            return self._link_to_note(resolved)

        return str(value)

    # ========================================================
    # Obsidian links
    # ========================================================

    def _resolve_link(
        self,
        value,
    ):

        if not isinstance(value, str):
            return None

        match = WIKILINK_RE.search(value)

        if not match:
            return None

        name = match.group(1).strip()

        if not name:
            return None

        normalized_name = (
            name
            .replace("\\", "/")
            .strip("/")
        )

        if normalized_name.lower().endswith(".md"):

            key = (
                self.docs_dir
                / normalized_name
            ).as_posix().lower()

            if key in self.notes:
                return self.notes[key]

        key = name.lower()

        if key in self.notes:
            return self.notes[key]

        for note in self.notes.values():

            if note["name"].lower() == name.lower():
                return note

        return None

    def _resolve_link_by_name(
        self,
        name,
    ):

        if not name:
            return None

        for note in self.notes.values():

            if note["name"].lower() == str(name).lower():
                return note

        return None

    def _link_to_note(
        self,
        note,
    ):

        if not note:
            return ""

        relative = (
            note["relative_path"]
            .as_posix()
            .replace("\\", "/")
        )

        if relative.lower().endswith(".md"):
            relative = relative[:-3]

        parts = relative.split("/")

        encoded_parts = [
            quote(
                part,
                safe=".-_()",
            )
            for part in parts
        ]

        path = "/".join(encoded_parts)

        if self.use_directory_urls:

            href = (
                self.site_url_path
                + path
                + "/"
            )

            if relative.lower() == "index":

                href = self.site_url_path

            elif relative.lower().endswith("/index"):

                directory = path[:-len("/index")]

                href = (
                    self.site_url_path
                    + directory
                    + "/"
                )

        else:

            href = (
                self.site_url_path
                + path
                + ".html"
            )

        return (
            f"[{self._escape_link_text(note['name'])}]"
            f"({href})"
        )

    def _escape_link_text(
        self,
        value,
    ):

        return (
            str(value)
            .replace("[", "\\[")
            .replace("]", "\\]")
        )

    # ========================================================
    # Backlinks
    # ========================================================

    def _find_backlinks(
        self,
        target_note,
    ):

        result = []

        target_name = (
            target_note["name"]
            .lower()
        )

        seen = set()

        for note in self.notes.values():

            path = note["path"]

            if path in seen:
                continue

            seen.add(path)

            if path == target_note["path"]:
                continue

            try:

                text = path.read_text(
                    encoding="utf-8"
                )

            except Exception:
                continue

            for match in WIKILINK_RE.finditer(text):

                linked_name = (
                    match.group(1)
                    .strip()
                    .lower()
                )

                if linked_name == target_name:

                    result.append(note)

                    break

        return result

    def _has_backlink_to(
        self,
        note,
        current_file,
    ):

        if current_file is None:
            return False

        current_file = current_file.resolve()

        backlinks = self._find_backlinks(note)

        for backlink in backlinks:

            if backlink["path"].resolve() == current_file:
                return True

        return False

    # ========================================================
    # Utility
    # ========================================================

    def _contains(
        self,
        values,
        wanted,
    ):

        if isinstance(values, str):
            values = [values]

        wanted = str(wanted).strip().lower()

        wanted_no_hash = (
            wanted[1:]
            if wanted.startswith("#")
            else wanted
        )

        for value in values:

            value = str(value).strip()

            value_no_hash = (
                value[1:]
                if value.startswith("#")
                else value
            )

            # Direct comparison.
            if value.lower() == wanted:
                return True

            # Hash-insensitive comparison.
            if value_no_hash.lower() == wanted_no_hash:
                return True

            # Obsidian wikilink comparison.
            resolved = self._resolve_link(value)

            if resolved:

                if (
                    resolved["name"].lower()
                    == wanted_no_hash
                ):
                    return True

        return False

    def _is_conflict_file(
        self,
        path,
    ):

        return (
            "(relay conflict " in path.name
        )

    def _is_trash(
        self,
        path,
    ):

        return ".trash" in path.parts
