#!/usr/bin/env python3
"""
╔══════════════════════════════════════════════════════╗
║        KRİPTO LİKİDASYON TERMİNALİ                  ║
║  Isı Haritası + Fon + L/S + CVD + CB Premium         ║
║  Binance & Coinbase API — Tamamen Ücretsiz           ║
╚══════════════════════════════════════════════════════╝

Kurulum:
    pip install dash plotly requests numpy

Çalıştırma:
    python kripto_terminal.py
    Tarayıcıda: http://localhost:8050
"""

import requests
import numpy as np
from datetime import datetime

import dash
from dash import dcc, html, Input, Output
import plotly.graph_objects as go
from plotly.subplots import make_subplots

# ─────────────────────────────────────────────────────
#  AYARLAR
# ─────────────────────────────────────────────────────
COINS     = ['BTC', 'ETH', 'SOL', 'XRP', 'AVAX', 'TAO']
INTERVALS = ['15m', '1h', '4h']

BINANCE_SPOT    = 'https://api.binance.com'
BINANCE_FUTURES = 'https://fapi.binance.com'
BINANCE_SPOT    = 'https://api.binance.com'
COINBASE_API    = 'https://api.exchange.coinbase.com'

# Coinbase sembol eşleştirme
CB_SYMBOLS = {
    'BTC': 'BTC-USD', 'ETH': 'ETH-USD', 'SOL': 'SOL-USD',
    'XRP': 'XRP-USD', 'AVAX': 'AVAX-USD', 'TAO': 'TAO-USD',
    'BNB': 'BNB-USD', 'DOGE': 'DOGE-USD',
}

# Coinbase granularity (saniye)
CB_GRAN = {'15m': 900, '1h': 3600, '4h': 21600}

# 3 kademeli ısı rengi: Yeşil → Sarı → Kırmızı
HEATMAP_SCALE = [
    [0.00, 'rgb(10,40,15)'],
    [0.25, 'rgb(34,160,60)'],
    [0.50, 'rgb(220,200,20)'],
    [0.75, 'rgb(230,100,10)'],
    [1.00, 'rgb(220,30,30)'],
]

BG      = '#080c14'
BG_PLOT = '#0c1020'
BG_CARD = '#0f1428'
BORDER  = '#1c2038'
TEXT    = '#c8cce0'
MUTED   = '#606880'
GREEN   = '#22c55e'
RED     = '#ef4444'
YELLOW  = '#eab308'
BLUE    = '#60a5fa'
PURPLE  = '#a78bfa'


# ─────────────────────────────────────────────────────
#  VERİ ÇEKME
# ─────────────────────────────────────────────────────
def get(url, params=None):
    try:
        r = requests.get(url, params=params, timeout=12)
        return r.json() if r.status_code == 200 else []
    except Exception:
        return []


def fetch_klines(symbol, interval, limit=150):
    """Binance Futures mum verisi"""
    data = get(f'{BINANCE_FUTURES}/fapi/v1/klines',
               {'symbol': symbol, 'interval': interval, 'limit': limit})
    if not isinstance(data, list) or not data:
        raise RuntimeError(f'{symbol} için veri alınamadı')
    return [{'time': d[0], 'open': float(d[1]), 'high': float(d[2]),
             'low': float(d[3]), 'close': float(d[4]), 'volume': float(d[5])}
            for d in data]


def fetch_funding(symbol):
    """Fonlama oranı"""
    return get(f'{BINANCE_FUTURES}/fapi/v1/fundingRate',
               {'symbol': symbol, 'limit': 100})


def fetch_ls(symbol, interval):
    """Global long/short oranı"""
    return get(f'{BINANCE_FUTURES}/futures/data/globalLongShortAccountRatio',
               {'symbol': symbol, 'period': interval, 'limit': 100})


def fetch_spot_cvd(symbol, interval, limit=150):
    """
    Binance Spot CVD (Cumulative Volume Delta)
    Kline kolonları: [9] = taker buy base asset volume
    Delta = taker_buy - taker_sell = 2*taker_buy - total_volume
    CVD   = delta'ların kümülatif toplamı
    """
    data = get(f'{BINANCE_SPOT}/api/v3/klines',
               {'symbol': symbol, 'interval': interval, 'limit': limit})
    if not data:
        return []

    result = []
    cvd = 0.0
    for d in data:
        total_vol  = float(d[5])
        taker_buy  = float(d[9])
        delta      = 2.0 * taker_buy - total_vol   # buy - sell
        cvd       += delta
        result.append({'time': d[0], 'delta': delta, 'cvd': cvd})

    # Sıfırdan başlat
    if result:
        base = result[0]['cvd']
        for r in result:
            r['cvd'] -= base

    return result


