# Android VPN runtime — 0.8.0

Android 0.7.2/code14 → **0.8.0/code15 (MINOR)**. Windows 0.12.0,
backend 0.10.0 и schema0026 не изменяются. Отдельная ветка
`feat/android-wireguard-vpn` от develop `f9fd9ae0dd2ee7063e887fedf4e0174f7670a30b`.
Точные product/build SHA, run/attempt, APK и результаты последнего CI фиксируются
в PR. Наличие реализации и синтетического теста не доказывает работу живого узла.

## Границы

Официальный `com.wireguard.android:tunnel:1.0.20260102`, userspace GoBackend без root.
Версия и SHA256 AAR закреплены: `2b9c16db026496123e4db695d26d03d1958a201096c7c4c89b21077dc70f3119`.
CI проверяет digest, совместимость API и native payload текущего APK.
Неиспользуемые root executables libwg.so/libwg-quick.so исключены из упаковки,
VpnService использует только libwg-go.so.
В manifest один `.vpn.PrettyVpnService`, наследник `GoBackend.VpnService`.
Исходный сервис библиотеки удаляется manifest merger. `super.onCreate()` передаёт
наш экземпляр библиотеке ДО setState(UP); второй TUN/service не запускается.
FGS запускается из foreground после системного consent, использует systemExempted
для одобренного пользователем VPN, постоянное low-importance уведомление и stop action.
POST_NOTIFICATIONS запрашивается отдельно на API33+; отказ не подменяет VPN consent.
START_NOT_STICKY, always-on/boot restart не включены. Нет обхода background limits.

Поддерживается только **первый явный WIREGUARD/UDP/WIREGUARD/NONE** candidate,
MTU1280, VPN DNS, FULL_TUNNEL, IPv4 endpoint/client /32, ровно `0.0.0.0/0`.
Country/port должны совпадать с bootstrap. Empty, missing, legacy NATIVE,
обфускация, OpenVPN и MASQUE отклоняются с DELETE сессии; fallback не выполняется.
Windows legacy-секреты/переменные окружения не копируются. Если development node
выдаёт только legacy NATIVE, настоящий connect останется недоступным для этого узла
до отдельной настройки совместимого профиля; backend здесь не меняется.
Split tunneling/IPv6 forwarding не реализованы. Один peer с IPv4 default route
не включает GoBackend allowFamily: не сконфигурированный IPv6 блокируется Android,
не используется allowBypass и не исключается весь UID приложения.

## Control plane и ключи

POST /vpn/sessions, GET /vpn/sessions/current (X-VPN-Candidates:1),
DELETE /vpn/sessions/{UUID}; те же bearer/rotation через SessionCoordinator.
Сервер выбирает узел, лимит Free и expires_at. Приложение не выдумывает новый час.
Deadline рассчитывается из expires_at − server_time и monotonic elapsedRealtime.

На каждую новую попытку WireGuard KeyPair из официальной crypto API; приватный ключ
только в памяти runtime, не в Snapshot/SavedState/BuildConfig/config-файле или logs.
После остановки native config отпускается. Полное затирание JVM strings не обещается.
После смерти процесса ключ не восстанавливается: старый peer удаляется, Connected
не восстанавливается из диска. AES-GCM/Keystore/AtomicFile/noBackup хранит только
account UUID и намерение cleanup (session UUID либо uncertain create), без ключей.
Записи разных аккаунтов не переиспользуются и не отправляются с чужим bearer.

## Проверка и завершение

UP → VERIFYING, затем CONNECTED только при живом handshake нужного peer,
VPN network с нашим client address/default route/DNS, VPN-bound DNS resolution,
TLS HTTPS204 фиксированного canary и росте RX/TX. SocketFactory и DNS привязаны к
конкретному VPN Network; нет fallback на физическую сеть, protect() probe или
process-wide bind. Обычная доступность API/public location не является доказательством.
Handshake без canary и canary без tunnel counters недостаточны. Expected egress
адрес backend не сообщает: сравнение с endpoint не выдумывается.

