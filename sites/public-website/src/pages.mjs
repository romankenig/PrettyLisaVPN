import { website, releaseBlockers } from "./model.mjs";
import { legalPages } from "./legal.mjs";

export const escape = (value) =>
  String(value).replace(
    /[&<>"']/g,
    (c) =>
      ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[
        c
      ],
  );
const link = (href, text, secondary = false) =>
  `<a class="button${secondary ? " secondary" : ""}" href="${href}">${text}</a>`;
const intro = (eyebrow, title, text) =>
  `<div class="page-intro"><p class="eyebrow">${eyebrow}</p><h1>${title}</h1><p class="lead">${text}</p></div>`;
const legalLinks = () =>
  Object.entries(legalPages)
    .map(([key, page]) => `<a href="/legal/${key}/">${page.title}</a>`)
    .join("");
const previewNotice =
  '<div class="preview-banner"><span class="draft-dot" aria-hidden="true"></span><strong>Предпросмотр сайта</strong><span>Оплата ещё не подключена. Документы — черновики.</span><a href="/readiness/">Что осталось</a></div>';

export function shell(path, title, description, body) {
  const nav = [
    ["/plans/", "Тарифы"],
    ["/setup/", "Приложения"],
    ["/support/", "Поддержка"],
  ];
  return `<!doctype html><html lang="ru"><head><meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1"><meta name="robots" content="noindex,nofollow"><meta name="description" content="${escape(description)}"><meta name="theme-color" content="#2c016d"><title>${escape(title)} — PrettyLisaVPN</title><link rel="icon" href="/assets/lock.svg" type="image/svg+xml"><link rel="stylesheet" href="/assets/style.css"><script type="module" src="/assets/app.js"></script></head><body><a class="skip-link" href="#main">К содержимому</a>${previewNotice}<header class="header wrap"><a class="brand" href="/" aria-label="PrettyLisaVPN — главная"><img src="/assets/lock.svg" alt="" width="34" height="40"><span>PrettyLisaVPN</span></a><button class="menu-toggle" aria-controls="navigation" aria-expanded="false">Меню <span aria-hidden="true">☰</span></button><nav id="navigation" aria-label="Основная навигация">${nav.map(([url, label]) => `<a href="${url}"${path === url ? ' aria-current="page"' : ""}>${label}</a>`).join("")}<a class="nav-account" href="/account/"${path === "/account/" ? ' aria-current="page"' : ""}>Моя подписка <span aria-hidden="true">↗</span></a></nav></header><main id="main" class="wrap" tabindex="-1">${body}</main><footer><div class="wrap footer-grid"><div><a class="brand" href="/"><img src="/assets/lock.svg" alt="" width="34" height="40"><span>PrettyLisaVPN</span></a><p>VPN для Android и Windows.<br>Вы выбираете, что защищать.</p><a href="mailto:${website.seller.email}">${website.seller.email}</a></div><div><h2>Сервис</h2><a href="/plans/">Тарифы</a><a href="/payment/">Оплата</a><a href="/setup/">Получение и настройка</a><a href="/account/">Управление подпиской</a><a href="/support/">Поддержка</a></div><div class="footer-docs"><h2>Документы <span>черновики</span></h2>${legalLinks()}</div></div><div class="wrap footer-bottom"><span>© ${website.reviewedOn.slice(0, 4)} PrettyLisaVPN</span><span>Кениг Роман Сергеевич · НПД · ИНН ${website.seller.inn}</span><a href="/readiness/">Статус готовности сайта</a></div></footer></body></html>`;
}

function home() {
  return `<section class="hero"><div class="hero-copy"><p class="eyebrow"><span class="small-dot"></span> Android + Windows</p><h1>Ваш интернет.<br>Ваш <span class="purple">выбор.</span></h1><p class="lead">Подключайте VPN для всего трафика или только для выбранных сервисов. Управляйте подключением в PrettyLisaVPN.</p><div class="actions">${link("/plans/", 'Выбрать тариф <span aria-hidden="true">↗</span>')}${link("/setup/", "Начать с Free", true)}</div><p class="hero-note">Один аккаунт. До 5 активных устройств.</p></div><div class="hero-visual" aria-label="Схема возможностей PrettyLisaVPN"><div class="orbit orbit-one"></div><div class="orbit orbit-two"></div><div class="visual-label">ВЫ РЕШАЕТЕ, ЧТО ЗАЩИЩАТЬ</div><div class="product-sheet"><div class="sheet-top"><span class="mini-symbol">↗</span><span>PrettyLisaVPN</span><span class="demo-label">схема</span></div><div class="sheet-row"><span>Куда подключиться</span><b>Выбрать страну</b></div><div class="sheet-connection"><span class="line-node"></span><i></i><span class="route-pill">VPN</span><i></i><span class="line-node outline"></span></div><div class="sheet-row"><span>Что защищаем</span><b>Выбранное</b></div><div class="service-row"><span class="service-chip youtube" aria-label="YouTube">▶</span><span class="service-chip telegram" aria-label="Telegram">➤</span><span class="service-chip add" aria-label="Другие сервисы">+</span><span class="service-caption">Выбираете вы</span></div><div class="sheet-bottom">Всё · Выбранное · Кроме выбранного</div></div><div class="visual-foot"><span>Телефон</span><span>Компьютер</span><span>Один аккаунт</span></div></div></section>
  <section class="facts-strip" aria-label="Коротко о сервисе"><div><b>5</b><span>активных устройств<br>на аккаунт</span></div><div><b>1 час</b><span>в сутки UTC<br>на Free</span></div><div><b>Без рекламы</b><span>на Free<br>и Premium</span></div></section>
  <section class="section"><div class="section-heading"><p class="eyebrow">ПОДКЛЮЧЕНИЕ ПОД ВАШИ ЗАДАЧИ</p><h2>Меньше лишнего.<br>Больше контроля.</h2></div><div class="feature-grid"><article><span class="feature-mark" aria-hidden="true">↔</span><h3>Выбор трафика</h3><p>Защитите всё, только выбранные сервисы или всё, кроме выбранного. Настройки каждого режима сохраняются отдельно.</p></article><article><span class="feature-mark" aria-hidden="true">⌁</span><h3>Несколько способов</h3><p>Приложение перебирает доступные способы подключения и проверяет результат. Среди реализованных — WireGuard и AmneziaWG.</p></article><article><span class="feature-mark" aria-hidden="true">＠</span><h3>Вход по почте</h3><p>Получите одноразовый код на email. Тариф и доступ к устройствам связаны с аккаунтом.</p></article></div><p class="muted section-note">VPN не гарантирует работу во всех сетях. Скорость и устойчивость зависят от вашего соединения и доступности сервера.</p></section>
  <section class="journey section"><div><p class="eyebrow">ОТ ВЫБОРА ДО ПОДКЛЮЧЕНИЯ</p><h2>Понятно на<br>каждом шаге.</h2><a class="text-link" href="/setup/">Посмотреть инструкцию →</a></div><ol class="steps"><li><span>01</span><div><h3>Выберите тариф</h3><p>Попробуйте Free или изучите условия Premium.</p></div></li><li><span>02</span><div><h3>Проверьте оплату</h3><p>Для Premium будут показаны сумма, срок и условия. Приём платежей пока не открыт.</p></div></li><li><span>03</span><div><h3>Войдите в приложение</h3><p>Используйте email своего аккаунта. Оплаченный доступ должен появиться после подтверждения платежа.</p></div></li><li><span>04</span><div><h3>Настройте подключение</h3><p>Выберите сервер и режим защиты. Free доступен без покупки.</p></div></li></ol></section>
  <section class="cta"><div><p class="eyebrow">СНАЧАЛА ПОПРОБУЙТЕ</p><h2>Начните с одного часа.</h2><p>Free — один общий час в сутки на весь аккаунт, без рекламы.</p></div>${link("/setup/", 'Как начать <span aria-hidden="true">→</span>')}</section>
  <section class="section faq"><h2>Коротко о главном</h2>${faqItems()}</section>`;
}

function faqItems() {
  return [
    [
      "Какие устройства поддерживаются сейчас?",
      'Рабочие клиенты есть для Android и Windows. Сайт не обещает готовые версии для iOS, macOS, Linux, телевизоров или браузера. <a href="/setup/">Получение приложений</a>.',
    ],
    [
      "Чем Free отличается от Premium?",
      'Free даёт один час в сутки UTC на аккаунт. У Premium нет суточного лимита времени в течение оплаченного периода. До пяти активных устройств доступно на обоих тарифах. <a href="/plans/">Сравнить тарифы</a>.',
    ],
    [
      "Будут ли автоматические списания?",
      'Сейчас автосписания не подключены. Для первого варианта оплаты согласовано ручное продление: новый платёж по вашему действию. <a href="/legal/payments/">Проект правил оплаты</a>.',
    ],
    [
      "Можно ли уже оплатить на сайте?",
      'Пока нет. Cardlink ещё не одобрил проект, платёжный адаптер и документы не готовы к продажам. <a href="/payment/">Статус оплаты</a>.',
    ],
    [
      "Как обратиться за помощью?",
      'Напишите на help@prettylisavpn.com или откройте поддержку в приложении. Не отправляйте коды входа и данные карты. <a href="/support/">Подготовить письмо</a>.',
    ],
  ]
    .map(
      ([q, a]) =>
        `<details><summary>${q}<span aria-hidden="true">+</span></summary><div>${a}</div></details>`,
    )
    .join("");
}

function plans() {
  return `${intro("ТАРИФЫ", "Выберите свой ритм.", "Попробуйте Free. Для более долгих подключений — Premium с ручным продлением.")}<div class="currency-control" role="group" aria-label="Валюта отображения"><button data-currency="RUB" aria-pressed="true">₽ RUB</button><button data-currency="USD" aria-pressed="false">$ USD</button></div><div class="plan-grid"><article class="plan"><p class="eyebrow">ПОЗНАКОМИТЬСЯ С СЕРВИСОМ</p><h2>Free</h2><p class="price">0 ₽</p><p class="muted">Без покупки и привязки карты</p><ul class="check-list"><li>1 общий час в сутки UTC</li><li>До 5 активных устройств</li><li>Без рекламы</li><li>Выбор доступных Free-серверов</li><li>Режимы разделения трафика</li></ul>${link("/setup/", "Начать с Free", true)}<p class="fine-print">Лимит обновляется в 00:00 UTC. Время общее для всех устройств аккаунта.</p></article><article class="plan featured"><div class="plan-tag">ДЛЯ ДОЛГИХ ПОДКЛЮЧЕНИЙ</div><p class="eyebrow">ОПЛАЧЕННЫЙ ПЕРИОД</p><h2>Premium</h2><p class="price" data-premium-price>199 ₽</p><p class="muted">за один календарный месяц</p><ul class="check-list"><li>Без суточного лимита времени</li><li>До 5 активных устройств</li><li>Без рекламы</li><li>Выбор страны из доступных серверов</li><li>Режимы разделения трафика</li></ul>${link("/checkout/?currency=RUB", 'Посмотреть условия <span aria-hidden="true">→</span>')}<p class="fine-print">Ручное продление. Приём платежей пока не открыт.</p></article></div><section class="section compact"><h2>До оплаты — все условия.</h2><div class="terms-grid"><article><h3>Когда начинается месяц</h3><p>После подтверждения оплаты. Календарный месяц заканчивается в соответствующий день следующего месяца; если такого дня нет — в последний.</p></article><article><h3>Что с комиссией</h3><p>Комиссия Cardlink ещё не подтверждена. Пока она неизвестна, итог не рассчитывается и оплата недоступна.</p></article><article><h3>Что с продлением</h3><p>Новый платёж совершаете вы сами. Автоматических ежемесячных списаний сейчас нет.</p></article></div><p class="notice">Лимит объёма трафика, ограничения скорости и коммерческие условия доступности ещё нужно окончательно подтвердить. Они не подменяются обещанием «без ограничений».</p><div class="inline-links"><a href="/legal/payments/">Правила оплаты</a><a href="/legal/refunds/">Возвраты</a><a href="/legal/terms/">Соглашение</a></div></section>`;
}

function checkout() {
  return `${intro("ПРОВЕРКА УСЛОВИЙ", "Premium на месяц.", "Проверьте срок, стоимость и способ продления до перехода к оплате.")}<div class="checkout-grid"><section class="checkout-main"><h2>Условия подписки</h2><dl class="facts"><div><dt>Тариф</dt><dd>Premium</dd></div><div><dt>Срок</dt><dd>Один календарный месяц</dd></div><div><dt>Начало</dt><dd>После подтверждения оплаты</dd></div><div><dt>Продление</dt><dd>Вручную, новым платежом</dd></div><div><dt>Устройства</dt><dd>До 5 активных на аккаунт</dd></div></dl><label class="field-label" for="checkout-currency">Валюта цены</label><select id="checkout-currency"><option value="RUB">Рубли · RUB</option><option value="USD">Доллары США · USD</option></select><p class="muted">Валюты приёма Cardlink ещё нужно подтвердить. Указанные цены согласованы для черновика.</p><div class="provider-row"><span class="provider-icon" aria-hidden="true">▤</span><div><h3>Российская карта · Cardlink</h3><p>Заявка на подключение проекта ещё не подана.</p></div><span class="status">Недоступно</span></div><p class="fine-print">Название провайдера обозначает план подключения, а не партнёрство или одобрение. Данные карты здесь не запрашиваются.</p><div class="checkout-documents"><h3>Документы перед оплатой</h3><p>Документы ещё не утверждены. Приём согласий и платежей закрыт.</p><div class="inline-links">${legalLinks()}</div></div></section><aside class="order-summary" aria-labelledby="order-title"><p class="eyebrow">ВАШ ВЫБОР</p><h2 id="order-title">Premium</h2><div class="summary-line"><span>Календарный месяц</span><b data-premium-price>199 ₽</b></div><div class="summary-line"><span>Комиссия</span><span>Не подтверждена</span></div><div class="summary-total"><span>Итого к оплате</span><b>Пока не рассчитано</b></div><p class="notice" id="checkout-reason">Оплата откроется после одобрения Cardlink, подключения API и утверждения документов.</p><button class="button" disabled aria-describedby="checkout-reason">Оплата пока недоступна</button><p class="fine-print">Заказ не создан. Деньги не списываются. Вы можете начать с Free.</p><a class="text-link" href="/setup/">Попробовать Free →</a></aside></div>`;
}

function payment() {
  return `${intro("ОПЛАТА", "Сначала — ясные условия.", "В текущем плане подключения — российские карты через Cardlink. Реальная оплата ещё не включена.")}<section class="payment-card"><div><p class="eyebrow">ПЛАНИРУЕМЫЙ СПОСОБ</p><h2>Банковская карта</h2><p>Платёжная страница Cardlink будет открываться только после одобрения проекта и проверки интеграции.</p></div><span class="status">Не подключено</span></section><div class="terms-grid section compact"><article><h3>Без карты на этом сайте</h3><p>Номер карты и CVC нужно будет вводить у платёжного провайдера. PrettyLisaVPN не размещает здесь карточную форму.</p></article><article><h3>Итог до платежа</h3><p>Цена, валюта, комиссия и сумма должны быть показаны заранее. Неизвестная комиссия не считается нулевой.</p></article><article><h3>Без автосписаний</h3><p>Первый согласованный вариант — ручное продление. Возможность рекуррентных платежей отдельно не подтверждена.</p></article></div><div class="notice"><h3>Текущий статус</h3><p>Аккаунт Cardlink создан, заявка ещё не подана. Приём платежей и отправка картовых данных недоступны. Действующий тариф можно проверить в приложении.</p></div><div class="actions">${link("/checkout/", "Проверить условия Premium")}${link("/account/", "Моя подписка", true)}</div>`;
}

function setup() {
  return `${intro("ПРИЛОЖЕНИЯ И НАСТРОЙКА", "Подключитесь с вашего устройства.", "Сейчас реально поддерживаются Android и Windows. Вход — по одноразовому коду на email.")}<div class="download-grid"><article class="download-card"><div class="platform-mark" aria-hidden="true">◉</div><h2>Android</h2><p>Один APK. Установка поверх существующей версии сохраняет приложение и его настройки.</p><a class="button secondary" href="https://github.com/romankenig/PrettyLisaVPN/actions/runs/41589719117/artifacts/13210046686">Тестовая сборка 0.21.0 ↗</a><p class="fine-print">ZIP-архив с APK. Для скачивания нужен доступ к GitHub-репозиторию. Это временный канал тестирования.</p></article><article class="download-card"><div class="platform-mark windows-mark" aria-hidden="true">⊞</div><h2>Windows</h2><p>Установщик настраивает приложение и необходимые компоненты VPN.</p><a class="button secondary" href="https://github.com/romankenig/PrettyLisaVPN/actions/runs/41589719139/artifacts/13209642463">Тестовая сборка 0.25.0 ↗</a><p class="fine-print">ZIP-архив с PrettyLisaVPN-Setup.exe. Нужен доступ к GitHub-репозиторию.</p></article></div><p class="notice">Общедоступные загрузки для новых пользователей ещё нужно подготовить до запуска продаж. Если нет доступа к тестовым сборкам, <a href="/support/?topic=access">напишите в поддержку</a>.</p><section class="section"><div class="section-heading"><p class="eyebrow">ПОШАГОВО</p><h2>От установки до VPN.</h2></div><div class="setup-columns"><article><h3>Android</h3><ol><li>Распакуйте ZIP и установите единственный app-debug.apk.</li><li>Если Android попросит разрешение установки из выбранного источника, подтвердите его только для скачанного вами файла.</li><li>Откройте PrettyLisaVPN, укажите email и введите полученный код.</li><li>Выберите страну и нажмите «подключить». Подтвердите системное разрешение VPN при первом подключении.</li><li>Дождитесь проверки соединения. Первое подключение может занять несколько минут.</li></ol></article><article><h3>Windows</h3><ol><li>Распакуйте ZIP и запустите PrettyLisaVPN-Setup.exe.</li><li>Следуйте установщику; при установке системных компонентов может потребоваться разрешение администратора.</li><li>Войдите в PrettyLisaVPN по email и одноразовому коду.</li><li>Выберите страну и нажмите «подключить».</li><li>Проверьте статус подключения. В «что защищаем» можно выбрать режим маршрутизации.</li></ol></article></div></section><section class="access-help"><h2>Доступ не появился?</h2><p>Для Free покупать подписку не нужно. Для будущего платного подключения потребуется подтверждённый платёж и вход с правильным email. Точный предельный срок активации платного доступа ещё согласуется.</p><p>Обновите экран подписки. Если доступ не появился, сообщите поддержке email аккаунта и номер заказа, если он есть. Не оплачивайте повторно до выяснения статуса.</p>${link("/support/?topic=access", "Связаться с поддержкой")}</section>`;
}

function account() {
  return `${intro("МОЯ ПОДПИСКА", "Управление — в приложении.", "Используйте существующий интерфейс PrettyLisaVPN. Веб-кабинета с отдельным входом пока нет.")}<div class="account-guide"><div class="account-path"><span>PrettyLisaVPN</span><span aria-hidden="true">→</span><span>Настройки</span><span aria-hidden="true">→</span><strong>Подписка</strong></div><div class="terms-grid"><article><h3>Ваш тариф и срок</h3><p>Текущий план, дата окончания и оставшиеся оплаченные дни отображаются после входа в приложение.</p></article><article><h3>Продление и оплата</h3><p>Действия доступны только при подключённом провайдере. Сейчас экран позволяет изучить условия, но реальные платежи отключены.</p></article><article><h3>Поддержка</h3><p>Откройте «О приложении» → «Поддержка» или подготовьте письмо на сайте.</p></article></div></div><section class="section compact"><h2>История заказов и отмена</h2><p class="prose">Общая история оплаченных заказов на сайте ещё не реализована. Отображение статусов и обращений после реального платежа нужно проверить вместе с Cardlink до запуска продаж. Не показываем вымышленные заказы или статус чужой подписки.</p><p class="prose">Автосписания сейчас не подключены. Если они появятся, способ отмены и её подтверждение должны быть доступны до начала приёма согласий.</p><div class="actions">${link("/support/?topic=refund", "Запросить возврат", true)}${link("/setup/", "Получить приложение")}</div></section>`;
}

function support() {
  return `${intro("ПОДДЕРЖКА", "Поможем разобраться.", "Подготовьте письмо: оно откроется в вашей почтовой программе. Сайт не отправляет сообщение автоматически.")}<div class="support-grid"><form id="support-form" method="post" action="/support/" novalidate><label for="support-topic">Тема</label><select id="support-topic" name="topic"><option value="question">Вопрос о сервисе</option><option value="access">Не получен доступ</option><option value="refund">Запрос возврата</option><option value="privacy">Персональные данные</option></select><label for="support-message">Что произошло?</label><textarea id="support-message" name="message" rows="7" minlength="10" maxlength="1500" placeholder="Опишите проблему, устройство и время. Для оплаты — дата и номер заказа, если он есть." aria-describedby="support-hint support-error" required></textarea><p id="support-hint" class="fine-print">Не указывайте номер карты, CVC, пароли или одноразовые коды.</p><p id="support-error" class="form-error" role="alert"></p><button class="button" type="submit">Подготовить письмо <span aria-hidden="true">→</span></button><p id="support-result" class="muted" role="status"></p></form><aside><p class="eyebrow">НАПИСАТЬ НАПРЯМУЮ</p><a class="email-link" href="mailto:help@prettylisavpn.com">help@prettylisavpn.com</a><p>Если почтовая программа не настроена, скопируйте адрес и отправьте письмо привычным способом.</p><h3>О сроках</h3><p>Регламент ответа ещё согласуется. Не обещаем круглосуточную поддержку или ответ за определённое время.</p><div class="inline-links"><a href="/legal/seller/">Продавец и контакты</a><a href="/legal/refunds/">Запросы возврата</a><a href="/legal/privacy/">Персональные данные</a></div></aside></div>`;
}

function documents() {
  return `${intro("ДОКУМЕНТЫ", "Условия без мелкого шрифта.", "Все документы ниже — проекты на согласование, а не готовые условия продажи.")}<div class="document-grid">${Object.entries(
    legalPages,
  )
    .map(
      ([key, page], i) =>
        `<a href="/legal/${key}/"><span class="doc-number">0${i + 1}</span><h2>${page.title}</h2><p>${page.lead}</p><span class="text-link">Открыть черновик →</span></a>`,
    )
    .join("")}</div>`;
}
function legalPage(page) {
  return `<a class="back-link" href="/legal/">← Все документы</a>${intro("ЧЕРНОВИК · НЕ УТВЕРЖДЁН", page.title, page.lead)}<div class="legal-layout"><aside class="legal-nav" aria-label="Документы">${legalLinks()}</aside><article class="legal-document"><div class="draft-note"><strong>Не использовать как действующий документ.</strong><p>Редакция для проверки от 3 ноября 2026 года. Незаполненные условия отмечены. Приём платежей закрыт.</p></div>${page.sections.map(([heading, html]) => `<section><h2>${heading}</h2>${html}</section>`).join("")}<p class="fine-print">Применимая юрисдикция проекта: Россия. Полный текст и процедуры требуют согласования до публикации.</p></article></div>`;
}
function readiness() {
  return `${intro("ПРЕДПРОСМОТР · ДЛЯ ВЛАДЕЛЬЦА И ПРОВЕРКИ", "Что готово. Что ещё нет.", "Прозрачный статус проекта без утверждений об одобрении платёжного провайдера.")}<div class="readiness-grid"><section><h2>Можно проверить сейчас</h2><ul class="check-list"><li>Главная, тарифы и условия месяца</li><li>Сведения о продавце и контакт поддержки</li><li>Инструкции Android и Windows</li><li>Путь к управлению подпиской в приложениях</li><li>Форма подготовки письма и запрос возврата</li><li>Шесть отдельных черновиков документов</li></ul></section><section><h2>До приёма платежей</h2><ul class="blocker-list">${releaseBlockers()
    .map((x) => `<li>${escape(x)}</li>`)
    .join(
      "",
    )}<li>Комиссия, валюты и срок активации доступа не подтверждены</li><li>История заказов и обработка статусов реального платежа не проверены</li></ul></section></div><section class="section compact prose"><h2>Вопросы Cardlink</h2><ol><li>Принимаете ли вы VPN-сервис российского самозанятого на НПД? Какие сведения и документы нужны?</li><li>Какие карты и валюты доступны этому продавцу? Как узнать комиссию и итог до создания платежа?</li><li>Как проверять подлинность уведомления, сверять статус и безопасно повторять запросы после тайм-аута?</li><li>Как выполняются полный/частичный возврат и обработка спорного платежа?</li><li>Кто и как передаёт данные для чека НПД? Есть ли интеграция с «Мой налог»?</li><li>Если позже понадобятся автосписания: есть ли подтверждённый API, требования к согласию и способ отзыва?</li></ol><p>Текущий фокус — только Cardlink. Заявка ещё не подана; условия совместного использования других провайдеров в этой версии не реализуются.</p><a href="https://cardlink.link/en/reference" class="text-link">Официальные требования Cardlink ↗</a><h2>Сведения от владельца</h2><p>Получены: имя, статус НПД, Россия, ИНН, email поддержки, цены 199 ₽ / $2,99, календарный месяц, начало после подтверждения оплаты и ручное продление. Не получены: адрес для претензий, возвраты, выдача чеков, сроки активации и ответа, полные условия хранения данных и инфраструктуры.</p></section>`;
}

export function pages() {
  const list = [
    [
      "/",
      "VPN для Android и Windows",
      "PrettyLisaVPN: выбор трафика, Free и Premium, приложения и поддержка.",
      home(),
    ],
    [
      "/plans/",
      "Тарифы",
      "Free и Premium: цены, сроки, устройства и ручное продление.",
      plans(),
    ],
    [
      "/checkout/",
      "Условия Premium",
      "Проверка цены и условий перед будущей оплатой. Платежи пока недоступны.",
      checkout(),
    ],
    [
      "/payment/",
      "Оплата",
      "Статус подключения Cardlink и правила безопасной оплаты.",
      payment(),
    ],
    [
      "/setup/",
      "Получение и настройка",
      "Инструкции для Android и Windows и действия при неполучении доступа.",
      setup(),
    ],
    [
      "/account/",
      "Управление подпиской",
      "Как проверить подписку и обратиться в поддержку через приложения.",
      account(),
    ],
    [
      "/support/",
      "Поддержка",
      "Подготовьте письмо в поддержку PrettyLisaVPN.",
      support(),
    ],
    [
      "/legal/",
      "Документы",
      "Черновики документов и сведений о продавце.",
      documents(),
    ],
    [
      "/readiness/",
      "Готовность к запуску",
      "Что уже реализовано и что требуется перед приёмом оплаты.",
      readiness(),
    ],
    ...Object.entries(legalPages).map(([key, page]) => [
      `/legal/${key}/`,
      page.title,
      page.lead,
      legalPage(page),
    ]),
    [
      "/404/",
      "Страница не найдена",
      "Проверьте адрес или вернитесь на главную.",
      `${intro("404", "Здесь пока ничего нет.", "Возможно, ссылка устарела. Вернитесь на главную или напишите в поддержку.")}<div class="actions">${link("/", "На главную")}${link("/support/", "Поддержка", true)}</div>`,
    ],
  ];
  return new Map(
    list.map(([path, title, description, body]) => [
      path,
      shell(path, title, description, body),
    ]),
  );
}
