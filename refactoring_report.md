# Refactoring Report — `llm_review_report_legacy_v2.py`

## Contexto

El archivo original implementa un generador de reportes de revisión sistemática con llamadas a OpenAI.
El código presentaba varios code smells documentados intencionalmente con fines pedagógicos.
Se aplicaron 6 refactors incrementales, uno por commit.

---

## Refactor 1 — Extract Class: `ProjectDataLoader` *(Feature Envy)*

**Smell:** `ReporterService` contenía `_load_project_data` y 4 helpers que accedían
directamente al ORM de Django (queries, `prefetch_related`, atributos de modelos).
La clase sabía demasiado sobre los modelos de Django — responsabilidad de una capa de repositorio,
no de un servicio de reportes.

**Técnica:** *Extract Class* — los métodos con envidia de otra clase se mueven a una clase propia.

### Antes

```python
class ReporterService:
    def generate_report(self, project_id, export_mode="markdown"):
        project, articles, votes, criteria, discussions = self._load_project_data(project_id)
        ...

    def _load_project_data(self, project_id):
        from core.models import Project, SearchResult, ...
        project = Project.objects.get(id=project_id)
        search_results = SearchResult.objects.filter(...).prefetch_related(...)
        ...
        return project_dict, article_dicts, vote_dicts, criteria_dict, discussion_dicts

    def _collect_exclusion_criteria(self, project): ...
    def _split_lines(self, value): ...
    def _decision_from_relevance(self, relevance): ...
    def _status_from_result(self, result): ...
```

### Después

```python
class ProjectDataLoader:
    def load(self, project_id):
        from core.models import Project, SearchResult, ...
        project = Project.objects.get(id=project_id)
        ...
        return project_dict, article_dicts, vote_dicts, criteria_dict, discussion_dicts

    def _collect_exclusion_criteria(self, project): ...
    def _split_lines(self, value): ...
    def _decision_from_relevance(self, relevance): ...
    def _status_from_result(self, result): ...


class ReporterService:
    def __init__(self, ..., data_loader: Optional[ProjectDataLoader] = None):
        self.data_loader = data_loader or ProjectDataLoader()

    def generate_report(self, project_id, export_mode="markdown"):
        project, articles, votes, criteria, discussions = self.data_loader.load(project_id)
        ...
```

**Resultado:** `ReporterService` dejó de conocer el ORM de Django. `ProjectDataLoader` es
inyectable, por lo que los tests pueden pasarle un doble sin tocar la base de datos.

---

## Refactor 2 — Extract Method: `_call_llm` *(Duplicated Code)*

**Smell:** `_generate_markdown_report` y `_generate_html_report` contenían el mismo bloque
`try/except` con la llamada a `client.chat.completions.create`, la validación del contenido
y el manejo de errores. Solo diferían el prompt y la etiqueta del error.

**Técnica:** *Extract Method* — el código duplicado se extrae a un método con los puntos
de variación como parámetros.

### Antes

```python
def _generate_markdown_report(self, ...):
    prompt = "...Return only Markdown..."
    try:
        response = self.client.chat.completions.create(
            model=self.model,
            messages=[{"role": "system", ...}, {"role": "user", "content": prompt}],
            temperature=self.temperature,
        )
        content = response.choices[0].message.content
        if not content:
            raise ValueError("OpenAI returned an empty Markdown report")
        return content.strip()
    except Exception as exc:
        raise ValueError(f"OpenAI failed while generating the Markdown report: {exc}") from exc

def _generate_html_report(self, ...):
    prompt = "...Return only HTML..."
    try:
        response = self.client.chat.completions.create(...)  # idéntico
        content = response.choices[0].message.content
        if not content:
            raise ValueError("OpenAI returned an empty HTML report")
        return content.strip()
    except Exception as exc:
        raise ValueError(f"OpenAI failed while generating the HTML report: {exc}") from exc
```

### Después

```python
def _call_llm(self, prompt: str, format_label: str) -> str:
    try:
        response = self.client.chat.completions.create(
            model=self.model,
            messages=[{"role": "system", ...}, {"role": "user", "content": prompt}],
            temperature=self.temperature,
        )
        content = response.choices[0].message.content
        if not content:
            raise ValueError(f"OpenAI returned an empty {format_label} report")
        return content.strip()
    except Exception as exc:
        raise ValueError(f"OpenAI failed while generating the {format_label} report: {exc}") from exc

def _generate_markdown_report(self, ...):
    prompt = "...Return only Markdown..."
    return self._call_llm(prompt, "Markdown")

def _generate_html_report(self, ...):
    prompt = "...Return only HTML..."
    return self._call_llm(prompt, "HTML")
```

**Resultado:** La lógica de llamada a OpenAI vive en un único lugar. Añadir un nuevo
formato no requiere copiar el bloque try/except.

