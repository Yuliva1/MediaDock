# MediaDock — teknik devir notu (1.1.2)

Bu not, projeyi devralan kişi veya AI içindir. Önce **"GitHub'a gönderirken"** bölümünü okuyun.

## 1. Proje

PySide6 masaüstü uygulaması; yt-dlp tabanlı medya indirici (video, ses, görsel) ve kişisel kütüphane. Windows 10/11 hedefli. PyInstaller **onedir** paketi + Inno Setup kurulumu (`PrivilegesRequired=lowest`, kullanıcı klasörüne kurulur). Güncelleme dağıtımı GitHub Releases üzerinden. Geliştirici: Yuliva.

Sürüm tek kaynaktan gelir: `config/constants.py` → `APP_VERSION` (şu an **1.1.2**). `version_info.txt` ve kurulum sürümü build sırasında buradan üretilir.

## 2. GitHub'a gönderirken (kontrol listesi)

1. **Depo adını doğrulayın.** Kod ve kurulum betiği `Yuliva1/MediaDock` adresini varsayar (`config/constants.py` → `DEFAULT_UPDATE_REPO`, `installer.iss` içindeki 3 URL, README rozet/bağlantıları). Gerçek depo adı farklıysa hepsini birlikte güncelleyin; aksi hâlde uygulama yanlış depodan güncelleme arar. `tests/test_versions.py` eski depo adlarının kodda kalmadığını denetler.
2. **Kullanıcı verisi depoya girmesin.** `.gitignore` `data/` (veritabanı, günlükler), `assets/thumbnails/`, `dist/`, `build/`, `installer/`, `release/`, `*.exe` dosyalarını dışlar. `git add .` öncesi `git status` ile kontrol edin. Kaynak koddan çalıştırınca uygulama bu klasörleri proje dizininde oluşturur.
3. **Önce testleri çalıştırın:** `python -m pytest -q` ve `python -m pyflakes build_exe.py main.py config core ui tools tests` (37 test geçmeli, pyflakes sessiz olmalı).
4. **`main` dalına gönderince** yalnızca `test` işi (windows-latest) çalışır. **`v*` etiketi** atılınca release işi derler ve yayınlar. İlk etiketi atmadan önce `main` üzerindeki test işinin yeşil olduğunu görün.
5. **İlk release çalıştırması büyük olasılıkla ayar isteyecektir.** Workflow YAML sözdizimi doğrulandı ama **hiç çalıştırılmadı** (bkz. bölüm 6). Hata çıkarsa düzeltip yeni etiketle (örn. `v1.1.3`) yeniden deneyin; var olan etiketi zorla (`--force`) taşımayın.
6. Etiket, `APP_VERSION` ile aynı olmalı (`v1.1.2` ↔ `1.1.2`); workflow bunu denetler.
7. Lisans dosyası yok; README'de "lisans seçilmedi" yazıyor. Sahibi karar verince eklenmeli.

## 3. Mimari (özet)

