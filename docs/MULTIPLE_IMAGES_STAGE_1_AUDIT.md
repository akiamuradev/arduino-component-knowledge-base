# Этап 1: аудит поддержки множественных изображений

Дата аудита: 2026-07-23. Базовая версия: `0.21.0`, commit `ec3bfb6`.

## Статус пятиэтапного плана

| Этап | Статус |
|---:|---|
| 1. Аудит | done |
| 2. Backend | done |
| 3. Frontend editor | next |
| 4. Preview и публичная карточка | planned |
| 5. Полная test matrix | planned |

Stage 2 реализован без замены media-архитектуры: Alembic revision `20260723_19`, ordered image
aggregate, first-image-primary, атомарная mutation metadata/order/primary/detach с optimistic
component revision, publication gates, immutable published manifest и private-variant
`presigned_get`. Draft по-прежнему сохраняется без изображений; строгий media gate применяется
только к новой публикации.

## Цель и ограничения

Stage 1 был выполнен как чистый аудит без изменения application code. Stage 2 реализует
зафиксированный ниже backend-контракт. Целевое поведение:

- карточка содержит до 12 изображений;
- одно изображение является основным;
- редактор позволяет менять назначение, alt text, подпись и порядок;
- первое прикреплённое изображение автоматически становится основным;
- draft можно сохранить без изображения;
- новая публикация требует минимум одно `ready` изображение и ровно одно основное;
- опубликованные изображения читаются только из immutable revision snapshot;
- существующие private MinIO buckets, media workers и обработка variants сохраняются.

## Что уже реализовано

### Хранение и обработка

- `media_assets` хранит связь `component_id`, `kind`, `purpose`, обязательный `alt_text`,
  attribution, status, object key, hashes и технические metadata.
- `media_variants` хранит безопасные WebP variants `320w`, `800w`, `1600w`; оригинал остаётся
  в private quarantine bucket.
- Image pipeline проверяет размер, MIME, magic bytes, окончание контейнера, число пикселей,
  размеры, animation и декодирование Pillow, удаляет metadata и рассчитывает SHA-256/pHash.
- PostgreSQL и `MediaService` уже ограничивают карточку 12 изображениями, двумя видео и 600 MiB
  originals. Quota reservation сериализована advisory lock.
- Upload API использует presigned PUT, затем durable processing job. Teacher и administrator
  проверяются backend; state-changing endpoints используют CSRF.
- `component_id` имеет FK на `components`; duplicate merge уже переносит media survivor-карточке.

### Каталог и публикация

- Каталог использует optimistic `components.revision` и PostgreSQL row lock.
- Каждое сохранение и lifecycle transition создаёт `component_revisions.content_json`.
- Student API восстанавливает карточку из последнего immutable snapshot со status `published`.
- Источники, характеристики, совместимость и учебные примеры уже копируются в snapshot.

### Frontend

- `MediaGallery` умеет показать массив изображений и видео, использует безопасные URL,
  lazy loading и fallback.
- `ComponentCard` выбирает первое изображение из optional `media`.
- `CatalogComponentPage` уже имеет место под `MediaGallery`.
- Тип `CatalogMedia[]` существует, но является optional временным контрактом.

## Разрывы относительно требуемого поведения

| Область | Текущее состояние | Требуемое изменение |
|---|---|---|
| Metadata | Есть `purpose` и `alt_text` | Добавить `caption`, `display_order`, `is_primary` |
| Коллекция карточки | Assets связаны только `component_id` | Возвращать упорядоченную коллекцию в workspace |
| Primary | Не моделируется | At-most-one на уровне БД, exactly-one при публикации |
| Порядок | Не моделируется | Backend нормализует порядок под component row lock |
| Редактирование | Есть только reserve/complete/status | Добавить атомарную mutation metadata/order/primary/detach |
| Первый image | Не назначается основным | Назначать автоматически в транзакции backend |
| Публикация | Готовность media не проверяется | Требовать ready image и ровно один primary |
| Snapshot | Media полностью отсутствует | Копировать ordered media manifest в `content_json` |
| Public API | Не возвращает `media` | Читать manifest только из published snapshot |
| Download | Storage boundary имеет presigned PUT, но не GET | Добавить короткий presigned GET для разрешённого variant |
| Editor | Нет upload/dropzone и списка изображений | Добавить блок между идентификацией и учебным содержанием |
| Preview | Не отображает media editor state | Основное крупно, остальные галереей |
| Public gallery | Рендерит плоскую сетку | Primary-first gallery и keyboard navigation |
| Удаление | Endpoint отсутствует | Отвязывать asset логически; binary не удалять синхронно |
| Tests | Покрыты processing/quota/RBAC | Нет aggregate, ordering, snapshot и gallery сценариев |