---

## Refactor 3 — Replace Conditional with Dict of Strategies *(Switch Statements)*

**Smell:** `generate_report` usaba un `if/elif/elif/else` para seleccionar tanto el
generador de contenido como el exporter. Además, el bloque `GeneratedReport(...)` estaba
duplicado dentro de cada rama.

**Técnica:** *Replace Conditional with Polymorphism/Strategy* — usando un diccionario
que mapea cada modo a su par `(generate_fn, export_fn)`.

### Antes

```python
def generate_report(self, project_id, export_mode="markdown"):
    project, articles, votes, criteria, discussions = self._load_project_data(project_id)

    if export_mode == "markdown":
        body = self._generate_markdown_report(project, articles, votes, criteria, discussions)
        report = GeneratedReport(title=..., generated_at=..., export_mode=..., content=body)
        return self.export_facade.export_markdown(report)
    elif export_mode == "html":
        body = self._generate_html_report(project, articles, votes, criteria, discussions)
        report = GeneratedReport(title=..., generated_at=..., export_mode=..., content=body)
        return self.export_facade.export_html(report)
    elif export_mode == "pdf":
        body = self._generate_html_report(project, articles, votes, criteria, discussions)
        report = GeneratedReport(title=..., generated_at=..., export_mode=..., content=body)
        return self.export_facade.export_pdf(report)
    else:
        raise ValueError(f"Unsupported export mode: {export_mode}")
```

### Después

```python
def generate_report(self, project_id, export_mode="markdown"):
    data = self.data_loader.load(project_id)

    export_strategies = {
        "markdown": (self._generate_markdown_report, self.export_facade.export_markdown),
        "html":     (self._generate_html_report,     self.export_facade.export_html),
        "pdf":      (self._generate_html_report,     self.export_facade.export_pdf),
    }
    if export_mode not in export_strategies:
        raise ValueError(f"Unsupported export mode: {export_mode}")

    generate_fn, export_fn = export_strategies[export_mode]
    body = generate_fn(data)
    report = GeneratedReport(title=..., generated_at=..., export_mode=export_mode, content=body)
    return export_fn(report)
```

**Resultado:** Añadir un nuevo formato es una línea en el dict. `GeneratedReport` se
construye una sola vez. El método pasó de ~30 líneas a ~15.

---

## Refactor 4 — Introduce Parameter Object: `ProjectReviewData` *(Data Clumps)*

**Smell:** Los mismos 5 valores `(project, articles, votes, criteria, discussions)` viajaban
juntos como tupla a través de `load()`, `generate_report()`, `_generate_markdown_report()`,
`_generate_html_report()` y `_compact_json_text()`. Un grupo de datos que siempre viajan
juntos es una señal de que deben ser un objeto.

**Técnica:** *Introduce Parameter Object* — crear una dataclass que agrupe los datos relacionados.

### Antes

```python
# ProjectDataLoader devuelve una tupla de 5
return project_dict, article_dicts, vote_dicts, criteria_dict, discussion_dicts

# ReporterService desempaqueta y reenvía los 5 parámetros
project, articles, votes, criteria, discussions = self.data_loader.load(project_id)
body = self._generate_markdown_report(project, articles, votes, criteria, discussions)

# Cada método receptor los declara como 5 parámetros separados
def _generate_markdown_report(self, project, articles, votes, criteria, discussions): ...
def _compact_json_text(self, project, articles, votes, criteria, discussions): ...
```

### Después

```python
@dataclass
class ProjectReviewData:
    project: Dict[str, Any]
    articles: List[Dict[str, Any]]
    votes: List[Dict[str, Any]]
    criteria: Dict[str, Any]
    discussions: List[Dict[str, Any]]

# ProjectDataLoader devuelve el objeto
return ProjectReviewData(project=project_dict, articles=article_dicts, ...)

# ReporterService trabaja con el objeto directamente
data = self.data_loader.load(project_id)
body = generate_fn(data)

# Los métodos receptores reciben un único parámetro tipado
def _generate_markdown_report(self, data: ProjectReviewData): ...
def _compact_json_text(self, data: ProjectReviewData): ...
```

**Resultado:** Las firmas de 5 parámetros desaparecieron. El tipo `ProjectReviewData` es
explícito y checkeable estáticamente. Añadir un campo nuevo (e.g. `keywords`) requiere
tocar solo la dataclass y `ProjectDataLoader`, no todas las firmas intermedias.

---

## Refactor 5 — Remove Middle Man: `ReportExportFacade` *(Middle Man)*

**Smell:** `ReportExportFacade` tenía 3 métodos que únicamente reenviaban la llamada al
exporter correspondiente sin añadir ninguna lógica propia. Una clase que solo delega
es una indirección sin valor.

