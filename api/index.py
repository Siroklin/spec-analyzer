from fastapi import FastAPI, File, UploadFile, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse
import pdfplumber
import io
import re

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

HTML = """<!DOCTYPE html>
<html lang="ru">
<head>
  <meta charset="UTF-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1.0" />
  <title>Анализатор спецификаций</title>
  <style>
    *, *::before, *::after { box-sizing: border-box; margin: 0; padding: 0; }
    body {
      font-family: 'Segoe UI', Arial, sans-serif;
      background: #f0f4f8;
      min-height: 100vh;
      display: flex;
      flex-direction: column;
      align-items: center;
      padding: 48px 16px 64px;
      color: #1e293b;
    }
    h1 {
      font-size: 2rem;
      font-weight: 700;
      color: #1e293b;
      margin-bottom: 40px;
      text-align: center;
      letter-spacing: -0.5px;
    }
    .card {
      background: #fff;
      border-radius: 16px;
      box-shadow: 0 4px 24px rgba(0,0,0,0.08);
      padding: 40px 48px;
      width: 100%;
      max-width: 520px;
      display: flex;
      flex-direction: column;
      align-items: center;
      gap: 24px;
    }
    .upload-area {
      width: 100%;
      border: 2px dashed #cbd5e1;
      border-radius: 12px;
      padding: 32px 24px;
      text-align: center;
      cursor: pointer;
      transition: border-color 0.2s, background 0.2s;
      position: relative;
    }
    .upload-area:hover, .upload-area.drag-over { border-color: #3b82f6; background: #eff6ff; }
    .upload-area.has-file { border-color: #22c55e; background: #f0fdf4; }
    .upload-icon { font-size: 2.5rem; margin-bottom: 12px; display: block; }
    .upload-hint { color: #64748b; font-size: 0.95rem; line-height: 1.5; }
    .upload-hint strong { display: block; color: #1e293b; font-size: 1rem; margin-bottom: 4px; }
    .file-name { margin-top: 10px; font-size: 0.875rem; color: #16a34a; font-weight: 600; word-break: break-all; }
    input[type="file"] { position: absolute; inset: 0; opacity: 0; cursor: pointer; width: 100%; height: 100%; }
    .btn {
      width: 100%;
      padding: 14px;
      background: #3b82f6;
      color: #fff;
      border: none;
      border-radius: 10px;
      font-size: 1.05rem;
      font-weight: 600;
      cursor: pointer;
      transition: background 0.2s, transform 0.1s;
    }
    .btn:hover:not(:disabled) { background: #2563eb; }
    .btn:active:not(:disabled) { transform: scale(0.98); }
    .btn:disabled { background: #94a3b8; cursor: not-allowed; }
    .spinner {
      display: none;
      width: 40px; height: 40px;
      border: 4px solid #e2e8f0;
      border-top-color: #3b82f6;
      border-radius: 50%;
      animation: spin 0.8s linear infinite;
    }
    @keyframes spin { to { transform: rotate(360deg); } }
    .error-msg {
      display: none;
      background: #fef2f2;
      border: 1px solid #fca5a5;
      color: #dc2626;
      border-radius: 8px;
      padding: 12px 16px;
      font-size: 0.9rem;
      width: 100%;
      text-align: center;
    }
    #results { display: none; width: 100%; max-width: 1100px; margin-top: 40px; }
    #results h2 { font-size: 1.3rem; font-weight: 600; margin-bottom: 16px; color: #1e293b; }
    #results .count { font-size: 0.875rem; color: #64748b; margin-left: 8px; }
    .table-wrap { overflow-x: auto; border-radius: 12px; box-shadow: 0 2px 12px rgba(0,0,0,0.07); }
    table { width: 100%; border-collapse: collapse; background: #fff; font-size: 0.9rem; }
    thead tr { background: #1e293b; color: #fff; }
    th { padding: 12px 16px; text-align: left; font-weight: 600; white-space: nowrap; }
    td { padding: 10px 16px; border-bottom: 1px solid #f1f5f9; color: #334155; vertical-align: top; }
    tbody tr:hover { background: #f8fafc; }
    tbody tr:last-child td { border-bottom: none; }
    td:first-child { font-family: monospace; color: #64748b; font-size: 0.85rem; }
    .empty-cell { color: #cbd5e1; font-style: italic; }
  </style>
</head>
<body>
  <h1>Анализатор спецификаций</h1>
  <div class="card">
    <div class="upload-area" id="uploadArea">
      <input type="file" id="fileInput" accept=".pdf" required />
      <span class="upload-icon">📄</span>
      <div class="upload-hint">
        <strong>Укажите строительную спецификацию в формате PDF</strong>
        Нажмите или перетащите файл сюда
      </div>
      <div class="file-name" id="fileName"></div>
    </div>
    <div class="error-msg" id="errorMsg"></div>
    <div class="spinner" id="spinner"></div>
    <button class="btn" id="analyzeBtn" disabled>Анализировать</button>
  </div>

  <div id="results">
    <h2>Найденные материалы <span class="count" id="countLabel"></span></h2>
    <div class="table-wrap">
      <table>
        <thead>
          <tr>
            <th>Код</th>
            <th>Наименование и характеристики</th>
            <th>Тип / Марка</th>
            <th>Изготовитель</th>
            <th>Ед. изм.</th>
            <th>Количество</th>
            <th>Комментарий</th>
          </tr>
        </thead>
        <tbody id="tableBody"></tbody>
      </table>
    </div>
  </div>

  <script>
    const fileInput  = document.getElementById('fileInput');
    const fileName   = document.getElementById('fileName');
    const uploadArea = document.getElementById('uploadArea');
    const analyzeBtn = document.getElementById('analyzeBtn');
    const spinner    = document.getElementById('spinner');
    const errorMsg   = document.getElementById('errorMsg');
    const results    = document.getElementById('results');
    const tableBody  = document.getElementById('tableBody');
    const countLabel = document.getElementById('countLabel');

    fileInput.addEventListener('change', () => {
      const file = fileInput.files[0];
      if (file) {
        fileName.textContent = file.name;
        uploadArea.classList.add('has-file');
        analyzeBtn.disabled = false;
        hideError();
        results.style.display = 'none';
      }
    });

    uploadArea.addEventListener('dragover', e => { e.preventDefault(); uploadArea.classList.add('drag-over'); });
    uploadArea.addEventListener('dragleave', () => uploadArea.classList.remove('drag-over'));
    uploadArea.addEventListener('drop', e => {
      e.preventDefault();
      uploadArea.classList.remove('drag-over');
      const file = e.dataTransfer.files[0];
      if (file && file.name.toLowerCase().endsWith('.pdf')) {
        fileInput.files = e.dataTransfer.files;
        fileName.textContent = file.name;
        uploadArea.classList.add('has-file');
        analyzeBtn.disabled = false;
        hideError();
        results.style.display = 'none';
      }
    });

    analyzeBtn.addEventListener('click', async () => {
      const file = fileInput.files[0];
      if (!file) { showError('Пожалуйста, выберите PDF файл'); return; }
      hideError();
      setLoading(true);
      const formData = new FormData();
      formData.append('file', file);
      try {
        const resp = await fetch('/api/analyze', { method: 'POST', body: formData });
        const data = await resp.json();
        if (!resp.ok) { showError(data.detail || 'Ошибка сервера'); return; }
        renderTable(data.items);
        countLabel.textContent = '(' + data.total + ' позиций)';
        results.style.display = 'block';
        results.scrollIntoView({ behavior: 'smooth', block: 'start' });
      } catch (err) {
        showError('Не удалось связаться с сервером. Попробуйте позже.');
      } finally {
        setLoading(false);
      }
    });

    function renderTable(items) {
      tableBody.innerHTML = '';
      items.forEach(item => {
        const tr = document.createElement('tr');
        ['код', 'наименование', 'тип', 'изготовитель', 'единица', 'количество', 'комментарий'].forEach(col => {
          const td = document.createElement('td');
          const val = item[col];
          if (val) { td.textContent = val; } else { td.textContent = '—'; td.classList.add('empty-cell'); }
          tr.appendChild(td);
        });
        tableBody.appendChild(tr);
      });
    }

    function setLoading(on) {
      analyzeBtn.disabled = on;
      spinner.style.display = on ? 'block' : 'none';
      analyzeBtn.textContent = on ? 'Анализирую...' : 'Анализировать';
    }
    function showError(msg) { errorMsg.textContent = msg; errorMsg.style.display = 'block'; }
    function hideError() { errorMsg.style.display = 'none'; }
  </script>
</body>
</html>"""


