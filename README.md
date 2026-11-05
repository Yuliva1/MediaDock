# MediaDock – Universal Media Downloader

**MediaDock**, Windows 10 ve Windows 11 için **Linear** tasarım dilinden ilham alınarak geliştirilmiş; ultra hızlı, sade, kurgu (Adobe Premiere Pro) uyumlu masaüstü video, ses ve görsel indirme ile kişisel medya kütüphanesi uygulamasıdır.

Sahibi / Geliştirici: **Yuliva**

YouTube, Kick, X (Twitter), Instagram, TikTok, Twitch, Reddit, Facebook, Vimeo, Pinterest, ArtStation, Imgur ve `yt-dlp` motorunun desteklediği tüm platformlardan medya indirmenizi ve arşivlemenizi sağlar.

---

## Öne Çıkan Özellikler

- **Ultra Yüksek Performans & Akıcı UI:** PySide6 ile 60 FPS akıcı arayüz, anında başlatma, asenkron çok kanallı (multi-threaded) mimari.
- **Görsel (Image) İndirme Desteği:** Web üzerindeki görselleri veya doğrudan görsel URL'lerini anında algılar; Orijinal, PNG, JPG ve WEBP format seçenekleriyle diske kaydeder ve kütüphaneye ekler.
- **Adobe Premiere Pro Uyumluluğu:** MP4 seçildiğinde H.264 video ve AAC ses kodeklerine öncelik verilir. "Premiere Pro için optimize et" seçeneği ile YUV420p piksel formatı ve CFR çıktısı üretilir.
- **Otomatik Çerez & Oturum Algılama:** Edge, Chrome, Firefox, Brave, Opera ve Vivaldi tarayıcılarındaki açık oturumları arka planda otomatik kullanır.
- **Gelişmiş Dosya Gezgini Seçimi:** İndirme tamamlandığında veya klasör butonuna tıklandığında Windows Gezgini doğrudan ilgili dosyayı seçili olarak açar.
- **Sürüm Güncelleme & Changelog Dağıtım Sistemi:** Arkadaşlarınıza kurulum dosyasını gönderdiğinizde, yeni bir güncelleme yayınladığınızda uygulama açılışta veya Ayarlar sayfasında yeni sürümü otomatik tespit eder, değişiklik günlüğünü (changelog) gösterir ve tek tıkla indirip günceller.
- **Gizlilik & Temiz Meta Veri:** Setup ve çalıştırılabilir dosya özelliklerinde yalnızca `Yuliva` bilgisi yer alır.

---

## Arkadaşlara Güncelleme Nasıl Dağıtılır?

MediaDock, profesyonel açık kaynak projelerdeki gibi **GitHub Releases API** altyapısıyla çalışır:

1. **GitHub Deposu Oluşturun:** Projenizi GitHub'da (örneğin `Yuliva/MediaDock`) barındırın.
2. **Release (Sürüm) Yayınlayın:**
   - GitHub deposunda **Releases -> Draft a new release** butonuna tıklayın.
   - Tag olarak yeni sürüm numarasını girin (Örn: `v1.1.0`).
   - Sürüm başlığı ve **Changelog (Yenilikler)** metnini markdown olarak yazın (neler eklendi, hangi hatalar çözüldü).
   - Derlenen `MediaDock-Setup.exe` dosyasını release alanına sürükleyip yükleyin.
   - **Publish release** butonuna basın.
3. **Arkadaşlarınızın Ekranında Ne Olacak?**
   - Arkadaşlarınız MediaDock'u açtığında veya Ayarlar sayfasından "Güncellemeleri Denetle" butonuna bastığında uygulama arka planda GitHub API'sini sorgular.
   - Yeni sürüm varsa ekranda şık, Linear temalı **MediaDock Güncellemesi** penceresi açılır.
   - Sizin yazdığınız Changelog (yenilikler) doğrudan bu pencerede gösterilir.
   - **"Şimdi Güncelle ve Yeniden Başlat"** butonuna tıklandığında yeni setup dosyası arka planda indirilir ve tek tıkla kurulum tamamlanır.

---

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
Bu komut sırasıyla PyInstaller paketlemesini yapar, FFmpeg ikililerini içine kopyalar ve Inno Setup ile tek parça `installer/MediaDock-Setup.exe` dosyasını üretir.