**Técnica:** *Remove Middle Man* — eliminar la clase intermediaria e inyectar las
dependencias reales directamente en el consumidor.

### Antes

```python
class ReportExportFacade:
    def export_markdown(self, report): return self.markdown_exporter.export(report)
    def export_html(self, report):     return self.html_exporter.export(report)
    def export_pdf(self, report):      return self.pdf_exporter.export(report)

class ReporterService:
    def __init__(self, ..., export_facade: Optional[ReportExportFacade] = None):
        self.export_facade = export_facade or ReportExportFacade()

    # uso:
    export_strategies = {
        "markdown": (..., self.export_facade.export_markdown),
        "html":     (..., self.export_facade.export_html),
        "pdf":      (..., self.export_facade.export_pdf),
    }
```

### Después

```python
# ReportExportFacade eliminada

class ReporterService:
    def __init__(
        self, ...,
        markdown_exporter: Optional[MarkdownExporter] = None,
        html_exporter: Optional[HtmlExporter] = None,
        pdf_exporter: Optional[PdfExporter] = None,
    ):
        self.markdown_exporter = markdown_exporter or MarkdownExporter()
        self.html_exporter     = html_exporter     or HtmlExporter()
        self.pdf_exporter      = pdf_exporter      or PdfExporter()

    # uso:
    export_strategies = {
        "markdown": (..., self.markdown_exporter.export),
        "html":     (..., self.html_exporter.export),
        "pdf":      (..., self.pdf_exporter.export),
    }
```

**Resultado:** La clase intermediaria (15 líneas, 0 lógica) desaparece. Los exporters
son inyectables individualmente, lo que facilita mockear solo el que interesa en cada test.

---

## Refactor 6 — Collapse Hierarchy: `OpenAIClient` *(Middle Man / Wrappers innecesarios)*

**Smell:** Existían 5 clases para realizar una única llamada HTTP:
- `OpenAIClient` → solo tenía `self.chat = OpenAIChat(...)`
- `OpenAIChat` → solo tenía `self.completions = OpenAICompletions(...)`
- `OpenAICompletions` → tenía la lógica HTTP real en `create()`
- `OpenAIResponse`, `OpenAIChoice`, `OpenAIMessage` → envolvían el string de respuesta en 3 capas de objetos

Esta jerarquía imitaba la interfaz del SDK oficial de OpenAI (`client.chat.completions.create(...)`)
sin necesitar compatibilidad con él, creando indirección sin beneficio.

**Técnica:** *Collapse Hierarchy* — fusionar la cadena en una única clase con interfaz directa.

### Antes

```python
class OpenAIMessage:
    def __init__(self, content): self.content = content

class OpenAIChoice:
    def __init__(self, content): self.message = OpenAIMessage(content)

class OpenAIResponse:
    def __init__(self, content): self.choices = [OpenAIChoice(content)]

class OpenAICompletions:
    def create(self, model, messages, temperature) -> OpenAIResponse:
        ...  # HTTP call
        return OpenAIResponse(content)

class OpenAIChat:
    def __init__(self, ...): self.completions = OpenAICompletions(...)

class OpenAIClient:
    def __init__(self, ...): self.chat = OpenAIChat(...)

# uso en _call_llm:
response = self.client.chat.completions.create(...)
content  = response.choices[0].message.content
```

### Después

```python
class OpenAIClient:
    def __init__(self, api_key, base_url, timeout):
        if not api_key:
            raise ValueError("Missing OpenAI API key")
        self.api_key  = api_key
        self.base_url = base_url.rstrip("/")
        self.timeout  = timeout

    def create(self, model, messages, temperature) -> str:
        response = requests.post(...)
        if response.status_code >= 400:
            raise ValueError(...)
        return response.json().get("choices", [{}])[0].get("message", {}).get("content", "")

# uso en _call_llm:
content = self.client.create(...)
```

**Resultado:** 5 clases → 1. La interfaz es directa: `client.create()` devuelve `str`.
Mockear el cliente en tests requiere solo un objeto con un método `create()`.

---

## Resumen

| Refactor | Smell eliminado | Técnica |
|---|---|---|
| 1 — `ProjectDataLoader` | Feature Envy, God Class | Extract Class |
| 2 — `_call_llm` | Duplicated Code | Extract Method |
| 3 — Dict de estrategias | Switch Statements, Duplicated Code | Replace Conditional with Strategy |
| 4 — `ProjectReviewData` | Data Clumps, Primitive Obsession | Introduce Parameter Object |
| 5 — Eliminar `ReportExportFacade` | Middle Man | Remove Middle Man |
| 6 — Colapsar wrappers OpenAI | Middle Man, Wrappers innecesarios | Collapse Hierarchy |
