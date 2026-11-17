# BizdenBize

**BizdenBize** (Turkish for "from us", used with the hashtag #BizdenBize) is a daily wildfire-risk platform for Türkiye. For every land cell of a 0.05° grid covering the whole country, it estimates how likely a wildfire is on each of the next seven days. The result is displayed on an interactive map with four risk classes: *düşük* (low), *orta* (moderate), *yüksek* (high) and *ekstrem* (extreme).

The project was developed for the COP31 Climate Tech Creathon in Antalya, Türkiye. The pilot region is Antalya–Muğla, and the national model is trained with the same method. The project's base article is Bilgili's *"Forest Fires in 2021"* (Kızılay Akademi), and the 2021 megafires it discusses serve as the main validation case.

> **Naming note.** The project is called BizdenBize. Some internal scripts and comments still use the older working name *FireBridge*. Both names refer to the same code.

---

# English

## 1. System overview

The system is a pipeline of five layers. Each layer reads the output of the layer before it, so the complete chain can be rebuilt from raw data by running the scripts in order. This design keeps every stage inspectable: a reviewer can check the labels, the features and the model separately before trusting the final map.

| Layer | Question it answers | Main files |
|---|---|---|
| **1. Data acquisition** | Where can weather, fire and geography data be obtained? | `bizdenbize/scripts/01_data_acquisition.py`, `03_fwi_turkiye.py` |
| **2. Labels (ground truth)** | On which cell-days did a wildfire actually occur? | `02_build_labels.py`, `04_grid_labels_turkiye.py` |
| **3. Features** | What is known about each cell on each day? | `firebridge_core.py`, `firebridge_fwi.py` |
| **4. Model** | How risky is each cell, given its features? | `05_train_turkiye.py` → `models/fire_lgbm_turkiye.joblib` |
| **5. Output and dashboard** | What does the public see? | `06_predict_live.py` → `bizdenbize/dashboard/` |

### Layer 1 — Data acquisition
This layer downloads or prepares the raw inputs. `03_fwi_turkiye.py` requests the Fire Weather Index (FWI) system variables for Türkiye, one year at a time, from the Copernicus Emergency Management Service. `01_data_acquisition.py` is the earlier pilot version. It fetches similar data for the Antalya–Muğla box, together with the OpenStreetMap layers. Both scripts cache their results, so an interrupted run can resume without downloading everything again.

### Layer 2 — Labels
A label records whether a fire happened in a given cell on a given day. `02_build_labels.py` builds this table for the pilot region, and `04_grid_labels_turkiye.py` builds it nationally. The script drops detections with low VIIRS confidence. It also removes persistent heat sources such as factories, flares and landfills, because these are hot every day but do not spread as wildfires. A spot is treated as persistent when it shows heat on ten or more different days. Cell-days that look like agricultural burning are excluded from training and evaluation rather than being counted as "no fire." This choice stops the model from learning that field burning is the same as a forest fire.

### Layer 3 — Features
`firebridge_core.py` holds the shared feature code. Both training and live prediction use it, so the two always build the same input table. The features fall into four groups:

- **Weather (Hava Durumu):** the six FWI components (FFMC, DMC, DC, ISI, BUI and the FWI itself), together with 3-day and 7-day rolling means and maxima, the 7-day change in the Drought Code, and the day of the year. Rolling windows never cross from one year into the next.
- **Human access (İnsan Erişimi):** the distance from each cell to the nearest road, settlement and farmland, and the total road length inside the cell. Human-caused fires cluster near access routes, so these distances carry much of the signal.
- **History (Geçmiş):** the number of fire-days per year in the cell and in its 3×3 neighbourhood. Training uses only the other training years, so the history feature never sees the answer for the year it is predicting.
- **Environment (Çevre):** land-cover shares from ESA WorldCover 2021 (tree, shrub, grass, cropland, built-up), and elevation and slope from the Copernicus DEM GLO-90.

`firebridge_fwi.py` implements the Canadian FWI equations in Python. The live pipeline needs this module because weather forecasts do not come with FWI values. The indices therefore have to be computed from temperature, humidity, wind and rain.

### Layer 4 — Model
The model is a **LightGBM** gradient-boosted decision-tree classifier, and a logistic regression is trained alongside it as a baseline. Wildfire cell-days are rare, so the script keeps every fire cell-day and a random 5 % sample of the other cell-days. It then gives each sampled non-fire row a weight of 1/0.05. This keeps the model calibrated to the real frequency while keeping training fast. The main hyperparameters are a learning rate of 0.03, 80 % row and column subsampling, and a minimum of 200 samples per leaf. The number of leaves and the class weight were tuned on the 2024 validation year.

The script uses a strict time split. Training uses 2021–2023, validation uses 2024, and the test year is 2025, for which the model is trained on 2021–2024. A separate hindcast model is trained on 2022–2025 and predicts 2021, so the team can check the model against the megafire week of 27 July to 2 August 2021. The live model is trained on all of 2021–2025. Each cell's score is converted into a risk class using cut-points found on out-of-sample data. The output uses the cut-points 0.30, 0.55 and 0.75.

### Layer 5 — Output and dashboard
`06_predict_live.py` runs once a day, for example from Windows Task Scheduler at 06:00. It takes the current FWI state, carries it forward using Open-Meteo weather, runs the FWI equations for the next seven days, and scores every cell with the live model. It also pulls the latest NASA FIRMS hotspots, so the map can show active fires alongside the forecast. The result is written to `data.live.json`, which the browser dashboard (`index.html`, `app.js`) reads. The dashboard offers a demo mode and a pilot mode, so the same interface can display the 2021 hindcast.

---

## 2. Algorithm in brief

For each cell *c* and day *t*, the model estimates the probability that a wildfire is burning or will burn in that cell:

> p(c, t) = LightGBM( weather(c, t), human access(c), history(c), environment(c) )

The raw probability is then combined with the FWI value of the cell to produce the final score. The FWI acts as a ceiling, so a cell with a low fire-weather index cannot be shown as extreme risk merely because of its other features. The score is then mapped to the four classes described above. In the hindcast week, the team also reported which classes the burning cells fell into, and whether the highest-risk cells coincided with the 2021 megafire sites at Manavgat, Gündoğmuş, Akseki, Marmaris, Köyceğiz, Milas and Bodrum.

### Evaluation
Two metrics suit rare events. **ROC-AUC** measures how well the model ranks risky cell-days above safe ones. **PR-AUC** (average precision) measures how precise the top-ranked predictions are, and it is the more demanding of the two when fires are rare. The team also reports the share of actual fires that fall inside the top 5 % of predicted risk. Results are stored in `models/metrics_turkiye.csv`.

For the 2025 test year across all of Türkiye, the LightGBM model reaches a ROC-AUC of 0.915. The FWI value alone reaches 0.669, and logistic regression reaches 0.881. The PR-AUC is 0.010. This number looks low, but it reflects how rare fires are in the data, so it should be read together with the ROC-AUC rather than on its own. The top-5 % capture rate is 58.5 %, compared with 14.6 % for FWI alone.

---

## 3. Data sources

| Data | Source | Used for | Storage location |
|---|---|---|---|
| Fire Weather Index and sub-indices (FFMC, DMC, DC, ISI, BUI), 2021–2026 | Copernicus EWDS, dataset `cems-fire-historical-v1` (EFFIS/CEMS reanalysis) | Weather features, training, FWI start state for live runs | `data/turkiye/fwi_tr_<year>.grib` |
| Daily weather forecast and archive | Open-Meteo (no key required) | Live FWI forecast for the next seven days | Fetched at run time |
| Active-fire hotspots, VIIRS | EFFIS hotspot export (`hs_viirs`, Türkiye, 2021–2026) | Fire labels | `data/a29cb7c7d8004c7c81778ad1bd237a5b.csv` |
| Near-real-time hotspots | NASA FIRMS (requires a free map key) | Active fires on the live map | Fetched at run time |
| Roads, settlements, farmland, land use | OpenStreetMap via Geofabrik (`turkey-latest-free`) | Human-access features | `data/turkey-latest-free.shp.zip`, `data/turkiye/osm_*.gpkg` |
| Administrative boundaries | OpenStreetMap, admin level 6 (districts) and national outline | Land mask (cells at least 30 % land) | `data/turkiye/adminareas.gpkg` |
| Land cover | ESA WorldCover 2021 | Environment features | `data/turkiye/static_landcover.csv` |
| Elevation and slope | Copernicus DEM GLO-90 | Environment features | `data/turkiye/static_env.csv` |
| Megafire reference sites, 2021 | Listed in `firebridge_core.py` (seven sites, including Manavgat and Marmaris) | Validation of the hindcast week | `bizdenbize/scripts/firebridge_core.py` |

The FWI implementation was calibrated against CEMS values using Open-Meteo weather, so that the live FWI closely matches the reanalysis. The check is carried out by `06b_check_fwi_calibration.py`, and its results are stored in `data/turkiye/fwi_calibration.json`.

Key cell-level tables are stored in `data/turkiye/`: `cells.csv` (land cells), `static_human.csv` (distances and road lengths), `static_env.csv` (environment), and `fire_pos.csv` / `fire_pos_wild.csv` (positive cell-days).

---

## 4. Repository layout

```
BizdenBize/
├── bizdenbize/
│   ├── scripts/        pipeline scripts 01–06, firebridge_core.py, firebridge_fwi.py
│   └── dashboard/      index.html, app.js, data*.json (demo, pilot, hindcast, live)
├── api/                historical CEMS notebook
├── data/               raw and derived data (see section 3)
├── labels/             labels_pilot.csv (pilot labels)
└── models/             trained model (.joblib), metric tables and training logs
```

## 5. How to run

1. Install the Python dependencies: `cdsapi`, `geopandas`, `xarray`, `cfgrib`, `lightgbm`, `scikit-learn`, `scipy`, `shapely`, `requests`, `pandas`, `numpy` and `joblib`.
2. Create `~/.cdsapirc` with a Copernicus EWDS key, and set `FIRMS_MAP_KEY` (or add it to `.env`) for NASA FIRMS.
3. Run `03_fwi_turkiye.py` to download the FWI archive, then run `04_grid_labels_turkiye.py` to build the grid and labels.
4. Run `05_train_turkiye.py --export` to train the model and write the dashboard data. Add `--no-history` to produce the variant without history features.
5. Run `06_predict_live.py` to produce the daily map. Open `bizdenbize/dashboard/index.html` in a browser to view it.

## 6. Limitations

- The labels come from satellite hotspots, which detect only fires that are large or hot enough to be seen. Small fires that burn out quickly are missed.
- Agricultural and industrial burning is removed with heuristics, so some real fires are lost along with false alarms.
- The FWI system was designed for Canadian forests. Its fuel assumptions may not match every Turkish vegetation type, although the land-cover and history features help correct for this.
- Open-Meteo forecasts become less accurate beyond a few days, so risk for days five to seven is less reliable than for today and tomorrow.
- The risk map shows where conditions favour fire, not where a fire will start. It is a decision-support tool for prevention planning and does not replace the official warnings issued by the Turkish General Directorate of Forestry (OGM).


---

# Türkçe

## 1. Sistem genel bakışı

Sistem beş katmandan oluşan bir veri hattıdır. Her katman, kendinden önceki katmanın çıktısını okur. Bu nedenle tüm zincir, betikler sırayla çalıştırılarak ham veriden yeniden üretilebilir. Bu tasarım her aşamanın ayrı ayrı denetlenebilmesini sağlar. Böylece nihai haritaya güvenmeden önce etiketler, öznitelikler ve model tek tek kontrol edilebilir.

| Katman | Yanıtladığı soru | Ana dosyalar |
|---|---|---|
| **1. Veri edinimi** | Hava durumu, yangın ve coğrafya verileri nereden elde edilebilir? | `bizdenbize/scripts/01_data_acquisition.py`, `03_fwi_turkiye.py` |
| **2. Etiketler (gerçek veri)** | Hangi hücre-günlerinde gerçekten orman yangını yaşandı? | `02_build_labels.py`, `04_grid_labels_turkiye.py` |
| **3. Öznitelikler** | Her hücre hakkında her gün ne biliniyor? | `firebridge_core.py`, `firebridge_fwi.py` |
| **4. Model** | Öznitelikleri göz önüne alındığında her hücre ne kadar risklidir? | `05_train_turkiye.py` → `models/fire_lgbm_turkiye.joblib` |
| **5. Çıktı ve gösterge paneli** | Halk neyi görür? | `06_predict_live.py` → `bizdenbize/dashboard/` |

### Katman 1 — Veri edinimi
Bu katman ham girdileri indirir veya hazırlar. `03_fwi_turkiye.py`, Türkiye için Yangın Hava Durumu İndeksi (FWI) sistem değişkenlerini Copernicus Acil Durum Yönetim Servisi'nden yıl yıl talep eder. `01_data_acquisition.py` ise daha eski pilot sürümdür. Antalya–Muğla kutusu için benzer verileri ve OpenStreetMap katmanlarını getirir. Her iki betik de sonuçlarını önbelleğe alır. Böylece yarıda kalan bir çalıştırma, her şeyi baştan indirmeden kaldığı yerden devam edebilir.

### Katman 2 — Etiketler
Etiket, belirli bir hücrede belirli bir günde yangın olup olmadığını kaydeder. `02_build_labels.py` bu tabloyu pilot bölge için, `04_grid_labels_turkiye.py` ise ulusal ölçekte oluşturur. Betik, düşük VIIRS güvenilirliğine sahip tespitleri eler. Ayrıca fabrikalar, alevler ve çöplükler gibi sürekli ısı kaynaklarını çıkarır. Bunlar her gün ısınır, ancak orman yangını gibi yayılmazlar. Bir nokta, on veya daha fazla farklı günde ısı gösterdiğinde sürekli kaynak sayılır. Tarımsal yakmaya benzeyen hücre-günleri eğitim ve değerlendirmeden çıkarılır ve "yangın yok" olarak sayılmaz. Bu tercih, modelin tarla yakmayı orman yangınıyla aynı şey olarak öğrenmesini engeller.

### Katman 3 — Öznitelikler
`firebridge_core.py` ortak öznitelik kodunu içerir. Hem eğitim hem de canlı tahmin bu kodu kullanır, dolayısıyla ikisi her zaman aynı girdi tablosunu oluşturur. Öznitelikler dört gruba ayrılır:

- **Hava Durumu:** altı FWI bileşeni (FFMC, DMC, DC, ISI, BUI ve FWI'nin kendisi), 3 günlük ve 7 günlük hareketli ortalamalar ve maksimumlar, 7 günlük Kuraklık Kodu değişimi ve yılın günü. Kayan pencereler hiçbir zaman bir yıldan diğerine geçmez.
- **İnsan Erişimi:** her hücreden en yakın yola, yerleşim yerine ve tarım arazisine olan uzaklık ile hücre içindeki toplam yol uzunluğu. İnsan kaynaklı yangınlar erişim güzergâhlarının yakınında yoğunlaştığı için bu uzaklıklar sinyalin büyük bölümünü taşır.
- **Geçmiş:** hücrede ve 3×3 komşuluğunda yıl başına yangın günlerinin sayısı. Eğitim yalnızca diğer eğitim yıllarını kullanır. Dolayısıyla geçmiş özniteliği, tahmin edilen yılın cevabını hiçbir zaman görmez.
- **Çevre:** ESA WorldCover 2021 verisinden arazi örtüsü oranları (ağaç, çalılık, otlak, ekin alanı, yapılaşmış alan) ve Copernicus DEM GLO-90 verisinden yükseklik ve eğim.

`firebridge_fwi.py`, Kanada FWI denklemlerini Python'da uygular. Canlı hat bu modüle ihtiyaç duyar, çünkü hava durumu tahminleri FWI değerleriyle birlikte gelmez. Bu nedenle indeksler sıcaklık, nem, rüzgâr ve yağıştan hesaplanmalıdır.

### Katman 4 — Model
Model, bir **LightGBM** gradyan artırmalı karar ağacı sınıflandırıcısıdır. Yanında bir temel karşılaştırma modeli olarak lojistik regresyon da eğitilir. Orman yangını hücre-günleri nadir olduğundan, betik her yangın hücre-gününü ve diğer hücre-günlerinin rastgele %5'lik bir örneğini tutar. Ardından örneklenen yangın olmayan her satıra 1/0,05 ağırlığı verir. Bu yöntem, eğitimi hızlı tutarken modelin gerçek sıklığa göre kalibre kalmasını sağlar. Temel hiperparametreler şunlardır: öğrenme oranı 0,03, satır ve sütunların %80'i ile alt örnekleme ve yaprak başına en az 200 örnek. Yaprak sayısı ve sınıf ağırlığı 2024 doğrulama yılında ayarlanmıştır.

Betik katı bir zaman bölmesi kullanır. Eğitim 2021–2023 yıllarını, doğrulama 2024 yılını kullanır. Test yılı 2025'tir ve bu yıl için model 2021–2024 verisiyle eğitilir. Ayrı bir geriye dönük tahmin (hindcast) modeli 2022–2025 verisiyle eğitilir ve 2021'i tahmin eder. Böylece ekip, 27 Temmuz – 2 Ağustos 2021 büyük yangın haftasına karşı modeli sınayabilir. Canlı model ise 2021–2025 verisinin tamamıyla eğitilir. Her hücrenin puanı, örneklem dışı verilerde bulunan eşik değerleri kullanılarak bir risk sınıfına dönüştürülür. Çıktıda 0,30, 0,55 ve 0,75 eşik değerleri kullanılır.

### Katman 5 — Çıktı ve gösterge paneli
`06_predict_live.py` günde bir kez çalışır. Örneğin Windows Görev Zamanlayıcı ile sabah 06:00'da başlatılabilir. Betik, mevcut FWI durumunu alır, Open-Meteo hava durumu verisiyle önümüzdeki yedi gün için ileriye taşır, FWI denklemlerini bu günler için çalıştırır ve her hücreyi canlı modelle puanlar. Ayrıca NASA FIRMS'in en güncel ısı noktalarını çeker. Böylece harita, tahminin yanında aktif yangınları da gösterebilir. Sonuç, tarayıcı tabanlı gösterge paneli (`index.html`, `app.js`) tarafından okunan `data.live.json` dosyasına yazılır. Panel bir demo modu ve bir pilot modu sunar. Bu sayede aynı arayüz 2021 geriye dönük tahminini de gösterebilir.

---

## 2. Algoritmanın özeti

Her *c* hücresi ve her *t* günü için model, o hücrede bir orman yangınının yanmakta olma veya yanacak olma olasılığını tahmin eder:

> p(c, t) = LightGBM( hava durumu(c, t), insan erişimi(c), geçmiş(c), çevre(c) )

Ham olasılık daha sonra hücrenin FWI değeriyle birleştirilerek nihai puan üretilir. FWI bir tavan görevi görür. Dolayısıyla düşük yangın hava durumu indeksine sahip bir hücre, diğer özniteliklerinden dolayı yalnızca "ekstrem" olarak gösterilemez. Puan daha sonra yukarıda tanımlanan dört sınıfa eşlenir. Geriye dönük tahmin haftasında ekip, yanan hücrelerin hangi sınıflara düştüğünü ve en yüksek riskli hücrelerin 2021 büyük yangın noktalarıyla örtüşüp örtüşmediğini de raporlamıştır. Bu noktalar Manavgat, Gündoğmuş, Akseki, Marmaris, Köyceğiz, Milas ve Bodrum'dur.

### Değerlendirme
Nadir olaylara uygun iki metrik kullanılır. **ROC-AUC**, modelin riskli hücre-günlerini güvenli olanların üzerine ne kadar iyi sıraladığını ölçer. **PR-AUC** (ortalama kesinlik), en üst sırada yer alan tahminlerin ne kadar kesin olduğunu ölçer ve yangınlar nadir olduğunda daha zorlayıcı bir metriktir. Ekip ayrıca gerçek yangınların tahmin edilen riskin en yüksek %5'lik diliminde yer alma oranını da raporlar. Sonuçlar `models/metrics_turkiye.csv` dosyasında saklanır.

Tüm Türkiye için 2025 test yılında LightGBM modeli 0,915 ROC-AUC değerine ulaşır. Yalnızca FWI değeri 0,669, lojistik regresyon ise 0,881 değerine ulaşır. PR-AUC değeri 0,010'dur. Bu sayı düşük görünür, ancak yangınların veride ne kadar nadir olduğunu yansıtır. Bu nedenle tek başına değil, ROC-AUC ile birlikte yorumlanmalıdır. En yüksek %5'lik dilimde yakalama oranı %58,5'tir. Yalnızca FWI kullanıldığında bu oran %14,6'dır.

---

## 3. Veri kaynakları

| Veri | Kaynak | Kullanım amacı | Depolama konumu |
|---|---|---|---|
| Yangın Hava Durumu İndeksi ve alt indeksler (FFMC, DMC, DC, ISI, BUI), 2021–2026 | Copernicus EWDS, `cems-fire-historical-v1` veri seti (EFFIS/CEMS yeniden analizi) | Hava durumu öznitelikleri, eğitim, canlı çalıştırmalar için FWI başlangıç durumu | `data/turkiye/fwi_tr_<yıl>.grib` |
| Günlük hava durumu tahmini ve arşivi | Open-Meteo (anahtar gerekmez) | Önümüzdeki yedi gün için canlı FWI tahmini | Çalışma anında alınır |
| Aktif yangın ısı noktaları, VIIRS | EFFIS ısı noktası dışa aktarımı (`hs_viirs`, Türkiye, 2021–2026) | Yangın etiketleri | `data/a29cb7c7d8004c7c81778ad1bd237a5b.csv` |
| Neredeyse gerçek zamanlı ısı noktaları | NASA FIRMS (ücretsiz harita anahtarı gerekir) | Canlı haritada aktif yangınlar | Çalışma anında alınır |
| Yollar, yerleşim yerleri, tarım arazileri, arazi kullanımı | Geofabrik üzerinden OpenStreetMap (`turkey-latest-free`) | İnsan erişimi öznitelikleri | `data/turkey-latest-free.shp.zip`, `data/turkiye/osm_*.gpkg` |
| İdari sınırlar | OpenStreetMap, yönetim düzeyi 6 (ilçeler) ve ülke sınırı | Kara maskesi (en az %30 karasal alana sahip hücreler) | `data/turkiye/adminareas.gpkg` |
| Arazi örtüsü | ESA WorldCover 2021 | Çevre öznitelikleri | `data/turkiye/static_landcover.csv` |
| Yükseklik ve eğim | Copernicus DEM GLO-90 | Çevre öznitelikleri | `data/turkiye/static_env.csv` |
| 2021 büyük yangın referans noktaları | `firebridge_core.py` içinde listelenir (Manavgat ve Marmaris dahil yedi nokta) | Geriye dönük tahmin haftasının doğrulanması | `bizdenbize/scripts/firebridge_core.py` |

FWI uygulaması, Open-Meteo hava durumu verisi kullanılarak CEMS değerlerine karşı kalibre edilmiştir. Böylece canlı FWI, yeniden analiz verisiyle yakından eşleşir. Kontrol `06b_check_fwi_calibration.py` tarafından yapılır ve sonuçları `data/turkiye/fwi_calibration.json` dosyasında saklanır.

Hücre düzeyindeki temel tablolar `data/turkiye/` klasöründe tutulur: `cells.csv` (kara hücreleri), `static_human.csv` (uzaklıklar ve yol uzunlukları), `static_env.csv` (çevre) ve `fire_pos.csv` / `fire_pos_wild.csv` (pozitif hücre-günleri).

---

## 4. Depo yapısı

```
BizdenBize/
├── bizdenbize/
│   ├── scripts/        01–06 hat betikleri, firebridge_core.py, firebridge_fwi.py
│   └── dashboard/      index.html, app.js, data*.json (demo, pilot, geriye dönük, canlı)
├── api/                geçmiş CEMS not defteri
├── data/               ham ve türetilmiş veriler (bkz. bölüm 3)
├── labels/             labels_pilot.csv (pilot etiketleri)
└── models/             eğitilmiş model (.joblib), metrik tabloları ve eğitim günlükleri
```

## 5. Nasıl çalıştırılır

1. Python bağımlılıklarını kurun: `cdsapi`, `geopandas`, `xarray`, `cfgrib`, `lightgbm`, `scikit-learn`, `scipy`, `shapely`, `requests`, `pandas`, `numpy` ve `joblib`.
2. Copernicus EWDS anahtarını içeren `~/.cdsapirc` dosyasını oluşturun. NASA FIRMS için `FIRMS_MAP_KEY` değişkenini ayarlayın veya `.env` dosyasına ekleyin.
3. FWI arşivini indirmek için `03_fwi_turkiye.py` betiğini, ardından ızgarayı ve etiketleri oluşturmak için `04_grid_labels_turkiye.py` betiğini çalıştırın.
4. Modeli eğitmek ve gösterge paneli verilerini yazmak için `05_train_turkiye.py --export` komutunu çalıştırın. Öznitelik geçmişi olmayan varyantı üretmek için `--no-history` seçeneğini ekleyin.
5. Günlük haritayı üretmek için `06_predict_live.py` betiğini çalıştırın. Görüntülemek için `bizdenbize/dashboard/index.html` dosyasını bir tarayıcıda açın.

## 6. Sınırlamalar

- Etiketler uydu ısı noktalarından gelir. Bu noktalar yalnızca yeterince büyük veya sıcak olan yangınları algılar. Hızlı sönen küçük yangınlar gözden kaçar.
- Tarımsal ve endüstriyel yakmalar sezgisel yöntemlerle çıkarılır. Bu nedenle bazı gerçek yangınlar, yanlış alarmlarla birlikte kaybolabilir.
- FWI sistemi Kanada ormanları için tasarlanmıştır. Yakıt varsayımları Türkiye'deki her bitki örtüsü tipine uymayabilir. Yine de arazi örtüsü ve geçmiş öznitelikleri bu farkı kısmen telafi eder.
- Open-Meteo tahminleri birkaç günden sonra daha az isabetli olur. Bu nedenle beşinci ila yedinci günlerdeki risk, bugün ve yarına göre daha az güvenilirdir.
- Risk haritası, yangının nerede başlayacağını değil, koşulların yangına elverişli olduğu yerleri gösterir. Önleme planlaması için bir karar destek aracıdır. Orman Genel Müdürlüğü'nün (OGM) resmi uyarılarının yerini tutmaz.
