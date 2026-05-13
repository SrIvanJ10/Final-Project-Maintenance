"""
llm_review_report_legacy_v2.py

Smaller legacy implementation for a Mnemosyne-like review report generator.

Pedagogical purpose
-------------------
This file is intentionally simpler than llm_review_report_legacy.py, but it still keeps
several design problems visible for refactoring exercises.

Intentionally included smells:
- God Class: ReporterService loads Django data, transforms it, builds prompts, calls
  OpenAI, renders output, and chooses export mode.
- Switch Statements: export format selection is done with conditionals.
- Duplicated Code: prompt building and OpenAI calling logic are repeated.
- Primitive Obsession: data is passed around as nested dicts and lists.
- Middle Man: ReportExportFacade forwards to exporters without meaningful behavior.
- Feature Envy / Tight Coupling: the service knows too much about Django models and the
  OpenAI chat completions HTTP shape.

The runtime behavior is intentionally real: it calls OpenAI through HTTP and depends on
the configured API key/base URL/model.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from html import escape
import re
from typing import Any, Dict, List, Optional

import requests


class OpenAIMessage:
    def __init__(self, content: str):
        self.content = content


class OpenAIChoice:
    def __init__(self, content: str):
        self.message = OpenAIMessage(content)


class OpenAIResponse:
    def __init__(self, content: str):
        self.choices = [OpenAIChoice(content)]


class OpenAICompletions:
    def __init__(self, api_key: str, base_url: str = "https://api.openai.com/v1", timeout: int = 180):
        self.api_key = api_key
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout

    def create(self, model: str, messages: List[Dict[str, str]], temperature: float):
        if not self.api_key:
            raise ValueError("Missing OpenAI API key")

        response = requests.post(
            f"{self.base_url}/chat/completions",
            json={
                "model": model,
                "messages": messages,
                "temperature": temperature,
            },
            headers={
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
            },
            timeout=self.timeout,
        )
        if response.status_code >= 400:
            raise ValueError(f"OpenAI request failed ({response.status_code}): {response.text[:300]}")

        data = response.json()
        content = (
            data.get("choices", [{}])[0]
            .get("message", {})
            .get("content", "")
        )
        return OpenAIResponse(content)


class OpenAIChat:
    def __init__(self, api_key: str, base_url: str = "https://api.openai.com/v1", timeout: int = 180):
        self.completions = OpenAICompletions(api_key=api_key, base_url=base_url, timeout=timeout)


class OpenAIClient:
    def __init__(self, api_key: str, base_url: str = "https://api.openai.com/v1", timeout: int = 180):
        self.chat = OpenAIChat(api_key=api_key, base_url=base_url, timeout=timeout)


@dataclass
class GeneratedReport:
    title: str
    generated_at: str
    export_mode: str
    content: str


class MarkdownExporter:
    def export(self, report: GeneratedReport) -> str:
        return report.content


class HtmlExporter:
    def export(self, report: GeneratedReport) -> str:
        text = report.content or ""
        if "<html" in text.lower():
            return text

        html_lines = [
            "<html><head>",
            f"<title>{escape(report.title)}</title>",
            "</head><body>",
            f"<h1>{escape(report.title)}</h1>",
            f"<p><em>Generated at: {escape(report.generated_at)}</em></p>",
        ]
        for line in text.splitlines():
            stripped = line.strip()
            if not stripped:
                continue
            if stripped.startswith("# "):
                html_lines.append(f"<h2>{escape(stripped[2:])}</h2>")
            elif stripped.startswith("## "):
                html_lines.append(f"<h3>{escape(stripped[3:])}</h3>")
            elif stripped.startswith("- "):
                html_lines.append(f"<p>&bull; {escape(stripped[2:])}</p>")
            else:
                html_lines.append(f"<p>{escape(stripped)}</p>")
        html_lines.append("</body></html>")
        return "\n".join(html_lines)


class LegacyPdfRenderer:
    def render(self, html: str) -> bytes:
        text = re.sub(r"</(h1|h2|h3|p|section|pre|li|ul)>", "\n", html, flags=re.IGNORECASE)
        text = re.sub(r"<br\s*/?>", "\n", text, flags=re.IGNORECASE)
        text = re.sub(r"<[^>]+>", "", text)
        text = text.replace("&bull;", "- ").replace("&amp;", "&")

        lines = []
        for raw_line in text.splitlines():
            line = raw_line.strip()
            if line:
                lines.extend(self._wrap_line(line, 95))
        if not lines:
            lines = ["Empty report"]

        pages = [lines[index:index + 48] for index in range(0, len(lines), 48)]
        objects = [
            b"<< /Type /Catalog /Pages 2 0 R >>",
            self._build_pages_object([3 + (index * 2) for index in range(len(pages))]),
        ]

        page_object_numbers = []
        content_object_numbers = []
        next_object_number = 3
        for page_lines in pages:
            page_object_numbers.append(next_object_number)
            content_object_numbers.append(next_object_number + 1)
            objects.append(b"")
            objects.append(self._build_content_stream(page_lines))
            next_object_number += 2

        objects.append(b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>")
        font_object_number = len(objects)

        for index, page_object_number in enumerate(page_object_numbers):
            objects[page_object_number - 1] = self._build_page_object(content_object_numbers[index], font_object_number)

        pdf = b"%PDF-1.4\n%\xe2\xe3\xcf\xd3\n"
        offsets = []
        for index, obj in enumerate(objects, start=1):
            offsets.append(len(pdf))
            pdf += f"{index} 0 obj\n".encode("latin-1")
            pdf += obj + b"\nendobj\n"

        xref_offset = len(pdf)
        pdf += f"xref\n0 {len(objects) + 1}\n".encode("latin-1")
        pdf += b"0000000000 65535 f \n"
        for offset in offsets:
            pdf += f"{offset:010d} 00000 n \n".encode("latin-1")
        pdf += (
            b"trailer\n"
            + f"<< /Size {len(objects) + 1} /Root 1 0 R >>\n".encode("latin-1")
            + b"startxref\n"
            + str(xref_offset).encode("latin-1")
            + b"\n%%EOF"
        )
        return pdf

    def _build_pages_object(self, page_object_numbers: List[int]) -> bytes:
        kids = " ".join(f"{number} 0 R" for number in page_object_numbers)
        return f"<< /Type /Pages /Kids [{kids}] /Count {len(page_object_numbers)} >>".encode("latin-1")

    def _build_page_object(self, content_object_number: int, font_object_number: int) -> bytes:
        return (
            f"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] "
            f"/Resources << /Font << /F1 {font_object_number} 0 R >> >> "
            f"/Contents {content_object_number} 0 R >>"
        ).encode("latin-1")

    def _build_content_stream(self, lines: List[str]) -> bytes:
        content_lines = ["BT", "/F1 11 Tf", "50 780 Td"]
        first_line = True
        for raw_line in lines:
            safe_line = raw_line.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")
            if first_line:
                content_lines.append(f"({safe_line}) Tj")
                first_line = False
            else:
                content_lines.append("0 -14 Td")
                content_lines.append(f"({safe_line}) Tj")
        content_lines.append("ET")
        stream = "\n".join(content_lines).encode("latin-1", errors="replace")
        return f"<< /Length {len(stream)} >>\nstream\n".encode("latin-1") + stream + b"\nendstream"

    def _wrap_line(self, text: str, width: int) -> List[str]:
        if len(text) <= width:
            return [text]
        words = text.split()
        if not words:
            return [text[:width]]
        lines = []
        current = words[0]
        for word in words[1:]:
            if len(current) + 1 + len(word) <= width:
                current += " " + word
            else:
                lines.append(current)
                current = word
        lines.append(current)
        return lines


class PdfExporter:
    def __init__(self, html_exporter: Optional[HtmlExporter] = None, renderer: Optional[LegacyPdfRenderer] = None):
        self.html_exporter = html_exporter or HtmlExporter()
        self.renderer = renderer or LegacyPdfRenderer()

    def export(self, report: GeneratedReport) -> bytes:
        html = self.html_exporter.export(report)
        return self.renderer.render(html)


class ReportExportFacade:
    def __init__(
        self,
        markdown_exporter: Optional[MarkdownExporter] = None,
        html_exporter: Optional[HtmlExporter] = None,
        pdf_exporter: Optional[PdfExporter] = None,
    ):
        self.markdown_exporter = markdown_exporter or MarkdownExporter()
        self.html_exporter = html_exporter or HtmlExporter()
        self.pdf_exporter = pdf_exporter or PdfExporter()

    def export_markdown(self, report: GeneratedReport) -> str:
        return self.markdown_exporter.export(report)

    def export_html(self, report: GeneratedReport) -> str:
        return self.html_exporter.export(report)

    def export_pdf(self, report: GeneratedReport) -> bytes:
        return self.pdf_exporter.export(report)


class ProjectDataLoader:
    def load(self, project_id: Any):
        from django.db import models as django_models
        from core.models import ArticleDiscussionMessage, Project, SearchResult, SearchResultAssessment

        project = Project.objects.get(id=project_id)
        search_results = list(
            SearchResult.objects.filter(search__criteria__project=project)
            .select_related("article")
            .prefetch_related(
                django_models.Prefetch(
                    "assessments",
                    queryset=SearchResultAssessment.objects.select_related("reviewer", "search_result__article"),
                    to_attr="prefetched_assessments",
                )
            )
            .distinct()
        )
        assessments = [
            assessment
            for result in search_results
            for assessment in getattr(result, "prefetched_assessments", [])
        ]
        article_ids = [result.article_id for result in search_results]
        discussions = list(
            ArticleDiscussionMessage.objects.filter(project=project, article_id__in=article_ids).select_related("author")
        ) if article_ids else []

        project_dict = {
            "id": project.id,
            "title": project.title,
            "description": project.description,
            "research_questions": [project.research_question] if project.research_question else [],
            "inclusion_criteria": self._split_lines(project.inclusion_criteria),
            "exclusion_criteria": self._collect_exclusion_criteria(project),
        }
        article_dicts = []
        for result in search_results:
            article = result.article
            article_dicts.append(
                {
                    "id": article.id,
                    "title": article.title,
                    "abstract": article.abstract,
                    "year": article.publication_year,
                    "source": article.article_source,
                    "status": self._status_from_result(result),
                    "duplicate": result.relevance == "duplicate",
                    "full_text": bool(article.pdf_url),
                }
            )
        vote_dicts = []
        for assessment in assessments:
            vote_dicts.append(
                {
                    "article_id": assessment.search_result.article_id,
                    "reviewer": assessment.reviewer.username,
                    "decision": self._decision_from_relevance(assessment.relevance),
                    "reason": assessment.notes,
                }
            )
        discussion_dicts = []
        for message in discussions:
            discussion_dicts.append(
                {
                    "article_id": message.article_id,
                    "user": message.author.username,
                    "message": message.message,
                }
            )
        criteria_dict = {
            "inclusion": project_dict["inclusion_criteria"],
            "exclusion": project_dict["exclusion_criteria"],
        }
        return project_dict, article_dicts, vote_dicts, criteria_dict, discussion_dicts

    def _collect_exclusion_criteria(self, project: Any) -> List[str]:
        values = []
        for criteria in project.search_criteria.all():
            values.extend(self._split_lines(criteria.exclusion_criteria))
        return values

    def _split_lines(self, value: Any) -> List[str]:
        if not value:
            return []
        return [line.strip("- ").strip() for line in str(value).splitlines() if line.strip()]

    def _decision_from_relevance(self, relevance: Any) -> str:
        value = str(relevance or "").lower()
        if value in {"highly_relevant", "relevant", "somewhat_relevant"}:
            return "include"
        if value in {"not_relevant", "duplicate"}:
            return "exclude"
        return "maybe"

    def _status_from_result(self, result: Any) -> str:
        relevance = str(getattr(result, "relevance", "") or "").lower()
        if relevance == "duplicate":
            return "duplicate"
        if relevance == "highly_relevant":
            return "included"
        if relevance == "not_relevant":
            return "excluded"

        decisions = set()
        for assessment in getattr(result, "prefetched_assessments", []):
            decisions.add(self._decision_from_relevance(assessment.relevance))
        if "include" in decisions and "exclude" in decisions:
            return "conflict"
        return "pending"


class ReporterService:
    def __init__(
        self,
        openai_api_key: str = "",
        model: str = "gpt-4o-mini",
        openai_client: Optional[Any] = None,
        export_facade: Optional[ReportExportFacade] = None,
        openai_base_url: str = "https://api.openai.com/v1",
        openai_timeout: int = 180,
        data_loader: Optional[ProjectDataLoader] = None,
    ):
        self.openai_api_key = openai_api_key
        self.model = model
        self.temperature = 0.3
        self.client = openai_client or OpenAIClient(
            api_key=openai_api_key,
            base_url=openai_base_url,
            timeout=openai_timeout,
        )
        self.export_facade = export_facade or ReportExportFacade()
        self.data_loader = data_loader or ProjectDataLoader()

    def generate_report(self, project_id: Any, export_mode: str = "markdown") -> Any:
        project, articles, votes, criteria, discussions = self.data_loader.load(project_id)

        export_strategies = {
            "markdown": (self._generate_markdown_report, self.export_facade.export_markdown),
            "html":     (self._generate_html_report,     self.export_facade.export_html),
            "pdf":      (self._generate_html_report,     self.export_facade.export_pdf),
        }
        if export_mode not in export_strategies:
            raise ValueError(f"Unsupported export mode: {export_mode}")

        generate_fn, export_fn = export_strategies[export_mode]
        body = generate_fn(project, articles, votes, criteria, discussions)
        report = GeneratedReport(
            title=project.get("title", "Untitled review report"),
            generated_at=datetime.utcnow().isoformat(timespec="seconds") + "Z",
            export_mode=export_mode,
            content=body,
        )
        return export_fn(report)

    def _compact_json_text(self, project: Dict[str, Any], articles: List[Dict[str, Any]], votes: List[Dict[str, Any]], criteria: Dict[str, Any], discussions: List[Dict[str, Any]]) -> str:
        article_sample = [self._short_article(article) for article in articles[:15]]
        vote_sample = [self._short_vote(vote) for vote in votes[:30]]
        discussion_sample = [self._short_discussion(item) for item in discussions[:12]]
        return (
            f"Project: {project}\n\n"
            f"Criteria: {criteria}\n\n"
            f"Articles ({len(articles)} total, sample up to 15): {article_sample}\n\n"
            f"Votes ({len(votes)} total, sample up to 30): {vote_sample}\n\n"
            f"Discussions ({len(discussions)} total, sample up to 12): {discussion_sample}\n"
        )

    def _short_article(self, article: Dict[str, Any]) -> Dict[str, Any]:
        return {
            "id": article.get("id"),
            "title": str(article.get("title", ""))[:180],
            "year": article.get("year"),
            "source": article.get("source"),
            "status": article.get("status"),
        }

    def _short_vote(self, vote: Dict[str, Any]) -> Dict[str, Any]:
        return {
            "article_id": vote.get("article_id"),
            "reviewer": vote.get("reviewer"),
            "decision": vote.get("decision"),
            "reason": str(vote.get("reason", ""))[:160],
        }

    def _short_discussion(self, item: Dict[str, Any]) -> Dict[str, Any]:
        return {
            "article_id": item.get("article_id"),
            "user": item.get("user"),
            "message": str(item.get("message", ""))[:160],
        }

    def _call_llm(self, prompt: str, format_label: str) -> str:
        try:
            response = self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": "You are a systematic review reporting assistant."},
                    {"role": "user", "content": prompt},
                ],
                temperature=self.temperature,
            )
            content = response.choices[0].message.content
            if not content:
                raise ValueError(f"OpenAI returned an empty {format_label} report")
            return content.strip()
        except Exception as exc:
            raise ValueError(f"OpenAI failed while generating the {format_label} report: {exc}") from exc

    def _generate_markdown_report(
        self,
        project: Dict[str, Any],
        articles: List[Dict[str, Any]],
        votes: List[Dict[str, Any]],
        criteria: Dict[str, Any],
        discussions: List[Dict[str, Any]],
    ) -> str:
        prompt = f"""
