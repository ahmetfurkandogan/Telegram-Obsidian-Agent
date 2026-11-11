# Telegram’dan Obsidian’a Bilgi İşleme Ajanı Tasarımı

## Niyet

Tek kullanıcılı, yerel çalışan bir Telegram botu kurulacak. Kullanıcı bota metin veya URL gönderir. Bot içeriği analiz eder, Markdown önizlemesi gösterir ve onaydan sonra notu kullanıcının Obsidian vault’una kaydeder.

Amaç, Telegram’ı hızlı bilgi yakalama kutusuna çevirmektir. İlk sürüm not alma ve link özetleme işini güvenilir biçimde çözer.

## Mevcut durum

- Bu iş için mevcut proje kodu yok.
- Yeni proje kökü: `/Users/a.furkan/Documents/Telegram Obsidian Agent`
- Obsidian vault: `/Users/a.furkan/Documents/Obsidian Vault`
- Obsidian Local REST API mevcut.
- REST API yerel HTTP portu `27123`, TLS portu `27124`.
- API anahtarı yalnızca ortam değişkeninden okunacak.

## Hedefler

- Yalnızca izinli Telegram `chat_id` değerinden gelen mesajları işlemek.
- Metin ve HTTP(S) URL kabul etmek.
- URL içeriğini güvenli sınırlar içinde çekmek.
- Başlık, özet, etiket ve kaynak bilgisini LLM ile çıkarmak.
- Markdown önizlemesi üretmek.
- `Kaydet` ve `İptal` düğmeleriyle kullanıcı onayı almak.
- Onay sonrası Obsidian REST API’ye yeni Markdown dosyası yazmak.
- İşlemleri SQLite ile idempotent ve izlenebilir yapmak.
- Hataları kullanıcıya anlaşılır bildirmek.

## Hedef dışı

- Çok kullanıcılı hesap, rol veya davet sistemi.
- Telegram webhook ve bulut deployment.
- Ses mesajı transkripsiyonu.
- PDF, görsel ve dosya OCR.
- Otomatik cevap gönderme veya dış sistemlerde işlem yapma.
- Obsidian dosyalarını silme veya mevcut notları otomatik değiştirme.
- Tam metin arama ve ikinci beyin sorgulama.

## Başarısızlık ölçütleri

- Kullanıcı onayı olmadan not kaydedilmesi.
- Yetkisiz Telegram kullanıcısının veri görebilmesi.
- URL üzerinden localhost veya private network’e erişim.
- Aynı callback’in iki not oluşturması.
- Mevcut Obsidian notunun sessizce ezilmesi.
- API anahtarı veya bot token’ın loglanması.
- LLM hatasında bozuk Markdown kaydedilmesi.

## Yaklaşımlar

### Seçilen: yerel Python polling botu

Python botu Telegram polling ile çalışır. SQLite yerel durum ve bekleyen onayları tutar. URL içeriği `httpx` ile alınır. LLM, OpenAI-compatible HTTP arayüzüyle çağrılır; `base_url` sayesinde OpenAI veya yerel model kullanılabilir. Obsidian’a yerel REST API üzerinden `PUT /vault/<path>` gönderilir.

Bu yol tek kullanıcı, yerel vault ve hızlı MVP için en düşük toplam karmaşıklığa sahiptir.

### Elenen: bulut webhook

7/24 çalışma sağlar. Ancak HTTPS, deployment, dış ağda secret yönetimi ve vault erişimi gerektirir. İlk sürümün yerel kullanım amacını gereksiz büyütür.

### Elenen: yalnızca kurallı sınıflandırma

Gizlilik ve maliyet avantajı sağlar. Link özeti ve anlam çıkarma kalitesi düşük kalır. İleride LLM sağlayıcısı yerine yerel model seçilebildiği için bu sınırlama gerekli değildir.

## Kullanıcı akışı

```text
Telegram mesajı veya URL
    ↓
chat_id doğrulama
    ↓
URL ise güvenli içerik çekme
    ↓
LLM analizi ve alan doğrulama
    ↓
Markdown önizleme + Kaydet/İptal
    ↓
SQLite pending kaydı
    ↓
Kullanıcı Kaydet der
    ↓
Obsidian PUT + create-only koşulu
    ↓
Başarı mesajı ve note path
```

## Not biçimi

