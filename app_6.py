"""
ANA / JAL マイル vs 現金 比較アプリ
Streamlit + Anthropic API (claude-sonnet-4-20250514 with web_search)
"""

import streamlit as st
import anthropic
import json
import re
from datetime import date, datetime
import os

# ─── ページ設定 ────────────────────────────────────────────────
st.set_page_config(
    page_title="✈ マイル vs 現金 比較",
    page_icon="✈",
    layout="wide",
)

# ─── CSS ────────────────────────────────────────────────────────
st.markdown("""
<style>
.recommend-cash  { background:#e8f5e9; color:#2e7d32; padding:4px 10px; border-radius:6px; font-weight:600; font-size:13px; }
.recommend-mile  { background:#e3f2fd; color:#1565c0; padding:4px 10px; border-radius:6px; font-weight:600; font-size:13px; }
.recommend-na    { background:#f5f5f5; color:#757575; padding:4px 10px; border-radius:6px; font-size:13px; }
.section-head    { font-size:15px; font-weight:600; margin-bottom:4px; }
.note-text       { font-size:12px; color:#757575; }
</style>
""", unsafe_allow_html=True)

# ─── 国内空港コード一覧（自動判別用） ──────────────────────────
DOMESTIC_AIRPORTS = {
    "HND","NRT","CTS","OKA","KIX","ITM","NGO","FUK","OIT","KMJ","KOJ",
    "MYJ","TAK","AOJ","AXT","SDJ","KKJ","NGS","KMI","OKJ","HIJ","TKS",
    "MYE","MMB","HKD","TOY","KNZ","ISG","MMY","IKI","TSJ","OKI","UBJ",
    "TTJ","IWJ","YGJ","OKE","OAJ","HAC","NKM",
}

def detect_route_type(origin: str, dest: str) -> str:
    return "domestic" if (origin.upper() in DOMESTIC_AIRPORTS and dest.upper() in DOMESTIC_AIRPORTS) else "intl"

def get_season(dep_date: date, route_type: str) -> str:
    m = dep_date.month
    if route_type == "domestic":
        if m in (3, 4, 7, 8, 12, 1):
            return "H（繁忙期）"
        elif m in (5, 6, 9, 10, 11):
            return "R（通常期）"
        else:
            return "L（閑散期）"
    else:
        if m in (12, 1, 3, 4, 7, 8):
            return "H（ハイシーズン）"
        elif m in (5, 6, 9, 10, 11):
            return "R（レギュラー）"
        else:
            return "L（ローシーズン）"

def calc_pax_factor(adults: int, child_ages: list[int], route_type: str) -> float:
    eligible = sum(
        1 for a in child_ages
        if (route_type == "domestic" and 3 <= a <= 11)
        or (route_type == "intl"     and 2 <= a <= 11)
    )
    ineligible = len(child_ages) - eligible
    return adults + eligible * 0.5 + ineligible * 1.0

def build_prompt(origin, dest, dep_date, route_type, season, trip_mode, adults, child_ages) -> str:
    child_str = ", ".join(str(a) for a in child_ages) if child_ages else "なし"
    return f"""以下の条件でANAとJALのフライトをウェブ検索して調査し、JSONのみで返答してください。
前置き・説明文・マークダウンのコードブロック記号は一切不要です。

出発地: {origin}
到着地: {dest}
搭乗日: {dep_date}
路線種別: {"国内線" if route_type == "domestic" else "国際線"}
シーズン: {season}
片道/往復: {"往復" if trip_mode == "rt" else "片道"}
大人: {adults}名　子ども年齢: {child_str}

返すべきJSON構造（数値はすべて整数・大人1名・片道ベース）:
{{
  "ana": {{
    "economy": {{"cash_jpy": 数値, "miles": 数値, "tax_jpy": 数値, "notes": "備考"}},
    "business": {{"cash_jpy": 数値, "miles": 数値, "tax_jpy": 数値, "notes": "備考"}}
  }},
  "jal": {{
    "economy": {{"cash_jpy": 数値, "miles": 数値, "tax_jpy": 数値, "notes": "備考"}},
    "business": {{"cash_jpy": 数値, "miles": 数値, "tax_jpy": 数値, "notes": "備考"}}
  }}
}}

cash_jpy : 大人1名・片道の現金最安値（円）
miles    : 大人1名・片道の必要マイル数（特典航空券）
tax_jpy  : マイル利用時の諸税合計（燃油+空港税）大人1名・片道（円）
国内線にビジネスクラスがない場合や情報が取れない場合は cash_jpy=0, miles=0 としてください。
JSON以外は絶対に出力しないこと。"""

