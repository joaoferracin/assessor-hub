"""
AssessorHub — Atualizador Diário
Busca dados reais de mercado e gera o HTML atualizado.
APIs usadas (todas gratuitas):
  - brapi.dev     → cotações B3, dólar, Selic/CDI
  - newsdata.io   → notícias financeiras em português
"""

import json
import urllib.request
import urllib.parse
from datetime import datetime, timedelta
import os
import locale

# ── Configuração ──────────────────────────────────────────────────────────────
BRAPI_TOKEN   = os.environ.get("BRAPI_TOKEN", "")       # cadastre em brapi.dev (grátis)
NEWS_API_KEY  = os.environ.get("NEWS_API_KEY", "")      # cadastre em newsdata.io (grátis)
TICKERS       = ["PETR4", "VALE3", "ITUB4", "BBDC4", "WEGE3", "ABEV3"]

# ── Helpers ───────────────────────────────────────────────────────────────────
def fetch(url, headers=None):
    req = urllib.request.Request(url, headers=headers or {})
    try:
        with urllib.request.urlopen(req, timeout=10) as r:
            return json.loads(r.read().decode())
    except Exception as e:
        print(f"  [WARN] fetch falhou: {url[:80]}… → {e}")
        return {}

def fmt_brl(value):
    """Formata número como R$ brasileiro."""
    return f"{value:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")

def fmt_pct(value, decimals=2):
    sign = "+" if value >= 0 else ""
    return f"{sign}{value:.{decimals}f}%"

# ── 1. Cotações via Brapi ─────────────────────────────────────────────────────
def get_quotes():
    tickers_str = ",".join(TICKERS)
    url = f"https://brapi.dev/api/quote/{tickers_str}?token={BRAPI_TOKEN}&range=1mo&interval=1d"
    data = fetch(url)
    results = data.get("results", [])
    quotes = []
    for r in results:
        quotes.append({
            "ticker":   r.get("symbol", "—"),
            "name":     r.get("shortName", r.get("longName", "—"))[:28],
            "price":    r.get("regularMarketPrice", 0),
            "change":   r.get("regularMarketChangePercent", 0),
            "history":  [h.get("close", 0) for h in r.get("historicalDataPrice", [])][-30:],
        })
    return quotes

# ── 2. Ibovespa ───────────────────────────────────────────────────────────────
def get_ibov():
    url = f"https://brapi.dev/api/quote/%5EBVSP?token={BRAPI_TOKEN}&range=1mo&interval=1d"
    data = fetch(url)
    results = data.get("results", [{}])
    r = results[0] if results else {}
    history = [h.get("close", 0) for h in r.get("historicalDataPrice", [])][-30:]
    return {
        "value":   r.get("regularMarketPrice", 0),
        "change":  r.get("regularMarketChangePercent", 0),
        "history": history,
    }

# ── 3. Dólar ─────────────────────────────────────────────────────────────────
def get_dollar():
    url = f"https://brapi.dev/api/v2/currency?currency=USD-BRL&token={BRAPI_TOKEN}"
    data = fetch(url)
    currencies = data.get("currency", [{}])
    r = currencies[0] if currencies else {}
    return {
        "value":  float(r.get("bidPrice", 0) or 0),
        "change": float(r.get("pctChange", 0) or 0),
    }

# ── 4. Selic / CDI ────────────────────────────────────────────────────────────
def get_selic():
    # Banco Central API pública (sem token)
    url = "https://api.bcb.gov.br/dados/serie/bcdata.sgs.432/dados/ultimos/1?formato=json"
    data = fetch(url)
    if isinstance(data, list) and data:
        selic = float(data[0].get("valor", 0))
        return {"selic": selic, "cdi": round(selic - 0.10, 2)}
    return {"selic": 0, "cdi": 0}

# ── 5. Notícias ───────────────────────────────────────────────────────────────
def get_news():
    yesterday = (datetime.now() - timedelta(days=1)).strftime("%Y-%m-%d")
    url = (
        f"https://newsdata.io/api/1/news"
        f"?apikey={NEWS_API_KEY}"
        f"&q=mercado+financeiro+OR+bolsa+OR+selic+OR+ibovespa"
        f"&country=br&language=pt"
        f"&from_date={yesterday}"
        f"&category=business"
    )
    data = fetch(url)
    articles = data.get("results", [])[:6]
    news = []
    for a in articles:
        # Detectar impacto por palavras-chave no título
        title = (a.get("title") or "").lower()
        pos_words = ["alta", "sobe", "valoriza", "lucro", "aprovação", "crescimento", "recorde"]
        neg_words = ["queda", "cai", "recuo", "perde", "risco", "inflação", "crise", "tensão"]
        impact = "neu"
        if any(w in title for w in pos_words): impact = "pos"
        if any(w in title for w in neg_words): impact = "neg"

        # Categoria
        keywords = (a.get("keywords") or [])
        cat = "macro"
        if any(k in str(keywords).lower() for k in ["ação","ações","bolsa","ibovespa"]): cat = "acoes"
        elif any(k in str(keywords).lower() for k in ["câmbio","dólar","real"]): cat = "cambio"
        elif any(k in str(keywords).lower() for k in ["selic","cdi","tesouro","renda fixa"]): cat = "renda-fixa"

        news.append({
            "src":     (a.get("source_name") or "—")[:20],
            "title":   (a.get("title") or "Sem título")[:90],
            "summary": (a.get("description") or "")[:160],
            "time":    (a.get("pubDate") or "")[:16].replace("T", " · "),
            "impact":  impact,
            "cat":     cat,
            "url":     a.get("link", "#"),
        })
    return news

