"""Modelin çağırabileceği fonksiyonlar (araçlar): jestler ve konuşma akışı."""

from google.genai import types

from .govde import JESTLER

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
                name="jest",
                description=(
                    "Yüzünle bir ifade yap. Duygunun belirgin olduğu cevaplarda, konuşmaya başlamadan "
                    "hemen önce çağır; her cevapta değil, bir cevapta en fazla bir kez. Çağırdıktan sonra "
                    "cevabını sesli söylemeye devam et, sadece jestle yetinme. İfadeler: "
                    + ", ".join(f"{k} = {v}" for k, v in JEST_ACIKLAMALARI.items())
                ),
                parameters=types.Schema(
                    type=types.Type.OBJECT,
                    properties={"ad": types.Schema(type=types.Type.STRING, enum=list(JESTLER))},
                    required=["ad"],
                ),
                # BLOCKING: model yanıtı alınca aynı turda konuşmaya devam eder.
                # (NON_BLOCKING + SILENT denendi: model jestle turu bitirip susuyordu.)
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

# Sahne yönetimi: operatörün gönderdiği mesajlar bu önekle gelir
SAHNE_ONEKI = "[Sahne yönetimi]"
SAHNE_TALIMATI = (
    f"'{SAHNE_ONEKI}' ile başlayan mesajlar sahne operatöründendir, karşındaki kişi söylemiş değildir. "
    "Bu mesajlardaki yönlendirmeye uy ama operatörden ya da bu mesajlardan asla bahsetme."
)


def yanit(cagri: types.FunctionCall, sonuc: dict | None = None) -> types.FunctionResponse:
    """BLOCKING fonksiyonlar için yanıt: model bunu alınca turuna devam eder."""
    return types.FunctionResponse(id=cagri.id, name=cagri.name, response=sonuc or {"tamam": True})


def sessiz_yanit(cagri: types.FunctionCall, sonuc: dict | None = None) -> types.FunctionResponse:
    """Modelin konuşmasını bölmeyen (SILENT) fonksiyon yanıtı."""
    return types.FunctionResponse(
        id=cagri.id,
        name=cagri.name,
        response=sonuc or {"tamam": True},
        scheduling=types.FunctionResponseScheduling.SILENT,
    )