Her yeni not `Telegram Inbox/` altında benzersiz bir dosya adına sahip olacak.

```markdown
---
title: "Örnek başlık"
source: "https://example.com/article"
captured_at: "2026-11-11T12:00:00+03:00"
tags:
  - telegram-inbox
  - konu
---

## Özet

Kısa ve doğrulanabilir özet.

## İçerik

Kullanıcının gönderdiği metin veya URL içeriği.
```

LLM çıktısı yalnızca yapılandırılmış alanlardan alınacak. Frontmatter değerleri renderer tarafından güvenli biçimde escape edilecek. LLM’nin Markdown içine komut veya gizli talimat yerleştirmesi güvenilir talimat olarak kabul edilmeyecek.

## Modüller

- `config.py`: Ortam değişkenleri ve sınırların doğrulanması.
- `models.py`: İçerik, analiz ve pending kayıt veri tipleri.
- `security.py`: Telegram kimlik ve URL güvenlik kontrolleri.
- `fetcher.py`: HTTP içerik alma, redirect ve boyut sınırları.
- `llm.py`: LLM istemcisi ve yapılandırılmış analiz doğrulaması.
- `markdown.py`: Güvenli Obsidian Markdown üretimi.
- `storage.py`: SQLite şeması, pending durumları ve idempotency.
- `obsidian.py`: Obsidian Local REST API istemcisi.
- `bot.py`: Telegram komutları, mesajlar ve callback düğmeleri.
- `main.py`: Bağımlılıkları bağlama ve polling başlatma.

## Güvenlik ve invariant’lar

1. `ALLOWED_CHAT_ID` eşleşmeden hiçbir mesaj işlenmez.
2. Bot token, LLM anahtarı ve Obsidian anahtarı yalnızca environment’tan okunur.
3. URL yalnızca `http` veya `https` olabilir.
4. URL hostname’i loopback, private, link-local, multicast, reserved veya unspecified IP’ye çözülemez.
5. Redirect her adımda tekrar doğrulanır ve en fazla üç redirect izlenir.
6. Yanıt boyutu `MAX_SOURCE_BYTES` değerini aşarsa içerik reddedilir.
7. Sadece HTML ve düz metin içerik türleri kabul edilir.
8. Pending kayıt süresi 15 dakikadır.
9. Aynı pending kaydı birden fazla kez kaydedilemez.
10. Obsidian yazımı yeni dosyada `If-None-Match: *` kullanır.
11. Mevcut dosya üzerine yazma yoktur.
12. Callback verisi yalnızca opak pending token içerir.
13. Loglarda içerik, token ve API anahtarı bulunmaz.
14. LLM veya Obsidian hatasında kayıt başarısız kalır; kullanıcıya tekrar deneme yolu gösterilir.

## Konfigürasyon

`.env` dosyası örneği verilecek, gerçek secret commit edilmeyecek.

- `TELEGRAM_BOT_TOKEN`: Telegram BotFather token’ı.
- `TELEGRAM_ALLOWED_CHAT_ID`: Kullanıcının sayısal chat ID’si.
- `LLM_API_KEY`: OpenAI-compatible sağlayıcı anahtarı.
- `LLM_BASE_URL`: Sağlayıcının base URL’i.
- `LLM_MODEL`: Kullanılacak model adı.
- `OBSIDIAN_BASE_URL`: Varsayılan `http://127.0.0.1:27123`.
- `OBSIDIAN_API_KEY`: Obsidian Local REST API anahtarı.
- `OBSIDIAN_FOLDER`: Varsayılan `Telegram Inbox`.
- `DATABASE_PATH`: Varsayılan `data/agent.sqlite3`.

LLM sağlayıcısına gönderilen içerik, kullanıcı tarafından seçilen sağlayıcının veri politikasına tabidir. Yerel model kullanımı `LLM_BASE_URL` ile desteklenir.

## Doğrulama

- Birim testleri: config, URL güvenliği, renderer, SQLite durum geçişleri.
- HTTP contract testleri: fake LLM ve fake Obsidian REST API.
- Bot handler testleri: yetkisiz kullanıcı, önizleme, kaydet, iptal, tekrar callback.
- Tam test: `pytest -q`.
- Canlı smoke test: gerçek Telegram, LLM ve Obsidian ile tek örnek not.

