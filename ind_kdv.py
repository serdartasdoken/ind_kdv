import streamlit as st
import pandas as pd
import xml.etree.ElementTree as ET
import io
import re

# XML'den veri çekerken NoneType hatası almamak için yardımcı fonksiyon
def find_text(element, path, namespaces):
    """Belirtilen yoldaki elementi bulur ve metnini döndürür. Bulamazsa boş string döner."""
    found_element = element.find(path, namespaces)
    return found_element.text if found_element is not None else ""

def find_tax_id(party_element, ns):
    for party_id in party_element.findall("cac:PartyIdentification", ns):
        id_elem = party_id.find("cbc:ID", ns)
        if id_elem is not None and id_elem.get("schemeID") in ("VKN", "TCKN"):
            return id_elem.text
    return ""

def translate_unit_code(code):
    """Sık kullanılan UBL birim kodlarını okunabilir Türkçe metinlere çevirir."""
    unit_map = {
        'C62': 'Adet',
        'NIU': 'Adet',
        'KGM': 'Kg',
        'GRM': 'Gr',
        'LTR': 'Litre',
        'MTR': 'Metre',
        'MTK': 'm²',
        'MTQ': 'm³',
        'DAY': 'Gün',
        'MON': 'Ay',
        'SET': 'Set',
        'BX': 'Kutu'
    }
    # Eğer kod haritada yoksa, kodun kendisini geri döndürür.
    return unit_map.get(code, code)

def parse_invoice_xml(xml_content):
    """
    Tek bir UBL-TR XML fatura içeriğini ayrıştırır ve bir sözlük olarak döndürür.
    """
    try:
        root = ET.fromstring(xml_content)
        
        ns = {
            'cbc': 'urn:oasis:names:specification:ubl:schema:xsd:CommonBasicComponents-2',
            'cac': 'urn:oasis:names:specification:ubl:schema:xsd:CommonAggregateComponents-2'
        }

        invoice_date = find_text(root, 'cbc:IssueDate', ns)
        invoice_id_full = find_text(root, 'cbc:ID', ns)
        
        # Fatura serisi sütunu boş bırakılacak, fatura numarasının tamamı sıra no sütununa yazılacak
        invoice_series = ""  # Serisi boş
        invoice_number = invoice_id_full  # Tamamı sıra no

        supplier_party = root.find('cac:AccountingSupplierParty/cac:Party', ns)
        supplier_name = find_text(supplier_party, 'cac:PartyName/cbc:Name', ns)
        supplier_tax_id = find_tax_id(supplier_party, ns)

        # Fatura Satırlarını Toplama
        item_names = []
        quantities = []
        line_extension_amounts = []
        tax_amounts = []

        for line in root.findall('cac:InvoiceLine', ns):
            # Ürün/Hizmet adını listeye ekle (None ise boş string olarak ekle)
            item_name = find_text(line, 'cac:Item/cbc:Name', ns) or ""
            item_names.append(item_name)
            
            # Miktar ve birim kodunu alıp çevir
            quantity_element = line.find('cbc:InvoicedQuantity', ns)
            if quantity_element is not None:
                quantity = quantity_element.text or "0"
                unit_code = quantity_element.get('unitCode', '')
                translated_unit = translate_unit_code(unit_code)
                quantities.append(f"{quantity} {translated_unit.strip()}")
            else:
                quantities.append("0 Adet") # Makul bir varsayılan

            # None kontrolü ile float'a çevir
            le_amount = find_text(line, 'cbc:LineExtensionAmount', ns)
            line_extension_amounts.append(float(le_amount) if le_amount not in (None, "") else 0)
            tax_amt = find_text(line, 'cac:TaxTotal/cbc:TaxAmount', ns)
            tax_amounts.append(float(tax_amt) if tax_amt not in (None, "") else 0)

        total_line_extension = sum(line_extension_amounts)
        total_tax_amount = sum(tax_amounts)
        
        # Tevkifatlı fatura kontrolü ve değerleri alma
        withholding_kdv_amount = 0
        actual_kdv_amount = total_tax_amount
        
        # Tevkifat bilgilerini kontrol et
        withholding_tax_totals = root.findall('.//cac:WithholdingTaxTotal', ns)
        if withholding_tax_totals:
            for wht_total in withholding_tax_totals:
                # WithholdingTaxTotal altındaki TaxAmount'u al (2 Nolu Beyanname için)
                wht_amount = find_text(wht_total, 'cbc:TaxAmount', ns)
                if wht_amount:
                    withholding_kdv_amount = float(wht_amount)
                
                # TaxSubtotal altındaki TaxableAmount'u al (KDV'si için)
                taxable_amount = find_text(wht_total, 'cac:TaxSubtotal/cbc:TaxableAmount', ns)
                if taxable_amount:
                    actual_kdv_amount = float(taxable_amount)
        
        # --- DEĞİŞİKLİK BURADA ---
        # Listeleri virgül ile birleştirerek tek bir string haline getiriyoruz.
        formatted_invoice_date = ""
        if invoice_date:
            try:
                formatted_invoice_date = pd.to_datetime(invoice_date).strftime('%d.%m.%Y')
            except Exception:
                formatted_invoice_date = invoice_date
        
        # --- SADECE XML'DEKİ DEĞERLERİ AL ---
        # KDV'si ve 2 Nolu Beyanname'de Ödenen Kdv Tutarı doğrudan XML'den alınacak
        kdv_value = None
        withholding_kdv_value = None
        # KDV'si: ilk <cac:TaxTotal>/<cac:TaxSubtotal>/<cbc:TaxAmount>
        tax_total = root.find('cac:TaxTotal', ns)
        if tax_total is not None:
            tax_subtotal = tax_total.find('cac:TaxSubtotal', ns)
            if tax_subtotal is not None:
                kdv_text = find_text(tax_subtotal, 'cbc:TaxAmount', ns)
                if kdv_text:
                    kdv_value = float(kdv_text)
        # 2 Nolu Beyanname: ilk <cac:WithholdingTaxTotal>/<cbc:TaxAmount>
        withholding_tax_total = root.find('cac:WithholdingTaxTotal', ns)
        if withholding_tax_total is not None:
            wht_text = find_text(withholding_tax_total, 'cbc:TaxAmount', ns)
            if wht_text:
                withholding_kdv_value = float(wht_text)

        # Tevkifatlı Faturanın Tevkifata Tabi Olmayan Ve Bu Dönemde İndirilen Kdv Tutarı: KDV'si - 2 Nolu Beyanname
        tevkifata_tabi_olmayan_kdv = 0
        if kdv_value is not None and withholding_kdv_value is not None:
            tevkifata_tabi_olmayan_kdv = kdv_value - withholding_kdv_value
        elif kdv_value is not None:
            tevkifata_tabi_olmayan_kdv = kdv_value

        invoice_data = {
            "Alış Faturasının Tarihi": formatted_invoice_date,
            "Alış Faturasının Serisi": invoice_series,  # Boş bırak
            "Alış Faturasının Sıra No'su": invoice_number,  # Tamamı
            "Satıcının Adı-Soyadı / Ünvanı": supplier_name,
            "Satıcının Vergi Kimlik Numarası / TC Kimlik Numarası": supplier_tax_id,
            "Alınan Mal ve/veya Hizmetin Cinsi": ", ".join(item_names),
            "Alınan Mal ve/veya Hizmetin Miktarı": ", ".join(quantities),
            "Alınan Mal ve/veya Hizmetin KDV Hariç Tutarı": total_line_extension,
            "KDV'si": kdv_value if kdv_value is not None else 0,
            "Tevkifatlı Faturanın Tevkifata Tabi Olmayan Ve Bu Dönemde İndirilen Kdv Tutarı": tevkifata_tabi_olmayan_kdv,
            "2 Nolu Beyannamede Ödenen Kdv Tutarı": withholding_kdv_value if withholding_kdv_value is not None else 0,
            "Toplam İndirilen KDV Tutarı": kdv_value if kdv_value is not None else 0,
            "GGB Tescil No'su (Alış İthalat İse)": "",
            "Belgenin İndirim Hakkının Kullanıldığı KDV Dönemi": pd.to_datetime(invoice_date).strftime('%Y/%m') if invoice_date else ""
        }
        
        return invoice_data
    
    except Exception as e:
        st.error(f"XML dosyası ayrıştırılırken bir hata oluştu: {e}")
        return None

