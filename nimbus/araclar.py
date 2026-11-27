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
                    "Yüzünle bir ifade yap. Konuşurken duygunun belirgin olduğu anlarda kullan, "
                    "her cümlede değil (bir cevapta en fazla bir kez). Ifadeler: "
                    + ", ".join(f"{k} = {v}" for k, v in JEST_ACIKLAMALARI.items())
                ),
                parameters=types.Schema(
                    type=types.Type.OBJECT,
                    properties={"ad": types.Schema(type=types.Type.STRING, enum=list(JESTLER))},
                    required=["ad"],
                ),
                behavior=types.Behavior.NON_BLOCKING,
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


def sessiz_yanit(cagri: types.FunctionCall, sonuc: dict | None = None) -> types.FunctionResponse:
    """Modelin konuşmasını bölmeyen (SILENT) fonksiyon yanıtı."""
    return types.FunctionResponse(
        id=cagri.id,
        name=cagri.name,
        response=sonuc or {"tamam": True},
        scheduling=types.FunctionResponseScheduling.SILENT,
    )
