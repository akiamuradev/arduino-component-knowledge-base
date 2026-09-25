# Frontend screenshots

Скриншоты создаются детерминированным Playwright-сценарием `frontend/e2e/product-ui.spec.ts`
с test-only API fixtures. Для обновления используется `ACKB_UPDATE_SCREENSHOTS=1`; production
frontend не содержит mock-данных.

Из каталога `frontend` после установки зависимостей и Chromium:

```bash
ACKB_UPDATE_SCREENSHOTS=1 npm run test:e2e -- --grep "captures approved responsive theme views"
```

Desktop — каталог 1920×1080 с full-page footer; mobile — страница входа 360×800.
Сценарий снимает обе темы, отключает анимации и ждёт загрузки шрифтов и изображений,
включая lazy-логотипы footer. Метаданные на снимке относятся к использованной сборке,
а не подтверждают production deployment. Повторная генерация на той же сборке и в том
же browser/font environment воспроизводима. Новая сборка может изменить видимый Git SHA.
Layout assertions выполняются отдельными E2E-тестами, а не сравнением этих PNG.
