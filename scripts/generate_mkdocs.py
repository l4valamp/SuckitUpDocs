from __future__ import annotations

import re
import shutil
from pathlib import Path
from typing import Any

import yaml


# ============================================================
# CONFIG
# ============================================================

PROJECT_ROOT = Path(__file__).resolve().parent.parent

SOURCE_DOCS = PROJECT_ROOT / "docs"
GENERATED_DOCS = PROJECT_ROOT / ".mkdocs_docs"


# ============================================================
# FRONTMATTER
# ============================================================

FRONTMATTER_RE = re.compile(
    r"^---\s*\n(.*?)\n---\s*\n",
    re.DOTALL,
)


def read_frontmatter(path: Path) -> dict[str, Any]:
    """Read YAML frontmatter from a Markdown file."""

    try:
        text = path.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        return {}

    match = FRONTMATTER_RE.match(text)

    if not match:
        return {}

    try:
        data = yaml.safe_load(match.group(1))
        return data if isinstance(data, dict) else {}
    except yaml.YAMLError:
        return {}


# ============================================================
# PROPERTY HELPERS
# ============================================================

def normalize(value: Any) -> Any:
    """Turn Obsidian-style values into easier Python values."""

    if value is None:
        return None

    if isinstance(value, list):
        return [normalize(v) for v in value]

    if isinstance(value, dict):
        return {k: normalize(v) for k, v in value.items()}

    if isinstance(value, str):

        # [[Fireball]] -> Fireball
        if value.startswith("[[") and value.endswith("]]"):
            value = value[2:-2]

        return value

    return value


def property_values(
    data: dict[str, Any],
    key: str,
) -> list[str]:

    value = normalize(data.get(key))

    if value is None:
        return []

    if isinstance(value, list):
        return [str(v) for v in value]

    return [str(value)]


def has_tag(
    data: dict[str, Any],
    tag: str,
) -> bool:

    tags = property_values(
        data,
        "tags",
    )

    tag = tag.lstrip("#")

    return any(
        t.lstrip("#") == tag
        for t in tags
    )


# ============================================================
# DOCUMENT INDEX
# ============================================================

class Document:

    def __init__(
        self,
        path: Path,
        root: Path,
    ):

        self.path = path

        self.relative_path = (
            path.relative_to(root)
        )

        self.name = path.stem

        self.frontmatter = read_frontmatter(
            path
        )

    @property
    def tags(self):

        return property_values(
            self.frontmatter,
            "tags",
        )

    def has_tag(
        self,
        tag: str,
    ) -> bool:

        return has_tag(
            self.frontmatter,
            tag,
        )

    def values(
        self,
        property_name: str,
    ):

        return property_values(
            self.frontmatter,
            property_name,
        )

    def folder(self) -> str:

        return self.relative_path.parent.as_posix()

    def __repr__(self):

        return (
            f"<Document {self.relative_path}>"
        )


def build_document_index(
    root: Path,
) -> list[Document]:

    documents = []

    for path in root.rglob("*.md"):

        if ".trash" in path.parts:
            continue

        documents.append(
            Document(
                path,
                root,
            )
        )

    return documents


# ============================================================
# BASE FILE INDEX
# ============================================================

def build_base_index(
    root: Path,
) -> dict[str, list[Path]]:

    """
    Find every .base file.

    The dictionary is indexed by filename, while each
    Path remains relative to the generated documentation
    tree.

    Multiple files can have the same filename, so keep
    a list.
    """

    result: dict[str, list[Path]] = {}

    for path in root.rglob("*.base"):

        if ".trash" in path.parts:
            continue

        result.setdefault(
            path.name,
            [],
        ).append(path)

    return result


def load_base(
    path: Path,
) -> dict[str, Any]:

    try:

        data = yaml.safe_load(
            path.read_text(
                encoding="utf-8"
            )
        )

        return (
            data
            if isinstance(data, dict)
            else {}
        )

    except yaml.YAMLError as exc:

        print(
            f"WARNING: Could not parse {path}: {exc}"
        )

        return {}


