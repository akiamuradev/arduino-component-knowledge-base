# Contributing and forks / Участие в разработке и fork

**[English](#english) · [Русский](#русский)**

## English

### Contributing to the upstream project

1. Open the project on GitHub and select **Fork**. Create the fork under your own account.
2. Clone your fork, then register the original repository as `upstream`:

```bash
git clone https://github.com/<username>/arduino-component-knowledge-base.git
cd arduino-component-knowledge-base
git remote add upstream https://github.com/akiamuradev/arduino-component-knowledge-base.git
git fetch upstream
git switch -c feature/<short-name> upstream/main
```

Do not develop directly on `main`, and do not send feature commits directly to it. A pull request
should solve one bounded problem.

Before opening or updating a PR:

1. Synchronize the original repository and rebase or merge according to the maintainer's policy:

   ```bash
   git fetch upstream
   ```

2. Run the checks relevant to your change. For the complete release matrix, follow
   [Testing](docs/TESTING.md); the main backend, frontend, documentation, and browser commands are
   also listed in [README.md](README.md).
3. Review the diff and make sure it contains no `.env`, credentials, generated build output,
   user uploads, database dumps, logs, or other user data.
4. Push the feature branch to your fork and open a pull request against
   `akiamuradev/arduino-component-knowledge-base:main`.
5. Explain the problem, the bounded solution, verification results, migrations or operational
   impact, and any remaining risk.

Keep shared commands synchronized between [README.md](README.md) and
[README.ru.md](README.ru.md).

### Independent forks and derivative projects

Application code is licensed under the
[GNU General Public License v3.0 or later](LICENCE). SPDX: `GPL-3.0-or-later`. Copyright © 2026 akiamuradev.
Review the license text before distributing a fork or derivative.

Imported third-party data does not become part of the application-code license. Preserve the
source-specific license, attribution, provenance, upstream revision, and modification notice.
See [Data licensing](docs/DATA_LICENSING.md) and
[Third-party notices](THIRD_PARTY_NOTICES.md).

Before any public deployment:

- replace every development or example credential and keep real secrets outside Git;
- complete the [security](docs/SECURITY.md), [deployment](docs/DEPLOYMENT.md), and
  [operations](docs/OPERATIONS.md) requirements;
- do not imply official affiliation with Arduino, Seeed Studio, KiCad, or akiamuradev;
- if the product is renamed, update branding, package metadata, Compose image names, frontend
  metadata, versions, and documentation consistently.

## Русский

### Вклад в исходный проект

1. Откройте проект на GitHub, нажмите **Fork** и создайте копию в своём аккаунте.
2. Клонируйте fork и добавьте исходный репозиторий как `upstream`:

```bash
git clone https://github.com/<username>/arduino-component-knowledge-base.git
cd arduino-component-knowledge-base
git remote add upstream https://github.com/akiamuradev/arduino-component-knowledge-base.git
git fetch upstream
git switch -c feature/<short-name> upstream/main
```

Не разрабатывайте непосредственно в `main` и не отправляйте feature-коммиты прямо в неё. Один
pull request должен решать одну ограниченную задачу.

Перед созданием или обновлением PR:

1. Получите актуальное состояние исходного репозитория и выполните rebase или merge согласно
   правилам maintainer:

   ```bash
   git fetch upstream
   ```

2. Запустите проверки, соответствующие изменению. Полная release matrix описана в
   [документе о тестировании](docs/TESTING.md), а основные команды backend, frontend,
   документации и browser приведены в [README.ru.md](README.ru.md).
3. Проверьте diff: в нём не должно быть `.env`, credentials, generated build output,
   пользовательских uploads, database dumps, логов и других пользовательских данных.
4. Отправьте feature-ветку в свой fork и откройте pull request в
   `akiamuradev/arduino-component-knowledge-base:main`.
5. Опишите проблему, ограниченное решение, результаты проверок, влияние на миграции или
   эксплуатацию и оставшиеся риски.

Общие команды в [README.md](README.md) и [README.ru.md](README.ru.md) должны оставаться
синхронизированными.

### Обязательный release gate

Для любой версии, bugfix, UI/layout или CI-исправления «код готов» не означает
«релиз завершён». Нельзя объявлять задачу completed / done / release-ready, пока:

1. Все обязательные GitHub CI checks не завершились успешно. Pending, failed,
   cancelled и пропуски из-за ошибок конфигурации не считаются успехом.
2. После merge в `main` и разрешённого production deployment не проверены running
   containers, production smoke и build metadata на сайте/API.
3. Версия, полный Git SHA и дата/время сборки из обслуживаемых артефактов не сверены
   с фактическим deployed checkout и сборкой. Значения получают из project metadata,
   Git и процесса сборки, а не придумывают и не берут из устаревшего `.env`.

Итоговый отчёт должен содержать version, full commit SHA, build date, CI status,
production smoke result и подтверждение обслуживания именно этого build.
Несовпадение provenance оставляет релиз незавершённым независимо от работоспособности UI.
Зелёные локальные тесты, tag, CHANGELOG или merge сами по себе этот gate не закрывают.
Если deployment запрещён или не разрешён в задаче, production не изменяют:
явно фиксируют незавершённую production-проверку и запрашивают отдельное разрешение.

### Независимый fork или производный проект

Код приложения распространяется по
[GNU General Public License v3.0 or later](LICENCE). SPDX: `GPL-3.0-or-later`. Автор: akiamuradev. Перед распространением fork или производного проекта изучите полный текст лицензии.

Импортированные сторонние данные не становятся частью лицензии кода приложения. Сохраняйте
лицензию источника, attribution, provenance, upstream revision и описание преобразований.
Подробнее: [лицензирование данных](docs/DATA_LICENSING.md) и
[уведомления о сторонних материалах](THIRD_PARTY_NOTICES.md).

Перед любым публичным deployment:

- замените все development/example credentials и храните реальные secrets вне Git;
- выполните требования [безопасности](docs/SECURITY.md),
  [развёртывания](docs/DEPLOYMENT.md) и [эксплуатации](docs/OPERATIONS.md);
- не создавайте впечатление официальной связи с Arduino, Seeed Studio, KiCad или akiamuradev;
- при переименовании продукта согласованно обновите branding, package metadata, Compose image
  names, frontend metadata, версии и документацию.