# ── 6. Gera o HTML ────────────────────────────────────────────────────────────
def generate_html(ibov, dollar, selic_data, quotes, news):
    today = datetime.now()
    date_str = today.strftime("%a, %d/%m/%Y · %H:%M")

    # KPIs
    ibov_val   = fmt_brl(ibov["value"])
    ibov_chg   = fmt_pct(ibov["change"])
    ibov_color = "var(--green)" if ibov["change"] >= 0 else "var(--red)"
    ibov_arrow = "▲" if ibov["change"] >= 0 else "▼"

    dol_val    = fmt_brl(dollar["value"])
    dol_chg    = fmt_pct(dollar["change"])
    dol_color  = "var(--red)" if dollar["change"] >= 0 else "var(--green)"  # dólar subindo = ruim para bolsa
    dol_arrow  = "▲" if dollar["change"] >= 0 else "▼"

    selic_val  = f"{selic_data['selic']:.2f}%".replace(".", ",")
    cdi_val    = f"{selic_data['cdi']:.2f}%".replace(".", ",")

    # Histórico Ibovespa → pontos SVG
    hist = ibov["history"]
    hist_js = json.dumps(hist)

    # Quotes para tabela
    rows_html = ""
    for q in quotes[:6]:
        pos = q["change"] >= 0
        arrow = "▲" if pos else "▼"
        cls = "pos-bg" if pos else "neg-bg"
        color_cls = "pos" if pos else "neg"
        rows_html += f"""<tr>
            <td><div class="ticker-name">{q['ticker']}</div><div class="ticker-full">{q['name']}</div></td>
            <td style="font-family:'DM Mono',monospace">R$ {fmt_brl(q['price'])}</td>
            <td><span class="badge {cls}">{arrow} {abs(q['change']):.2f}%</span></td>
        </tr>"""

    # Notícias
    news_js = json.dumps(news, ensure_ascii=False)

    html = f"""<!DOCTYPE html>
<html lang="pt-BR">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>AssessorHub — {today.strftime('%d/%m/%Y')}</title>
<link href="https://fonts.googleapis.com/css2?family=Playfair+Display:wght@400;700&family=DM+Sans:wght@300;400;500;600&family=DM+Mono:wght@400;500&display=swap" rel="stylesheet">
<style>
  :root {{
    --bg:#0a0e17;--surface:#111827;--surface2:#1a2235;--border:#1e2d42;
    --gold:#c9a84c;--gold-light:#e8c97a;--green:#2ecc8f;--red:#e05252;
    --blue:#4a9eff;--text:#e8eaf0;--muted:#6b7a99;
  }}
  *{{margin:0;padding:0;box-sizing:border-box;}}
  body{{font-family:'DM Sans',sans-serif;background:var(--bg);color:var(--text);min-height:100vh;overflow-x:hidden;}}
  body::before{{content:'';position:fixed;inset:0;background:radial-gradient(ellipse 60% 40% at 80% 10%,rgba(201,168,76,.06) 0%,transparent 60%),radial-gradient(ellipse 40% 60% at 10% 80%,rgba(74,158,255,.04) 0%,transparent 60%);pointer-events:none;z-index:0;}}
  .wrapper{{position:relative;z-index:1;}}
  header{{display:flex;align-items:center;justify-content:space-between;padding:20px 36px;border-bottom:1px solid var(--border);background:rgba(10,14,23,.9);backdrop-filter:blur(12px);position:sticky;top:0;z-index:100;}}
  .logo{{display:flex;align-items:center;gap:12px;}}
  .logo-icon{{width:38px;height:38px;background:linear-gradient(135deg,var(--gold),var(--gold-light));border-radius:10px;display:flex;align-items:center;justify-content:center;font-size:18px;}}
  .logo-text{{font-family:'Playfair Display',serif;font-size:1.3rem;color:var(--gold-light);letter-spacing:.02em;}}
  .logo-sub{{font-size:.7rem;color:var(--muted);letter-spacing:.12em;text-transform:uppercase;margin-top:1px;}}
  .date-pill{{background:var(--surface2);border:1px solid var(--border);padding:6px 14px;border-radius:20px;font-size:.78rem;color:var(--muted);font-family:'DM Mono',monospace;}}
  .pulse{{display:inline-block;width:7px;height:7px;background:var(--green);border-radius:50%;margin-right:6px;animation:pulse 2s infinite;}}
  @keyframes pulse{{0%,100%{{opacity:1;transform:scale(1)}}50%{{opacity:.5;transform:scale(.8)}}}}
  .tab-nav{{display:flex;gap:4px;padding:16px 36px 0;border-bottom:1px solid var(--border);}}
  .tab-btn{{padding:10px 20px;border:none;background:transparent;color:var(--muted);font-family:'DM Sans',sans-serif;font-size:.85rem;font-weight:500;cursor:pointer;border-bottom:2px solid transparent;transition:all .2s;letter-spacing:.04em;text-transform:uppercase;display:flex;align-items:center;gap:7px;}}
  .tab-btn:hover{{color:var(--text);}}
  .tab-btn.active{{color:var(--gold);border-bottom-color:var(--gold);}}
  .tab-panel{{display:none;padding:30px 36px 40px;}}
  .tab-panel.active{{display:block;animation:fadeIn .3s ease;}}
  @keyframes fadeIn{{from{{opacity:0;transform:translateY(10px)}}to{{opacity:1;transform:translateY(0)}}}}
  .kpi-row{{display:grid;grid-template-columns:repeat(4,1fr);gap:16px;margin-bottom:28px;}}
  .kpi-card{{background:var(--surface);border:1px solid var(--border);border-radius:14px;padding:20px 22px;position:relative;overflow:hidden;transition:border-color .2s;}}
  .kpi-card:hover{{border-color:rgba(201,168,76,.3);}}
  .kpi-card::before{{content:'';position:absolute;top:0;left:0;right:0;height:2px;}}
  .kpi-card.gold::before{{background:linear-gradient(90deg,var(--gold),transparent);}}
  .kpi-card.green::before{{background:linear-gradient(90deg,var(--green),transparent);}}
  .kpi-card.red::before{{background:linear-gradient(90deg,var(--red),transparent);}}
  .kpi-card.blue::before{{background:linear-gradient(90deg,var(--blue),transparent);}}
  .kpi-label{{font-size:.72rem;color:var(--muted);text-transform:uppercase;letter-spacing:.1em;margin-bottom:10px;}}
  .kpi-value{{font-family:'DM Mono',monospace;font-size:1.6rem;font-weight:500;margin-bottom:6px;}}
  .kpi-change{{font-size:.78rem;font-family:'DM Mono',monospace;}}
  .pos{{color:var(--green);}} .neg{{color:var(--red);}}
  .dashboard-grid{{display:grid;grid-template-columns:1fr 380px;gap:20px;}}
  .card{{background:var(--surface);border:1px solid var(--border);border-radius:14px;overflow:hidden;}}
  .card-header{{padding:18px 22px;border-bottom:1px solid var(--border);display:flex;align-items:center;justify-content:space-between;}}
  .card-title{{font-family:'Playfair Display',serif;font-size:1rem;color:var(--gold-light);}}
  .card-body{{padding:22px;}}
  .market-table{{width:100%;border-collapse:collapse;}}
  .market-table th{{text-align:left;font-size:.7rem;text-transform:uppercase;letter-spacing:.08em;color:var(--muted);padding:6px 10px;border-bottom:1px solid var(--border);}}
  .market-table td{{padding:11px 10px;font-size:.85rem;border-bottom:1px solid rgba(30,45,66,.5);font-family:'DM Mono',monospace;}}
  .market-table tr:last-child td{{border-bottom:none;}}
  .ticker-name{{font-family:'DM Sans',sans-serif;font-weight:600;color:var(--text);}}
  .ticker-full{{font-size:.72rem;color:var(--muted);font-family:'DM Sans',sans-serif;margin-top:1px;}}
  .badge{{display:inline-block;padding:2px 8px;border-radius:6px;font-size:.75rem;}}
  .pos-bg{{background:rgba(46,204,143,.12);color:var(--green);}}
  .neg-bg{{background:rgba(224,82,82,.12);color:var(--red);}}
  /* MENSAGENS */
  .msg-layout{{display:grid;grid-template-columns:300px 1fr;gap:20px;height:620px;}}
  .msg-sidebar{{background:var(--surface);border:1px solid var(--border);border-radius:14px;overflow:hidden;display:flex;flex-direction:column;}}
  .msg-sidebar-title{{padding:16px 18px;font-size:.75rem;text-transform:uppercase;letter-spacing:.1em;color:var(--muted);border-bottom:1px solid var(--border);}}
  .template-list{{overflow-y:auto;flex:1;}}
  .template-item{{padding:14px 18px;cursor:pointer;border-bottom:1px solid rgba(30,45,66,.4);transition:background .15s;}}
  .template-item:hover,.template-item.active{{background:var(--surface2);}}
  .template-item.active{{border-left:2px solid var(--gold);}}
  .template-tag{{font-size:.68rem;text-transform:uppercase;letter-spacing:.08em;color:var(--gold);margin-bottom:4px;}}
  .template-name{{font-size:.85rem;font-weight:500;color:var(--text);}}
  .msg-main{{background:var(--surface);border:1px solid var(--border);border-radius:14px;display:flex;flex-direction:column;overflow:hidden;}}
  .msg-header{{padding:16px 22px;border-bottom:1px solid var(--border);display:flex;align-items:center;justify-content:space-between;}}
  .msg-header-title{{font-size:.9rem;font-weight:600;color:var(--gold-light);}}
  .tag-row{{display:flex;gap:8px;flex-wrap:wrap;padding:14px 22px;border-bottom:1px solid var(--border);}}
  .tag{{padding:4px 12px;border-radius:20px;font-size:.72rem;border:1px solid var(--border);color:var(--muted);cursor:pointer;transition:all .15s;}}
  .tag.active{{border-color:var(--gold);color:var(--gold);background:rgba(201,168,76,.06);}}
  .msg-editor{{flex:1;padding:22px;display:flex;flex-direction:column;gap:16px;}}
  .msg-textarea{{flex:1;background:var(--surface2);border:1px solid var(--border);border-radius:10px;padding:16px;color:var(--text);font-family:'DM Sans',sans-serif;font-size:.9rem;line-height:1.65;resize:none;outline:none;transition:border-color .2s;}}
  .msg-textarea:focus{{border-color:rgba(201,168,76,.4);}}
  .btn{{padding:10px 20px;border-radius:9px;font-family:'DM Sans',sans-serif;font-size:.83rem;font-weight:500;cursor:pointer;border:none;transition:all .2s;display:flex;align-items:center;gap:7px;}}
  .btn-gold{{background:linear-gradient(135deg,var(--gold),#a8832c);color:#0a0e17;font-weight:600;}}
  .btn-gold:hover{{filter:brightness(1.1);transform:translateY(-1px);}}
  .btn-outline{{background:transparent;border:1px solid var(--border);color:var(--muted);}}
  .btn-outline:hover{{border-color:var(--gold);color:var(--gold);}}
  .copied-toast{{background:var(--green);color:#0a0e17;padding:6px 14px;border-radius:8px;font-size:.8rem;font-weight:600;opacity:0;transition:opacity .3s;pointer-events:none;}}
  .copied-toast.show{{opacity:1;}}
  .var-chip{{display:inline-flex;align-items:center;gap:4px;background:rgba(74,158,255,.1);border:1px solid rgba(74,158,255,.3);color:var(--blue);padding:2px 8px;border-radius:5px;font-size:.75rem;font-family:'DM Mono',monospace;cursor:pointer;transition:background .15s;}}
  .var-chip:hover{{background:rgba(74,158,255,.2);}}
  .vars-row{{display:flex;gap:8px;padding:0 22px 14px;flex-wrap:wrap;}}
  .vars-label{{font-size:.7rem;color:var(--muted);text-transform:uppercase;letter-spacing:.08em;padding:0 22px;margin-bottom:6px;}}
  /* GRÁFICOS */
  .charts-grid{{display:grid;grid-template-columns:repeat(2,1fr);gap:20px;}}
  .chart-full{{grid-column:span 2;}}
  select.styled{{background:var(--surface2);border:1px solid var(--border);color:var(--text);padding:6px 12px;border-radius:8px;font-family:'DM Sans',sans-serif;font-size:.8rem;outline:none;cursor:pointer;}}
  /* NOTÍCIAS */
  .news-grid{{display:grid;grid-template-columns:repeat(3,1fr);gap:18px;}}
  .news-card{{background:var(--surface);border:1px solid var(--border);border-radius:14px;padding:20px;cursor:pointer;transition:all .2s;}}
  .news-card:hover{{border-color:rgba(201,168,76,.3);transform:translateY(-2px);}}
  .news-source{{font-size:.68rem;text-transform:uppercase;letter-spacing:.1em;margin-bottom:10px;font-weight:600;}}
  .news-title{{font-size:.92rem;font-weight:600;line-height:1.4;margin-bottom:10px;color:var(--text);}}
  .news-summary{{font-size:.8rem;color:var(--muted);line-height:1.5;margin-bottom:14px;}}
  .news-footer{{display:flex;align-items:center;justify-content:space-between;font-size:.72rem;color:var(--muted);}}
  .news-impact{{display:flex;align-items:center;gap:5px;font-size:.72rem;font-weight:600;padding:2px 8px;border-radius:5px;}}
  .impact-pos{{background:rgba(46,204,143,.1);color:var(--green);}}
  .impact-neg{{background:rgba(224,82,82,.1);color:var(--red);}}
  .impact-neu{{background:rgba(107,122,153,.15);color:var(--muted);}}
  .news-filter-row{{display:flex;gap:10px;margin-bottom:22px;flex-wrap:wrap;}}
  .filter-btn{{padding:7px 16px;border-radius:20px;border:1px solid var(--border);background:transparent;color:var(--muted);font-family:'DM Sans',sans-serif;font-size:.78rem;cursor:pointer;transition:all .15s;}}
  .filter-btn:hover,.filter-btn.active{{background:rgba(201,168,76,.1);border-color:var(--gold);color:var(--gold);}}
  /* PLANILHA */
  .sheet-toolbar{{display:flex;gap:10px;margin-bottom:18px;align-items:center;flex-wrap:wrap;}}
  .sheet-title-input{{background:var(--surface2);border:1px solid var(--border);color:var(--text);padding:8px 14px;border-radius:8px;font-family:'Playfair Display',serif;font-size:1rem;outline:none;width:240px;}}
  .data-table-wrap{{background:var(--surface);border:1px solid var(--border);border-radius:14px;overflow:auto;}}
  table.data-table{{width:100%;border-collapse:collapse;font-size:.83rem;}}
  table.data-table th{{background:var(--surface2);padding:11px 14px;text-align:left;font-size:.7rem;text-transform:uppercase;letter-spacing:.08em;color:var(--muted);border-bottom:1px solid var(--border);white-space:nowrap;}}
  table.data-table td{{padding:10px 14px;border-bottom:1px solid rgba(30,45,66,.5);font-family:'DM Mono',monospace;font-size:.82rem;}}
  table.data-table tr:last-child td{{border-bottom:none;}}
  table.data-table td:first-child{{font-family:'DM Sans',sans-serif;font-weight:600;color:var(--text);}}
  table.data-table td[contenteditable]:focus{{outline:1px solid var(--gold);border-radius:3px;background:rgba(201,168,76,.05);}}
  .alloc-bar{{display:flex;height:8px;border-radius:4px;overflow:hidden;margin-top:12px;gap:2px;}}
  .alloc-seg{{height:100%;border-radius:2px;transition:flex .4s ease;}}
  ::-webkit-scrollbar{{width:5px;height:5px;}}
  ::-webkit-scrollbar-track{{background:transparent;}}
  ::-webkit-scrollbar-thumb{{background:var(--border);border-radius:4px;}}
  .msg-actions{{display:flex;gap:10px;align-items:center;}}
</style>
</head>
<body>
<div class="wrapper">

<header>
  <div class="logo">
    <div class="logo-icon">₿</div>
    <div>
      <div class="logo-text">AssessorHub</div>
      <div class="logo-sub">Painel do Assessor</div>
    </div>
  </div>
  <div style="display:flex;align-items:center;gap:20px;">
    <span class="date-pill">{date_str}</span>
    <span style="font-size:.75rem;color:var(--muted);display:flex;align-items:center;"><span class="pulse"></span>Atualizado hoje</span>
  </div>
</header>

<div class="tab-nav">
  <button class="tab-btn active" onclick="switchTab('dashboard',this)"><span>📊</span>Dashboard</button>
  <button class="tab-btn" onclick="switchTab('mensagens',this)"><span>💬</span>Mensagens WhatsApp</button>
  <button class="tab-btn" onclick="switchTab('graficos',this)"><span>📈</span>Gráficos</button>
  <button class="tab-btn" onclick="switchTab('noticias',this)"><span>📰</span>Notícias</button>
  <button class="tab-btn" onclick="switchTab('planilha',this)"><span>🗂️</span>Planilha</button>
</div>

<!-- DASHBOARD -->
<div id="tab-dashboard" class="tab-panel active">
  <div class="kpi-row">
    <div class="kpi-card gold">
      <div class="kpi-label">Ibovespa</div>
      <div class="kpi-value" style="color:var(--gold-light)">{ibov_val}</div>
      <div class="kpi-change" style="color:{ibov_color}">{ibov_arrow} {ibov_chg} ontem</div>
    </div>
    <div class="kpi-card green">
      <div class="kpi-label">Dólar (USD/BRL)</div>
      <div class="kpi-value">R$ {dol_val}</div>
      <div class="kpi-change" style="color:{dol_color}">{dol_arrow} {dol_chg}</div>
    </div>
    <div class="kpi-card blue">
      <div class="kpi-label">CDI (anual)</div>
      <div class="kpi-value">{cdi_val}</div>
      <div class="kpi-change" style="color:var(--muted)">→ Referência Selic</div>
    </div>
    <div class="kpi-card red">
      <div class="kpi-label">Selic Meta</div>
      <div class="kpi-value">{selic_val}</div>
      <div class="kpi-change" style="color:var(--muted)">Banco Central do Brasil</div>
    </div>
  </div>
  <div class="dashboard-grid">
    <div class="card">
      <div class="card-header">
        <span class="card-title">Ibovespa — Últimos 30 dias</span>
        <span style="font-size:.75rem;color:{ibov_color};font-family:'DM Mono',monospace">{ibov_arrow} {ibov_chg}</span>
      </div>
      <div class="card-body">
        <svg id="mainChart" viewBox="0 0 700 160" preserveAspectRatio="none" style="width:100%;height:160px;"></svg>
      </div>
    </div>
    <div class="card">
      <div class="card-header"><span class="card-title">Principais Ativos</span></div>
      <div class="card-body" style="padding:0">
        <table class="market-table">
          <thead><tr><th>Ativo</th><th>Preço</th><th>Var. Dia</th></tr></thead>
          <tbody>{rows_html}</tbody>
        </table>
      </div>
    </div>
  </div>
</div>

<!-- MENSAGENS -->
<div id="tab-mensagens" class="tab-panel">
  <div class="msg-layout">
    <div class="msg-sidebar">
      <div class="msg-sidebar-title">📁 Templates</div>
      <div class="template-list" id="templateList"></div>
    </div>
    <div class="msg-main">
      <div class="msg-header">
        <span class="msg-header-title" id="msgTitle">Relatório de Carteira</span>
        <div style="display:flex;gap:8px;align-items:center;">
          <span class="copied-toast" id="copiedToast">✓ Copiado!</span>
          <button class="btn btn-outline" onclick="clearMsg()">🗑 Limpar</button>
          <button class="btn btn-gold" onclick="copyMsg()">📋 Copiar mensagem</button>
        </div>
      </div>
      <div class="vars-label">Variáveis rápidas</div>
      <div class="vars-row" id="varsRow"></div>
      <div class="tag-row" id="tagRow"></div>
      <div class="msg-editor">
        <textarea class="msg-textarea" id="msgArea" rows="12"></textarea>
        <div class="msg-actions">
          <span style="font-size:.75rem;color:var(--muted)" id="charCount">0 caracteres</span>
        </div>
      </div>
    </div>
  </div>
</div>

<!-- GRÁFICOS -->
<div id="tab-graficos" class="tab-panel">
  <div style="display:flex;gap:12px;margin-bottom:22px;align-items:center;">
    <select class="styled" id="chartSelect"><option>Ibovespa (30d)</option></select>
    <button class="btn btn-outline" style="font-size:.78rem;" onclick="drawBigChart()">🔄 Atualizar</button>
  </div>
  <div class="charts-grid">
    <div class="card chart-full">
      <div class="card-header">
        <span class="card-title">Ibovespa — Últimos 30 dias (dados reais)</span>
        <span style="font-size:.75rem;color:var(--muted)">Fonte: brapi.dev</span>
      </div>
      <div class="card-body">
        <svg id="bigChart" viewBox="0 0 900 220" preserveAspectRatio="none" style="width:100%;height:220px;"></svg>
      </div>
    </div>
    <div class="card">
      <div class="card-header"><span class="card-title">Alocação por Classe</span></div>
      <div class="card-body">
        <svg id="pieChart" viewBox="0 0 200 200" style="width:200px;height:200px;display:block;margin:auto;"></svg>
        <div id="pieLegend" style="margin-top:16px;display:flex;flex-wrap:wrap;gap:10px;justify-content:center;font-size:.78rem;"></div>
      </div>
    </div>
    <div class="card">
      <div class="card-header"><span class="card-title">Rentabilidade Mensal — Ibovespa</span></div>
      <div class="card-body">
        <svg id="barChart" viewBox="0 0 400 160" style="width:100%;height:160px;"></svg>
      </div>
    </div>
  </div>
</div>

<!-- NOTÍCIAS -->
<div id="tab-noticias" class="tab-panel">
  <div class="news-filter-row">
    <button class="filter-btn active" onclick="filterNews('todos',this)">Todos</button>
    <button class="filter-btn" onclick="filterNews('macro',this)">Macro</button>
    <button class="filter-btn" onclick="filterNews('renda-fixa',this)">Renda Fixa</button>
    <button class="filter-btn" onclick="filterNews('acoes',this)">Ações</button>
    <button class="filter-btn" onclick="filterNews('cambio',this)">Câmbio</button>
  </div>
  <div class="news-grid" id="newsGrid"></div>
</div>

<!-- PLANILHA -->
<div id="tab-planilha" class="tab-panel">
  <div class="sheet-toolbar">
    <input class="sheet-title-input" value="Carteira do Cliente" id="sheetTitle">
    <button class="btn btn-outline" onclick="addRow()">＋ Adicionar ativo</button>
    <button class="btn btn-gold" onclick="exportSheet()">⬇ Exportar CSV</button>
    <span style="font-size:.78rem;color:var(--muted);margin-left:auto;">Clique nas células para editar</span>
  </div>
  <div class="data-table-wrap">
    <table class="data-table" id="sheetTable">
      <thead><tr><th>Ativo</th><th>Classe</th><th>Valor (R$)</th><th>Rentab. %</th><th>% Carteira</th><th>Venc./Prazo</th><th>Observação</th></tr></thead>
      <tbody id="sheetBody"></tbody>
    </table>
  </div>
  <div style="margin-top:20px;">
    <div style="font-size:.75rem;color:var(--muted);text-transform:uppercase;letter-spacing:.08em;margin-bottom:8px;">Alocação visual</div>
    <div class="alloc-bar" id="allocBar"></div>
    <div style="display:flex;gap:16px;margin-top:10px;flex-wrap:wrap;" id="allocLegend"></div>
  </div>
</div>

</div>

<script>
// Dados injetados pelo Python
const IBOV_HISTORY = {hist_js};
const NEWS_DATA    = {news_js};

// ── Tabs ──────────────────────────────────────────────────────────────────────
function switchTab(name,el){{
  document.querySelectorAll('.tab-panel').forEach(p=>p.classList.remove('active'));
  document.querySelectorAll('.tab-btn').forEach(b=>b.classList.remove('active'));
  document.getElementById('tab-'+name).classList.add('active');
  el.classList.add('active');
}}

// ── SVG helpers ───────────────────────────────────────────────────────────────
function pathFromPoints(pts,w,h,minV,maxV){{
  const xs=pts.map((_,i)=>i/(pts.length-1)*w);
  const ys=pts.map(v=>h-((v-minV)/(maxV-minV))*(h-20)-10);
  let d=`M${{xs[0]}},${{ys[0]}}`;
  for(let i=1;i<pts.length;i++) d+=` L${{xs[i]}},${{ys[i]}}`;
  return {{d,xs,ys}};
}}
function areaFromPoints(pts,w,h,minV,maxV){{
  const {{d,xs,ys}}=pathFromPoints(pts,w,h,minV,maxV);
  return d+` L${{xs[xs.length-1]}},${{h}} L${{xs[0]}},${{h}} Z`;
}}

// ── Mini chart dashboard ──────────────────────────────────────────────────────
function drawMainChart(){{
  const svg=document.getElementById('mainChart');
  const W=700,H=160,pts=IBOV_HISTORY.filter(v=>v>0);
  if(!pts.length)return;
  const minV=Math.min(...pts)*.998,maxV=Math.max(...pts)*1.002;
  const {{d}}=pathFromPoints(pts,W,H,minV,maxV);
  const area=areaFromPoints(pts,W,H,minV,maxV);
  svg.innerHTML=`<defs><linearGradient id="g1" x1="0" y1="0" x2="0" y2="1"><stop offset="0%" stop-color="#c9a84c" stop-opacity="0.25"/><stop offset="100%" stop-color="#c9a84c" stop-opacity="0"/></linearGradient></defs><path d="${{area}}" fill="url(#g1)"/><path d="${{d}}" fill="none" stroke="#c9a84c" stroke-width="2" stroke-linejoin="round"/>`;
}}
drawMainChart();

// ── Big chart ─────────────────────────────────────────────────────────────────
function drawBigChart(){{
  const svg=document.getElementById('bigChart');
  const W=900,H=220,pts=IBOV_HISTORY.filter(v=>v>0);
  if(!pts.length)return;
  const minV=Math.min(...pts)*.997,maxV=Math.max(...pts)*1.003;
  const {{d,xs,ys}}=pathFromPoints(pts,W,H,minV,maxV);
  let grid='';
  for(let i=0;i<=4;i++){{
    const y=10+(H-20)*i/4;
    const val=Math.round(maxV-(maxV-minV)*i/4);
    grid+=`<line x1="0" y1="${{y}}" x2="${{W}}" y2="${{y}}" stroke="#1e2d42" stroke-width="1"/>`;
    grid+=`<text x="4" y="${{y-3}}" font-size="9" fill="#6b7a99" font-family="DM Mono,sans-serif">${{(val/1000).toFixed(0)}}k</text>`;
  }}
  svg.innerHTML=`<defs><linearGradient id="bg2" x1="0" y1="0" x2="0" y2="1"><stop offset="0%" stop-color="#c9a84c" stop-opacity="0.18"/><stop offset="100%" stop-color="#c9a84c" stop-opacity="0"/></linearGradient></defs>${{grid}}<path d="${{areaFromPoints(pts,W,H,minV,maxV)}}" fill="url(#bg2)"/><path d="${{d}}" fill="none" stroke="#c9a84c" stroke-width="2.5" stroke-linejoin="round"/><circle cx="${{xs[xs.length-1]}}" cy="${{ys[ys.length-1]}}" r="5" fill="#c9a84c"/>`;
}}
drawBigChart();

// ── Pie ───────────────────────────────────────────────────────────────────────
function drawPie(){{
  const svg=document.getElementById('pieChart'),leg=document.getElementById('pieLegend');
  const slices=[{{l:'Renda Fixa',v:45,c:'#c9a84c'}},{{l:'Ações',v:30,c:'#4a9eff'}},{{l:'FIIs',v:15,c:'#2ecc8f'}},{{l:'Exterior',v:10,c:'#e05252'}}];
  const cx=100,cy=100,r=80;let start=-Math.PI/2,paths='';
  const total=slices.reduce((a,s)=>a+s.v,0);
  slices.forEach(s=>{{
    const angle=(s.v/total)*2*Math.PI;
    const x1=cx+r*Math.cos(start),y1=cy+r*Math.sin(start);
    start+=angle;
    const x2=cx+r*Math.cos(start),y2=cy+r*Math.sin(start);
    const large=angle>Math.PI?1:0;
    paths+=`<path d="M${{cx}},${{cy}} L${{x1}},${{y1}} A${{r}},${{r}} 0 ${{large}},1 ${{x2}},${{y2}} Z" fill="${{s.c}}" opacity="0.85"/>`;
  }});
  svg.innerHTML=paths+`<circle cx="${{cx}}" cy="${{cy}}" r="40" fill="#111827"/>`;
  leg.innerHTML=slices.map(s=>`<span style="display:flex;align-items:center;gap:5px;color:var(--muted)"><span style="width:10px;height:10px;border-radius:2px;background:${{s.c}};display:inline-block"></span>${{s.l}} <b style="color:var(--text)">${{s.v}}%</b></span>`).join('');
}}
drawPie();

// ── Barras mensais ────────────────────────────────────────────────────────────
function drawBar(){{
  const svg=document.getElementById('barChart');
  const months=['Set/25','Out/25','Nov/25','Dez/25','Jan/26','Fev/26'];
  const vals=[6.54,1.80,-4.31,-4.83,4.19,-1.20];
  const W=400,H=160,barW=42,gap=22,maxV=8;
  let bars='',labels='',vt='';
  months.forEach((m,i)=>{{
    const x=20+i*(barW+gap),v=vals[i];
    const barH=Math.abs(v)/maxV*(H-50);
    const y=v>=0?H-30-barH:H-30;
    const col=v>=0?'#2ecc8f':'#e05252';
    bars+=`<rect x="${{x}}" y="${{y}}" width="${{barW}}" height="${{barH}}" rx="4" fill="${{col}}" opacity="0.8"/>`;
    labels+=`<text x="${{x+barW/2}}" y="${{H-10}}" text-anchor="middle" font-size="10" fill="#6b7a99" font-family="DM Sans,sans-serif">${{m}}</text>`;
    vt+=`<text x="${{x+barW/2}}" y="${{v>=0?y-5:y+barH+14}}" text-anchor="middle" font-size="10" fill="${{col}}" font-family="DM Mono,monospace">${{v>0?'+':''}}${{v}}%</text>`;
  }});
  svg.innerHTML=`<line x1="20" y1="${{H-30}}" x2="${{W-10}}" y2="${{H-30}}" stroke="#1e2d42"/>`+bars+labels+vt;
}}
drawBar();

// ── Notícias ──────────────────────────────────────────────────────────────────
function renderNews(filter){{
  const grid=document.getElementById('newsGrid');
  const filtered=filter==='todos'?NEWS_DATA:NEWS_DATA.filter(n=>n.cat===filter);
  if(!filtered.length){{grid.innerHTML='<p style="color:var(--muted);padding:20px">Nenhuma notícia encontrada.</p>';return;}}
  grid.innerHTML=filtered.map(n=>`
    <a href="${{n.url||'#'}}" target="_blank" style="text-decoration:none">
    <div class="news-card">
      <div class="news-source" style="color:#c9a84c">${{n.src}}</div>
      <div class="news-title">${{n.title}}</div>
      <div class="news-summary">${{n.summary}}</div>
      <div class="news-footer">
        <span>${{n.time}}</span>
        <span class="news-impact ${{n.impact==='pos'?'impact-pos':n.impact==='neg'?'impact-neg':'impact-neu'}}">${{n.impact==='pos'?'▲ Positivo':n.impact==='neg'?'▼ Negativo':'→ Neutro'}}</span>
      </div>
    </div></a>`).join('');
}}
renderNews('todos');
function filterNews(cat,el){{
  document.querySelectorAll('.filter-btn').forEach(b=>b.classList.remove('active'));
  el.classList.add('active');
  renderNews(cat);
}}

// ── Templates WhatsApp ────────────────────────────────────────────────────────
const templates=[
  {{cat:'Carteira',name:'Relatório Mensal',tags:['📊 Performance','💼 Carteira'],vars:['[NOME]','[MES]','[RENTAB]','[CDI%]'],text:`Olá, [NOME]! 👋\\n\\nSegue o resumo da sua carteira referente a *[MES]*:\\n\\n📊 *Rentabilidade:* [RENTAB]%\\n📈 *vs CDI:* [CDI%]% do CDI\\n\\nSua carteira manteve boa performance no período.\\n\\nQualquer dúvida, estou à disposição!\\n\\nAbraços 🤝`}},
  {{cat:'Oportunidade',name:'Nova Oportunidade RF',tags:['💰 Renda Fixa','🔔 Urgente'],vars:['[NOME]','[ATIVO]','[TAXA]','[PRAZO]','[RATING]'],text:`Olá, [NOME]! 🌟\\n\\nPassando para te informar sobre uma oportunidade em *Renda Fixa*:\\n\\n🏦 *Emissor:* [ATIVO]\\n💰 *Taxa:* [TAXA]% ao ano\\n📅 *Prazo:* [PRAZO]\\n⭐ *Rating:* [RATING]\\n\\nOferta limitada! Me avisa se tiver interesse.\\n\\nAbraços 🤝`}},
  {{cat:'Reunião',name:'Confirmação de Reunião',tags:['📅 Agenda'],vars:['[NOME]','[DIA]','[HORA]','[FORMATO]'],text:`Oi, [NOME]! 😊\\n\\nConfirmando nossa reunião para *[DIA]* às *[HORA]* — [FORMATO].\\n\\nPauta:\\n✅ Revisão de carteira\\n✅ Cenário macro atual\\n✅ Oportunidades do trimestre\\n\\nAté lá! 👋`}},
  {{cat:'Mercado',name:'Alerta de Mercado',tags:['🚨 Alerta'],vars:['[NOME]','[EVENTO]','[IMPACTO]'],text:`Oi, [NOME]! 🚨\\n\\n*Evento:* [EVENTO]\\n*Impacto esperado:* [IMPACTO]\\n\\nEstou monitorando. Caso precise de ajuste na carteira, te aviso.\\n\\nQualquer dúvida, estou aqui! 💬`}},
  {{cat:'Aniversário',name:'Felicitações',tags:['🎂 Relacionamento'],vars:['[NOME]'],text:`Feliz aniversário, [NOME]! 🎉🎂\\n\\nMuita saúde, prosperidade e bons investimentos! 😄📈\\n\\nAbraços 🤝`}},
  {{cat:'Encerramento',name:'Follow-up Pós-Reunião',tags:['📝 Follow-up'],vars:['[NOME]','[RESUMO]','[ACAO]','[PRAZO]'],text:`Olá, [NOME]! 😊\\n\\nResumo da nossa conversa:\\n\\n📋 *Resumo:* [RESUMO]\\n🎯 *Próximo passo:* [ACAO]\\n⏰ *Prazo:* [PRAZO]\\n\\nEstou à disposição! 🤝`}},
];
let activeTemplate=0;
function loadTemplate(i){{
  activeTemplate=i;
  const t=templates[i];
  document.getElementById('msgTitle').textContent=t.name;
  document.getElementById('msgArea').value=t.text;
  updateCharCount();
  document.getElementById('tagRow').innerHTML=t.tags.map(tag=>`<span class="tag active">${{tag}}</span>`).join('');
  document.getElementById('varsRow').innerHTML=t.vars.map(v=>`<span class="var-chip" onclick="insertVar('${{v}}')">${{v}}</span>`).join('');
  document.querySelectorAll('.template-item').forEach((el,idx)=>el.classList.toggle('active',idx===i));
}}
const tl=document.getElementById('templateList');
templates.forEach((t,i)=>{{
  tl.innerHTML+=`<div class="template-item${{i===0?' active':''}}" onclick="loadTemplate(${{i}})"><div class="template-tag">${{t.cat}}</div><div class="template-name">${{t.name}}</div></div>`;
}});
loadTemplate(0);
function insertVar(v){{const ta=document.getElementById('msgArea');const s=ta.selectionStart,e=ta.selectionEnd;ta.value=ta.value.slice(0,s)+v+ta.value.slice(e);ta.focus();ta.setSelectionRange(s+v.length,s+v.length);updateCharCount();}}
function updateCharCount(){{document.getElementById('charCount').textContent=document.getElementById('msgArea').value.length+' caracteres';}}
document.getElementById('msgArea').addEventListener('input',updateCharCount);
function copyMsg(){{navigator.clipboard.writeText(document.getElementById('msgArea').value);const t=document.getElementById('copiedToast');t.classList.add('show');setTimeout(()=>t.classList.remove('show'),2000);}}
function clearMsg(){{document.getElementById('msgArea').value='';updateCharCount();}}

// ── Planilha ──────────────────────────────────────────────────────────────────
const sheetData=[
  {{a:'PETR4',cl:'Ações',v:'12.400,00',r:'+0,47',p:'18',vc:'—',obs:'Monitorar balanço'}},
  {{a:'CDB Banco XYZ',cl:'Renda Fixa',v:'30.000,00',r:'+14,51',p:'35',vc:'15/06/2026',obs:'CDI+0,8%'}},
  {{a:'FII HGLG11',cl:'FII',v:'8.500,00',r:'+9,4',p:'12',vc:'—',obs:'DY 9,1%'}},
  {{a:'Tesouro IPCA 2029',cl:'Renda Fixa',v:'15.000,00',r:'+13,68',p:'22',vc:'15/05/2029',obs:'IPCA+6,1%'}},
  {{a:'BDR AAPL34',cl:'Exterior',v:'9.000,00',r:'+22,3',p:'13',vc:'—',obs:'Hedge cambial'}},
];
const colors=['#c9a84c','#4a9eff','#2ecc8f','#e05252','#a78bfa'];
function renderSheet(){{
  const sb=document.getElementById('sheetBody');
  sb.innerHTML=sheetData.map((r,i)=>`<tr><td contenteditable="true">${{r.a}}</td><td contenteditable="true">${{r.cl}}</td><td contenteditable="true" style="color:var(--gold-light)">R$ ${{r.v}}</td><td contenteditable="true" class="${{parseFloat(r.r)>=0?'pos':'neg'}}">${{r.r}}%</td><td contenteditable="true"><span class="badge" style="background:rgba(201,168,76,.1);color:var(--gold)">${{r.p}}%</span></td><td contenteditable="true" style="color:var(--muted)">${{r.vc}}</td><td contenteditable="true" style="color:var(--muted)">${{r.obs}}</td></tr>`).join('');
  document.getElementById('allocBar').innerHTML=sheetData.map((r,i)=>`<div class="alloc-seg" style="flex:${{r.p}};background:${{colors[i]}};opacity:.8"></div>`).join('');
  document.getElementById('allocLegend').innerHTML=sheetData.map((r,i)=>`<span style="display:flex;align-items:center;gap:5px;font-size:.75rem;color:var(--muted)"><span style="width:10px;height:10px;border-radius:2px;background:${{colors[i]}};display:inline-block"></span>${{r.a}} <b style="color:var(--text)">${{r.p}}%</b></span>`).join('');
}}
renderSheet();
function addRow(){{sheetData.push({{a:'Novo Ativo',cl:'—',v:'0,00',r:'0,0',p:'0',vc:'—',obs:'—'}});renderSheet();}}
function exportSheet(){{
  const rows=[['Ativo','Classe','Valor (R$)','Rentab %','% Cart','Vencimento','Obs']];
  sheetData.forEach(r=>rows.push([r.a,r.cl,r.v,r.r,r.p,r.vc,r.obs]));
  const csv=rows.map(r=>r.join(';')).join('\\n');
  const a=document.createElement('a');a.href='data:text/csv;charset=utf-8,\\uFEFF'+encodeURIComponent(csv);a.download=(document.getElementById('sheetTitle').value||'carteira')+'.csv';a.click();
}}
</script>
</body>
</html>"""
    return html

# ── Main ──────────────────────────────────────────────────────────────────────
def main():
    print("🔄 AssessorHub — Iniciando atualização...")

    print("  📈 Buscando Ibovespa...")
    ibov = get_ibov()

    print("  💵 Buscando Dólar...")
    dollar = get_dollar()

    print("  🏦 Buscando Selic/CDI...")
    selic_data = get_selic()

    print("  📊 Buscando cotações B3...")
    quotes = get_quotes()

    print("  📰 Buscando notícias...")
    news = get_news()

    print("  🖊️  Gerando HTML...")
    html = generate_html(ibov, dollar, selic_data, quotes, news)

    with open("index.html", "w", encoding="utf-8") as f:
        f.write(html)

    print(f"  ✅ index.html gerado com sucesso!")
    print(f"     Ibovespa: {ibov['value']:,.0f} ({ibov['change']:+.2f}%)")
    print(f"     Dólar:    R$ {dollar['value']:.2f} ({dollar['change']:+.2f}%)")
    print(f"     Selic:    {selic_data['selic']}%")
    print(f"     Notícias: {len(news)} encontradas")

if __name__ == "__main__":
    main()