def fallback_data(route_type: str) -> dict:
    if route_type == "domestic":
        return {
            "ana": {
                "economy": {"cash_jpy": 15000, "miles": 4000, "tax_jpy": 440,  "notes": "参考値（自動取得失敗）"},
                "business": {"cash_jpy": 0,     "miles": 0,    "tax_jpy": 0,    "notes": "国内線ビジネスなし"},
            },
            "jal": {
                "economy": {"cash_jpy": 14000, "miles": 4000, "tax_jpy": 440,  "notes": "参考値（自動取得失敗）"},
                "business": {"cash_jpy": 0,     "miles": 0,    "tax_jpy": 0,    "notes": "国内線ビジネスなし"},
            },
        }
    else:
        return {
            "ana": {
                "economy": {"cash_jpy": 80000,  "miles": 35000, "tax_jpy": 25000, "notes": "参考値（自動取得失敗）"},
                "business": {"cash_jpy": 300000, "miles": 80000, "tax_jpy": 30000, "notes": "参考値（自動取得失敗）"},
            },
            "jal": {
                "economy": {"cash_jpy": 75000,  "miles": 35000, "tax_jpy": 25000, "notes": "参考値（自動取得失敗）"},
                "business": {"cash_jpy": 280000, "miles": 80000, "tax_jpy": 30000, "notes": "参考値（自動取得失敗）"},
            },
        }

def call_claude(prompt: str, api_key: str) -> dict:
    client = anthropic.Anthropic(api_key=api_key)
    response = client.messages.create(
        model="claude-sonnet-4-20250514",
        max_tokens=1000,
        tools=[{"type": "web_search_20250305", "name": "web_search"}],
        system="あなたは航空券・マイレージ専門家です。必ずJSON形式のみで返答してください。",
        messages=[{"role": "user", "content": prompt}],
    )
    text = "".join(b.text for b in response.content if b.type == "text")
    clean = re.sub(r"```(?:json)?|```", "", text).strip()
    return json.loads(clean)

def mile_value(cash: int, tax: int, miles: int) -> float | None:
    if miles <= 0:
        return None
    return (cash - tax) / miles

def verdict_html(val: float | None) -> str:
    if val is None:
        return '<span class="recommend-na">対象外</span>'
    if val >= 2.0:
        return f'<span class="recommend-mile">マイル推奨 ¥{val:.2f}/マイル</span>'
    return f'<span class="recommend-cash">現金推奨 ¥{val:.2f}/マイル</span>'

def render_airline_table(label: str, data: dict, pax: float, trip_mult: int):
    st.markdown(f"#### {label}")
    rows = []
    for cls, cls_label in [("economy", "エコノミー"), ("business", "ビジネス")]:
        d = data.get(cls, {})
        if not d or d.get("cash_jpy", 0) == 0:
            rows.append({
                "クラス": cls_label,
                "現金最安値（合計）": "—",
                "必要マイル（合計）": "—",
                "諸税（合計）": "—",
                "1マイルの価値": "—",
                "判定": "対象外",
                "_verdict": None,
            })
            continue
        tm = trip_mult
        cash  = round(d["cash_jpy"]  * pax * tm)
        miles = round(d["miles"]     * pax * tm)
        tax   = round(d["tax_jpy"]   * pax * tm)
        val   = mile_value(cash, tax, miles)
        rows.append({
            "クラス": cls_label,
            "現金最安値（合計）": f"¥{cash:,}",
            "必要マイル（合計）": f"{miles:,} マイル",
            "諸税（合計）": f"¥{tax:,}",
            "1マイルの価値": f"¥{val:.2f}" if val else "—",
            "判定": ("マイル推奨" if val and val >= 2.0 else "現金推奨") if val else "対象外",
            "_verdict_val": val,
            "_notes": d.get("notes", ""),
        })

    for r in rows:
        col1, col2, col3, col4, col5, col6 = st.columns([1.2, 1.5, 1.5, 1.3, 1.3, 1.5])
        col1.write(f"**{r['クラス']}**")
        col2.write(r["現金最安値（合計）"])
        col3.write(r["必要マイル（合計）"])
        col4.write(r["諸税（合計）"])
        col5.write(r["1マイルの価値"])
        val = r.get("_verdict_val")
        if val is None:
            col6.markdown('<span class="recommend-na">対象外</span>', unsafe_allow_html=True)
        elif val >= 2.0:
            col6.markdown(f'<span class="recommend-mile">マイル推奨</span>', unsafe_allow_html=True)
        else:
            col6.markdown(f'<span class="recommend-cash">現金推奨</span>', unsafe_allow_html=True)
        if r.get("_notes"):
            st.caption(r["_notes"])
    st.markdown("---")