# ============================================================
# BASE PATH RESOLUTION
# ============================================================

def resolve_base_path(
    base_reference: str,
    base_index: dict[str, list[Path]],
) -> Path | None:

    """
    Resolve an Obsidian Base reference.

    Examples supported:

        Needs.base

        Needs

        Suck It Up/Templates/Bases/Needs.base

        Suck It Up/Templates/Bases/Needs.base#TeamPage

    Resolution order:

    1. Exact vault-relative path.
    2. Filename fallback.
    3. Prefer non-relay-conflict copies.
    """

    reference = (
        base_reference
        .replace("\\", "/")
        .strip()
    )

    # Remove leading ./ if present.
    reference = re.sub(
        r"^\./",
        "",
        reference,
    )

    # Remove .base extension.
    if reference.lower().endswith(".base"):
        reference = reference[:-5]

    # --------------------------------------------------------
    # EXACT PATH
    # --------------------------------------------------------

    exact_path = (
        GENERATED_DOCS /
        f"{reference}.base"
    )

    if exact_path.exists():

        return exact_path

    # --------------------------------------------------------
    # FILENAME FALLBACK
    # --------------------------------------------------------

    filename = (
        Path(reference).name +
        ".base"
    )

    candidates = base_index.get(
        filename,
        [],
    )

    if not candidates:

        return None

    # --------------------------------------------------------
    # PREFER NON-CONFLICT COPY
    # --------------------------------------------------------

    candidates = sorted(
        candidates,
        key=lambda path:
            "relay conflict"
            in path.name.lower(),
    )

    return candidates[0]


# ============================================================
# FILTER EVALUATION
# ============================================================

def contains_property(
    doc: Document,
    property_name: str,
    target: Any,
) -> bool:

    values = doc.values(
        property_name
    )

    target = normalize(target)

    if isinstance(target, str):
        target = target.strip("#")

    return any(
        str(value).strip("#")
        == str(target)
        for value in values
    )


def evaluate_simple_condition(
    condition: Any,
    doc: Document,
    current_doc: Document | None = None,
) -> bool:

    if isinstance(condition, dict):

        if len(condition) == 1:

            key, value = next(
                iter(condition.items())
            )

            # ------------------------------------------------
            # file.tags.contains("needs")
            # ------------------------------------------------

            if key == "file.tags.contains":

                return has_tag(
                    doc,
                    str(value),
                )

            # ------------------------------------------------
            # features.contains(this)
            # ------------------------------------------------

            if key == "features.contains(this)":

                if current_doc is None:
                    return False

                return (
                    current_doc.name
                    in doc.values("features")
                )

            # ------------------------------------------------
            # teams.contains(this)
            # ------------------------------------------------

            if key == "teams.contains(this)":

                if current_doc is None:
                    return False

                return (
                    current_doc.name
                    in doc.values("teams")
                )

        return False

    # --------------------------------------------------------
    # Generic expression represented as a string.
    # --------------------------------------------------------

    if isinstance(condition, str):

        expression = condition.strip()

        # ----------------------------------------------------
        # file.tags.contains("needs")
        # ----------------------------------------------------

        match = re.match(
            r'file\.tags\.contains\(["\'](.+?)["\']\)',
            expression,
        )

        if match:

            return has_tag(
                doc,
                match.group(1),
            )

        # ----------------------------------------------------
        # this.hasTag("#feature")
        # ----------------------------------------------------

        match = re.match(
            r'this\.hasTag\(["\'](.+?)["\']\)',
            expression,
        )

        if match:

            if current_doc is None:
                return False

            return current_doc.has_tag(
                match.group(1)
            )

        # ----------------------------------------------------
        # features.contains(this)
        # ----------------------------------------------------

        if expression == "features.contains(this)":

            if current_doc is None:
                return False

            return (
                current_doc.name
                in doc.values("features")
            )

        # ----------------------------------------------------
        # teams.contains(this)
        # ----------------------------------------------------

        if expression == "teams.contains(this)":

            if current_doc is None:
                return False

            return (
                current_doc.name
                in doc.values("teams")
            )

        # ----------------------------------------------------
        # this.inFolder(...)
        # ----------------------------------------------------

        match = re.match(
            r'this\.inFolder\(["\'](.+?)["\']\)',
            expression,
        )

        if match:

            folder = (
                match.group(1)
                .replace("\\", "/")
            )

            return doc.folder().endswith(
                folder
            )

    return False


