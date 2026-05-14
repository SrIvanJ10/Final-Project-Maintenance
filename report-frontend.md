# 📋 Informe de Deuda Técnica — `App.vue` (Frontend)

> **Archivo analizado:** [App.vue](file:///Users/rodriigomediina/Desktop/Final-Project-Maintenance-main/frontend/src/App.vue)  
> **Líneas de código:** 1 170  
> **Framework:** Vue 3 (Composition API con `<script setup>`)  
> **Fecha:** 2026-05-13

---

## Tabla Resumen

| ID | Bad Smell | Severidad | Impacto |
|----|-----------|-----------|---------|
| TD-01 | **God Component** — archivo monolítico de 1 170 LOC | 🔴 Alta | Mantenibilidad, Testabilidad, Legibilidad |
| TD-02 | **Mixed Concerns** — lógica de negocio, estado, UI y llamadas API en un solo `<script setup>` | 🔴 Alta | Mantenibilidad, Testabilidad |
| TD-03 | **Lack of Component Decomposition** — template de 450 líneas sin sub-componentes | 🔴 Alta | Legibilidad, Mantenibilidad, Rendimiento |
| TD-04 | **God State Object** — estado global acoplado en objetos `reactive` monolíticos (`ui`, `drafts`, `lists`) | 🟡 Media | Mantenibilidad, Bug Risk |
| TD-05 | **Implicit Screen Router** — navegación manual con `ui.screen` en vez de un router real | 🟡 Media | Mantenibilidad, Bug Risk, Testabilidad |
| TD-06 | **Duplicated Relevance Logic** — constantes y funciones de relevancia repetidas (`relevanceTag`, `relevanceClass`, `reviewerDecisionText`) | 🟡 Media | Mantenibilidad, Bug Risk |
| TD-07 | **No Error Boundary / Inconsistent Error Handling** — `try/catch` repetido con patrón idéntico en ~15 funciones async | 🟡 Media | Mantenibilidad, Bug Risk |
| TD-08 | **CSV Export acoplado al componente** — lógica de generación de CSV dentro de `App.vue` (L588-628) | 🟢 Baja | Mantenibilidad, Testabilidad |
| TD-09 | **Magic Strings** — valores como `'scopus'`, `'semantic_scholar'`, `'not_reviewed'`, `'highly_relevant'` hardcodeados | 🟡 Media | Bug Risk, Legibilidad |
| TD-10 | **No Type Safety** — ausencia total de tipos (ni TypeScript ni JSDoc ni PropTypes) | 🟡 Media | Bug Risk, Legibilidad |
| TD-11 | **Side-effect en variable global** — `let flashTimeoutId = null` fuera del ciclo de vida reactivo de Vue | 🟢 Baja | Bug Risk |
| TD-12 | **Untestable Architecture** — imposible hacer unit-test de ninguna lógica porque todo está atado al SFC | 🔴 Alta | Testabilidad |

---

## Detalle de cada ítem

### TD-01 · God Component (Blob / Large Class)

> **Severidad: 🔴 Alta** — Mantenibilidad, Testabilidad, Legibilidad

**Problema:**  
`App.vue` contiene **1 170 líneas**: 718 de `<script setup>` y 450 de `<template>`. Gestiona autenticación, listado de proyectos, workspace de búsqueda, pantalla de revisión, discusión, IA, exportación CSV, modal de creación, toasts… todo en un solo archivo.

**Impacto:**  
- Cualquier cambio en una pantalla requiere navegar por las 1 170 líneas del fichero.
- Dos desarrolladores no pueden trabajar en paralelo en distintas pantallas sin conflictos de merge.
- Es imposible reutilizar partes de la UI en otros contextos.

**Solución — Qué hacer:**
1. Crear una carpeta `src/components/` con sub-componentes por pantalla:
   - `AuthCard.vue` (L724-756)
   - `ProjectsScreen.vue` (L778-801)
   - `WorkspaceScreen.vue` (L803-988)
   - `ReviewScreen.vue` (L990-1146)
   - `ProjectModal.vue` (L1148-1165)
   - `ToastStack.vue` (L767-776)
2. Cada componente recibe sólo los props que necesita y emite eventos (`emit`) para acciones.
3. `App.vue` queda como **orquestador** de ~100 LOC.

---

### TD-02 · Mixed Concerns (Divergent Change)

> **Severidad: 🔴 Alta** — Mantenibilidad, Testabilidad

**Problema:**  
El `<script setup>` mezcla cuatro responsabilidades:
1. **Estado de la aplicación** (`user`, `lists`, `ui`, `drafts`)
2. **Lógica de negocio** (filtrado de artículos, cálculo de progreso, parsing de tareas)
3. **Orquestación de API** (`refreshData`, `login`, `createProject`…)
4. **Lógica de presentación** (`formatAuthors`, `sourceLabel`, `relevanceTag`…)

**Impacto:**  
- Cambiar el modelo de datos obliga a tocar el mismo archivo que la UI.
- Imposible testear la lógica de filtrado sin renderizar el componente.

**Solución — Qué hacer:**
1. Extraer **composables** (hooks) en `src/composables/`:
   - `useAuth.js` → estado de usuario, login, register, logout
   - `useProjects.js` → CRUD de proyectos, selección, refreshData
   - `useReview.js` → lógica de revisión, navegación de artículos, assessRelevance, AI
   - `useDiscussion.js` → hilo de discusión, envío de mensajes
   - `useFlash.js` → sistema de mensajes/toasts
2. Extraer **utilidades puras** en `src/utils/`:
   - `formatters.js` → `formatAuthors`, `formatDateTime`, `sourceLabel`, `roleLabel`, `providerLabel`
   - `relevance.js` → constantes `INCLUDED_RELEVANCE`, `EXCLUDED_RELEVANCE`, funciones `relevanceTag`, `relevanceClass`, `relevanceDecisionText`

---

### TD-03 · Lack of Component Decomposition (Long Method → Template)

> **Severidad: 🔴 Alta** — Legibilidad, Mantenibilidad, Rendimiento

**Problema:**  
El template tiene **450 líneas** con 4 pantallas renderizadas condicionalmente dentro de un solo árbol. Vue re-evalúa las dependencias reactivas de todo el template aunque solo una pantalla sea visible.

**Impacto:**  
- Legibilidad: un desarrollador nuevo necesita entender las 450 líneas para modificar un detalle.
- Rendimiento: Vue recalcula computed properties y virtual DOM de secciones no visibles.

**Solución — Qué hacer:**
1. Extraer cada bloque `v-if="ui.screen === '…'"` a su propio componente `.vue`.
2. Usar `<component :is="currentScreen" />` o un simple `v-if` sobre componentes importados.
3. Considerar `<KeepAlive>` si se quiere preservar el estado al cambiar de pantalla.

---

### TD-04 · God State Object (Data Clump)

> **Severidad: 🟡 Media** — Mantenibilidad, Bug Risk

**Problema:**  
Tres objetos `reactive` (`ui`, `drafts`, `lists`) agrupan estado no relacionado. Por ejemplo, `ui` controla: pantalla activa, tab, modales, tipo de fuente, filtros, índice de revisión y 4 flags de loading.

**Impacto:**  
- Cualquier componente hijo necesitaría recibir el objeto entero, creando acoplamiento.
- Dificulta saber qué parte del estado es de solo-lectura vs modificable.

**Solución — Qué hacer:**
1. Dividir el estado en composables por dominio (ver TD-02).
2. Cada composable expone sólo refs individuales: `const loading = ref(false)`.
3. No pasar objetos `reactive` completos como props; pasar valores individuales.

---

### TD-05 · Implicit Screen Router (Simulated Polymorphism)

> **Severidad: 🟡 Media** — Mantenibilidad, Bug Risk, Testabilidad

**Problema:**  
La navegación entre pantallas se hace con `ui.screen = 'projects' | 'workspace' | 'review'`. No hay rutas, no hay historial de navegación, no hay deep-linking.

**Impacto:**  
- El usuario no puede usar el botón "Atrás" del navegador.
- No se puede compartir un enlace directo a un proyecto o a una revisión.
- Si se añade una 4ª pantalla, hay que añadir otro `v-if` al template monolítico.

**Solución — Qué hacer:**
1. Instalar `vue-router`.
2. Definir rutas: `/login`, `/projects`, `/projects/:id`, `/projects/:id/review`.
3. Mover cada pantalla a `src/views/` como un componente de página.
4. Eliminar `ui.screen` y usar `router.push()`.

---

### TD-06 · Duplicated Relevance Logic (Duplicated Code)

> **Severidad: 🟡 Media** — Mantenibilidad, Bug Risk

**Problema:**  
Las constantes `INCLUDED_RELEVANCE` / `EXCLUDED_RELEVANCE` y las funciones `relevanceTag()`, `relevanceClass()`, `reviewerDecisionText()`, `consensusLabel()` repiten la misma lógica de clasificación con `if/else` sobre los mismos arrays.

**Impacto:**  
- Si se añade un nuevo tipo de relevancia (e.g. `marginally_relevant`), hay que actualizar **4 funciones y 2 constantes** en el mismo archivo.

**Solución — Qué hacer:**
1. Crear `src/utils/relevance.js`:
   ```js
   export const RELEVANCE_GROUPS = {
     included: ['highly_relevant', 'relevant', 'somewhat_relevant'],
     excluded: ['not_relevant', 'duplicate'],
   }
   export function classifyRelevance(value) { /* … */ }
   export function relevanceLabel(value) { /* … */ }
   export function relevanceCssClass(value) { /* … */ }
   ```
2. Importar estas funciones donde se necesiten.

---

### TD-07 · No Error Boundary / Repetitive Error Handling (Duplicated Code)

> **Severidad: 🟡 Media** — Mantenibilidad, Bug Risk

**Problema:**  
Al menos **15 funciones async** siguen el patrón:
```js
try { await api.xxx(); setFlash('ok msg'); await refreshData() }
catch (e) { setFlash('', e.message) }
```
El patrón se repite textualmente en `login`, `register`, `createProject`, `saveProjectInclusionCriteria`, `addCollaborator`, `saveQuery`, `runSemanticSearch`, `importScopus`, `startReview`, `reviewCurrent`, `suggestCurrentWithAI`, `sendDiscussionMessage`…

**Impacto:**  
- Si se quiere cambiar el manejo de errores (e.g., añadir logging, reintentos, o códigos HTTP específicos), hay que tocar todas las funciones.

**Solución — Qué hacer:**
1. Crear un helper `withFlash(asyncFn, successMsg?)`:
   ```js
   async function withFlash(fn, okMsg) {
     setFlash()
     try { await fn(); if (okMsg) setFlash(okMsg) }
     catch (e) { setFlash('', e.message) }
   }
   ```
2. O delegar esto al composable `useFlash` con un wrapper genérico.

---

### TD-08 · CSV Export acoplado al componente (Feature Envy)

> **Severidad: 🟢 Baja** — Mantenibilidad, Testabilidad

**Problema:**  
La función `exportResultsCsv()` (L588-628) contiene **40 líneas** de lógica pura de generación de CSV + descarga de Blob. No tiene ninguna dependencia del DOM de Vue excepto los datos.

**Solución — Qué hacer:**
1. Mover a `src/utils/csv.js`:
   ```js
   export function generateCsv(rows) { /* … */ }
   export function downloadCsv(csvString, filename) { /* … */ }
   ```

---

### TD-09 · Magic Strings (Primitive Obsession)

> **Severidad: 🟡 Media** — Bug Risk, Legibilidad

**Problema:**  
Strings como `'scopus'`, `'semantic_scholar'`, `'not_reviewed'`, `'highly_relevant'`, `'owner'`, `'reviewer'`, `'projects'`, `'workspace'`, `'review'` se repiten a lo largo de todo el archivo sin constantes ni enums.

**Impacto:**  
- Un typo (`'sematic_scholar'`) pasaría desapercibido y causaría un bug silencioso.

**Solución — Qué hacer:**
1. Crear `src/constants.js`:
   ```js
   export const SOURCES = { SCOPUS: 'scopus', SEMANTIC: 'semantic_scholar' }
   export const SCREENS = { PROJECTS: 'projects', WORKSPACE: 'workspace', REVIEW: 'review' }
   export const ROLES = { OWNER: 'owner', REVIEWER: 'reviewer', VIEWER: 'viewer' }
   ```
2. Importar y usar estas constantes en vez de strings literales.

---

### TD-10 · No Type Safety (Missing Abstraction)

> **Severidad: 🟡 Media** — Bug Risk, Legibilidad

**Problema:**  
No hay TypeScript, ni interfaces, ni JSDoc en todo el frontend. Las funciones `ref(null)` no indican qué tipo de objeto se espera. Los objetos API se usan con optional chaining defensivo por todas partes (`result.article?.title`, `selectedProject.value?.owner?.id`).

**Impacto:**  
- Es fácil acceder a una propiedad que no existe y obtener `undefined` silenciosamente.
- El IDE no puede ofrecer autocompletado fiable.

**Solución — Qué hacer:**
1. **Mínimo:** Añadir JSDoc con `@typedef` para `Project`, `Article`, `SearchResult`, `User`.
2. **Ideal:** Renombrar a `.ts`/`.vue` con `<script setup lang="ts">` y definir interfaces.

---

### TD-11 · Side-effect con variable global (Inappropriate Intimacy)

> **Severidad: 🟢 Baja** — Bug Risk

**Problema:**  
`let flashTimeoutId = null` (L11) es una variable de módulo fuera del sistema reactivo de Vue. Si Vue reutiliza el módulo (HMR, SSR), el timer podría quedar "huérfano".

**Solución — Qué hacer:**
1. Mover el timer dentro de un composable `useFlash()` con `onUnmounted(() => clearTimeout(…))`.

---

### TD-12 · Untestable Architecture

> **Severidad: 🔴 Alta** — Testabilidad

**Problema:**  
No es posible hacer unit test de:
- El filtrado de artículos (`currentResults`)
- El cálculo de progreso (`progressPercent`)
- El parsing de tasks (`parseTaskAssignments`)
- El formateo de autores (`formatAuthors`)

…sin montar el componente Vue completo.

**Solución — Qué hacer:**
1. Extraer toda la lógica pura a funciones exportadas en `src/utils/`.
2. Extraer la lógica con estado a composables que se puedan testear con `@vue/test-utils` o con un wrapper mínimo.
3. Los computed properties complejos (e.g., `currentResults`) deberían vivir en el composable `useReview`, donde se pueden testear aisladamente.

---

## 🎯 Qué tienes que hacer — Plan de Acción para Refactorizar

### Fase 1: Extraer utilidades puras (sin romper nada)

| Archivo nuevo | Qué mover desde `App.vue` |
|---|---|
| `src/constants.js` | `INCLUDED_RELEVANCE`, `EXCLUDED_RELEVANCE`, magic strings de screens, sources, roles |
| `src/utils/formatters.js` | `formatAuthors()`, `formatDateTime()`, `sourceLabel()`, `providerLabel()`, `roleLabel()` |
| `src/utils/relevance.js` | `relevanceTag()`, `relevanceClass()`, `reviewerDecisionText()`, `consensusLabel()`, constantes de relevancia |
| `src/utils/csv.js` | `exportResultsCsv()` (la parte de generación de CSV y descarga) |

> **Efecto:** reduces ~80 LOC de `App.vue`, ganas funciones testeables, no cambias nada visual.

### Fase 2: Extraer composables

| Archivo nuevo | Qué mover desde `App.vue` |
|---|---|
| `src/composables/useFlash.js` | `msg`, `err`, `flashTimeoutId`, `setFlash()`, `dismissFlash()` |
| `src/composables/useAuth.js` | `user`, `auth`, `status`, `login()`, `register()`, `logout()`, `boot()` |
| `src/composables/useProjects.js` | `lists`, `selectedProject`, `projectCriteria`, `refreshData()`, `createProject()`, `openProject()`, `saveProjectInclusionCriteria()`, `addCollaborator()` |
| `src/composables/useSearch.js` | `sourceCriteria`, `drafts.scopusQuery/semanticKeywords`, `upsertCriteriaForSource()`, `saveQuery()`, `runSemanticSearch()`, `importScopus()` |
| `src/composables/useReview.js` | `reviewResults`, `currentReviewResult`, computed de progreso, `startReview()`, `reviewCurrent()`, `suggestCurrentWithAI()`, `nextArticle()`, `previousArticle()` |
| `src/composables/useDiscussion.js` | `discussionMessages`, `loadDiscussionThread()`, `sendDiscussionMessage()` |

> **Efecto:** el `<script setup>` de `App.vue` baja a ~30 LOC de importaciones + composable calls.

### Fase 3: Extraer componentes de template

| Componente nuevo | Líneas de `App.vue` que absorbe |
|---|---|
| `src/components/AuthCard.vue` | L724–756 |
| `src/components/TopBar.vue` | L759–776 |
| `src/components/ProjectsScreen.vue` | L778–801 |
| `src/components/WorkspaceScreen.vue` | L803–988 (puede sub-dividirse en `StatsGrid`, `QueryTab`, `ArticlesTab`) |
| `src/components/ReviewScreen.vue` | L990–1146 (puede sub-dividirse en `ReviewCard`, `AiPanel`, `DiscussionPanel`) |
| `src/components/ProjectModal.vue` | L1148–1165 |
| `src/components/ToastStack.vue` | L767–776 |

> **Efecto:** `App.vue` baja a ~50-80 LOC de template. Cada componente tiene una única responsabilidad.

### Fase 4 (Opcional): Router + TypeScript

1. Instalar `vue-router` y crear `src/router.js`.
2. Migrar `ui.screen` a rutas reales.
3. Añadir TypeScript de forma incremental empezando por las interfaces de datos.

---

## Estructura final propuesta

```
src/
├── App.vue                        (~80 LOC, orquestador)
├── main.js
├── styles.css
├── constants.js
├── router.js                      (opcional)
├── components/
│   ├── AuthCard.vue
│   ├── TopBar.vue
│   ├── ToastStack.vue
│   ├── ProjectsScreen.vue
│   ├── ProjectModal.vue
│   ├── WorkspaceScreen.vue
│   │   ├── StatsGrid.vue
│   │   ├── QueryTab.vue
│   │   └── ArticlesTab.vue
│   └── ReviewScreen.vue
│       ├── ReviewCard.vue
│       ├── AiPanel.vue
│       └── DiscussionPanel.vue
├── composables/
│   ├── useAuth.js
│   ├── useFlash.js
│   ├── useProjects.js
│   ├── useSearch.js
│   ├── useReview.js
│   └── useDiscussion.js
├── utils/
│   ├── formatters.js
│   ├── relevance.js
│   └── csv.js
└── lib/
    └── api.js                     (ya existe, no tocar)
```

> [!TIP]
> Empieza por la **Fase 1** (utils) porque no cambia la estructura del componente y puedes verificar que nada se rompe con imports simples. Luego sigue con la **Fase 2** (composables) que es donde se obtiene el mayor beneficio en testabilidad. La **Fase 3** (componentes de template) es la más visual y requiere pasar props/emits.