# ─── 履歴管理（セッション） ─────────────────────────────────────
if "history" not in st.session_state:
    st.session_state.history = []

def save_to_history(entry: dict):
    st.session_state.history.insert(0, entry)
    if len(st.session_state.history) > 20:
        st.session_state.history.pop()

# ─── UI ────────────────────────────────────────────────────────
st.title("✈ ANA / JAL マイル vs 現金 比較アプリ")
st.caption("Powered by Claude AI (web search)")

# サイドバー：APIキー & 履歴
with st.sidebar:
    st.header("設定")
    api_key = st.text_input(
        "Anthropic API キー",
        type="password",
        value=os.environ.get("ANTHROPIC_API_KEY", ""),
        help="sk-ant-... の形式のキーを入力してください",
    )

    st.divider()
    st.header("📋 調査履歴")
    if st.session_state.history:
        if st.button("🗑 履歴をすべて削除", use_container_width=True):
            st.session_state.history = []
            st.rerun()
        for i, h in enumerate(st.session_state.history):
            label = f"{h['origin']}→{h['dest']}  {h['dep_date']}  {h['trip_label']}"
            if st.button(label, key=f"hist_{i}", use_container_width=True):
                st.session_state.restore = h
                st.rerun()
    else:
        st.caption("まだ履歴がありません")

# 履歴から復元
restore = st.session_state.pop("restore", None)

# ─── 入力フォーム ───────────────────────────────────────────────
with st.form("search_form"):
    st.subheader("フライト条件")
    col1, col2 = st.columns(2)
    with col1:
        origin = st.text_input("出発地（空港コード）", value=restore["origin"] if restore else "FUK").upper()
        dep_date = st.date_input("搭乗日", value=datetime.strptime(restore["dep_date"], "%Y-%m-%d").date() if restore else date.today())
    with col2:
        dest = st.text_input("到着地（空港コード）", value=restore["dest"] if restore else "").upper()
        route_sel = st.selectbox("国内 / 国際線", ["自動判別", "国内線", "国際線"],
                                 index=["自動判別","国内線","国際線"].index(restore["route_sel"]) if restore else 0)

    trip_mode = st.radio("片道 / 往復", ["片道", "往復"], horizontal=True,
                         index=0 if (not restore or restore["trip_label"]=="片道") else 1)

    st.subheader("搭乗人数")
    col_a, col_c = st.columns(2)
    with col_a:
        adults = st.number_input("大人（人）", min_value=1, max_value=9,
                                 value=restore["adults"] if restore else 1)
    with col_c:
        num_children = st.number_input("子ども（人）", min_value=0, max_value=6,
                                       value=len(restore["child_ages"]) if restore else 0)

    child_ages: list[int] = []
    if num_children > 0:
        st.caption("子どもの年齢を入力してください（国内線: 3〜11歳が小児、国際線: 2〜11歳がChild）")
        cols = st.columns(int(num_children))
        prev_ages = (restore["child_ages"] if restore else []) + [6] * num_children
        for i, c in enumerate(cols):
            age = c.number_input(f"子ども{i+1}（歳）", min_value=0, max_value=17,
                                 value=prev_ages[i] if i < len(prev_ages) else 6,
                                 key=f"child_{i}")
            child_ages.append(age)

    submitted = st.form_submit_button("🔍 リアルタイム調査・比較する", use_container_width=True)