def evaluate_filter(
    filter_node: Any,
    doc: Document,
    current_doc: Document | None = None,
) -> bool:

    if filter_node is None:
        return True

    if isinstance(filter_node, str):

        return evaluate_simple_condition(
            filter_node,
            doc,
            current_doc,
        )

    if not isinstance(filter_node, dict):
        return True

    # --------------------------------------------------------
    # AND
    # --------------------------------------------------------

    if "and" in filter_node:

        conditions = filter_node["and"]

        return all(
            evaluate_filter(
                condition,
                doc,
                current_doc,
            )
            for condition in conditions
        )

    # --------------------------------------------------------
    # OR
    # --------------------------------------------------------

    if "or" in filter_node:

        conditions = filter_node["or"]

        return any(
            evaluate_filter(
                condition,
                doc,
                current_doc,
            )
            for condition in conditions
        )

    # --------------------------------------------------------
    # YAML form:
    #
    # file:
    #   tags:
    #     contains: needs
    # --------------------------------------------------------

    if "file" in filter_node:

        file_filter = (
            filter_node["file"]
        )

        if isinstance(
            file_filter,
            dict,
        ):

            tags_filter = (
                file_filter.get("tags")
            )

            if isinstance(
                tags_filter,
                dict,
            ):

                if "contains" in tags_filter:

                    return has_tag(
                        doc,
                        str(
                            tags_filter[
                                "contains"
                            ]
                        ),
                    )

    # --------------------------------------------------------
    # Otherwise simple expression.
    # --------------------------------------------------------

    return evaluate_simple_condition(
        filter_node,
        doc,
        current_doc,
    )


# ============================================================
# VIEW PROCESSING
# ============================================================

def find_view(
    base: dict[str, Any],
    view_name: str,
):

    for view in base.get(
        "views",
        [],
    ):

        if view.get("name") == view_name:

            return view

    return None


def display_value(
    value: Any,
) -> str:

    value = normalize(value)

    if value is None:
        return ""

    if isinstance(value, list):

        return ", ".join(
            display_value(v)
            for v in value
        )

    if isinstance(value, dict):

        return str(value)

    return str(value)


def make_link(
    value: str,
    current_file: Path,
) -> str:

    """
    Convert an Obsidian [[Page]] value into
    simple Markdown text.

    Link conversion is handled separately.
    """

    value = value.strip()

    if (
        value.startswith("[[")
        and value.endswith("]]")
    ):

        value = value[2:-2]

    if "|" in value:

        value = value.split(
            "|",
            1,
        )[0]

    return value


def render_property(
    doc: Document,
    property_name: str,
) -> str:

    values = doc.values(
        property_name
    )

    if not values:
        return ""

    rendered = []

    for value in values:

        rendered.append(
            make_link(
                value,
                doc.path,
            )
        )

    return ", ".join(
        rendered
    )


# ============================================================
# TABLE GENERATION
# ============================================================

