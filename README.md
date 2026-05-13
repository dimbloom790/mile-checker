# ✈ ANA / JAL マイル vs 現金 比較アプリ

## 必要なもの
- Python 3.11 以上
- Anthropic API キー（https://console.anthropic.com で取得）

## ローカル起動手順

```bash
# 1. 依存パッケージをインストール
pip install -r requirements.txt

# 2. 起動
streamlit run app.py
```

ブラウザで `http://localhost:8501` が自動で開きます。  
サイドバーに Anthropic API キーを入力してください。

---

## Streamlit Cloud にデプロイする場合

1. このファイル一式を GitHub リポジトリに push する  
2. https://share.streamlit.io でリポジトリを選択してデプロイ  
3. **Settings → Secrets** に以下を追加する：

```toml
ANTHROPIC_API_KEY = "sk-ant-xxxxxxxx"
```

---

## 環境変数で API キーを渡す場合（ローカル）

```bash
export ANTHROPIC_API_KEY="sk-ant-xxxxxxxx"
streamlit run app.py
```

---

## 機能一覧

| 機能 | 内容 |
|------|------|
| リアルタイム調査 | Claude AI が ANA/JAL 公式情報をウェブ検索して取得 |
| シーズン自動判定 | 搭乗日から L/R/H を判別し正しいマイル数を適用 |
| 人数対応 | 大人・子ども（年齢別）の合計金額を自動算出 |
| 手動修正 | 自動取得値が実態と異なる場合に数値を上書き可能 |
| 履歴機能 | セッション内で最大 20 件を保存・復元 |
| 国内 / 国際線 | 空港コードから自動判別、または手動選択 |
| 片道 / 往復 | 往復は × 2 で合計を算出 |
