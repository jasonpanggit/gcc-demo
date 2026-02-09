#!/usr/bin/env python3
"""Fetch Azure MCP tool documentation and generate structured metadata.

This script crawls the Azure MCP Server tools documentation starting from the
"Available tools" table and produces a JSON metadata file with quick examples
and parameter descriptions for every documented tool.

Usage:
    python app/agentic/eol/deploy/update_mcp_tool_metadata.py

The script writes JSON output to
    app/agentic/eol/static/data/azure_mcp_tool_metadata.json
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Tuple

from bs4 import BeautifulSoup, NavigableString, Tag
from urllib import request
from urllib.parse import parse_qsl, urljoin, urlparse, urlunparse

BASE_URL = "https://learn.microsoft.com/en-us/azure/developer/azure-mcp-server/tools/"
OUTPUT_PATH = (
    Path(__file__).resolve()
    .parent
    .parent
    / "static"
    / "data"
    / "azure_mcp_tool_metadata.json"
)
USER_AGENT = (
    "Mozilla/5.0 (compatible; AzureMcpMetadataBot/1.0; "
    "+https://github.com/microsoft/mcp)"
)
MICROSOFT_LEARN_DOC_URL = "https://learn.microsoft.com/en-us/training/browse/"

CATEGORY_REWRITE = {
    "Best practices": "Guidance & Best Practices",
    "Analytics": "Analytics",
    "AI and Machine Learning": "AI & Machine Learning",
    "Compute": "Compute",
    "Containers": "Compute & Containers",
    "Databases": "Storage & Databases",
    "Developer tools": "Developer Tools",
    "DevOps": "DevOps & Deployment",
    "Hybrid and multicloud": "Hybrid & Multicloud",
    "Identity": "Security & Identity",
    "Integration": "Networking & Messaging",
    "Internet of Things (IoT)": "IoT",
    "Management and governance": "Monitoring & Management",
    "Messaging": "Networking & Messaging",
    "Mobile": "Mobile",
    "Security": "Security & Identity",
    "Storage": "Storage & Databases",
    "Virtual desktop infrastructure (VDI)": "Virtual Desktop",
    "Web": "Web & App Services",
    "Other": "Other",
}


@dataclass
class ExamplePrompt:
    label: str
    prompt: str
    parameter_names: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, object]:
        placeholder_pairs: List[Tuple[str, str, int, int]] = []
        seen: set[str] = set()
        for index, name in enumerate(self.parameter_names):
            if not name:
                continue
            token = format_placeholder(name)
            if token in seen:
                continue
            seen.add(token)
            priority = _placeholder_sort_key(self.prompt, name, token)
            placeholder_pairs.append((token, name, index, priority))

        placeholder_pairs.sort(
            key=lambda item: (
                item[3],
                item[2],
            )
        )

        sanitized_prompt = apply_placeholder_tokens(
            self.prompt, [(token, name, priority) for token, name, _, priority in placeholder_pairs]
        )

        payload: Dict[str, object] = {
            "label": self.label,
            "prompt": sanitized_prompt,
            "original_prompt": self.prompt,
        }

        if placeholder_pairs:
            payload["parameter_placeholders"] = [
                f"<{token}>" for token, _, _, _ in placeholder_pairs
            ]

        return payload


@dataclass
class ToolParameter:
    name: str
    required: bool
    description: str
    options: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, object]:
        payload: Dict[str, object] = {
            "name": self.name,
            "required": self.required,
            "description": self.description,
        }
        if self.options:
            payload["options"] = self.options
        return payload


@dataclass
class ToolOperation:
    title: str
    description: str
    examples: List[ExamplePrompt] = field(default_factory=list)
    parameters: List[ToolParameter] = field(default_factory=list)

    def to_dict(self) -> Dict[str, object]:
        payload: Dict[str, object] = {
            "title": self.title,
            "description": self.description,
        }
        if self.examples:
            payload["examples"] = [example.to_dict() for example in self.examples]
        if self.parameters:
            payload["parameters"] = [param.to_dict() for param in self.parameters]
        return payload


@dataclass
class ToolMetadata:
    slug: str
    display_name: str
    category: str
    namespace: str
    description: str
    doc_url: str
    source_url: str
    fragment: Optional[str] = None
    query_params: Dict[str, str] = field(default_factory=dict)
    operations: List[ToolOperation] = field(default_factory=list)

    def to_dict(self) -> Dict[str, object]:
        flattened_examples: List[Dict[str, str]] = []
        for op in self.operations:
            for example in op.examples:
                flattened_examples.append(example.to_dict())

        flattened_params: List[Dict[str, object]] = []
        for op in self.operations:
            for parameter in op.parameters:
                flattened_params.append(parameter.to_dict())

        payload: Dict[str, object] = {
            "slug": self.slug,
            "display_name": self.display_name,
            "category": self.category,
            "namespace": self.namespace,
            "description": self.description,
            "doc_url": self.doc_url,
        }
        if flattened_examples:
            payload["examples"] = flattened_examples
        if flattened_params:
            payload["parameters"] = flattened_params
        if self.operations:
            payload["operations"] = [operation.to_dict() for operation in self.operations]
        return payload


def normalize_category(raw_category: str) -> str:
    raw_category = raw_category.strip()
    return CATEGORY_REWRITE.get(raw_category, raw_category)


def slugify(text: str) -> str:
    normalized = re.sub(r"[^a-z0-9]+", "-", text.strip().lower())
    return normalized.strip("-")


def format_placeholder(name: str) -> str:
    slug = slugify(name)
    return slug or "value"


def _placeholder_sort_key(prompt: str, name: str, token: str) -> int:
    prompt_lower = prompt.lower()
    name_tokens = [segment.lower() for segment in re.split(r"[\s/_-]+", name or "") if segment]
    if name_tokens:
        primary = name_tokens[-1]
        if primary and primary in prompt_lower:
            return 0
        for token_candidate in name_tokens[:-1]:
            if token_candidate and token_candidate in prompt_lower:
                return 1
    token_slug = token.lower() if token else ""
    if token_slug and token_slug in prompt_lower:
        return 2
    return 3


STOPWORDS = {
    "show",
    "list",
    "get",
    "create",
    "update",
    "delete",
    "for",
    "in",
    "the",
    "a",
    "an",
    "my",
    "all",
    "from",
    "to",
    "and",
    "with",
    "of",
    "by",
    "on",
    "last",
    "hour",
    "hours",
    "minutes",
    "minute",
    "seconds",
    "second",
    "resource",
    "resources",
    "workspace",
    "workspaces",
    "group",
    "groups",
    "subscription",
    "subscriptions",
    "logs",
    "entries",
    "only",
    "virtual",
    "machine",
    "machines",
    "test",
    "tests",
    "web",
    "list",
    "details",
    "information",
    "status",
    "name",
    "id",
    "value",
}

CONTEXT_WORDS = {
    "azure",
    "data",
    "explorer",
    "adx",
    "default",
    "sample",
    "example",
    "my",
    "the",
    "this",
    "that",
    "your",
    "their",
    "status",
    "details",
    "information",
    "for",
    "to",
    "in",
    "on",
    "at",
    "by",
    "from",
    "with",
    "of",
    "using",
    "through",
}


def apply_placeholder_tokens(prompt: str, placeholders: List[Tuple[str, str, int]]) -> str:
    sanitized = prompt
    appended_count = 0
    for placeholder, name, priority in placeholders:
        allow_keyword_strategies = priority <= 2
        sanitized, replaced = _replace_placeholder_token(
            sanitized, placeholder, name, allow_keyword_strategies
        )
        if not replaced:
            sanitized, appended_count = _append_placeholder(
                sanitized, placeholder, name, appended_count
            )
    return sanitized


def _replace_placeholder_token(
    text: str, placeholder: str, name: str, allow_keyword_strategies: bool
) -> Tuple[str, bool]:
    keywords, primary_keywords = _prepare_keywords(name, placeholder)
    strategies = [
        lambda value: _replace_contextual_quoted_sequence(value, placeholder, keywords),
        lambda value: _replace_path_sequence(value, placeholder),
    ]
    if allow_keyword_strategies:
        strategies.extend(
            [
                lambda value: _replace_keyword_neighbor(value, placeholder, primary_keywords),
                lambda value: _replace_keyword_following(value, placeholder, primary_keywords),
                lambda value: _insert_after_keyword(value, placeholder, primary_keywords),
            ]
        )

    for strategy in strategies:
        updated = strategy(text)
        if updated is not None:
            return updated, True
    return text, False


def _prepare_keywords(name: str, placeholder: str) -> Tuple[List[str], List[str]]:
    name_tokens = [token.lower() for token in re.split(r"[\s/_-]+", name or "") if token]
    placeholder_tokens = [token.lower() for token in re.split(r"[\s/_-]+", placeholder or "") if token]

    keywords: List[str] = []
    primary_tokens: List[str] = []

    if name_tokens:
        primary_tokens.append(name_tokens[-1])
        keywords.extend(name_tokens)

    for token in placeholder_tokens:
        if token not in keywords:
            keywords.append(token)

    deduped: List[str] = []
    for token in keywords:
        if token not in deduped:
            deduped.append(token)

    deduped_primary: List[str] = []
    for token in primary_tokens:
        if token in deduped and token not in deduped_primary:
            deduped_primary.append(token)

    if not deduped_primary and deduped:
        deduped_primary.append(deduped[0])

    return deduped or [placeholder], deduped_primary or [placeholder]


def _replace_contextual_quoted_sequence(text: str, placeholder: str, keywords: List[str]) -> Optional[str]:
    for match in re.finditer(r"(['\"])(.+?)\1", text):
        before = text[: match.start()]
        after = text[match.end() :]
        preceding_words = re.findall(r"\b[A-Za-z0-9][A-Za-z0-9_\-.]*\b", before)[-3:]
        following_words = re.findall(r"\b[A-Za-z0-9][A-Za-z0-9_\-.]*\b", after)[:3]
        context_words = [word.lower() for word in preceding_words + following_words]
        for keyword in keywords:
            if keyword and keyword.lower() in context_words:
                return f"{text[:match.start()]}<{placeholder}>{text[match.end():]}"
    return None


def _replace_path_sequence(text: str, placeholder: str) -> Optional[str]:
    match = re.search(r"/[A-Za-z0-9][A-Za-z0-9_./\-]*", text)
    if not match:
        return None
    return f"{text[:match.start()]}<{placeholder}>{text[match.end():]}"


def _insert_after_keyword(text: str, placeholder: str, keywords: List[str]) -> Optional[str]:
    for keyword in keywords:
        if not keyword:
            continue
        pattern = re.compile(rf"\b({re.escape(keyword)})\b", re.IGNORECASE)
        match = pattern.search(text)
        if match:
            if match.start() > 0 and text[match.start() - 1] == "<":
                continue
            # Avoid inserting if placeholder already follows keyword.
            following = text[match.end() : match.end() + len(placeholder) + 2]
            if following.startswith(f" <{placeholder}>"):
                return None
            return f"{text[:match.end()]} <{placeholder}>{text[match.end():]}"
    return None


def _replace_keyword_neighbor(text: str, placeholder: str, keywords: List[str]) -> Optional[str]:
    for keyword in keywords:
        if not keyword:
            continue
        pattern = re.compile(rf"\b([A-Za-z0-9][A-Za-z0-9_\-.]*)\s+({re.escape(keyword)})\b", re.IGNORECASE)
        match = pattern.search(text)
        if match:
            if match.start(1) > 0 and text[match.start(1) - 1] == "<":
                continue
            if match.group(1).startswith("<"):
                continue
            if match.group(1).lower() in CONTEXT_WORDS:
                continue
            return f"{text[:match.start(1)]}<{placeholder}>{text[match.end(1):]}"
    return None


def _replace_keyword_following(text: str, placeholder: str, keywords: List[str]) -> Optional[str]:
    for keyword in keywords:
        if not keyword:
            continue
        pattern = re.compile(rf"\b({re.escape(keyword)})\s+([A-Za-z0-9][A-Za-z0-9_\-.]*)\b", re.IGNORECASE)
        match = pattern.search(text)
        if match:
            if match.start(2) > 0 and text[match.start(2) - 1] == "<":
                continue
            if match.group(2).startswith("<"):
                continue
            if match.group(2).lower() in CONTEXT_WORDS:
                continue
            return f"{text[:match.start(2)]}<{placeholder}>{text[match.end(2):]}"
    return None


def _append_placeholder(
    text: str, placeholder: str, name: str, appended_count: int
) -> Tuple[str, int]:
    descriptor_tokens = [token for token in re.split(r"[\s/_-]+", name or "") if token]
    descriptor = " ".join(descriptor_tokens) if descriptor_tokens else "value"
    base = text.rstrip()
    if not base:
        return f"Use <{placeholder}> for {descriptor}.", appended_count + 1

    trailing_punct = ""
    if base[-1] in ".!?":
        trailing_punct = base[-1]
        base = base.rstrip(".!?")

    connector = " using" if appended_count == 0 else " and"
    phrase = f"{connector} <{placeholder}> for {descriptor}"
    updated = f"{base}{phrase}"
    terminal = trailing_punct or "."
    return f"{updated}{terminal}", appended_count + 1


class MCPMetadataCrawler:
    def __init__(self) -> None:
        self.headers = {"User-Agent": USER_AGENT}

    def fetch_html(self, url: str) -> BeautifulSoup:
        print(f"📡 Fetching: {url}")
        req = request.Request(url, headers=self.headers)
        with request.urlopen(req, timeout=30.0) as response:
            html = response.read().decode("utf-8", errors="ignore")
        return BeautifulSoup(html, "lxml")

    def crawl(self) -> Dict[str, ToolMetadata]:
        print("\n🔍 Starting Azure MCP tool metadata crawl...")
        print(f"📖 Base URL: {BASE_URL}\n")
        
        soup = self.fetch_html(BASE_URL)
        print("\n📋 Parsing tool index...")
        tool_index = self._parse_index_tables(soup)
        print(f"✅ Found {len(tool_index)} tools in index\n")
        
        print("📝 Fetching detailed documentation for each tool...")
        for idx, (slug, metadata) in enumerate(tool_index.items(), 1):
            print(f"   [{idx}/{len(tool_index)}] {metadata.display_name}")
            detail_soup = self.fetch_html(metadata.source_url)
            operations = self._parse_tool_detail(detail_soup, metadata)
            metadata.operations = operations
            print(f"      → {len(operations)} operation(s) found")
        
        print(f"\n✅ Crawl complete: {len(tool_index)} tools processed\n")
        return tool_index

    def _parse_index_tables(self, soup: BeautifulSoup) -> Dict[str, ToolMetadata]:
        tool_index: Dict[str, ToolMetadata] = {}
        section_anchor = soup.find(id="available-tools")
        if not section_anchor:
            return tool_index

        current_category: Optional[str] = None
        for sibling in section_anchor.next_siblings:
            if isinstance(sibling, NavigableString):
                continue
            if isinstance(sibling, Tag):
                if sibling.name == "h2":
                    title = sibling.get_text(strip=True)
                    if title and title.lower() in {"related content", "feedback"}:
                        break
                    current_category = normalize_category(title) if title else None
                    continue
                if sibling.name == "h3":
                    title = sibling.get_text(strip=True)
                    current_category = normalize_category(title) if title else current_category
                    continue
                if sibling.name == "table" and current_category:
                    for row in sibling.find_all("tr"):
                        cells = row.find_all(["td", "th"])
                        if len(cells) < 3:
                            continue
                        if all(cell.name == "th" for cell in cells):
                            continue
                        name_cell = cells[0]
                        namespace_cell = cells[1]
                        description_cell = cells[2]

                        link = name_cell.find("a")
                        link_info = self._parse_tool_link(link.get("href")) if link else None
                        if not link_info:
                            continue
                        link_slug, doc_url, source_url, fragment, query_params = link_info
                        display_name = name_cell.get_text(" ", strip=True)
                        namespace = namespace_cell.get_text(" ", strip=True)
                        description = description_cell.get_text(" ", strip=True)

                        base_slug = slugify(display_name) if display_name else link_slug
                        slug = base_slug or link_slug
                        if slug in tool_index:
                            category_slug = slugify(current_category or "category")
                            if category_slug:
                                slug_candidate = f"{base_slug or link_slug}__category-{category_slug}"
                                if slug_candidate not in tool_index:
                                    slug = slug_candidate
                                else:
                                    slug = self._dedupe_slug(slug_candidate, tool_index)
                            else:
                                slug = self._dedupe_slug(slug, tool_index)

                        tool_index[slug] = ToolMetadata(
                            slug=slug,
                            display_name=display_name,
                            category=current_category,
                            namespace=namespace,
                            description=description,
                            doc_url=doc_url,
                            source_url=source_url,
                            fragment=fragment,
                            query_params=query_params,
                        )
        return tool_index

    def _dedupe_slug(self, slug: str, tool_index: Dict[str, ToolMetadata]) -> str:
        counter = 2
        new_slug = f"{slug}__{counter}"
        while new_slug in tool_index:
            counter += 1
            new_slug = f"{slug}__{counter}"
        return new_slug

    def _parse_tool_detail(self, soup: BeautifulSoup, metadata: ToolMetadata) -> List[ToolOperation]:
        operations: List[ToolOperation] = []
        for heading in soup.find_all("h2"):
            title = heading.get_text(strip=True)
            if not title:
                continue

            normalized_title = title.strip().lower()
            if normalized_title in {"feedback", "related resources", "additional links"}:
                continue

            section_nodes = list(self._iter_section_nodes(heading))
            description = self._collect_description(section_nodes)
            parameters = self._collect_parameters(section_nodes)
            examples = self._collect_examples(section_nodes, parameters)

            # Skip empty sections that don't describe tool operations.
            if not any([description, examples, parameters]):
                continue

            operations.append(
                ToolOperation(
                    title=title,
                    description=description,
                    examples=examples,
                    parameters=parameters,
                )
            )
        if metadata.fragment:
            operations = self._filter_operations_by_fragment(metadata.fragment, operations)
        return operations

    def _iter_section_nodes(self, heading: Tag) -> Iterable[Tag]:
        for sibling in heading.next_siblings:
            if isinstance(sibling, Tag):
                if sibling.name == "h2":
                    break
                yield sibling

    def _parse_tool_link(
        self, href: Optional[str]
    ) -> Optional[Tuple[str, str, str, Optional[str], Dict[str, str]]]:
        if not href:
            return None

        href = href.strip()
        if not href:
            return None

        absolute_url = urljoin(BASE_URL, href)
        parsed = urlparse(absolute_url)
        path_parts = [part for part in parsed.path.split("/") if part]
        if not path_parts:
            return None

        base_slug = path_parts[-1]
        if not base_slug or base_slug == "index":
            return None

        query_params = dict(parse_qsl(parsed.query, keep_blank_values=False))
        fragment = parsed.fragment or None

        suffixes: List[str] = []
        if query_params:
            for key, value in sorted(query_params.items()):
                key_slug = slugify(key)
                value_slug = slugify(value) if value else ""
                suffixes.append(f"{key_slug}-{value_slug}" if value_slug else key_slug)
        if fragment:
            fragment_slug = slugify(fragment)
            if fragment_slug:
                suffixes.append(f"section-{fragment_slug}")

        slug = base_slug
        if suffixes:
            slug = f"{base_slug}__{'__'.join(suffixes)}"

        source_url = urlunparse(parsed._replace(query="", fragment=""))
        return slug, absolute_url, source_url, fragment, query_params

    def _filter_operations_by_fragment(
        self, fragment: str, operations: List[ToolOperation]
    ) -> List[ToolOperation]:
        if not fragment:
            return operations

        target = slugify(fragment)
        matched: List[ToolOperation] = []
        for operation in operations:
            section = operation.title.split(":", 1)[0]
            section_slug = slugify(section)
            if section_slug == target:
                matched.append(operation)

        return matched or operations

    def _collect_description(self, nodes: Iterable[Tag]) -> str:
        paragraphs: List[str] = []
        for node in nodes:
            if isinstance(node, Tag) and node.name in {"p", "div"}:
                text = node.get_text(" ", strip=True)
                if text and not text.lower().startswith("example prompts include"):
                    paragraphs.append(text)
        return "\n\n".join(paragraphs)

    def _collect_examples(
        self, nodes: Iterable[Tag], parameters: List[ToolParameter]
    ) -> List[ExamplePrompt]:
        examples: List[ExamplePrompt] = []
        expect_list = False
        for node in nodes:
            if isinstance(node, NavigableString):
                continue
            text = node.get_text(" ", strip=True) if isinstance(node, Tag) else ""
            if expect_list and isinstance(node, Tag) and node.name in {"ul", "ol"}:
                for li in node.find_all("li", recursive=False):
                    example_text = li.get_text(" ", strip=True)
                    if not example_text:
                        continue
                    label, prompt = self._split_example(example_text)
                    examples.append(
                        ExamplePrompt(
                            label=label,
                            prompt=prompt,
                            parameter_names=[param.name for param in parameters if param.name],
                        )
                    )
                expect_list = False
            if isinstance(node, Tag) and text:
                if "Example prompts include" in text:
                    expect_list = True
        return examples

    def _split_example(self, text: str) -> Tuple[str, str]:
        if ":" in text:
            label, prompt = text.split(":", 1)
            label = label.strip()
            prompt = prompt.strip().strip("\"").strip()
            return label, prompt or label
        return text, text

    def _collect_parameters(self, nodes: Iterable[Tag]) -> List[ToolParameter]:
        parameters: List[ToolParameter] = []
        for node in nodes:
            if isinstance(node, Tag) and node.name == "table":
                headers = [th.get_text(" ", strip=True).lower() for th in node.find_all("th")]
                if not headers or "parameter" not in headers[0]:
                    continue
                for row in node.find_all("tr"):
                    cells = row.find_all(["td", "th"])
                    if len(cells) < 2:
                        continue
                    name = cells[0].get_text(" ", strip=True)
                    if not name or name.lower() in {"parameter", "name"}:
                        continue
                    requirement = cells[1].get_text(" ", strip=True)
                    required = "required" in requirement.lower()
                    description = cells[2].get_text(" ", strip=True) if len(cells) > 2 else ""
                    options = self._extract_options(description)
                    parameters.append(
                        ToolParameter(
                            name=name,
                            required=required,
                            description=description,
                            options=options,
                        )
                    )
        return parameters

    def _extract_options(self, text: str) -> List[str]:
        options = re.findall(r"'([^']+)'", text)
        cleaned = []
        for option in options:
            value = option.strip()
            if value:
                cleaned.append(value)
        return cleaned


def _manual_microsoft_learn_tools() -> Dict[str, ToolMetadata]:
    tools: List[ToolMetadata] = []

    tools.append(
        ToolMetadata(
            slug="microsoft-learn-search-learning-paths",
            display_name="Microsoft Learn · Search learning paths",
            category="Microsoft Learn",
            namespace="microsoft_learn.searchLearningPaths",
            description="Search Microsoft Learn for learning paths aligned to certification exams or keywords.",
            doc_url=MICROSOFT_LEARN_DOC_URL,
            source_url=MICROSOFT_LEARN_DOC_URL,
            operations=[
                ToolOperation(
                    title="Search learning paths",
                    description="Find Microsoft Learn learning paths by certification exam, Azure role, or topic keyword.",
                    parameters=[
                        ToolParameter(
                            name="Query",
                            required=True,
                            description="Keyword, certification exam number, or topic to match across Microsoft Learn learning paths.",
                        ),
                        ToolParameter(
                            name="Role",
                            required=False,
                            description="Optional Azure job role focus, such as administrator, developer, or security-engineer.",
                        ),
                        ToolParameter(
                            name="Language",
                            required=False,
                            description="Preferred content language code like en or fr for localized learning paths.",
                        ),
                    ],
                    examples=[
                        ExamplePrompt(
                            label="Exam aligned learning paths",
                            prompt="Find Microsoft Learn learning paths to prepare for the AZ-104 exam",
                            parameter_names=["Query", "Language"],
                        ),
                        ExamplePrompt(
                            label="Role focused learning paths",
                            prompt="Show learning paths for Azure administrator responsibilities",
                            parameter_names=["Query", "Role"],
                        ),
                        ExamplePrompt(
                            label="Topic keyword search",
                            prompt="Search for learning paths that cover Azure monitoring skills",
                            parameter_names=["Query"],
                        ),
                    ],
                )
            ],
        )
    )

    tools.append(
        ToolMetadata(
            slug="microsoft-learn-list-modules-by-topic",
            display_name="Microsoft Learn · List modules by topic",
            category="Microsoft Learn",
            namespace="microsoft_learn.listModulesByTopic",
            description="List Microsoft Learn modules for a topic with duration and unit counts.",
            doc_url=MICROSOFT_LEARN_DOC_URL,
            source_url=MICROSOFT_LEARN_DOC_URL,
            operations=[
                ToolOperation(
                    title="List modules by topic",
                    description="Discover Microsoft Learn modules grouped by topic, difficulty, and estimated duration.",
                    parameters=[
                        ToolParameter(
                            name="Topic",
                            required=True,
                            description="Microsoft Learn topic or product focus, such as Azure networking or AI services.",
                        ),
                        ToolParameter(
                            name="Level",
                            required=False,
                            description="Optional difficulty filter like beginner, intermediate, or advanced.",
                        ),
                        ToolParameter(
                            name="Language",
                            required=False,
                            description="Preferred content language code like en or es for localized modules.",
                        ),
                    ],
                    examples=[
                        ExamplePrompt(
                            label="Beginner modules for a topic",
                            prompt="List beginner modules about Azure networking",
                            parameter_names=["Topic", "Level"],
                        ),
                        ExamplePrompt(
                            label="Localized topic modules",
                            prompt="Show modules covering Azure OpenAI concepts in Japanese",
                            parameter_names=["Topic", "Language"],
                        ),
                        ExamplePrompt(
                            label="Topic catalog overview",
                            prompt="List Microsoft Learn modules for Azure governance",
                            parameter_names=["Topic"],
                        ),
                    ],
                )
            ],
        )
    )

    tools.append(
        ToolMetadata(
            slug="microsoft-learn-get-module-outline",
            display_name="Microsoft Learn · Get module outline",
            category="Microsoft Learn",
            namespace="microsoft_learn.getModuleOutline",
            description="Retrieve the unit-by-unit outline for a Microsoft Learn module.",
            doc_url=MICROSOFT_LEARN_DOC_URL,
            source_url=MICROSOFT_LEARN_DOC_URL,
            operations=[
                ToolOperation(
                    title="Get module outline",
                    description="Retrieve the unit names, durations, and prerequisites for a Microsoft Learn module.",
                    parameters=[
                        ToolParameter(
                            name="Module ID",
                            required=True,
                            description="The Microsoft Learn module ID or URL slug, such as learn.az-104.configure-virtual-networking.",
                        ),
                        ToolParameter(
                            name="Language",
                            required=False,
                            description="Preferred content language code like en or de for localized module outlines.",
                        ),
                    ],
                    examples=[
                        ExamplePrompt(
                            label="Module outline by slug",
                            prompt="Show the outline for the learn.az-104.configure-virtual-networking module",
                            parameter_names=["Module ID"],
                        ),
                        ExamplePrompt(
                            label="Localized module outline",
                            prompt="Get the learn.azure.well-architected module outline in Spanish",
                            parameter_names=["Module ID", "Language"],
                        ),
                    ],
                )
            ],
        )
    )

    tools.append(
        ToolMetadata(
            slug="microsoft-learn-recommend-content-for-role",
            display_name="Microsoft Learn · Recommend content for role",
            category="Microsoft Learn",
            namespace="microsoft_learn.recommendContentForRole",
            description="Recommend Microsoft Learn content for a specific Azure job role and prerequisite knowledge.",
            doc_url=MICROSOFT_LEARN_DOC_URL,
            source_url=MICROSOFT_LEARN_DOC_URL,
            operations=[
                ToolOperation(
                    title="Recommend content for role",
                    description="Get personalized module and learning path recommendations for an Azure job role.",
                    parameters=[
                        ToolParameter(
                            name="Role",
                            required=True,
                            description="Target Azure or cloud job role such as administrator, solutions-architect, or developer.",
                        ),
                        ToolParameter(
                            name="Experience level",
                            required=False,
                            description="Optional experience band like beginner, intermediate, or advanced to tune recommendations.",
                        ),
                        ToolParameter(
                            name="Focus area",
                            required=False,
                            description="Optional specialization focus like security, networking, or data platform.",
                        ),
                    ],
                    examples=[
                        ExamplePrompt(
                            label="Role based recommendations",
                            prompt="Recommend Microsoft Learn content for Azure security engineer responsibilities",
                            parameter_names=["Role"],
                        ),
                        ExamplePrompt(
                            label="Experience tuned recommendations",
                            prompt="Suggest intermediate learning for Azure developer focusing on AI integration",
                            parameter_names=["Role", "Experience level", "Focus area"],
                        ),
                    ],
                )
            ],
        )
    )

    return {tool.slug: tool for tool in tools}
def main() -> None:
    print("="*60)
    print("Azure MCP Tool Metadata Updater")
    print("="*60)
    
    crawler = MCPMetadataCrawler()
    metadata = crawler.crawl()

    print("📚 Adding manual Microsoft Learn tools...")
    manual_tools = _manual_microsoft_learn_tools()
    for slug, tool in manual_tools.items():
        if slug not in metadata:
            metadata[slug] = tool
    print(f"   → Added {len(manual_tools)} manual tool(s)\n")

    # Generate summary by category
    categories = {}
    for tool in metadata.values():
        category = tool.category or "Uncategorized"
        categories[category] = categories.get(category, 0) + 1
    
    total_operations = sum(len(tool.operations) for tool in metadata.values())
    
    payload = {
        "tools": [tool.to_dict() for tool in metadata.values()],
        "source": BASE_URL,
    }

    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT_PATH.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    
    print("="*60)
    print("📊 SUMMARY")
    print("="*60)
    print(f"Total tools: {len(metadata)}")
    print(f"Total operations: {total_operations}")
    print(f"\nTools by category:")
    for category in sorted(categories.keys()):
        print(f"   • {category}: {categories[category]} tool(s)")
    print(f"\n💾 Output: {OUTPUT_PATH}")
    print(f"📦 File size: {OUTPUT_PATH.stat().st_size / 1024:.1f} KB")
    print("="*60)
    print("✅ Metadata update complete!")
    print("="*60)


if __name__ == "__main__":
    main()