def generate_table(
    documents: list[Document],
    view: dict[str, Any],
    current_doc: Document | None = None,
) -> str:

    filters = view.get(
        "filters"
    )

    matching = []

    for doc in documents:

        if evaluate_filter(
            filters,
            doc,
            current_doc,
        ):

            matching.append(doc)

    # --------------------------------------------------------
    # SORTING
    # --------------------------------------------------------

    sorts = view.get(
        "sort",
        [],
    )

    for sort in reversed(sorts):

        property_name = sort.get(
            "property"
        )

        direction = (
            sort.get(
                "direction",
                "ASC",
            )
            .upper()
        )

        if property_name == "file.name":

            matching.sort(
                key=lambda d:
                    d.name.lower(),
                reverse=(
                    direction == "DESC"
                ),
            )

        elif property_name:

            matching.sort(
                key=lambda d:
                    display_value(
                        d.frontmatter.get(
                            property_name,
                            "",
                        )
                    ).lower(),
                reverse=(
                    direction == "DESC"
                ),
            )

    # --------------------------------------------------------
    # COLUMNS
    # --------------------------------------------------------

    order = view.get(
        "order"
    )

    if order:

        columns = order

    else:

        columns = [
            "file.name",
            "status",
            "teams",
            "features",
        ]

    # --------------------------------------------------------
    # HEADERS
    # --------------------------------------------------------

    headers = []

    for column in columns:

        if column == "file.name":

            headers.append(
                "Name"
            )

        elif column.startswith(
            "formula."
        ):

            headers.append(
                column.replace(
                    "formula.",
                    "",
                )
            )

        else:

            headers.append(
                column
                .replace(
                    "note.",
                    "",
                )
                .replace(
                    "_",
                    " ",
                )
                .title()
            )

    lines = []

    lines.append(
        "| " +
        " | ".join(headers) +
        " |"
    )

    lines.append(
        "| " +
        " | ".join(
            "---"
            for _ in headers
        ) +
        " |"
    )

    # --------------------------------------------------------
    # ROWS
    # --------------------------------------------------------

    for doc in matching:

        values = []

        for column in columns:

            if column == "file.name":

                value = doc.name

            elif column.startswith(
                "formula."
            ):

                value = ""

            else:

                property_name = (
                    column.replace(
                        "note.",
                        "",
                    )
                )

                value = render_property(
                    doc,
                    property_name,
                )

            # Escape Markdown table characters.
            value = value.replace(
                "|",
                "\\|",
            )

            value = value.replace(
                "\n",
                " ",
            )

            values.append(
                value
            )

        lines.append(
            "| " +
            " | ".join(values) +
            " |"
        )

    # --------------------------------------------------------
    # EMPTY RESULT
    # --------------------------------------------------------

    if not matching:

        lines.append(
            "| " +
            " | ".join(
                "No matching pages"
                if i == 0
                else ""
                for i in range(
                    len(headers)
                )
            ) +
            " |"
        )

    return "\n".join(lines)


# ============================================================
# EMBED PROCESSING
# ============================================================

BASE_EMBED_RE = re.compile(
    r'!\[\[([^\]]+?)\.base(?:#([^\]]+))?\]\]',
    re.IGNORECASE,
)