def to_excel(df):
    """
    DataFrame'i Excel formatına çevirir ve byte olarak döndürür.
    """
    output = io.BytesIO()
    with pd.ExcelWriter(output, engine='openpyxl') as writer:
        df.to_excel(writer, index=False, sheet_name='Indirilecek_KDV_Listesi')
        worksheet = writer.sheets['Indirilecek_KDV_Listesi']
        for idx, col in enumerate(df):
            series = df[col]
            max_len = max((
                series.astype(str).map(len).max(),
                len(str(series.name))
            )) + 2
            worksheet.column_dimensions[chr(65 + idx)].width = max_len
    processed_data = output.getvalue()
    return processed_data

# --- Streamlit Arayüzü ---

st.set_page_config(page_title="XML Fatura Dönüştürücü", layout="wide")

st.title("📄 UBL-TR XML Fatura -> Excel Dönüştürücü")
st.write(
    "Bu araç, GİB standartlarındaki UBL-TR formatında olan e-Fatura XML dosyalarınızı, "
    "**İndirilecek KDV Listesi** veya **Stok Listesi** formatında bir Excel dosyasına dönüştürür."
)
st.markdown("---")

modul = st.radio(
    "Lütfen kullanmak istediğiniz modülü seçin:",
    ("İndirilecek KDV Listesi Modülü", "Stok Listesi Modülü")
)

uploaded_files = st.file_uploader(
    "Lütfen XML formatındaki fatura dosyalarınızı seçin",
    type="xml",
    accept_multiple_files=True
)