COLUMN_KEYWORDS = {
    "наименование": [
        "наименование и техническая характеристика",
        "наименование и технические характеристики",
        "наименование",
        "технические характеристики",
        "характеристика",
        "описание",
        "материал",
    ],
    "тип": [
        "тип марка обозначение документа",
        "тип марка обозначение",
        "тип марка",
        "обозначение документа",
        "опросного листа",
        "тип",
        "марка",
    ],
    "код": [
        "код оборудования изделия материала",
        "код оборудования",
        "код изделия",
        "код материала",
        "код",
        "артикул",
        "номер",
    ],
    "изготовитель": [
        "завод изготовитель",
        "изготовитель",
        "производитель",
        "завод",
    ],
    "единица": [
        "единица измерения",
        "единица",
        "ед изм",
        "ед",
    ],
    "количество": [
        "количество",
        "кол во",
        "кол",
        "объем",
        "объём",
    ],
    "комментарий": [
        "примечание",
        "комментарий",
        "прим",
        "заметки",
    ],
}

MIN_SCORE = 0.35
REQUIRED_COLUMNS = {"наименование", "единица"}


def normalize(text: str) -> str:
    text = str(text).lower().strip()
    # "Коли-\nчество" → "количество" (мягкий перенос строки через дефис)
    text = re.sub(r"-\s*\n\s*", "", text)
    # остальные дефисы и знаки препинания → пробел
    text = re.sub(r"[-,;/\\]+", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def tokenize(text: str) -> set:
    return set(re.findall(r"[а-яёa-z0-9]+", normalize(text)))


def col_score(header: str, keywords: list) -> float:
    h_norm = normalize(header)
    h_tokens = tokenize(header)
    best = 0.0
    for kw in keywords:
        kw_norm = normalize(kw)
        kw_tokens = tokenize(kw)
        if not kw_tokens:
            continue
        if kw_norm in h_norm:
            score = len(kw_tokens) + 1.0  # бонус за точное вхождение фразы
        else:
            overlap = len(kw_tokens & h_tokens)
            score = overlap / len(kw_tokens)
        best = max(best, score)
    return best


def identify_columns(headers: list) -> dict:
    candidates = []
    for i, header in enumerate(headers):
        for col_name, keywords in COLUMN_KEYWORDS.items():
            score = col_score(header, keywords)
            if score >= MIN_SCORE:
                candidates.append((score, col_name, i))

    candidates.sort(reverse=True)
    assigned_cols: set = set()
    assigned_idxs: set = set()
    mapping: dict = {}

    for score, col_name, idx in candidates:
        if col_name not in assigned_cols and idx not in assigned_idxs:
            mapping[col_name] = idx
            assigned_cols.add(col_name)
            assigned_idxs.add(idx)

    return mapping


def is_valid_table(headers: list) -> bool:
    mapping = identify_columns(headers)
    return REQUIRED_COLUMNS.issubset(mapping.keys())


def is_numbering_row(row: list) -> bool:
    """Строка-нумерация колонок вида [None, None, '1', '2', '3', ...]"""
    values = [str(c or "").strip() for c in row if str(c or "").strip()]
    return bool(values) and all(re.fullmatch(r"\d{1,2}", v) for v in values)


def extract_row(row: list, mapping: dict) -> dict:
    def get(col: str) -> str:
        idx = mapping.get(col)
        if idx is None or idx >= len(row):
            return ""
        return re.sub(r"\s+", " ", str(row[idx] or "")).strip()

    return {
        "код": get("код"),
        "наименование": get("наименование"),
        "тип": get("тип"),
        "изготовитель": get("изготовитель"),
        "единица": get("единица"),
        "количество": get("количество"),
        "комментарий": get("комментарий"),
    }


@app.get("/")
async def root():
    return HTMLResponse(HTML)


@app.post("/api/analyze")
async def analyze_pdf(file: UploadFile = File(...)):
    if not file.filename.lower().endswith(".pdf"):
        raise HTTPException(status_code=400, detail="Файл должен быть в формате PDF")

    content = await file.read()
    if len(content) > 20 * 1024 * 1024:
        raise HTTPException(status_code=400, detail="Файл слишком большой (максимум 20 МБ)")

    results = []

    try:
        with pdfplumber.open(io.BytesIO(content)) as pdf:
            for page in pdf.pages:
                for table in (page.extract_tables() or []):
                    if not table or len(table) < 3:
                        continue

                    headers = [str(cell or "") for cell in table[0]]
                    if not is_valid_table(headers):
                        continue

                    mapping = identify_columns(headers)

                    # пропускаем строку-нумерацию вида '1', '2', '3'...
                    start = 2 if len(table) > 1 and is_numbering_row(table[1]) else 1

                    for row in table[start:]:
                        if not row or not any(row):
                            continue
                        item = extract_row(row, mapping)
                        if item["наименование"] or item["код"]:
                            results.append(item)

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Ошибка обработки PDF: {str(e)}")

    if not results:
        raise HTTPException(
            status_code=404,
            detail="Таблица с материалами не найдена. Убедитесь, что PDF содержит спецификацию.",
        )

    return {"items": results, "total": len(results)}