# ─── 実行 ──────────────────────────────────────────────────────
if submitted or restore:
    if not api_key:
        st.error("サイドバーに Anthropic API キーを入力してください。")
        st.stop()
    if not dest:
        st.error("到着地を入力してください。")
        st.stop()

    # ルート種別
    if route_sel == "自動判別":
        route_type = detect_route_type(origin, dest)
    elif route_sel == "国内線":
        route_type = "domestic"
    else:
        route_type = "intl"

    season = get_season(dep_date, route_type)
    trip_mult = 2 if trip_mode == "往復" else 1
    pax = calc_pax_factor(adults, child_ages, route_type)

    # 復元時はAPIを叩かない
    if restore:
        result_data = restore["result_data"]
        st.info(f"📋 履歴から復元: {restore['origin']}→{restore['dest']}  {restore['dep_date']}")
    else:
        prompt = build_prompt(origin, dest, dep_date.isoformat(), route_type, season,
                              "rt" if trip_mode == "往復" else "ow", adults, child_ages)
        with st.spinner("Claude AIがANA/JAL公式情報をリアルタイム検索中..."):
            try:
                result_data = call_claude(prompt, api_key)
            except Exception as e:
                st.warning(f"自動取得に失敗しました（{e}）。フォールバック値で表示します。手動修正欄で上書き可能です。")
                result_data = fallback_data(route_type)

        save_to_history({
            "origin": origin, "dest": dest,
            "dep_date": dep_date.isoformat(),
            "route_sel": route_sel, "trip_label": trip_mode,
            "adults": adults, "child_ages": child_ages,
            "result_data": result_data,
        })

    # ─── 結果表示 ────────────────────────────────────────────────
    st.divider()
    route_label = "国内線" if route_type == "domestic" else "国際線"
    st.subheader(f"📊 比較結果：{origin} → {dest}  {dep_date}  {trip_mode}  {route_label}")
    col_s1, col_s2, col_s3 = st.columns(3)
    col_s1.metric("路線種別", route_label)
    col_s2.metric("シーズン", season)
    col_s3.metric("換算人数係数", f"{pax:.1f} 人分")

    st.markdown("#### 表の見方")
    st.caption("1マイルの価値が **¥2.00 以上 → マイル推奨**、未満 → 現金推奨。合計額は人数・往復を加味済み。")

    col_ana, col_jal = st.columns(2)
    with col_ana:
        render_airline_table("ANA", result_data.get("ana", {}), pax, trip_mult)
    with col_jal:
        render_airline_table("JAL", result_data.get("jal", {}), pax, trip_mult)

    # ─── 手動修正 ────────────────────────────────────────────────
    with st.expander("✏️ 数値を手動で修正して再計算する"):
        st.caption("自動取得値が実際と異なる場合、大人1名・片道ベースの数値を上書きしてください。")
        manual_data = {}
        for airline in ["ana", "jal"]:
            st.markdown(f"**{airline.upper()}**")
            manual_data[airline] = {}
            for cls, cls_label in [("economy", "エコノミー"), ("business", "ビジネス")]:
                d = result_data.get(airline, {}).get(cls, {})
                mc1, mc2, mc3 = st.columns(3)
                cash_v  = mc1.number_input(f"{cls_label} 現金（円）",  value=d.get("cash_jpy", 0), key=f"m_{airline}_{cls}_cash", step=1000)
                miles_v = mc2.number_input(f"{cls_label} マイル",      value=d.get("miles", 0),    key=f"m_{airline}_{cls}_miles", step=500)
                tax_v   = mc3.number_input(f"{cls_label} 諸税（円）",  value=d.get("tax_jpy", 0),  key=f"m_{airline}_{cls}_tax", step=100)
                manual_data[airline][cls] = {"cash_jpy": cash_v, "miles": miles_v, "tax_jpy": tax_v, "notes": "手動入力"}

        if st.button("🔄 手動値で再計算", use_container_width=True):
            st.subheader("📊 手動修正後の比較結果")
            col_m1, col_m2 = st.columns(2)
            with col_m1:
                render_airline_table("ANA（手動）", manual_data["ana"], pax, trip_mult)
            with col_m2:
                render_airline_table("JAL（手動）", manual_data["jal"], pax, trip_mult)

    st.caption("※ 表示価格・マイル数は参考値です。実際の予約前に各公式サイトでご確認ください。")