Повторная проверка каждые 15 секунд, плюс backend current/expiry; потеря проверки,
отзыв/stop сервиса и expiry прекращают Connected и ведут к local stop → DELETE.
Переход Wi-Fi/mobile обслуживает штатный GoBackend; бесшовность не обещается,
неуспешная проверка безопасно разрывает попытку. При logout/current-device revoke
cleanup выполняется перед потерей bearer; неподтверждённый cleanup блокирует logout.
Явное удаление локальных auth credentials останавливает local VPN и сохраняет
неразрешённый cleanup для следующего входа того же аккаунта. Backend device revoke
сам выполняет durable termination; приложение не сообщает успешный DELETE без ответа.
Ответ DELETE подтверждает termination intent; при недоступном Node Agent backend
может удалить peer позднее своим worker. API не выдаёт peer_removed_at, поэтому
Android не объявляет этот ответ доказательством физического удаления peer на узле.
Force-stop/убийство процесса не гарантирует код cleanup: Android закрывает TUN,
при следующем входе выполняется current/DELETE; серверная expiry/reconciliation
остаётся последней гарантией. Системный lockdown/kill switch не заявляется.

Backend POST не имеет идемпотентности. До POST сохраняется durable uncertain intent.
Timeout/cancel/невалидный ответ не порождают автоматический повтор POST. Проверяется
current; найденная сессия удаляется. Null current не доказывает отсутствие ещё
выполняющегося provisioning: intent остаётся, новое подключение блокируется.
Это сознательный предел существующего API, особенно для Premium без краткой expiry.
Повтор cleanup через кнопку, каждые 15 секунд в живом процессе и после restart.
При offline нет ложного обещания удаления peer; UI явно показывает pending cleanup.
Если сервер так и не опубликовал результат, требуется серверная reconciliation /
отзыв устройства владельцем; Android не обходит это новой сессией/ключом.

## Проверки и пределы приёмки

JVM: HTTP contract/header, first candidate, malformed transport, single-flight,
startup failure, no premature Connected, uncertain POST, cancellation, cleanup retry,
restart, owner isolation, revocation/health loss и storage-before-POST.
Native API26/35/36: реальный consent/отказ, production foreground VpnService,
WireGuard JNI/TUN, notification, unresponsive isolated peer (НЕ Connected),
затем ephemeral kernel WireGuard peer на том же CI runner (handshake + DNS/HTTPS
через NAT, CONNECTED), disconnect/revoke
и cleanup. Дополнительный seed/check в двух процессах: настоящий connected peer,
force-stop, затем cleanup сохранённого UUID без нового POST/ключа/start. Скриншот снимается screencap без обработки. Автотесты не отправляют OTP,
письма поддержки, платежи и не создают реальный backend peer.

Отдельная ручная приёмка с совместимым живым узлом должна подтвердить успешный
handshake/DNS/HTTPS, внешний IPv4 и отсутствие IPv6 обхода, Wi-Fi/mobile, фон/screen
lock, expiry, node peer removal и процесс restart на физическом arm64 устройстве.
Эти результаты не заменяются синтетическим успешным VpnApi или старой Windows сборкой.
Магазинная публикация/подпись release и transport-обфускация — вне этой задачи.

## Лицензии

Tunnel library/config/crypto Java — Apache-2.0 (WireGuard LLC); native wireguard-go —
MIT; Go/x packages — BSD-3-Clause. GPL-2.0 root tools из AAR исключены из APK. Сохранять upstream notices в распространяемом артефакте, см.
[WireGuard Android](https://github.com/WireGuard/wireguard-android),
[embedding](https://www.wireguard.com/embedding/). Не переносить Windows
WireGuardNT prebuilt license на Android. CI проверяет ABI и ELF page alignment
нативных библиотек в текущем APK; runtime x86_64 проверяется эмулятором,
arm64 — упаковкой, до отдельного handset-прогона.
