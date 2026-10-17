export function TrafficMode() {
  return (
    <section className="traffic-mode" aria-labelledby="traffic-mode-title">
      <h2 id="traffic-mode-title">что защищаем</h2>
      <fieldset className="traffic-mode__options">
        <legend className="sr-only">режим трафика</legend>
        <label className="traffic-choice traffic-choice--active">
          <input
            type="radio"
            name="traffic-mode"
            checked
            readOnly
            value="all"
          />
          <span className="traffic-choice__icon">
            <svg
              width="24"
              height="24"
              viewBox="0 0 24 24"
              fill="none"
              stroke="currentColor"
              strokeWidth="1.7"
              aria-hidden="true"
            >
              <path d="m12 3-8 3v6c0 5 8 9 8 9s8-4 8-9V6Z" />
              <path d="m8 12 3 3 5-6" />
            </svg>
          </span>
          <span>
            <strong>весь трафик</strong>
            <small>все сайты и приложения через VPN</small>
          </span>
          <span className="traffic-choice__check" aria-hidden="true">
            ✓
          </span>
        </label>
        <label className="traffic-choice traffic-choice--future">
          <input type="radio" name="traffic-mode" disabled value="include" />
          <span className="traffic-choice__icon" aria-hidden="true">
            ＋
          </span>
          <span>
            <strong>только выбранные сайты</strong>
            <small>остальной трафик — напрямую</small>
            <em>скоро</em>
          </span>
        </label>
        <label className="traffic-choice traffic-choice--future">
          <input type="radio" name="traffic-mode" disabled value="exclude" />
          <span className="traffic-choice__icon" aria-hidden="true">
            −
          </span>
          <span>
            <strong>кроме выбранных сайтов</strong>
            <small>VPN для всего, кроме вашего списка</small>
            <em>скоро</em>
          </span>
        </label>
      </fieldset>
    </section>
  );
}
