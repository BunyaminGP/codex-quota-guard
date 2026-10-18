# codex-quota-guard

[![CI](https://github.com/BunyaminGP/codex-quota-guard/actions/workflows/ci.yml/badge.svg)](https://github.com/BunyaminGP/codex-quota-guard/actions/workflows/ci.yml)
[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)

Standart Codex CLI oturumları için kota kontrol noktaları ve abonelik limitlerinin sıfırlanmasını bekleyip oturumu kaydedilen kesin iş parçacığıyla (thread ID) sürdüren otomatik devam çalıştırıcısı. [cc-quota-guard](https://github.com/BunyaminGP/cc-quota-guard) projesinden uyarlanmıştır.

*[English README.md](README.md)*

Python 3.10+, kanca (hook) ve app-server destekli Codex CLI ile mevcut bir ChatGPT girişi gerektirir. CLI sözleşmeleri 0.162.1 sürümüne göre doğrulanmıştır. Harici Python çalışma zamanı bağımlılığı yoktur. Bu proje hiçbir API anahtarını veya kimlik dosyasını okumaz; oturum yönetimini doğrudan Codex'in kendisi yürütür.

## Kurulum

Bu depodan `python install.py` komutunu çalıştırın. Bu işlem, `$CODEX_HOME/hooks.json` (varsayılan `~/.codex/hooks.json`) dosyasına mevcut kancaları ezmeden veya `config.toml` dosyasını değiştirmeden gerekli kanca tanımlarını ekler. Kurulum deposunu silmeyin. Codex içinde `/hooks` menüsünü açın, eklenen iki kancayı inceleyin ve güvenilir (`trust`) olarak onaylayın. Kancalar onaylanana kadar çalıştırılmaz. Kurulum idempotenttir (tekrar çalıştırılabilir). Kaldırmak için `hooks.json` içindeki ilgili iki girdiyi silmeniz yeterlidir.

Kök dizindeki `plugin.json` ve `hooks/hooks.json` dosyaları aynı zamanda bir eklenti paketi oluşturur. Manuel kanca kaydını veya eklenti kurulumunu seçebilirsiniz, ikisini birden kurmayın.

Çalıştığınız projenin `.gitignore` dosyasına `.codex-quota/` satırını ekleyin.

```powershell
# Windows üzerinde projenizin dizininden:
& C:\proje\codex-quota\bin\codex-run.ps1 --lang tr "Görevi gerçekleştir"
& C:\proje\codex-quota\bin\codex-run.ps1 --resume
```

```sh
# macOS/Linux üzerinde projenizin dizininden:
sh /path/to/codex-quota/bin/codex-run --threshold 80 @task.md
sh /path/to/codex-quota/bin/codex-run --resume
```

`python /path/to/scripts/run.py` komutu her platformda doğrudan çalışır. Standart `codex` oturumları da onaylanan kancalar aracılığıyla kontrol noktası talimatı alır; ancak yalnızca otomatik çalıştırıcı sıfırlanmayı bekleyip oturumu kendiliğinden sürdürür.

## Çalışma Mantığı

Kota okuyucu, resmi olarak belgelenmiş `account/rateLimits/read` app-server RPC çağrısını yapar ve yanıtı 30 saniye boyunca önbelleğe alır. Döndürülen birincil ve ikincil tüm pencereleri korur. Özel HTTP uç noktaları veya kimlik dosyaları asla okunmaz. Abonelik kotası bulunmayan API anahtarlı hesaplarda kota-yok uyarısıyla güvenli şekilde devam edilir; belirteç (token) sayımlarından tahmini kota hesaplanmaz.

- **Varsayılan Yumuşak (Soft) Eşikler:** Oturum %80, haftalık %97.
- **Varsayılan Sert (Hard) Eşikler:** Oturum %95, haftalık %98.
- Haftalık pencere, döndürülen en az 10080 dakikalık limitleri ifade eder. Değerleri `--threshold`, `--session-hard`, `--weekly-soft`, `--weekly-hard` parametreleriyle değiştirebilirsiniz. `CODEX_QUOTA_SESSION_SOFT`, `CODEX_QUOTA_SESSION_HARD`, `CODEX_QUOTA_WEEKLY_SOFT`, `CODEX_QUOTA_WEEKLY_HARD` ortam değişkenleri `.codex-quota/config.json` dosyasına öncelik eder.

Yumuşak durdurma `update_plan` adımlarının sınırlarında veya aktif bir plan maddesi yoksa araç çağrısı sonrasında devreye girer. Sert durdurma herhangi bir aracın ardından kontrol noktası talep edebilir. Durdurma işareti yazıldığında kontrol noktası araçları açık kalır. Stop kancası, kota durdurmasından sonra ilerleme dosyası güncellenmemişse modele ek bir tur fırsatı sunar.

Çalıştırıcı, `thread.started.thread_id` değerini `.codex-quota/run.json` dosyasına yazar, uzun görevleri stdin üzerinden iletir ve oturumu yalnızca o kesin kimlikle sürdürür. Asla belirsiz `--last` parametresine sığınmaz. Çoklu pencere aşıldığında en geç sıfırlanacak olanı bekler, `--resume-buffer` saniye (varsayılan 60 sn) ekler ve başlamadan önce kotayı yeniden kontrol eder.

Yalnızca `progress.md` içindeki kesin `CODEX_QUOTA_DONE` satırı ve başarılı bir tur görevin tamamlandığı anlamına gelir. Hatalar `--max-retries` (varsayılan 5) kez, katsayılı bekleme süresiyle (`--retry-backoff`, varsayılan 30 sn) tekrar denenir. Zaman aşımı (`--round-timeout`, varsayılan 3600 sn) ve Ctrl+C tüm alt süreç ağacını güvenle sonlandırır.

## İsteğe Bağlı Sert Geri Alma (Hard Rollback)

`--enable-hard-abort` veya `CODEX_QUOTA_HARD_ABORT=1` seçeneği `git stash push -u` mekanizmasını etkinleştirir. Bu seçenek proje yapılandırmasından asla açılamaz. Stash işlemi yalnızca takip edilen plan maddesi başladığında çalışma ağacı temizse (`checkpoint_clean: true`) ve kontrol noktası commit'i halen HEAD ise denenir. Çalışma zamanı durum dizini stash dışında tutulur. Başarı için yeni bir stash referansı doğrulanmalıdır. Hiçbir değişiklik otomatik olarak geri yüklenmez; kaydedilen değişiklikleri incelemek için `git stash list` kullanabilirsiniz.

## Telefon Bildirimleri ve Dil

Telefonunuza bildirim almak için bir ntfy konusuna abone olun ve `CODEX_QUOTA_NOTIFY_URL=https://ntfy.sh/konu-adiniz` değişkenini tanımlayın. Yalnızca kısa durum, sıfırlanma, devam ve hata bildirimleri gönderilir; görev içeriği veya dosya yolları asla sızdırılmaz. Düz metin POST kullanılır.

Türkçe yaşam döngüsü mesajları için `--lang tr`, `CODEX_QUOTA_LANG=tr` veya proje konfigürasyonunda `{"language":"tr"}` kullanın.

## Doğrulama ve Test

```sh
python scripts/usage.py --no-cache
python -m pip install pytest
python -m pytest -q
```

Testler yerel sahte CLI süreçleri ve HTTP sunucuları kullanır; harici model çağrısı veya push bildirimi yapmaz.

## Lisans

Bu proje [MIT Lisansı](LICENSE) kapsamında lisanslanmıştır.