| Dosya | Görev |
|---|---|
| `main.py` | Giriş; `sys.excepthook`, thread hook'u, `faulthandler` (`crash.log`); frozen ise `cleanup_old_files` |
| `core/downloader.py` | İndirme kuyruğu, yt-dlp ve FFmpeg işleri, dosyayı açma/Gezgin'de gösterme |
| `core/metadata.py` | Bağlantı çözümleme (`fetch_video_metadata`), **hata çevirisi** (`translate_ytdlp_error`), görsel ve galeri kazıma |
| `core/extractor.py` | yt-dlp çağrısı; çerez politikası (Instagram için çerez **her zaman** atılır) |
| `core/updater.py` | GitHub release kontrolü, indirme worker'ı, kurulumu başlatma |
| `core/delta_update.py` | Delta güncelleme (Qt'ye bağımlı değil) |
| `core/ytdlp_updater.py` | yt-dlp'yi PyPI'dan güncelleme (wheel, `data/ytdlp_pkg` altında override) |
| `core/ffmpeg.py` | FFmpeg/FFprobe bulma ve çalıştırma |
| `core/scanner.py` | Yerel klasör tarama (ffprobe ile) |
| `core/database.py` | SQLite (WAL); geçmiş, kütüphane, ayarlar |
| `tools/make_release_assets.py` | `release/` altında zip, manifest, `sha256sums.txt` üretir |

### Delta güncelleme tasarımı

- `manifest.json`: `{"version", "zip", "zip_size", "files": [{"path", "size", "sha256", "doff", "csize", "method"}]}`. `doff` zip içindeki ham veri başlangıç ofseti, `csize` sıkıştırılmış boyut, `method` 0 (saklı) veya 8 (deflate).
- `plan_changes`: boyut/hash farkını bulur. `delta_is_worthwhile`: indirilecek `csize` toplamı tüm paketin %60'ını aşarsa delta kullanılmaz.
- `download_changed`: yalnızca gerekli baytları HTTP Range ile çeker (yanıt 206 değilse `DeltaError`), ham deflate'i `zlib.decompress(raw, -15)` ile açar, boyut ve SHA-256 doğrular, `staging/` altına yazar. İptal: `DeltaCancelled`.
- `apply_staged`: her dosya için `.new` kopyalanır, mevcut hedef `.old` adına `os.replace` ile alınır (Windows'ta çalışan exe/DLL **silinemez ama yeniden adlandırılabilir**), sonra `.new` yerine konur. Hata olursa hepsi geri alınır. Başarıda `.mediadock-manifest.json` yazılır.
- `safe_rel_path`: `..`, mutlak yol, `\`, `:` içeren manifest yollarını reddeder. `check_writable`: yazma izni yoksa `DeltaError` → tam kuruluma düşülür.
- `core/updater.py` → `UpdateDownloadWorker`: önce delta, olmazsa tam kurulum. `finished(str)` sinyali: **klasör yolu = delta hazır**, **dosya yolu = tam kurulum**. `finalize_update` buna göre `apply_delta_and_restart` veya `launch_installer_and_exit` çağırır. Kurulum argümanları: `/SILENT /SUPPRESSMSGBOXES /NORESTART /CLOSEAPPLICATIONS` (`/RESTARTAPPLICATIONS` bilerek yok; `[Run]` girdisiyle çift açılma olurdu).

## 4. Bu oturumda yapılanlar (1.1.0 → 1.1.2)

Ayrıntı: `CHANGELOG.md`. Özet:

**1.1.1 — Instagram hata teşhisi**
- Kullanıcının logunda yt-dlp güncel olmasına rağmen `No video formats found!` çıkıyordu. Hata kimliği (`DdhtmSuMYnj`) gönderi kısa kodundan (`Ddht6F2DFbD`) farklıydı → çoklu görsel (carousel) içindeki bir görsel öğesi. yt-dlp'nin GitHub kayıtlarına göre (araştırma çıktısı; kullanıcının verdiği, tarafımızca doğrudan açılıp doğrulanmadı) Instagram görsel gönderilerini indirmemek bilinen ve "planlanmayan" bir sınır.
- Hata çevirisi düzeltildi: bu ifade artık "motor güncel değil" demiyor ve arka planda gereksiz yt-dlp güncellemesi tetiklemiyor. Motor sürümü yakın tarihliyse (`_ytdlp_is_fresh`, 10 gün) genel uyarı farklı yazılıyor.
- Ana sayfadaki hata kartına "Ayrıntıları Kopyala" eklendi.

**1.1.2 — güvenlik ve dayanıklılık taraması**
- **PowerShell komut enjeksiyonu** (`core/downloader.py::_select_item_in_explorer`): yol betiğe gömülüydü; dosya adı video başlığından geldiği için `'; komut; '` içeren bir başlık çalıştırılabilirdi. Düzeltme: yol `MEDIADOCK_TARGET` ortam değişkeniyle iletiliyor. Aynısı masaüstü kısayolu için `ui/settings_page.py` içinde (`MD_*` değişkenleri).
- `open_file_in_default_player`: yalnızca `SUPPORTED_MEDIA_EXTENSIONS` uzantılı dosyaları açar; diğerlerini Gezgin'de gösterir.
- Güncelleyici: indirme adresleri `https` + GitHub alan adı (veya kaynakla aynı sunucu) olmalı; depo adı regex ile doğrulanır. yt-dlp wheel: yalnızca `files.pythonhosted.org`, SHA-256 zorunlu, açılmış boyut sınırı.
- `core/scanner.py`: silinen dosya taramayı çökertmesin; `main.py`: `tmp_*.dat` temizliği.
- Testler: `tests/test_security.py` (+ `test_pure.py` içinde Instagram hata testleri). Toplam 37.

## 5. Kararlar ve nedenleri (bunları geri almayın)

- **Instagram görselleri bilerek devre dışı.** Denenen ve elenen yollar:
  - `/embed/` ve `/embed/captioned/` sayfaları giriş yapmadan genel bir giriş kabuğu döndürüyor (kullanıcının makinesinde denendi: gönderiye ait medya adresi yok).
  - **gallery-dl** uygulamaya gömülmedi: girişsiz tekil gönderi erişimi güvenilir değil (araştırmaya göre), çerez gerektirmesi yabancı kullanıcılardan çerez/hesap istemek demek, IP başına hız sınırı kullanıcıya yansır ve lisansı **GPL-2.0** (yt-dlp Unlicense). Dağıtılan bir uygulamaya gömmek lisans yükümlülüğü getirebilir; hukuki kontrol gerekir.
  - Üçüncü taraf sitelere (StorySaver vb.) bağlanılmadı: kapanabilir/değişebilir, bağlantılar onlara gider.
  - **Çerez:** Instagram'da hiçbir koşulda kullanılmıyor (`core/extractor.py`). Yedek hesap çerezi seçeneği kullanıcı tarafından şimdilik reddedildi.
  - Doğrudan görsel bağlantısı (kullanıcı tarayıcıdan kopyalar) desteklenen yoldur.
- **Kod imzalama yapılmadı.** Azure Artifact Signing Türkiye'deki bireysel geliştiriciye kapalı (organizasyonlar: ABD/Kanada/AB/BK; bireysel: ABD/Kanada). OV sertifika yıllık ücretli ve anahtar donanımda (USB token/bulut HSM) olmak zorunda; kullanıcı ücret vermemeyi seçti. README SmartScreen uyarısını ve SHA-256 doğrulamasını anlatıyor.
- Güncelleme sağlama toplamları **bütünlüğü korur ama kimliği kanıtlamaz** (`sha256sums.txt` aynı release'ten gelir). Gerçek koruma yalnızca imza ile mümkün.

## 6. Doğrulananlar ve doğrulanmayanlar

**Doğrulandı (Linux, Python 3.12):** 37 pytest testi geçiyor; `pyflakes` temiz; `python main.py --self-test` (offscreen) hatasız; delta indirme yerel bir Range sunucusuna karşı uçtan uca çalıştı.

**Hiç çalıştırılmadı (Windows gerektirir):**
- PyInstaller derlemesi ve `MediaDock.spec` içindeki Qt ayıklaması (`opengl32sw.dll`, çeviriler, QML/Quick/PDF DLL'leri kod okuyarak çıkarıldı; derlenip açıldığı doğrulanmadı — sorun çıkarsa `_DROP_BINARIES` listesinden ilgili satırı silin).
- Inno Setup, `/SILENT` kurulum ve `[Run]` sessiz yeniden başlatma girdisi.
- GitHub Actions workflow'u (YAML sözdizimi doğrulandı, çalıştırılmadı).
- Çalışan exe'nin `.old` olarak yeniden adlandırılması (yalnızca Linux'ta `os.replace` mantığı test edildi).
- PowerShell'e ortam değişkeniyle yol iletme (testler `subprocess.run` çağrısını taklit ederek komutta yolun bulunmadığını denetler).
- GitHub release CDN'inin HTTP Range desteği **varsayıldı**; desteklemezse kod otomatik tam kuruluma düşer.
- İlk delta güncelleme, bu mekanizmayı içeren sürümden **sonraki** sürümde çalışır; eski kurulumlar bir kez tam kurulumla güncellenir.

## 7. Bilinen sorunlar ve yapılabilecekler (öncelik sırasıyla)

1. **Windows'ta uçtan uca deneme:** derle, `--self-test` ile aç, kurulumu ve bir delta güncellemeyi dene. Derleme sonrası `Get-ChildItem dist\MediaDock -Recurse | Sort Length -Desc` çıktısıyla 122 MB'ın dağılımına bakılıp sıradaki kesilebilir dosyalar belirlenmeli.
2. **yt-dlp nightly sürümleri otomatik kuruluyor** (`fetch_latest_release` pre-release'leri de seçer; kullanıcının logunda `.dev0`). Hız kazandırır ama bozuk bir nightly herkeste sorun çıkarabilir. Yalnızca kararlı sürüme geçmek veya ayarla seçtirmek düşünülebilir.
3. **Güncelleyicide Authenticode kontrolü:** kod imzalama yapılırsa indirilen kurulum dosyasının imzası çalıştırmadan önce doğrulanmalı. İmza, `tools/make_release_assets.py` çalışmadan **önce** atılmalı (özetler değişir).
4. **Küçük resim önbelleği** (`assets/thumbnails/thumb_*.jpg`) sınırsız büyür; geçmiş kayıtları bunlara bağlı olabileceği için silinmedi.
5. İlk kütüphane taraması büyük klasörlerde yavaş olabilir (dosyalar tek tek ffprobe'a verilir, ilerleme yok).
6. Logda her çıkarma hatası ~20 ms arayla iki kez yazılıyor (aynı bağlantı iki kez sorgulanıyor olabilir); nedeni araştırılmadı.
7. `ui/settings_page.py` içinde ölü kod: `_save_update_repo` ve `repo_input` (UI'da böyle bir alan oluşturulmuyor). Silinmedi.
8. FFmpeg'in ilk açılışta hash'li indirilmesi yapılmadı (şu an pakette tek kopya).

## 8. Yapmayın

- Instagram için çerez kullanımını açmayın; gallery-dl, Instagram iç API/GraphQL kazıma veya üçüncü taraf indirme sitelerini entegre etmeyin (gerekçeler bölüm 5).
- Kullanıcı verisini (`data/`, `assets/thumbnails/`, günlükler) depoya eklemeyin.
- Hata mesajlarına kullanıcıya ait çerez/token/sorgu parametreli URL yazmayın (`core/logutil.py` yalnızca sorgusuz URL yazar).