if uploaded_files:
    all_invoice_data = []
    all_stock_rows = []
    progress_bar = st.progress(0)
    total_files = len(uploaded_files)

    for i, uploaded_file in enumerate(uploaded_files):
        xml_content = uploaded_file.getvalue()
        error_in_file = False
        parsed_data = None
        try:
            parsed_data = parse_invoice_xml(xml_content)
            if parsed_data:
                all_invoice_data.append(parsed_data)
        except Exception as e:
            error_in_file = True
            st.warning(f"{uploaded_file.name} işlenirken hata: {e}")
        # Stok Listesi için satır bazında ürün/hizmetleri topla
        try:
            root = ET.fromstring(xml_content)
            ns = {
                'cbc': 'urn:oasis:names:specification:ubl:schema:xsd:CommonBasicComponents-2',
                'cac': 'urn:oasis:names:specification:ubl:schema:xsd:CommonAggregateComponents-2'
            }
            invoice_id_full = find_text(root, 'cbc:ID', ns)
            invoice_date = find_text(root, 'cbc:IssueDate', ns)
            formatted_invoice_date = ""
            if invoice_date:
                try:
                    formatted_invoice_date = pd.to_datetime(invoice_date).strftime('%d.%m.%Y')
                except Exception:
                    formatted_invoice_date = invoice_date
            supplier_party = root.find('cac:AccountingSupplierParty/cac:Party', ns)
            supplier_name = find_text(supplier_party, 'cac:PartyName/cbc:Name', ns)
            for line in root.findall('cac:InvoiceLine', ns):
                item_name = find_text(line, 'cac:Item/cbc:Name', ns) or ""
                quantity_element = line.find('cbc:InvoicedQuantity', ns)
                if quantity_element is not None:
                    quantity = quantity_element.text or "0"
                    unit_code = quantity_element.get('unitCode', '')
                    translated_unit = translate_unit_code(unit_code)
                    quantity_str = f"{quantity} {translated_unit.strip()}"
                else:
                    quantity_str = "0 Adet"
                unit_price = find_text(line, 'cac:Price/cbc:PriceAmount', ns)
                all_stock_rows.append({
                    "Fatura No": invoice_id_full,
                    "Fatura Tarihi": formatted_invoice_date,
                    "Satıcı": supplier_name,
                    "Ürün/Hizmet": item_name,
                    "Miktar": quantity_str,
                    "Birim Fiyat": float(unit_price) if unit_price not in (None, "") else 0
                })
        except Exception as e:
            error_in_file = True
            st.warning(f"{uploaded_file.name} stok listesi oluşturulurken hata: {e}")
        progress_bar.progress((i + 1) / total_files)
        # Sadece hatalı dosyalar için isim ve hata mesajı gösterilecek, başarılılar için çıktı yok

    if modul == "İndirilecek KDV Listesi Modülü" and all_invoice_data:
        st.success(f"{len(all_invoice_data)} adet fatura başarıyla işlendi!")
        df = pd.DataFrame(all_invoice_data)
        df.insert(0, 'Sıra No', df["Alış Faturasının Sıra No'su"])  # Sıra No sütununa fatura numarasının tamamı yazılacak
        desired_columns = [
            "Sıra No", "Alış Faturasının Tarihi", "Alış Faturasının Serisi", 
            "Alış Faturasının Sıra No'su", "Satıcının Adı-Soyadı / Ünvanı",
            "Satıcının Vergi Kimlik Numarası / TC Kimlik Numarası",
            "Alınan Mal ve/veya Hizmetin Cinsi", "Alınan Mal ve/veya Hizmetin Miktarı",
            "Alınan Mal ve/veya Hizmetin KDV Hariç Tutarı", "KDV'si",
            "Tevkifatlı Faturanın Tevkifata Tabi Olmayan Ve Bu Dönemde İndirilen Kdv Tutarı",
            "2 Nolu Beyannamede Ödenen Kdv Tutarı", "Toplam İndirilen KDV Tutarı",
            "GGB Tescil No'su (Alış İthalat İse)", "Belgenin İndirim Hakkının Kullanıldığı KDV Dönemi"
        ]
        df = df[desired_columns]
        st.dataframe(df)
        excel_data = to_excel(df)
        st.download_button(
            label="📥 Excel Dosyasını İndir",
            data=excel_data,
            file_name="indirilecek_kdv_listesi.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        )
    elif modul == "Stok Listesi Modülü" and all_stock_rows:
        st.success(f"{len(all_stock_rows)} satır stok listesi oluşturuldu!")
        stock_df = pd.DataFrame(all_stock_rows)
        stock_df = stock_df[["Fatura No", "Fatura Tarihi", "Satıcı", "Ürün/Hizmet", "Miktar", "Birim Fiyat"]]
        st.dataframe(stock_df)
        excel_data = to_excel(stock_df)
        st.download_button(
            label="📥 Stok Listesi Excel'i İndir",
            data=excel_data,
            file_name="stok_listesi.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        )