def fetch_coinbase_premium(symbol, interval, limit=150):
    """
    Coinbase - Binance fiyat farkı (%)
    Pozitif = Coinbase daha pahalı → kurumsal alım → boğa sinyali
    Negatif = Binance daha pahalı → perakende satış → ayı sinyali
    """
    coin      = symbol.replace('USDT', '')
    cb_symbol = CB_SYMBOLS.get(coin)
    if not cb_symbol:
        return []

    granularity = CB_GRAN.get(interval, 3600)

    try:
        cb_r = requests.get(
            f'{COINBASE_API}/products/{cb_symbol}/candles',
            params={'granularity': granularity},
            timeout=12
        )
        if cb_r.status_code != 200:
            return []

        cb_candles = cb_r.json()
        if not isinstance(cb_candles, list) or not cb_candles:
            return []

        cb_candles.sort(key=lambda x: x[0])   # zaman sırasına diz

        # Binance spot kapanış fiyatları
        bn_data = get(f'{BINANCE_SPOT}/api/v3/klines',
                      {'symbol': symbol, 'interval': interval, 'limit': limit})
        if not bn_data:
            return []

        bn_map = {int(d[0] // 1000): float(d[4]) for d in bn_data}

        result = []
        for c in cb_candles[-limit:]:
            ts_sec   = int(c[0])
            cb_close = float(c[4])
            bn_close = bn_map.get(ts_sec)
            if bn_close and bn_close > 0:
                premium = (cb_close - bn_close) / bn_close * 100
                result.append({'time': ts_sec * 1000, 'premium': premium})

        return result

    except Exception:
        return []


# ─────────────────────────────────────────────────────
#  YOĞUNLUK ISISI
# ─────────────────────────────────────────────────────
def build_heatmap(klines, n_buckets=220):
    """
    Gövde (2.5x) + Fitil (1.0x) ağırlıklı fiyat yoğunluğu.
    Kırmızı = yoğun  |  Sarı = orta  |  Yeşil = seyrek
    """
    highs = [k['high'] for k in klines]
    lows  = [k['low']  for k in klines]
    p_min = min(lows)  - (max(highs) - min(lows)) * 0.05
    p_max = max(highs) + (max(highs) - min(lows)) * 0.05
    p_rng = p_max - p_min

    n_x  = len(klines)
    grid = np.zeros((n_buckets, n_x), dtype=np.float32)

    def buck(p):
        return int(np.clip((p - p_min) / p_rng * n_buckets, 0, n_buckets - 1))

    for xi, k in enumerate(klines):
        y_lo = buck(k['low']);  y_hi = buck(k['high'])
        grid[y_lo:y_hi + 1, xi] += 1.0
        b_lo = buck(min(k['open'], k['close']))
        b_hi = buck(max(k['open'], k['close']))
        if b_hi >= b_lo:
            grid[b_lo:b_hi + 1, xi] += 1.5

    window = min(30, n_x // 4)
    cumul  = np.zeros_like(grid)
    for xi in range(n_x):
        cumul[:, xi] = grid[:, max(0, xi - window + 1):xi + 1].sum(axis=1)

    mx = cumul.max()
    if mx > 0:
        cumul /= mx

    return cumul, np.linspace(p_min, p_max, n_buckets), p_min, p_max


# ─────────────────────────────────────────────────────
#  ANA FİGÜR
# ─────────────────────────────────────────────────────
def anno(text, x, y):
    return dict(text=text, xref='paper', yref='paper', x=x, y=y,
                xanchor='left', yanchor='top', showarrow=False,
                font=dict(size=9, color=MUTED))


def build_figure(coin, interval):
    symbol = coin + 'USDT'

    # Veri çek
    try:
        klines = fetch_klines(symbol, interval)
    except RuntimeError as e:
        fig = go.Figure()
        fig.add_annotation(text=str(e), x=0.5, y=0.5, showarrow=False,
                           font=dict(color=RED, size=14))
        fig.update_layout(paper_bgcolor=BG, plot_bgcolor=BG_PLOT, height=800)
        return fig

    fr_data  = fetch_funding(symbol)
    ls_data  = fetch_ls(symbol, interval)
    cvd_data = fetch_spot_cvd(symbol, interval)
    cb_data  = fetch_coinbase_premium(symbol, interval)

    # Isı haritası
    grid, prices, p_min, p_max = build_heatmap(klines)
    times  = [datetime.fromtimestamp(k['time'] / 1000) for k in klines]
    closes = [k['close'] for k in klines]

    # ── Alt grafik düzeni: 3 satır ──────────────────────
    # Satır 1: Isı haritası (tam genişlik, büyük)
    # Satır 2: Fonlama + Long/Short (küçük)
    # Satır 3: Spot CVD + Coinbase Premium (orta)
    fig = make_subplots(
        rows=3, cols=2,
        row_heights=[0.50, 0.18, 0.32],
        column_widths=[0.5, 0.5],
        specs=[
            [{'colspan': 2}, None],
            [{}, {}],
            [{}, {}],
        ],
        vertical_spacing=0.05,
        horizontal_spacing=0.06,
    )

    # ── BÖLÜM 1: Isı haritası ─────────────────────────
    fig.add_trace(go.Heatmap(
        x=times, y=prices, z=grid,
        colorscale=HEATMAP_SCALE,
        showscale=False, zmin=0, zmax=1, opacity=0.95,
        hovertemplate='Fiyat: %{y:,.4f}<br>Yoğunluk: %{z:.2f}<extra></extra>',
    ), row=1, col=1)

    fig.add_trace(go.Scatter(
        x=times, y=closes, mode='lines',
        line=dict(color='rgba(255,255,255,0.75)', width=1.5),
        showlegend=False,
        hovertemplate='%{x|%d/%m %H:%M}<br>%{y:,.4f}<extra></extra>',
    ), row=1, col=1)

    last_price = closes[-1]
    price_str  = f'{last_price:,.1f}' if last_price >= 1000 else f'{last_price:,.4f}'
    fig.add_hline(
        y=last_price,
        line=dict(dash='dot', color='rgba(255,255,255,0.35)', width=1),
        annotation_text=f'  {price_str}',
        annotation_font=dict(color='white', size=11),
        annotation_position='right', row=1, col=1,
    )

    # ── BÖLÜM 2a: Fonlama oranı ───────────────────────
    if fr_data:
        fr_times  = [datetime.fromtimestamp(d['fundingTime'] / 1000) for d in fr_data]
        fr_rates  = [float(d['fundingRate']) * 100 for d in fr_data]
        fig.add_trace(go.Bar(
            x=fr_times, y=fr_rates,
            marker_color=[GREEN if r >= 0 else RED for r in fr_rates],
            marker_opacity=0.8, showlegend=False,
            hovertemplate='%{x|%d/%m}<br><b>%{y:.4f}%</b><extra></extra>',
        ), row=2, col=1)
        fig.add_hline(y=0, line=dict(color='rgba(255,255,255,0.15)', width=1), row=2, col=1)

    # ── BÖLÜM 2b: Long/Short yüzde alanı ─────────────
    if ls_data:
        ls_times   = [datetime.fromtimestamp(d['timestamp'] / 1000) for d in ls_data]
        long_pcts  = [float(d['longAccount']) * 100 for d in ls_data]
        short_pcts = [100 - lp for lp in long_pcts]

        fig.add_trace(go.Scatter(
            x=ls_times, y=long_pcts, mode='lines',
            line=dict(color=GREEN, width=1.5),
            fill='tozeroy', fillcolor='rgba(34,197,94,0.15)',
            showlegend=False,
            hovertemplate='Long: <b>%{y:.1f}%</b><extra></extra>',
        ), row=2, col=2)

        hundreds = [100] * len(ls_times)
        fig.add_trace(go.Scatter(
            x=ls_times, y=hundreds, mode='lines',
            line=dict(color='rgba(0,0,0,0)', width=0),
            showlegend=False, hoverinfo='skip',
        ), row=2, col=2)

        fig.add_trace(go.Scatter(
            x=ls_times, y=short_pcts, mode='lines',
            line=dict(color=RED, width=1.5),
            fill='tonexty', fillcolor='rgba(239,68,68,0.15)',
            showlegend=False,
            hovertemplate='Short: <b>%{y:.1f}%</b><extra></extra>',
        ), row=2, col=2)

        fig.add_hline(y=50, line=dict(dash='dot', color='rgba(255,255,255,0.15)', width=1), row=2, col=2)

        cur_long  = long_pcts[-1]
        cur_short = short_pcts[-1]
        fig.add_annotation(
            xref='paper', yref='y4',
            x=0.99, y=cur_long / 2,
            text=f'<b>{cur_long:.1f}%</b> Long',
            showarrow=False, xanchor='right',
            font=dict(color=GREEN, size=10, family='monospace'),
        )
        fig.add_annotation(
            xref='paper', yref='y4',
            x=0.99, y=cur_long + cur_short / 2,
            text=f'<b>{cur_short:.1f}%</b> Short',
            showarrow=False, xanchor='right',
            font=dict(color=RED, size=10, family='monospace'),
        )

    # ── BÖLÜM 3a: Binance Spot CVD ────────────────────
    if cvd_data:
        cvd_times  = [datetime.fromtimestamp(d['time'] / 1000) for d in cvd_data]
        cvd_values = [d['cvd']   for d in cvd_data]
        delta_vals = [d['delta'] for d in cvd_data]

        # Delta bar'ları (alım/satım farkı)
        fig.add_trace(go.Bar(
            x=cvd_times, y=delta_vals,
            marker_color=[GREEN if d >= 0 else RED for d in delta_vals],
            marker_opacity=0.5, showlegend=False,
            name='Delta',
            hovertemplate='%{x|%d/%m %H:%M}<br>Delta: <b>%{y:,.0f}</b><extra></extra>',
        ), row=3, col=1)

        # CVD çizgisi
        fig.add_trace(go.Scatter(
            x=cvd_times, y=cvd_values, mode='lines',
            line=dict(color=BLUE, width=1.8),
            showlegend=False,
            hovertemplate='%{x|%d/%m %H:%M}<br>CVD: <b>%{y:,.0f}</b><extra></extra>',
        ), row=3, col=1)

        fig.add_hline(y=0, line=dict(color='rgba(255,255,255,0.15)', width=1), row=3, col=1)

    # ── BÖLÜM 3b: Coinbase Premium ────────────────────
    if cb_data:
        cb_times    = [datetime.fromtimestamp(d['time'] / 1000) for d in cb_data]
        cb_premiums = [d['premium'] for d in cb_data]

        fig.add_trace(go.Bar(
            x=cb_times, y=cb_premiums,
            marker_color=[GREEN if p >= 0 else RED for p in cb_premiums],
            marker_opacity=0.75, showlegend=False,
            hovertemplate='%{x|%d/%m %H:%M}<br>Premium: <b>%{y:.4f}%</b><extra></extra>',
        ), row=3, col=2)

        fig.add_hline(y=0, line=dict(color='rgba(255,255,255,0.15)', width=1), row=3, col=2)

        cur_prem = cb_premiums[-1]
        prem_col = GREEN if cur_prem >= 0 else RED
        prem_txt = 'Coinbase daha pahalı → Kurumsal alım 🟢' if cur_prem >= 0 \
                   else 'Binance daha pahalı → Perakende satış 🔴'
        fig.add_annotation(
            xref='paper', yref='paper',
            x=0.99, y=0.015,
            text=f'<span style="color:{prem_col};font-size:10px">{prem_txt}</span>',
            showarrow=False, xanchor='right', yanchor='bottom',
            font=dict(family='monospace'),
        )
    else:
        # Coinbase verisi gelmezse açıklama göster
        fig.add_annotation(
            xref='paper', yref='paper',
            x=0.75, y=0.13,
            text='Coinbase verisi bu coin için mevcut değil',
            showarrow=False, xanchor='center',
            font=dict(size=10, color=MUTED, family='monospace'),
        )

    # ── Başlık istatistikleri ─────────────────────────
    prev      = closes[-2] if len(closes) > 1 else last_price
    pct       = (last_price - prev) / prev * 100
    last_fr   = float(fr_data[-1]['fundingRate']) * 100 if fr_data else 0
    last_ls   = float(ls_data[-1]['longShortRatio'])    if ls_data else 0
    last_long = float(ls_data[-1]['longAccount']) * 100 if ls_data else 0
    last_cvd  = cvd_data[-1]['cvd']   if cvd_data else 0
    last_prem = cb_data[-1]['premium'] if cb_data  else None

    p_col  = GREEN if pct     >= 0 else RED
    fr_col = GREEN if last_fr >= 0 else RED
    ls_col = GREEN if last_ls >= 1 else RED
    c_col  = GREEN if last_cvd >= 0 else RED

    prem_part = ''
    if last_prem is not None:
        pc = GREEN if last_prem >= 0 else RED
        prem_part = (f'<span style="color:#404860"> │ </span>'
                     f'CB Premium <span style="color:{pc}">{last_prem:+.4f}%</span>')

    title = (
        f'<b style="color:#e8eaf0">{coin}/USDT</b>'
        f'<span style="color:#404860"> │ </span>'
        f'<b style="color:#e8eaf0">{price_str}</b>'
        f'<span style="color:{p_col}"> {pct:+.2f}%</span>'
        f'<span style="color:#404860"> │ </span>'
        f'Fon <span style="color:{fr_col}">{last_fr:+.4f}%</span>'
        f'<span style="color:#404860"> │ </span>'
        f'L/S <span style="color:{ls_col}">{last_ls:.3f}</span>'
        f'<span style="color:#404860"> │ </span>'
        f'Long <span style="color:{GREEN}">{last_long:.1f}%</span>'
        f' Short <span style="color:{RED}">{100-last_long:.1f}%</span>'
        f'<span style="color:#404860"> │ </span>'
        f'CVD <span style="color:{c_col}">{last_cvd:+,.0f}</span>'
        f'{prem_part}'
    )

    # ── Layout ────────────────────────────────────────
    ax = dict(
        gridcolor='rgba(255,255,255,0.05)',
        zerolinecolor='rgba(255,255,255,0.08)',
        color=MUTED,
        tickfont=dict(size=9, family='monospace'),
        showgrid=True,
    )

    fig.update_layout(
        title=dict(text=title, font=dict(size=12), x=0.01, y=0.99),
        paper_bgcolor=BG, plot_bgcolor=BG_PLOT,
        font=dict(color=TEXT, family='monospace', size=10),
        showlegend=False, height=820,
        margin=dict(l=12, r=12, t=40, b=12),
        uirevision=f'{coin}_{interval}',
        bargap=0.1,
        annotations=[
            anno('FİYAT YOĞUNLUK ISI HARİTASI  ─  Kırmızı: yoğun  Sarı: orta  Yeşil: seyrek', 0.01, 0.995),
            anno('FON ORANI', 0.01, 0.475),
            anno('LONG / SHORT  ─  Yeşil: Long%  Kırmızı: Short%', 0.52, 0.475),
            anno('BİNANCE SPOT CVD  ─  Çubuk: delta  Çizgi: kümülatif', 0.01, 0.295),
            anno('COİNBASE PREMİUM  ─  Yeşil: CB>BN (kurumsal alım)  Kırmızı: BN>CB', 0.52, 0.295),
        ],
    )

    fig.update_xaxes(ax)
    fig.update_yaxes(ax)
    fig.update_xaxes(rangeslider_visible=False, row=1, col=1)

    return fig


# ─────────────────────────────────────────────────────
#  DASH UYGULAMASI
# ─────────────────────────────────────────────────────
app = dash.Dash(__name__, title='Kripto Terminal', update_title=None)


def lbl(text):
    return html.Div(text, style={
        'color': MUTED, 'fontSize': '10px', 'letterSpacing': '0.06em',
        'marginBottom': '4px', 'fontFamily': 'monospace',
    })


app.layout = html.Div([

    # Başlık
    html.Div([
        html.Span('◈ ', style={'color': YELLOW, 'fontSize': '16px'}),
        html.Span('KRİPTO TERMİNALİ', style={
            'color': '#e8eaf0', 'fontFamily': 'monospace',
            'fontSize': '14px', 'letterSpacing': '0.1em', 'fontWeight': '500',
        }),
        html.Span('  Binance + Coinbase • Ücretsiz', style={
            'color': MUTED, 'fontFamily': 'monospace', 'fontSize': '11px',
        }),
    ], style={
        'padding': '10px 16px', 'backgroundColor': '#060810',
        'borderBottom': f'1px solid {BORDER}',
        'display': 'flex', 'alignItems': 'center',
    }),

    # Kontroller
    html.Div([
        html.Div([lbl('COİN'), dcc.Dropdown(
            id='coin-dd',
            options=[{'label': c, 'value': c} for c in COINS],
            value='BTC', clearable=False,
            style={'width': '110px', 'backgroundColor': BG_CARD, 'color': TEXT,
                   'border': f'1px solid {BORDER}', 'fontFamily': 'monospace'},
        )]),
        html.Div([lbl('ZAMAN'), dcc.Dropdown(
            id='iv-dd',
            options=[{'label': i, 'value': i} for i in INTERVALS],
            value='1h', clearable=False,
            style={'width': '90px', 'backgroundColor': BG_CARD, 'color': TEXT,
                   'border': f'1px solid {BORDER}', 'fontFamily': 'monospace'},
        )]),
        html.Div([lbl(''), html.Button('↺  Yenile', id='refresh-btn', n_clicks=0, style={
            'padding': '6px 16px', 'backgroundColor': '#141830', 'color': BLUE,
            'border': f'1px solid #222850', 'borderRadius': '6px',
            'cursor': 'pointer', 'fontFamily': 'monospace', 'fontSize': '12px',
        })]),
        html.Div(id='last-update', style={
            'marginLeft': 'auto', 'color': MUTED,
            'fontFamily': 'monospace', 'fontSize': '11px', 'alignSelf': 'center',
        }),
    ], style={
        'display': 'flex', 'alignItems': 'flex-end', 'gap': '12px',
        'padding': '12px 16px', 'backgroundColor': BG_CARD,
        'borderBottom': f'1px solid {BORDER}',
    }),

    # Grafik
    dcc.Graph(
        id='main-chart',
        config={'displayModeBar': True, 'displaylogo': False,
                'modeBarButtonsToRemove': ['select2d', 'lasso2d']},
        style={'backgroundColor': BG},
    ),

    dcc.Interval(id='auto-refresh', interval=60_000, n_intervals=0),

    # Alt açıklama
    html.Div([
        html.Span('■ ', style={'color': RED}),
        html.Span('Kırmızı=Yoğun  ', style={'marginRight': '10px'}),
        html.Span('■ ', style={'color': YELLOW}),
        html.Span('Sarı=Orta  ', style={'marginRight': '10px'}),
        html.Span('■ ', style={'color': GREEN}),
        html.Span('Yeşil=Seyrek  ', style={'marginRight': '20px'}),
        html.Span('CVD↑ ', style={'color': GREEN}),
        html.Span('= Net alım baskısı  ', style={'marginRight': '10px'}),
        html.Span('CB Premium↑ ', style={'color': GREEN}),
        html.Span('= Kurumsal alım'),
    ], style={
        'padding': '6px 16px', 'backgroundColor': '#060810',
        'borderTop': f'1px solid {BORDER}', 'color': MUTED,
        'fontFamily': 'monospace', 'fontSize': '10px',
    }),

], style={'backgroundColor': BG, 'minHeight': '100vh'})


@app.callback(
    Output('main-chart',  'figure'),
    Output('last-update', 'children'),
    Input('coin-dd',      'value'),
    Input('iv-dd',        'value'),
    Input('refresh-btn',  'n_clicks'),
    Input('auto-refresh', 'n_intervals'),
)
def update(coin, interval, _clicks, _intervals):
    return (build_figure(coin, interval),
            f'Son güncelleme: {datetime.now().strftime("%H:%M:%S")}')


if __name__ == '__main__':
    print()
    print('╔══════════════════════════════════════════╗')
    print('║   KRİPTO TERMİNALİ — Hazır               ║')
    print('╠══════════════════════════════════════════╣')
    print('║  Adres  :  http://localhost:8050         ║')
    print('║  Durmak :  CTRL + C                      ║')
    print('╚══════════════════════════════════════════╝')
    print()
    import os
port = int(os.environ.get('PORT', 8050))
app.run(debug=False, port=port, host='0.0.0.0')
