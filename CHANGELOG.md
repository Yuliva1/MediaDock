# Değişiklik günlüğü

Sürüm numarası tek kaynaktan gelir: `config/constants.py` → `APP_VERSION`.

## 1.1.4 — 2026-11-06

- **Canlı Güncelleme Testi:** v1.1.3 üzerinden otomatik güncelleme akışını doğrulamak için yayınlanan test sürümü.

## 1.1.3 — 2026-11-06

- **"Güncellemeleri Denetle" düğmesi sessiz kalıyordu.** Denetim sonucu, arka plan iş parçacığında çalışan bir kapanış fonksiyonuna bağlanmıştı; güncelleme penceresi ana iş parçacığında açılmıyordu. Sonuç artık pencere sınıflarının yöntemlerine bağlanıyor (`ui/settings_page.py`, `ui/main_window.py`). Windows'ta elle denenmedi.

## 1.1.2 — 2026-11-06

Güvenlik ve dayanıklılık sürümü.

### Güvenlik
- **PowerShell komut enjeksiyonu düzeltildi.** "Klasörde göster", dosya yolunu doğrudan PowerShell betiğine gömüyordu; dosya adı video başlığından geldiği için `'`, `;`, `$` içeren bir başlık komut çalıştırabilirdi (ayrıca `Don't Stop.mp4` gibi normal adlar bu özelliği bozuyordu). Yol artık ortam değişkeniyle iletiliyor. Masaüstü kısayolu oluşturma da aynı şekilde düzeltildi.
- **"Aç" yalnızca medya dosyalarını açıyor.** `.exe`, `.bat`, `.lnk` gibi uzantılar varsayılan uygulamayla çalıştırılmıyor, klasörde gösteriliyor.
- **Güncelleme adresleri doğrulanıyor:** indirme adresleri `https` olmalı ve GitHub alan adlarından (veya güncelleme kaynağıyla aynı sunucudan) gelmeli; depo adı `sahip/depo` biçiminde doğrulanıyor.
- **yt-dlp paketi:** yalnızca `files.pythonhosted.org` adresinden, SHA-256 özeti zorunlu; açılmış boyut sınırı (200 MB) eklendi.

### Dayanıklılık
- Kütüphane taraması sırasında bir dosya silinirse tüm tarama çökmüyor, o dosya atlanıyor.
- Yarım kalan küçük resim indirmeleri (`tmp_*.dat`) açılışta temizleniyor.

### Değişiklikler
- Instagram görsel gönderileri için hata mesajı netleştirildi: yt-dlp Instagram görsellerini desteklemiyor, motoru güncellemek çözmez.
- Yeni testler (`tests/test_security.py`); toplam 37 test.
- `.gitignore`: `data/` ve `assets/thumbnails/` (kullanıcı verisi) depo dışında tutuluyor.
- README baştan yazıldı; `docs/DEVIR_NOTU.md` eklendi.

## 1.1.1 — 2026-11-06

- **Instagram "No video formats found" hatası yanlış yorumlanıyordu.** yt-dlp bu ifadeyi motor güncel olsa da içerikte video yoksa (görsel gönderi) üretir. Artık motor bozuk sayılmıyor ve gereksiz arka plan yt-dlp güncellemesi tetiklenmiyor.
- yt-dlp sürümü son 10 gün içindeyse "motor güncel değil" uyarısı verilmiyor.
- Ana sayfadaki hata kartına **"Ayrıntıları Kopyala"** düğmesi (sürüm, motor ve son günlük satırları).

## 1.1.0 ve öncesi

Önceki oturumlarda hazırlanan ve 1.1.0'da yer alan değişiklikler (ayrıntı `docs/DEVIR_NOTU.md` içinde):

- **Delta güncelleme** (`core/delta_update.py`): yalnızca değişen dosyalar HTTP Range ile indirilir, SHA-256 ile doğrulanır, hata olursa geri alınır. Delta mümkün değilse tam kurulum (`/SILENT`) yedek yoludur.
- **Doğrulama:** kurulum dosyası ve manifest `sha256sums.txt` ile doğrulanır; uyuşmazlıkta dosya silinir.
- **Tek sürüm kaynağı** (`config/constants.py`); `version_info.txt` ve kurulum sürümü build sırasında üretilir.
- **Release otomasyonu:** `tools/make_release_assets.py` ve `.github/workflows/release.yml` (test → derleme → release).
- **Hata izi:** `sys.excepthook`, thread hook'u, `faulthandler` (`crash.log`); Ayarlar'da "Günlüğü Aç" ve "Hata Raporunu Kopyala".
- **FFmpeg:** sistemdeki ffmpeg'in gömülü olandan önce seçilmesi hatası düzeltildi; pakette tek kopya.
- **Paket boyutu:** PyInstaller'da kullanılmayan Qt modülleri ve dosyaları ayıklandı.
- **Güncelleme deposu adı** tek sabitten (`DEFAULT_UPDATE_REPO`) okunuyor.
- Testler ve CI eklendi.
