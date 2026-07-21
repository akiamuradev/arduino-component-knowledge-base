# Корпоративное развёртывание

Этот runbook относится к этапу 20 и описывает одну внутреннюю Ubuntu Server VM. Он не меняет
сетевые настройки автоматически: неверный Netplan или firewall может оборвать удалённый доступ.
Команды выполняет системный администратор через console-access или с проверенным rollback.

## 1. Ubuntu Server и static IP

Поддерживаемый baseline: Ubuntu Server 24.04 LTS, Docker Engine с Compose plugin, `curl`,
`openssl` и доступ к внутреннему DNS. VM получает постоянный адрес из серверного VLAN. Пример
Netplan необходимо адаптировать к реальным interface, subnet, gateway и DNS:

```yaml
network:
  version: 2
  ethernets:
    enp1s0:
      addresses: [192.0.2.10/24]
      routes:
        - to: default
          via: 192.0.2.1
      nameservers:
        addresses: [192.0.2.53]
        search: [college.internal]
```

Перед `netplan apply` используйте `sudo netplan try`: он автоматически откатывает конфигурацию,
если администратор не подтвердит доступ. Диапазон `192.0.2.0/24` выше является документационным,
а не готовым адресом.

Во внутреннем DNS создайте A-record, например `components.college.internal`, указывающий ровно
на static IP VM. Запись должна разрешаться с VM и с клиентских ПК. Не публикуйте PostgreSQL,
Redis или MinIO в DNS и не создавайте для них host port.

## 2. Внутренний CA и сертификаты

Нужны два сертификата внутреннего CA:

- edge certificate с SAN внутреннего browser hostname;
- MinIO certificate с SAN `minio` (Compose service name).

Private keys создаются и хранятся вне Git с mode `0600`. Для backend сформируйте CA bundle,
содержащий стандартные public roots Ubuntu и root/intermediate внутреннего CA. Это сохраняет
проверку внешних HTTPS-сайтов parser и одновременно позволяет проверять MinIO:

```bash
sudo install -d -m 0750 /etc/ackb/tls
sudo sh -c 'cat /etc/ssl/certs/ca-certificates.crt /path/to/college-root-ca.crt > /etc/ackb/tls/ca-bundle.crt'
sudo chmod 0644 /etc/ackb/tls/ca-bundle.crt
sudo chmod 0600 /etc/ackb/tls/*.key
```

Не используйте self-signed leaf certificate и не отключайте TLS verification. Root CA должен
быть установлен в trust store всех клиентских ПК до открытия сайта.

## 3. Production environment и preflight

```bash
cp .env.production.example .env.production
chmod 600 .env.production
# заполнить placeholders, не выводя значения в shell history или логи
./scripts/production_preflight.sh .env.production
```

`ACKB_BIND_ADDRESS` — static IP VM, `ACKB_INTERNAL_HOSTNAME` — соответствующая DNS-запись.
Все пути к сертификатам, ключам и CA bundle должны быть абсолютными. Preflight проверяет Ubuntu,
наличие IP на interface, DNS, SAN, срок действия не менее семи дней, цепочку доверия, mode ключей
и итоговый Compose config. Он ничего не записывает и не меняет firewall.

Запуск и обновление состояния:

```bash
docker compose --env-file .env.production \
  -f compose.yaml -f compose.production.yaml up --build -d
docker compose --env-file .env.production \
  -f compose.yaml -f compose.production.yaml ps
```

Production override публикует только `static-ip:80` и `static-ip:443`. HTTP возвращает `308`
на exact internal hostname. Browser traffic завершается на nginx с TLS 1.2/1.3 и HSTS;
quarantine/variants остаются private MinIO buckets, а MinIO traffic также использует TLS.

## 4. Host firewall

Сначала сохраните console-access. Подставьте реальные management и college client CIDR; не
копируйте документационные сети буквально:

```bash
sudo ufw default deny incoming
sudo ufw default allow outgoing
sudo ufw allow from <management-cidr> to any port 22 proto tcp
sudo ufw allow from <college-client-cidr> to any port 80 proto tcp
sudo ufw allow from <college-client-cidr> to any port 443 proto tcp
sudo ufw enable
sudo ufw status verbose
```

Docker published ports могут обходить обычные UFW chains. Поэтому обязательна отдельная
проверка с машины вне разрешённого college CIDR: 80/443 должны быть недоступны. На самой VM
`ss -lnt` не должен показывать host listeners 5432, 6379, 9000 или 9001. Правила `DOCKER-USER`
зависят от реальных interface/CIDR и применяются сетевым администратором; универсальный скрипт
намеренно не включён, чтобы не заблокировать VM ошибочным шаблоном.

## 5. Smoke и приёмка

```bash
export ACKB_SMOKE_BASE_URL='https://components.college.internal/'
export ACKB_SMOKE_CA_FILE='/etc/ackb/tls/ca-bundle.crt'
python scripts/production_smoke.py
```

Smoke не имеет insecure-режима: он проверяет hostname/CA, `/health`, `/ready`, frontend,
security headers и HTTP→HTTPS redirect. Затем с одного разрешённого клиентского ПК вручную
проверьте login, каталог и загрузку небольшой тестовой картинки. С внешнего VLAN подтвердите
firewall deny. Результаты, DNS TTL, certificate serial/expiry и operator записываются в акт
приёмки без private keys, cookies и credentials.

Не проверяются автоматически: корректность выбранного static IP/gateway, распространение root
CA на все управляемые ПК, правила физического firewall и доступность после отказа VM. Это
инфраструктурные решения колледжа и требуют администратора сети.

## 6. Media retention

Retention не запускается вместе с обычным application profile. Сначала выполните безопасный
dry-run и сохраните только итоговые счётчики без object keys:

```bash
docker compose --env-file .env.production \
  -f compose.yaml -f compose.production.yaml run --rm backend ackb-retain-media
```

После проверки backup/MinIO monitoring запустите maintenance profile с явным удалением:

```bash
docker compose --env-file .env.production \
  -f compose.yaml -f compose.production.yaml --profile maintenance \
  run --rm media-retention
```

Этот вызов эквивалентен `ackb-retain-media --apply`: он очищает original у expired/rejected
assets, детерминированные partial variants и не привязанные к PostgreSQL objects старше
`ACKB_MEDIA_RETENTION_GRACE_HOURS`. Ready originals и зарегистрированные variants сохраняются.
Запускайте dry-run ежедневно, а apply — по утверждённому расписанию после мониторинга и backup.
