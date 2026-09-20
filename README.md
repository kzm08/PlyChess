# PlyC — Ply Chess

**Satranç açılışlarını "süper bilgisayar" mantığıyla, gerçekten sonuna kadar hesaplayan açık kaynak araç.**

PlyC, Stockfish motorunu kullanarak bir açılış pozisyonundan itibaren hem sizin
oynayabileceğiniz en iyi hamleleri (ve öğretici tuzak hamleleri) hem de rakibin
oynayabileceği tüm makul karşılıkları derinlemesine tarar. Amaç: kimsenin fark
etmediği ama kazanca götüren o nadir hamleyi bulmak — isterse saatler sürsün.

Çıktı, [Lichess Study](https://lichess.org/study)'ye doğrudan import edilebilen,
etiketli bir varyasyon PGN dosyasıdır.


## Neden?

Satranç öğreniminde iki alan var: açılış ve açılış-sonrası orta oyun. İnternette
satranç materyali çoğalsa da, belirli bir açılışı *gerçekten* tüketen, hem "bizim
en iyi hamlelerimiz" hem "rakibin olası tüm cevapları + biz onlara nasıl cevap
veririz" sorusunu cevaplayan ücretsiz bir araç yoktu. PlyC bunu, elinizdeki
sıradan bir PC'yi (4 çekirdek, 4GB RAM bile yeterli) bir gecede çalıştırarak
yapmayı hedefliyor.

## Özellikler

- **Etiketli hamle analizi**: her pozisyonda mükemmel / harika / iyi / tuzak
  hamleler ayrı ayrı bulunur ve derecelendirilir.
- **Simetrik ağaç**: hem sizin hem rakibin hamleleri aynı derinlikte analiz edilir.
- **Ply-decay dallanma**: kökte geniş, derinlerde daralan arama — kombinatorik
  patlamayı kontrol altında tutar.
- **Hazır seviyeler**: `hizli` (test, ~15sn) / `orta` (birkaç dakika) / `derin`
  (üretim kalitesi, dakikalar).
- **Çoklu dil**: Türkçe / İngilizce, kurulumda sorulur, `--dil` ile geçici
  değiştirilebilir.
- **Motor ekle**: `--motor-ekle <URL>` ile farklı bir Stockfish sürümü indirip
  kullanabilirsiniz (Stockfish bundle edilmez, ayrıca kurulur — bkz. Lisans).
- **Taraf etiketi**: `--taraf beyaz/siyah` ile hangi renk için çalıştığınızı
  PGN başlığına ve konsola işler.
- **Lichess Study uyumlu PGN çıktısı**: her hamlede etiket + eval yorumu.

## Amaç nedir?

Satranç için herkesin kendi oyununu veya çalışması gereken oyunu analiz etmesi gerekir. Birçok motor kaynağı ücretli ya da süre sınırlıdır. Projenin amacında ise local bilgisayarda çalıştırılabilecek, kaliteli, kullanışlı ve sınırsız derin analiz için hazırlanmaya çalışılmıştır. Projenin diğer amaçlarından birisi ise kodlamada kendimi geliştirmeye çalışmak. Başlangıç temeli Claude Sonneet 5 ile atılmış olup kalan sürümleri bu temelle geliştirmeye çalışıcağım.

## Kurulum

### .deb paketi ile (Debian / Ubuntu / Linux Mint)

```bash
sudo apt install stockfish   # önce bağımlılık
sudo dpkg -i plyc_0.3.0_amd64.deb
sudo apt install -f          # eksik bağımlılık varsa
```

### Kaynaktan

```bash
pip install python-chess --break-system-packages
sudo apt install stockfish
python3 plyc.py --seviye hizli --opening "d4 d5 c4"
```

## Kullanım

```bash
# Hızlı doğrulama
plyc --seviye hizli --opening "d4 d5 c4" --outdir ~/test

# Gerçek/derin analiz, beyaz repertuvarı
plyc --seviye derin --opening "e4 c5" --taraf beyaz --outdir ~/sicilyan

# İngilizce arayüz
plyc --seviye orta --opening "e4" --dil en --outdir ~/e4_black_repertoire

# Farklı bir Stockfish sürümü indirip kullanma
plyc --motor-ekle "https://github.com/official-stockfish/Stockfish/releases/download/sf_18/stockfish-ubuntu-x86-64-avx2.tar" --motor-isim sf18
plyc --seviye derin --opening "e4 e5" --motor ~/.local/share/plyc/engines/sf18
```

Tüm seçenekler için: `plyc --help`

## Config parametreleri

`config.json` (ve `config_orta.json`, `config_hizli_test.json`) her ayarın
açıklamasını içerir. Öne çıkanlar:

| Parametre | Anlamı |
|---|---|
| `multipv` | Kökte kaç "iyi" hamleye bakılacağı |
| `max_ply` | Ağacın kaç yarım-hamle derinleşeceği |
| `time_per_node_seconds` | Her pozisyona harcanan analiz süresi |
| `trap_cp_min` / `trap_cp_max` | Tuzak sayılan centipawn aralığı |
| `multipv_floor` / `trap_candidates_floor` | Derinlerde dallanmanın ineceği taban |

## Çıktılar

- `tree.json`: ham ağaç verisi (FEN, eval, etiket, PV, çocuk düğümler)
- `variations.pgn`: Lichess Study'ye import edilebilir, etiketli varyasyon PGN'i

## Yol haritası

- [ ] Windows .exe + görsel arayüz (GUI)
- [ ] Konsol/GUI çıktısında hamle yolu bağlamının gösterilmesi (okunurluk)
- [ ] Linux için de GUI
- [ ] Çoklu dil kapsamının genişletilmesi

## Lisans

GNU General Public License v3.0 (veya sonrası) — bkz. [LICENSE](LICENSE).

Bu proje [python-chess](https://github.com/niklasf/python-chess) kütüphanesini
(GPL-3.0+) kullanır ve PyInstaller ile derlenen binary'ye gömer; bu yüzden
PlyC'nin kendisi de GPL-3.0-or-later lisanslıdır.

**Stockfish bundle edilmez.** [Stockfish](https://stockfishchess.org) (GPL-3.0)
kendi lisansı altında ayrıca kurulur (`apt install stockfish` veya
`--motor-ekle` ile). `engine_path` config alanı hangi motor binary'sinin
kullanılacağını belirler.

## Katkıda bulunma

Issue ve pull request'ler açıktır. Proje hâlâ erken aşamada (v0.3.0) — özellikle
GUI/exe tarafında istediğiniz gibi yardım edebilirsiniz.
