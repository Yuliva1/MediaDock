# MediaDock – Universal Media Downloader

**MediaDock**, Windows 10 ve Windows 11 için **Linear** tasarım dilinden ilham alınarak geliştirilmiş; ultra hızlı, sade, kurgu (Adobe Premiere Pro) uyumlu masaüstü video, ses ve görsel indirme ile kişisel medya kütüphanesi uygulamasıdır.

Sahibi / Geliştirici: **Yuliva**

YouTube, Kick, X (Twitter), Instagram, TikTok, Twitch, Reddit, Facebook, Vimeo, Pinterest, ArtStation, Imgur ve `yt-dlp` motorunun desteklediği tüm platformlardan medya indirmenizi ve arşivlemenizi sağlar.

---

## Öne Çıkan Özellikler

- **Ultra Yüksek Performans & Akıcı UI:** PySide6 ile 60 FPS akıcı arayüz, anında başlatma, asenkron çok kanallı (multi-threaded) mimari.
- **Görsel (Image) İndirme Desteği:** Web üzerindeki görselleri veya doğrudan görsel URL'lerini anında algılar; Orijinal, PNG, JPG ve WEBP format seçenekleriyle diske kaydeder ve kütüphaneye ekler.
- **Adobe Premiere Pro Uyumluluğu:** MP4 seçildiğinde H.264 video ve AAC ses kodeklerine öncelik verilir. "Premiere Pro için optimize et" seçeneği ile YUV420p piksel formatı ve CFR çıktısı üretilir.
- **Çerezsiz & Güvenli Oturum Politikası:** Tarayıcı çerezleri varsayılan olarak KAPALIDIR. İsteğe bağlı olarak Ayarlar'dan açılabilir; Instagram için hesap güvenliği nedeniyle çerez kullanımı her zaman devre dışıdır.
- **Kendini Güncelleyen İndirme Motoru:** yt-dlp, MediaDock yeniden derlenmeden arka planda (günde en fazla bir kez) güncellenir. Ayarlar > İndirme Motorları bölümünden elle de güncellenebilir. Yeni sürüm uygulama yeniden başlatılınca etkinleşir.
- **Hata Günlüğü:** İndirme hataları `data/logs/mediadock.log` dosyasına (çerez ve kişisel veri olmadan) yazılır.
- **Gelişmiş Dosya Gezgini Seçimi:** İndirme tamamlandığında veya klasör butonuna tıklandığında Windows Gezgini doğrudan ilgili dosyayı seçili olarak açar.
- **Sürüm Güncelleme & Changelog Dağıtım Sistemi:** Arkadaşlarınıza kurulum dosyasını gönderdiğinizde, yeni bir güncelleme yayınladığınızda uygulama açılışta veya Ayarlar sayfasında yeni sürümü otomatik tespit eder, değişiklik günlüğünü (changelog) gösterir ve tek tıkla indirip günceller.
- **Gizlilik & Temiz Meta Veri:** Setup ve çalıştırılabilir dosya özelliklerinde yalnızca `Yuliva` bilgisi yer alır.

---

## Güncelleme Nasıl Dağıtılır?

1. **Sürümü yükseltin:** yalnızca `config/constants.py` içindeki `APP_VERSION` değerini değiştirin.
   `version_info.txt` ve kurulum sürümü build sırasında buradan üretilir.
2. **Etiket atın:** `git tag v1.0.6 && git push origin v1.0.6`
   GitHub Actions testleri çalıştırır, uygulamayı derler ve release'e şunları yükler:
   `MediaDock-Setup.exe`, `mediadock-app.zip`, `manifest.json`, `sha256sums.txt`.
   (Elle derleyecekseniz: `python build_exe.py` → çıktılar `release/` klasöründe.)
3. **Kullanıcıda ne olur?**
   - Uygulama yeni sürümü bulunca değişiklik notlarıyla birlikte güncelleme penceresi açılır.
   - **Delta güncelleme:** yalnızca değişen dosyalar `mediadock-app.zip` içinden HTTP Range ile indirilir
     (tipik olarak birkaç MB), SHA-256 ile doğrulanır, yerine konur ve uygulama kendini yeniden başlatır.
   - **Yedek yol:** delta mümkün değilse (klasör yazılamıyor, manifest yok, değişiklik çok büyük)
     tam `MediaDock-Setup.exe` indirilir, hash'i `sha256sums.txt` ile doğrulanır ve
     sihirbazsız (`/SILENT`) kurulur.
   - Hata olursa dosyalar geri alınır; eski `.old` dosyaları bir sonraki açılışta temizlenir.

> İlk delta güncelleme, bu mekanizmayı içeren sürümden **sonraki** sürümde çalışır; eski sürümler tam kurulumla güncellenir.

## Hata Ayıklama

- Ayarlar → **Günlüğü Aç** / **Hata Raporunu Kopyala** (sürüm, yt-dlp, sistem ve son günlük satırları).
- Yakalanmayan hatalar `%LOCALAPPDATA%\MediaDock\data\logs\mediadock.log`, yerel çökmeler `crash.log` dosyasına yazılır.
- Testler: `pip install -r requirements-dev.txt && python -m pytest`

## Kurulum ve Çalıştırma

### Kurulum Dosyası (Setup):
- `installer/MediaDock-Setup.exe` dosyasını çalıştırarak Windows ortamına kurabilirsiniz.
- Kurulum, FFmpeg ve FFprobe bağımlılıklarını içinde gömülü barındırır. Ekstra hiçbir ayar yapılmasına gerek yoktur.

### Kaynak Koddan Çalıştırma:
```bash
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
python main.py
```

### Yeniden Derleme (Build):
```bash
python build_exe.py
```
Bu komut sırasıyla sürüm bilgisini üretir, PyInstaller paketlemesini yapar, FFmpeg'i `bin/` altına **tek kopya** olarak ekler, Inno Setup ile `installer/MediaDock-Setup.exe` dosyasını ve `tools/make_release_assets.py` ile delta paketini (`release/`) oluşturur.