OpenAPI `0.21.0` содержит только reserve, complete и status для image/video. В
`ComponentResponse` и `PublicComponentResponse` поле `media` отсутствует. Реальная локальная схема
также не содержит `caption`, `display_order` или `is_primary`.

## Минимальная целевая модель

Существующий `MediaAsset` уже выполняет роль рекомендованного `ComponentMedia`, поэтому новую
параллельную media-архитектуру или копирование binary не требуется. В `media_assets` добавляются:

```text
caption       varchar(1000) nullable
display_order integer not null
is_primary    boolean not null
```

Инварианты:

1. `display_order >= 0`.
2. `is_primary` разрешён только для `kind=image` и непустого `component_id`.
3. Partial unique index гарантирует не более одного primary image на component.
4. Backend под row lock компонента нормализует image order в `0..n-1`.
5. Первое прикреплённое image становится primary.
6. При удалении primary backend выбирает первый оставшийся image; draft без images допустим.
7. Перед публикацией backend требует хотя бы один `ready` image и ровно один ready primary.
8. Pending, processing, rejected и original object никогда не попадают в public manifest.

Порядок не нужно защищать non-deferrable unique constraint: при перестановке он создаёт временные
коллизии. Correctness обеспечивают component row lock, optimistic revision и последующая
нормализация; БД защищает bounds и единственность primary.

## Immutable published manifest

`component_revisions.content_json.media` содержит упорядоченный список:

```json
{
  "asset_id": "uuid",
  "kind": "image",
  "purpose": "product",
  "alt_text": "Вид модуля сверху",
  "caption": "Основной вид",
  "display_order": 0,
  "is_primary": true,
  "width": 1600,
  "height": 1200,
  "variants": [
    {
      "name": "320w",
      "mime": "image/webp",
      "width": 320,
      "height": 240,
      "sha256": "..."
    }
  ]
}
```

Bucket names, object keys и presigned URL в snapshot не сохраняются. При public read backend:

1. выбирает только asset IDs из published snapshot;
2. сверяет, что asset и variant всё ещё `ready` и соответствуют snapshot;
3. выдаёт короткий presigned GET на processed variant;
4. не выдаёт original/quarantine;
5. сохраняет snapshot order, primary, alt и caption, даже если draft позже изменён.

Исторические snapshots без ключа `media` читаются как пустой список. Это необходимо для
безопасной совместимости: в локальной базе сейчас три опубликованные карточки без ready image.
Новые и повторные публикации уже проходят строгий media gate; старые публикации не архивируются
и не получают выдуманные изображения автоматически.

## Backend change plan — этап 2

1. Alembic revision `20260723_19`:
   - добавить три поля и checks;
   - backfill order детерминированно по `(created_at, id)`;
   - выбрать первый неповреждённый image primary там, где изображения существуют;
   - создать partial unique primary index;
   - предоставить downgrade без удаления assets/variants.
2. Расширить SQLAlchemy/domain/Pydantic contracts типом `ComponentMedia`.
3. Добавить repository methods для ordered list, component locking, metadata mutation,
   primary reassignment и safe variant projection.
4. Добавить workspace mutations с `expected_revision`; backend, а не frontend, определяет
   итоговый порядок и primary.
5. Сохранить существующие reserve/complete endpoints, но привязку к карточке проверять через
   существующий editor RBAC и component revision.
6. Добавить `presigned_get` в storage boundary и никогда не возвращать storage identifiers.
7. Включить ready media manifest в каждый snapshot; public response строить только по
   published manifest.
8. Добавить publish gate с typed codes:
   - `component_image_required`;
   - `component_primary_image_required`;
   - `component_image_not_ready`.
