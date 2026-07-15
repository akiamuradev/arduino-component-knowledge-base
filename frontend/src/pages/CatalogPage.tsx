export function CatalogPage() {
  return (
    <section>
      <div className="hero">
        <div>
          <p className="eyebrow">Учебный каталог</p>
          <h1>Компоненты Arduino — понятно и по делу</h1>
          <p>
            Каркас готов к подключению опубликованных карточек. До появления catalog API
            интерфейс не подменяет backend тестовыми компонентами.
          </p>
        </div>
        <div className="hero__circuit" aria-hidden="true"><span /><span /><span /></div>
      </div>
      <div className="empty-panel">
        <p className="eyebrow">Состояние каталога</p>
        <h2>Карточки ещё не подключены</h2>
        <p>Следующий предметный этап добавит категории, поиск и опубликованные revision.</p>
      </div>
    </section>
  );
}