You are helping with a systematic literature review.
Generate the full final report directly in Markdown.

The report must include at least these sections:
- Executive Summary
- PRISMA
- Screening Metrics
- Inclusion/Exclusion Table
- Included Articles
- Excluded Articles

Use the following project data and do not invent article titles or counts.

{self._compact_json_text(project, articles, votes, criteria, discussions)}

Return only Markdown.
"""
        return self._call_llm(prompt, "Markdown")

    def _generate_html_report(
        self,
        project: Dict[str, Any],
        articles: List[Dict[str, Any]],
        votes: List[Dict[str, Any]],
        criteria: Dict[str, Any],
        discussions: List[Dict[str, Any]],
    ) -> str:
        prompt = f"""
You are helping with a systematic literature review.
Generate the full final report directly in HTML.

Requirements:
- Return a complete HTML document.
- Include headings and readable sections.
- Include these sections: Executive Summary, PRISMA, Screening Metrics,
  Inclusion/Exclusion Table, Included Articles, Excluded Articles.
- Include Section: Analysis, where included articles are compared in a table.
  Also this section must include a subsection identifying research gaps and future possible research works.
- Do not wrap the answer in Markdown code fences.

Use the following project data and do not invent article titles or counts.

{self._compact_json_text(project, articles, votes, criteria, discussions)}

Return only HTML.
"""
        return self._call_llm(prompt, "HTML")