9. При duplicate merge:
   - сохранить primary survivor, если он есть;
   - иначе выбрать первый ready image;
   - images loser дописать после survivor и сбросить конфликтующий primary;
   - нормализовать порядок в той же транзакции.
10. Audit events не содержат object keys или presigned URLs; mutation details содержат только
    component revision, asset IDs и безопасные metadata.

## Frontend change plan — этапы 3 и 4

### Редактор

- Вставить fieldset «Изображения» после «Идентификация» и до «Учебное содержание».
- Для нового draft показать предложение сначала сохранить карточку; отсутствие image не блокирует
  сохранение.
- После сохранения кнопка и dropzone остаются доступны до backend limit 12, а не исчезают после
  первого upload.
- Для каждого image показать thumbnail, status/error, purpose, alt, caption, primary control,
  remove и move controls.
- Использовать buttons с доступными именами для перемещения; drag-and-drop может быть
  дополнительным способом, но не единственным.
- Mutation всегда отправляет последнюю component revision. `revision_conflict` сохраняет локальный
  порядок и предлагает явную перезагрузку, как существующий текстовый editor.

### Preview и student card

- Один primary image показывать крупно.
- Остальные ready images показывать thumbnails/gallery в snapshot order.
- Выбор thumbnail и переход предыдущий/следующий доступны с клавиатуры.
- Использовать `alt_text`; caption отображать через `figcaption`.
- URL пропускать через существующую same-origin/HTTPS проверку.
- Catalog tile выбирает `is_primary`, а не первый случайный image.
- Failed/expired URL даёт детерминированный fallback без утечки draft media.

## Test plan — этап 5

Backend:

- migration upgrade/downgrade и backfill;
- first-image-primary, at-most-one primary и deterministic reorder;
- draft without images;
- publish без image, с pending/rejected image и без primary;
- immutable published order/metadata после изменения draft;
- public API не возвращает original/object key;
- teacher/admin allow, student deny, CSRF required, foreign asset is `404`;
- stale revision и concurrent primary/reorder;
- duplicate merge двух media collections;
- safe presigned GET only for published processed variant.

Frontend:

- повторное добавление второго и последующих images;
- upload pending/ready/rejected/error;
- primary selection, caption/alt/purpose edit, remove и accessible reorder;
- revision conflict без потери local state;
- preview primary/gallery;
- public gallery keyboard navigation and URL fallback;
- existing published response without `media`.

E2E:

- создать draft без images;
- загрузить два images и дождаться `ready`;
- выбрать primary, переставить, опубликовать;
- проверить public card и отсутствие original URL;
- изменить draft order после публикации и убедиться, что public snapshot не изменился до новой
  публикации.

Quality gate остаётся штатным: Ruff format/check, mypy, Bandit, pytest, PostgreSQL integration,
frontend lint/typecheck/test/build и Docker smoke.

## Проверенный baseline

- Актуальный `main` собран Docker Compose и доступен на `http://localhost:8080`.
- Backend health сообщает version `0.21.0`; backend, frontend, workers, PostgreSQL, Redis и MinIO
  healthy.
- Целевые media/catalog/security backend tests: `61 passed`.
- Целевые editor/catalog/media frontend tests в поддерживаемом Node 22 image: `9 passed`.
- Host Node `26.4.0` находится за пределами закреплённого диапазона `>=22.12 <26` и не считается
  поддерживаемым test environment.

## Проверка Stage 2

- unit/backend contracts: migration, OpenAPI, RBAC/CSRF, storage boundary и legacy snapshot;
- PostgreSQL aggregate: две последовательные загрузки, автоматический primary, pending/primary
  publish gates, reorder, смена primary, detach и нормализация;
- immutable publication: изменение draft metadata/order после публикации не меняет student
  snapshot до следующей публикации;
- snapshot не содержит bucket, object key, original URL или presigned URL.

Следующая работа выполняется по Stage 3: frontend fieldset «Изображения» между идентификацией и
учебным содержанием.

## Не входит в изменение

- public MinIO buckets;
- замена Dramatiq/Redis/PostgreSQL или существующих image variants;
- импорт remote images из repository parsers;
- автоматическая публикация parser draft;
- изменение video pipeline;
- физическое удаление binary в пользовательской HTTP mutation.
