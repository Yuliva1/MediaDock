# MediaDock

**Windows için hızlı, sade bir video, ses ve görsel indirici ve kişisel medya kütüphanesi.**
[yt-dlp](https://github.com/yt-dlp/yt-dlp) motorunu kullanır, Adobe Premiere Pro ile uyumlu çıktı üretebilir.

![Platform](https://img.shields.io/badge/platform-Windows%2010%20%7C%2011-0078D4)
![Python](https://img.shields.io/badge/python-3.12%2B-3776AB)
![UI](https://img.shields.io/badge/UI-PySide6-41CD52)
[![Sürüm](https://img.shields.io/github/v/release/Yuliva1/MediaDock?label=s%C3%BCr%C3%BCm)](https://github.com/Yuliva1/MediaDock/releases/latest)

---

## İçindekiler

- [Özellikler](#özellikler)
- [Kurulum](#kurulum)
- [Desteklenen siteler ve bilinen sınırlar](#desteklenen-siteler-ve-bilinen-sınırlar)
- [Kullanım](#kullanım)
- [Güvenlik ve gizlilik](#güvenlik-ve-gizlilik)
- [Güncelleme sistemi](#güncelleme-sistemi)
- [Sorun giderme](#sorun-giderme)
- [Geliştiriciler için](#geliştiriciler-için)
- [Yasal not](#yasal-not)
- [Lisans](#lisans)

---

## Özellikler

| | |
|---|---|
| **Çok platform** | YouTube, Kick, X (Twitter), Instagram (video ve Reels), TikTok, Twitch, Reddit, Facebook, Vimeo, Pinterest, ArtStation, Imgur ve yt-dlp'nin desteklediği diğer siteler |
| **Video, ses, görsel** | Kalite ve biçim seçimi; doğrudan görsel bağlantıları Orijinal, PNG, JPG veya WEBP olarak kaydedilir |
| **Premiere Pro uyumu** | MP4'te H.264 + AAC önceliği; "Premiere Pro için optimize et" seçeneği YUV420p ve sabit kare hızı (CFR) üretir |
| **Kişisel kütüphane** | İndirilenler geçmişte ve kütüphanede listelenir, aranır, favorilenir; mevcut klasör taranıp kütüphaneye eklenebilir |
| **Toplu indirme** | Birden çok bağlantıyı tek seferde ekleyebilirsiniz; kuyruk, duraklatma ve devam ettirme |
| **Kendini güncelleyen motor** | yt-dlp arka planda (günde en fazla bir kez) güncellenir; Ayarlar'dan elle de güncellenebilir |
| **Hafif uygulama güncellemesi** | Yeni sürümde yalnızca değişen dosyalar indirilir (genelde birkaç MB), doğrulanır ve uygulanır |
| **Hata raporu** | Ayarlar'dan tek tıkla sürüm, motor ve günlük bilgisini kopyalayabilirsiniz |
| **Gömülü FFmpeg** | Kurulumla birlikte gelir, ayrıca bir şey kurmanız gerekmez |

---

## Kurulum

1. [**Releases**](https://github.com/Yuliva1/MediaDock/releases/latest) sayfasından `MediaDock-Setup.exe` dosyasını indirin.
2. Çalıştırın. Kurulum yönetici izni istemez, kullanıcı klasörünüze kurulur.

### Windows "Bilinmeyen yayıncı" (SmartScreen) uyarısı

MediaDock şu an **kod imzalı değil**: imzalama sertifikaları ücretli ve bireysel geliştirici için pahalı. Bu yüzden Windows ilk çalıştırmada **"Windows bilgisayarınızı korudu"** uyarısı gösterebilir.

Çalıştırmak için **Daha fazla bilgi → Yine de çalıştır** deyin. İsterseniz önce dosyanın bozulmadığını doğrulayın:

```powershell
Get-FileHash .\MediaDock-Setup.exe -Algorithm SHA256
```

Çıkan değeri aynı sürümün release sayfasındaki `sha256sums.txt` dosyasıyla karşılaştırın; aynı olmalı. Kaynak kodun tamamı bu depoda, kendiniz de derleyebilirsiniz (bkz. [Geliştiriciler için](#geliştiriciler-için)).

---

## Desteklenen siteler ve bilinen sınırlar

MediaDock, yt-dlp'nin desteklediği her siteden **video ve ses** indirir. Bir sitenin çalışıp çalışmadığı ve ne kadar süre çalışacağı o sitenin değişikliklerine bağlıdır; motor güncellemeleri çoğu sorunu hızlıca çözer.

### Instagram

| İçerik | Durum |
|---|---|
| Video, Reels | İndirilebilir (herkese açık içerikte, giriş gerekmeden) |
| Görsel gönderisi, çoklu görsel (carousel) | **Desteklenmiyor.** yt-dlp bunları indirmiyor; bu onun bilinen bir sınırlaması ve motoru güncellemek çözmüyor |
| Doğrudan görsel bağlantısı (`...cdninstagram.com/...jpg`) | İndirilebilir; tarayıcıda görsele sağ tıklayıp **"Resim adresini kopyala"** ile alınan bağlantıyı yapıştırın |
| Özel hesaplar, hikayeler, giriş isteyen içerik | İndirilemez |

> Hesabınızın güvenliği için Instagram'da tarayıcı çerezleri **hiçbir koşulda** kullanılmaz.

---

## Kullanım

1. Bağlantıyı kopyalayın. MediaDock panodaki bağlantıyı algılayıp önerir; yapıştırabilir ya da sürükleyip bırakabilirsiniz.
2. Önizlemede kalite, biçim ve gerekirse "Premiere Pro için optimize et" seçeneğini ayarlayın.
3. **İndirmeyi Başlat**'a basın. İlerlemeyi **İndirmeler** sayfasından izleyin, bitince **Klasörde göster** ile dosyaya gidin.

Birden çok bağlantı için **Toplu Bağlantı Ekle**'yi kullanın. Çoklu görsel içeren sayfalarda hangi görsellerin indirileceğini seçebilirsiniz.

---

## Güvenlik ve gizlilik

- **Çerezler varsayılan olarak kapalı.** İsterseniz Ayarlar'dan açabilirsiniz; Instagram için her zaman kapalıdır. Çerezler günlüğe yazılmaz.
- **Günlükler** (`mediadock.log`) yalnızca bağlantının sorgusuz hâlini, yt-dlp sürümünü ve hata metnini içerir. Verileriniz dışarı gönderilmez; hata raporunu yalnızca siz kopyalayıp paylaşırsanız paylaşılır.
- **Güncellemeler doğrulanır:**
  - İndirme adresleri `https` olmalı ve GitHub sunucularından gelmeli.
  - Hem kurulum dosyası hem de delta paketi SHA-256 ile doğrulanır; uyuşmazsa dosya silinir.
  - Güvensiz dosya yolları (`../`) reddedilir; hata olursa değişiklikler geri alınır.
  - yt-dlp paketi yalnızca PyPI'ın resmî dosya sunucusundan indirilir ve özeti doğrulanır.
- **"Aç" butonu yalnızca medya dosyalarını** (video, ses, görsel) varsayılan uygulamayla açar; çalıştırılabilir dosyalar açılmaz.
- Verileriniz (geçmiş, ayarlar, küçük resimler) yalnızca bilgisayarınızda tutulur: kurulu sürümde `%LOCALAPPDATA%\MediaDock`, kaynak koddan çalıştırırsanız proje klasöründeki `data/` altında.

> **Sınırlama:** Güncelleme dosyalarının sağlama toplamları aynı GitHub release'inden geldiği için bütünlüğü korur ama yayıncının kimliğini kanıtlamaz. Bunun için kod imzalama gerekir (bkz. yukarıdaki SmartScreen notu).

---

## Güncelleme sistemi

Uygulama açılışta ve Ayarlar sayfasında yeni sürümü kontrol eder, değişiklik notlarıyla birlikte gösterir.

1. **Delta güncelleme (öncelikli):** Kurulu dosyaların SHA-256 değerleri yayındaki manifest ile karşılaştırılır; yalnızca farklı olanlar `mediadock-app.zip` içinden HTTP Range ile çekilir, doğrulanır, yerine konur ve uygulama yeniden başlar.
2. **Tam kurulum (yedek yol):** Delta mümkün değilse (klasör yazılamıyor, sunucu Range desteklemiyor, değişiklik çok büyük) tam `MediaDock-Setup.exe` indirilir, doğrulanır ve sessizce kurulur.
3. Hata olursa dosyalar geri alınır; eski `.old` dosyaları bir sonraki açılışta temizlenir.

> Delta güncelleme, bu mekanizmayı içeren sürümden **sonraki** sürümde çalışır. Daha eski kurulumlar bir kez tam kurulumla güncellenir.

---

## Sorun giderme

**"Instagram gönderisinde indirilebilir video yok" diyor.**
Gönderi görsel veya çoklu görseldir. yt-dlp Instagram görsellerini desteklemiyor; motoru güncellemek çözmez. Yukarıdaki [Instagram](#instagram) tablosuna bakın.

**"İndirme motoru bu bağlantıyı çözemedi."**
Site yapısı değişmiş olabilir. **Ayarlar → İndirme Motorları** bölümünden yt-dlp'yi güncelleyip uygulamayı yeniden başlatın. Sürüm zaten günceldir ve sorun sürüyorsa bir süre sonra tekrar deneyin.

**Windows SmartScreen uyarısı veriyor.**
[Bilinmeyen yayıncı](#windows-bilinmeyen-yayıncı-smartscreen-uyarısı) bölümüne bakın.

**Hata bildirmek istiyorum.**
**Ayarlar → Hata Raporunu Kopyala**'ya basıp çıkan metni bir [Issue](https://github.com/Yuliva1/MediaDock/issues)'ya ekleyin. Rapora bağlantılar da girebilir; paylaşmadan önce gözden geçirin.

**Günlükler nerede?**
Kurulu sürümde `%LOCALAPPDATA%\MediaDock\data\logs\` içinde: `mediadock.log` (olaylar ve indirme hataları) ve `crash.log` (yerel çökmeler). Ayarlar'daki **Günlüğü Aç** düğmesi klasörü açar.

---

## Geliştiriciler için

### Kaynak koddan çalıştırma

```powershell
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
python main.py
```

Python 3.12 veya üstü gerekir. Kendi başına derlediğiniz sürümde FFmpeg'i sistem yolundan veya Ayarlar'dan gösterebilirsiniz.

### Test ve kod denetimi

```powershell
pip install -r requirements-dev.txt
python -m pyflakes build_exe.py main.py config core ui tools tests
python -m pytest -q
```

Testler `QT_QPA_PLATFORM=offscreen` ile çalışır; Windows dışında da geçer. Kapsam: saf yardımcılar, sürüm tutarlılığı, delta güncelleme (yerel Range sunucusuna karşı uçtan uca), güvenlik denetimleri.

### Derleme

```powershell
python build_exe.py --clean
```

Bu komut sırasıyla `version_info.txt` üretir, PyInstaller paketlemesini yapar, FFmpeg'i `bin/` altına tek kopya olarak ekler, Inno Setup ile `installer/MediaDock-Setup.exe` dosyasını ve `tools/make_release_assets.py` ile `release/` altındaki delta paketini üretir. Inno Setup 6 ve (gömülecekse) FFmpeg kurulu olmalıdır.

### Sürüm yayınlama

1. `config/constants.py` içindeki **`APP_VERSION`** değerini yükseltin. `version_info.txt` ve kurulum sürümü build sırasında buradan üretilir (tek kaynak).
2. Değişiklikleri `CHANGELOG.md`'ye yazın.
3. Etiketleyin ve gönderin:
   ```powershell
   git tag v1.1.3
   git push origin v1.1.3
   ```
4. GitHub Actions testleri çalıştırır, etiketin `APP_VERSION` ile eşleştiğini denetler, derler ve release'e şunları yükler: `MediaDock-Setup.exe`, `mediadock-app.zip`, `manifest.json`, `sha256sums.txt`.

> **Önemli:** Delta güncelleme dosya özetlerine dayanır. İleride kod imzalama eklenirse imza, `tools/make_release_assets.py` çalışmadan **önce** atılmalıdır; aksi hâlde özetler tutmaz.

### Proje yapısı

```
main.py                  Uygulama girişi, çökme yakalama
config/                  Sabitler (sürüm, depo adı), ayarlar, yollar, tema
core/
  downloader.py          İndirme kuyruğu ve yt-dlp / FFmpeg işleri
  metadata.py            Bağlantı çözümleme, hata çevirisi, görsel/galeri
  extractor.py           yt-dlp çağrısı ve çerez politikası
  ffmpeg.py              FFmpeg/FFprobe yönetimi
  updater.py             Uygulama güncelleme akışı (GitHub release)
  delta_update.py        Yalnızca değişen dosyaları indirip uygulama
  ytdlp_updater.py       yt-dlp motoru güncelleme
  scanner.py             Yerel klasör tarama
  database.py            SQLite (geçmiş, kütüphane, ayarlar)
  logutil.py             Günlük ve hata raporu
ui/                      PySide6 arayüzü (sayfalar ve bileşenler)
tools/                   Release dosyalarını üreten betik
tests/                   pytest testleri
build_exe.py             Derleme betiği
MediaDock.spec           PyInstaller yapılandırması
installer.iss            Inno Setup betiği
.github/workflows/       Test ve release otomasyonu
```

---

## Yasal not

MediaDock bir indirme aracıdır; içeriğin sahibi değildir. Yalnızca erişim hakkınız olan içerikleri **kendi kişisel kullanımınız** için indirin, platformların kullanım şartlarına ve telif haklarına uyun. İçeriği izinsiz yeniden yayınlamak veya dağıtmak hukuki sorumluluk doğurabilir. Kullanımın sorumluluğu kullanıcıya aittir.

---

## Lisans

Bu depo için henüz bir lisans seçilmedi. Lisans dosyası eklenene kadar tüm haklar saklıdır.

Sahibi / Geliştirici: **Yuliva**
