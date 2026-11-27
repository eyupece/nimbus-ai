"""Modelin çağırabileceği fonksiyonlar (araçlar).

Not: Jestler önceden bir fonksiyondu (jest(ad)); BLOCKING olunca cevabı ~0.5-2.5 sn geciktiriyor,
NON_BLOCKING olunca model jestle turu bitirip susuyordu. Artık jestleri `ifade.py` söylenen
metinden gecikmesiz üretiyor. JEST_ACIKLAMALARI belgeleme için duruyor.
"""

from google.genai import types

JEST_ACIKLAMALARI = {
    "goz_kirp": "göz kırpma (şaka, ima)",
    "gozleri_kis": "gözleri kısma (şüphe, birini tartma)",
    "saskin": "şaşırma",
    "dusun": "düşünme (yukarı bakma)",
    "gul": "gülme / keyiflenme",
    "kizgin": "hafif kızgınlık / sitem",
}

ARACLAR = [
    types.Tool(
        function_declarations=[
            types.FunctionDeclaration(
                name="kisiyi_tani",
                description=(
                    "Karşındaki kişi adını söylediği anda, cevap vermeden önce çağır. Onu daha önce tanıyıp "
                    "tanımadığını ve onun hakkında hatırladıklarını döndürür; cevabını buna göre ver."
                ),
                parameters=types.Schema(
                    type=types.Type.OBJECT,
                    properties={"ad": types.Schema(type=types.Type.STRING, description="Kişinin söylediği adı")},
                    required=["ad"],
                ),
                # BLOCKING: model sonucu alıp tek seferde konuşur. NON_BLOCKING + WHEN_IDLE denendi:
                # cümle yarıda kesiliyor ve devamı sonraki tura karışıyordu (senaryo testi, 27.11.2026).
                behavior=types.Behavior.BLOCKING,
            ),
            types.FunctionDeclaration(
                name="uykuya_don",
                description=(
                    "Karşındaki vedalaştığında ya da konuşma doğal olarak bittiğinde, "
                    "veda cümleni söyledikten sonra çağır. Bulutlara (uykuya) dönersin."
                ),
                behavior=types.Behavior.NON_BLOCKING,
            ),
        ]
    )
]

# Gerçek dünya bilgisi: hava durumu, maç, haber, genel bilgi
ARAMA = types.Tool(google_search=types.GoogleSearch())

# Sahne yönetimi: operatörün gönderdiği mesajlar bu önekle gelir
SAHNE_ONEKI = "[Sahne yönetimi]"
SAHNE_TALIMATI = (
    f"'{SAHNE_ONEKI}' ile başlayan mesajlar sahne operatöründendir, karşındaki kişi söylemiş değildir. "
    "Bu mesajlardaki yönlendirmeye uy ama operatörden ya da bu mesajlardan asla bahsetme."
)


def yanit(cagri: types.FunctionCall, sonuc: dict | None = None) -> types.FunctionResponse:
    """BLOCKING fonksiyonlar için yanıt: model bunu alınca turuna devam eder."""
    return types.FunctionResponse(id=cagri.id, name=cagri.name, response=sonuc or {"tamam": True})


def bos_aninda_yanit(cagri: types.FunctionCall, sonuc: dict) -> types.FunctionResponse:
    """NON_BLOCKING fonksiyon sonucu: model o anki cümlesini bitirince (WHEN_IDLE) tepki verir."""
    return types.FunctionResponse(
        id=cagri.id, name=cagri.name, response=sonuc,
        scheduling=types.FunctionResponseScheduling.WHEN_IDLE,
    )


def sessiz_yanit(cagri: types.FunctionCall, sonuc: dict | None = None) -> types.FunctionResponse:
    """Modelin konuşmasını bölmeyen (SILENT) fonksiyon yanıtı."""
    return types.FunctionResponse(
        id=cagri.id,
        name=cagri.name,
        response=sonuc or {"tamam": True},
        scheduling=types.FunctionResponseScheduling.SILENT,
    )