def process_markdown(
    path: Path,
    base_index: dict[str, list[Path]],
    documents: list[Document],
    source_root: Path,
) -> None:

    text = path.read_text(
        encoding="utf-8"
    )

    matches = list(
        BASE_EMBED_RE.finditer(text)
    )

    if not matches:
        return

    current_doc = Document(
        path,
        source_root,
    )

    def replace(match):

        # ----------------------------------------------------
        # EXTRACT BASE REFERENCE
        # ----------------------------------------------------

        base_reference = (
            match.group(1)
            .replace("\\", "/")
            .strip()
        )

        view_name = match.group(2)

        print(
            "Processing Base embed:",
            base_reference,
            f"(view: {view_name or 'default'})",
        )

        # ----------------------------------------------------
        # RESOLVE BASE
        # ----------------------------------------------------

        base_path = resolve_base_path(
            base_reference,
            base_index,
        )

        if base_path is None:

            print(
                "WARNING: Could not find base:",
                base_reference,
            )

            return match.group(0)

        print(
            "Resolved Base:",
            base_path.relative_to(
                GENERATED_DOCS
            ),
        )

        # ----------------------------------------------------
        # LOAD BASE
        # ----------------------------------------------------

        base = load_base(
            base_path
        )

        if not base:

            print(
                "WARNING: Base is empty or could not be loaded:",
                base_path,
            )

            return match.group(0)

        # ----------------------------------------------------
        # SELECT VIEW
        # ----------------------------------------------------

        if view_name:

            view = find_view(
                base,
                view_name,
            )

            if view is None:

                print(
                    f"WARNING: View '{view_name}' "
                    f"not found in {base_path}"
                )

                return match.group(0)

        else:

            views = base.get(
                "views",
                [],
            )

            if not views:

                print(
                    "WARNING: Base has no views:",
                    base_path,
                )

                return match.group(0)

            view = views[0]

        # ----------------------------------------------------
        # GENERATE TABLE
        # ----------------------------------------------------

        table = generate_table(
            documents,
            view,
            current_doc=current_doc,
        )

        return table

    new_text = BASE_EMBED_RE.sub(
        replace,
        text,
    )

    path.write_text(
        new_text,
        encoding="utf-8",
    )


# ============================================================
# MAIN
# ============================================================

def main():

    print(
        "Generating MkDocs documentation..."
    )

    # --------------------------------------------------------
    # VERIFY SOURCE
    # --------------------------------------------------------

    if not SOURCE_DOCS.exists():

        raise FileNotFoundError(
            f"Source docs directory does not exist: "
            f"{SOURCE_DOCS}"
        )

    # --------------------------------------------------------
    # RECREATE GENERATED DOCS
    # --------------------------------------------------------

    if GENERATED_DOCS.exists():

        print(
            f"Removing old generated docs: "
            f"{GENERATED_DOCS}"
        )

        shutil.rmtree(
            GENERATED_DOCS
        )

    print(
        f"Copying entire docs tree to: "
        f"{GENERATED_DOCS}"
    )

    shutil.copytree(
        SOURCE_DOCS,
        GENERATED_DOCS,
    )

    # --------------------------------------------------------
    # INDEX GENERATED FILES
    # --------------------------------------------------------

    documents = build_document_index(
        GENERATED_DOCS
    )

    base_index = build_base_index(
        GENERATED_DOCS
    )

    print(
        f"Found {len(documents)} Markdown files."
    )

    print(
        f"Found "
        f"{sum(len(v) for v in base_index.values())} "
        f".base files."
    )

    # --------------------------------------------------------
    # SHOW BASE FILES
    # --------------------------------------------------------

    print(
        "Base files:"
    )

    for filename, paths in sorted(
        base_index.items()
    ):

        for base_path in paths:

            print(
                "  ",
                base_path.relative_to(
                    GENERATED_DOCS
                ),
            )

    # --------------------------------------------------------
    # PROCESS MARKDOWN
    # --------------------------------------------------------

    for path in GENERATED_DOCS.rglob(
        "*.md"
    ):

        if ".trash" in path.parts:
            continue

        process_markdown(
            path,
            base_index,
            documents,
            GENERATED_DOCS,
        )

    # --------------------------------------------------------
    # FINAL REPORT
    # --------------------------------------------------------

    generated_markdown = list(
        GENERATED_DOCS.rglob("*.md")
    )

    generated_bases = list(
        GENERATED_DOCS.rglob("*.base")
    )

    print()
    print(
        "============================================"
    )

    print(
        "MkDocs generation complete."
    )

    print(
        f"Markdown files: {len(generated_markdown)}"
    )

    print(
        f"Base files:     {len(generated_bases)}"
    )

    print(
        f"Output:         {GENERATED_DOCS}"
    )

    print(
        "============================================"
    )


if __name__ == "__main__":

    main()
