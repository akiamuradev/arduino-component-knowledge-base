import { isRouteErrorResponse, Link, useRouteError } from "react-router-dom";

import { ErrorState } from "../components/AsyncStates";

export function ForbiddenPage() {
  return (
    <main className="centered-page">
      <ErrorState
        title="Недостаточно прав"
        message="Backend не предоставил роль для этого раздела."
      />
      <Link to="/">Вернуться в каталог</Link>
    </main>
  );
}

export function NotFoundPage() {
  return (
    <main className="centered-page">
      <p className="eyebrow">404</p>
      <h1>Страница не найдена</h1>
      <Link to="/">Вернуться в каталог</Link>
    </main>
  );
}

export function RouteErrorPage() {
  const error = useRouteError();
  const message = isRouteErrorResponse(error)
    ? `Маршрут завершился с кодом ${String(error.status)}.`
    : "Произошла непредвиденная ошибка интерфейса.";
  return (
    <main className="centered-page">
      <ErrorState title="Ошибка страницы" message={message} />
      <Link to="/">Вернуться в каталог</Link>
    </main>
  );
}
