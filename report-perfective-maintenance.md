# Mantenimiento Perfectivo: Reporte de Ejecución

El presente documento detalla la implementación de las características requeridas durante la fase de *Perfective Maintenance* del proyecto Mnemosyne, correspondientes al **Generador de Reportes (LLM)** y la **Línea de Tiempo de Eventos (Event Timeline)**.

## 1. Línea de Tiempo de Eventos (Event Timeline)

### Arquitectura y Modelo de Datos
La trazabilidad de las acciones sobre cada artículo requería una estructura centralizada. Se optó por una aproximación explícita (Opción A del plan inicial), creando el modelo `ArticleEvent` en `myscience/core/models.py`. Este modelo registra el tipo de evento, el usuario responsable, una descripción legible y metadatos en formato JSON para facilitar su posterior consumo.

Los eventos registrados incluyen:
- Votos emitidos por los revisores.
- Cambios de consenso (inclusión/exclusión definitiva).
- Recomendaciones generadas por la Inteligencia Artificial.
- Comentarios añadidos en el foro de discusión del artículo.

### Instrumentación del Backend
Se procedió a instrumentar los métodos clave para automatizar la generación de eventos:
- En `SearchResult.record_assessment()`, se captura cada voto individual emitido por los revisores.
- En `SearchResult.sync_consensus_decision()`, se registra el evento de cambio de estado final del artículo.
- En `ArticleDiscussionMessageViewSet.create()` (`api/views.py`), se captura la publicación de nuevos comentarios.
- En `SearchResultViewSet.suggest_with_ai()` (`api/views.py`), se almacena la decisión recomendada por el LLM junto con sus metadatos.

Adicionalmente, se expuso el endpoint `GET /api/articles/<id>/timeline/` utilizando el nuevo serializador `ArticleEventSerializer` para que la capa de presentación pueda consultar la cronología de eventos.

### Implementación en el Frontend
- Se extendió el *composable* `useReview.js` para gestionar el estado de la línea de tiempo (`timelineEvents`, `timelineLoading`) y cargar los eventos cada vez que cambia el artículo actual.
- Se implementó la interfaz visual en `ReviewScreen.vue`, añadiendo un panel inferior que muestra el flujo cronológico de eventos (autor, fecha y descripción) en un formato similar al del panel de discusiones.

## 2. Generador de Reportes mediante LLMs

### Endpoint y Lógica de Servidor
Se incorporó el endpoint `POST /api/projects/<id>/generate_report/` dentro del `ProjectViewSet` (`api/views.py`). 
El flujo de validación exige que todas las tareas de *screening* asociadas al proyecto se encuentren en estado completado (`status='completed'`). De cumplirse la condición, el controlador delega la ejecución al `UnifiedReviewReportService`, el cual fue refactorizado previamente en la fase de mantenimiento preventivo. El servicio acepta un `custom_prompt` proporcionado por el usuario para refinar el reporte resultante.

### Interfaz de Usuario
La interfaz fue extendida en `WorkspaceScreen.vue` introduciendo un nuevo panel dedicado a la generación de reportes automáticos.
- Se añadió un área de texto para que el usuario pueda introducir instrucciones específicas (prompt).
- El panel se renderiza de forma condicional, activándose únicamente cuando el proyecto cumple los requisitos de finalización (todas las tareas de cribado completadas).
- Se gestionaron los estados de carga (`generatingReport`) en `useProjects.js` y se incluyó la visualización del reporte crudo dentro de un bloque preformateado tras su recepción.

## 3. Estado de la Base de Datos
Las modificaciones a nivel de modelo requirieron la generación de nuevas migraciones. Se ejecutó el comando `makemigrations` dentro del contenedor del servicio backend (`web`) para reflejar la existencia de la tabla asociada a `ArticleEvent`. Queda pendiente aplicar la migración (`migrate`) antes del próximo despliegue.
