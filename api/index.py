from fastapi import FastAPI, File, UploadFile, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
import pdfplumber
import io
import re
import os

HTML_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "public", "index.html")

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

COLUMN_KEYWORDS = {
    "код": ["код", "арт", "артикул", "номер", "№", "поз."],
    "наименование": [
        "наименование", "материал", "описание", "позиция",
        "товар", "номенклатура", "наименование и характеристика",
    ],
    "количество": ["количество", "кол-во", "кол.", "объем", "объём", "кол"],
    "производитель": ["производитель", "изготовитель", "завод"],
    "бренд": ["бренд", "марка", "торговая марка", "торговое наименование", "тм"],
    "единица": ["ед.", "ед.изм", "е.и.", "единица измерения", "единица"],
}


def normalize(text: str) -> str:
    return re.sub(r"\s+", " ", str(text).lower().strip())


def match_column(header: str, keywords: list) -> bool:
    h = normalize(header)
    return any(kw in h for kw in keywords)


def identify_columns(headers: list) -> dict:
    mapping = {}
    for i, header in enumerate(headers):
        for col_name, keywords in COLUMN_KEYWORDS.items():
            if col_name not in mapping and match_column(header, keywords):
                mapping[col_name] = i
                break
    return mapping


def score_table(headers: list) -> int:
    score = 0
    for col_name, keywords in COLUMN_KEYWORDS.items():
        for header in headers:
            if match_column(header, keywords):
                score += 1
                break
    return score


@app.post("/api/analyze")
async def analyze_pdf(file: UploadFile = File(...)):
    if not file.filename.lower().endswith(".pdf"):
        raise HTTPException(status_code=400, detail="Файл должен быть в формате PDF")

    content = await file.read()
    if len(content) > 20 * 1024 * 1024:
        raise HTTPException(status_code=400, detail="Файл слишком большой (максимум 20 МБ)")

    best_table = None
    best_score = -1
    best_mapping = {}

    try:
        with pdfplumber.open(io.BytesIO(content)) as pdf:
            for page in pdf.pages:
                tables = page.extract_tables()
                for table in tables:
                    if not table or len(table) < 2:
                        continue
                    # Try first two rows as potential headers
                    for header_row_idx in range(min(2, len(table))):
                        headers = [str(cell or "") for cell in table[header_row_idx]]
                        score = score_table(headers)
                        if score > best_score:
                            best_score = score
                            best_table = table
                            best_mapping = identify_columns(headers)
                            # data starts after header row
                            best_mapping["_header_row"] = header_row_idx
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Ошибка обработки PDF: {str(e)}")

    if best_table is None or best_score == 0:
        raise HTTPException(
            status_code=404,
            detail="Таблица с материалами не найдена. Убедитесь, что PDF содержит спецификацию с таблицей материалов.",
        )

    header_row = best_mapping.pop("_header_row", 0)
    results = []

    for row in best_table[header_row + 1:]:
        if not row or not any(row):
            continue

        def get(col: str) -> str:
            idx = best_mapping.get(col)
            if idx is None or idx >= len(row):
                return ""
            return str(row[idx] or "").strip()

        item = {
            "код": get("код"),
            "наименование": get("наименование"),
            "количество": get("количество"),
            "единица": get("единица"),
            "производитель": get("производитель"),
            "бренд": get("бренд"),
        }
        if item["наименование"]:
            results.append(item)

    if not results:
        raise HTTPException(
            status_code=404,
            detail="Таблица найдена, но строки с данными не обнаружены.",
        )

    return {"items": results, "total": len(results)}


@app.get("/")
async def root():
    return FileResponse(HTML_PATH)
