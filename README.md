# İndirilecek KDV Listesi ve Stok Listesi XML Dönüştürücü

Bu proje, GİB standartlarındaki UBL-TR formatında olan e-Fatura XML dosyalarını kolayca Excel formatına dönüştürmek için geliştirilmiş bir Streamlit uygulamasıdır.

## Özellikler
- **İndirilecek KDV Listesi Modülü:** XML faturalardan KDV, satıcı, mal/hizmet, tutar gibi bilgileri toplar ve Excel'e aktarır.
- **Stok Listesi Modülü:** Faturalardaki ürün/hizmet, miktar, birim fiyat gibi bilgileri stok listesi formatında Excel'e aktarır.
- Çoklu XML dosyası yükleme ve toplu işlem desteği.
- Kullanıcı dostu, hızlı ve pratik arayüz.

## Kullanım
1. Gerekli paketleri yükleyin:
   ```bash
   pip install -r requirements.txt
   ```
2. Uygulamayı başlatın:
   ```bash
   streamlit run ind_kdv.py
   ```
3. Web arayüzünde modül seçin ve XML dosyalarınızı yükleyin.
4. Sonuçları tablo olarak görüntüleyin ve Excel dosyası olarak indirin.

## Dosya Açıklamaları
- `ind_kdv.py`: Ana uygulama dosyası. XML okuma, veri işleme ve arayüz kodları burada bulunur.
- `requirements.txt`: Gerekli Python paketleri listesi.

## Notlar
- KDV dönemi, "202504" gibi yıl ve ayı birleştiren formatta (YYYYMM) oluşturulur.
- XML dosyalarınızın UBL-TR standardında olması gerekmektedir.

## Lisans
Bu proje MIT lisansı ile lisanslanmıştır.

---

Her türlü öneri ve katkı için pull request gönderebilirsiniz.
