<div align="center">

# Akasha Grimoire · アカシャ秘典

**一度きりの成功した Agent 協働を、チームが繰り返し使える能力へ。**

[![Agent Skills](https://img.shields.io/badge/Agent_Skills-10-6C5CE7?style=flat-square)](#スキル一覧)
[![Best on Codex App](https://img.shields.io/badge/Best_on-Codex_App-111827?style=flat-square)](#graph-engineering)
[![Languages](https://img.shields.io/badge/Languages-中文_·_English_·_日本語-2D9CDB?style=flat-square)](#)
[![Source of Truth](https://img.shields.io/badge/Source_of_Truth-Git-2EA44F?style=flat-square)](#設計原則)
[![License: GPL v3](https://img.shields.io/badge/License-GPL_v3-blue?style=flat-square)](LICENSE)

[简体中文](README.md) · [English](README.en.md) · **日本語**

</div>

---

Akasha Grimoire は、**Codex App** での利用に最適化された、チーム共有の Agent Skill コレクションです。タスク境界、検証済みのツール契約、決定的なスクリプト、低ノイズな待機、独立した受け入れ確認をインストール可能な能力としてまとめます。Agent の推測と無駄なポーリングを減らし、証拠に基づいて実務を完了させます。個別の Skill は互換 Agent や CLI でも利用できます。

> **画像・動画・音声・音楽の生成をすぐに試したい場合：** [LovBrowser](https://lovbrowser.com) でアカウントを登録し、クレジットを購入してください。Akasha Grimoire は既定で `https://newapi.1234bot.com/v1` に接続します。1 つの new-api key で GPT Image、Grok、Seedance、Fish Audio、Suno を利用でき、Skill ごとの Base URL 設定は不要です。

## 1 分で利用開始

1. [lovbrowser.com](https://lovbrowser.com) を開き、登録またはログインします。
2. プランを選択するか残高をチャージし、サイトの案内に従って支払いを完了します。
3. API Key 管理画面で new-api key を作成してコピーします。
4. 環境変数または認証情報マネージャーで安全に設定します。

   ```bash
   export NEW_API_API_KEY="<your-new-api-key>"
   ```

5. Codex に GPT Image の画像生成、Grok/Seedance の動画生成、Fish Audio の音声合成、Suno の音楽生成を依頼します。対応する Skill が既定 endpoint を自動的に使用します。

key を prompt、コマンド引数、ログ、リポジトリに保存しないでください。プライベート環境に接続する場合のみ `NEW_API_BASE_URL` または `--base-url` を使用します。

## 設計原則

- **契約を先に定義**：トリガー、入力、出力、非対象、完了条件を実行前に明確にします。
- **実行時の事実を優先**：CLI のバージョン、引数、エンドポイント、制限は現在の環境と信頼できる実装で確認します。
- **低ノイズ実行**：機械的なポーリングはスクリプトに任せ、モデルの token は判断と Review に使います。
- **独立した受け入れ確認**：worker の完了報告だけではなく、累積 diff、テスト、成果物、リモート Git の証拠を確認します。
- **唯一の情報源**：共有 Skill の正本はこのリポジトリです。ローカルにはシンボリックリンクで導入します。

## Graph Engineering

Graph Engineering は、納品作業を一時的な prompt の列ではなく、追跡可能な作業グラフとしてモデル化します。

`Spec → Epic → Issue → Agent Task → Evidence`

| 階層 | 責務 |
| --- | --- |
| **Spec** | 目標、境界、非対象、重要な判断、最終受け入れ条件を定義するルート契約 |
| **Epic** | Spec をマイルストーンのサブグラフに分解し、Issue 間依存と集約受け入れを管理 |
| **Issue** | owner、範囲、依存、出力、検証を持つ最小実行ノード |
| **Agent Task** | Codex App または外部 worker における Issue の実行インスタンス。Issue の記録を置き換えない |
| **Evidence** | diff、test、成果物、Review、remote SHA で Issue を閉じ、Epic と Spec へ完了を集約 |

実装と受け入れ確認を必要とする作業はすべて Issue 駆動にします。各 task を Issue に対応付け、依存関係を `depends_on`、`blocks`、`produces`、`validates` の edge で表し、準備済みの node だけを並列実行します。方向変更では先に Spec/Epic/Issue グラフを更新し、完了は Evidence で末端から上位へ集約します。Codex App は task、分離 worktree、長時間の境界付き待機、受け入れループを扱えるため、推奨 control plane です。

## スキル一覧

### 協働とガバナンス

| Skill | 主な用途 | 提供する能力 |
| --- | --- | --- |
| [`agent-task-supervisor`](skills/agent-task-supervisor/) | Spec/Epic/Issue グラフによる複数 task の監督、調整、受け入れ確認 | node、関係 edge、コンパクトなタスクボード。Codex App は現在の上限である 120 秒単位、外部 Agent は 240 秒の無出力待機スクリプトを使い、ブロック、逸脱、正式 Review、P0–P2 の場合だけ詳細を確認 |

### 画像・ゲーム・音声制作

| Skill | 主な用途 | 提供する能力 |
| --- | --- | --- |
| [`game-asset-forge`](skills/game-asset-forge/) | キャラクター、背景、UI、アイコン、Tileset、VFX、Sprite、アニメーションフレーム | アセット契約、smoke 後の一括生成、alpha/halo QA、キャラクター一貫性、ループ、2×2 tile、エンジン import、スクリーンショットによる受け入れ確認 |
| [`gpt-image-generation`](skills/gpt-image-generation/) | GPT Image の生成、参照画像編集、エンドポイント診断 | OpenAI-compatible generations/edits、base URL 正規化、安全な保存、プロトコル制限、失敗診断 |
| [`grok-media-generation`](skills/grok-media-generation/) | Grok 画像/動画の生成と編集 | OpenAI-compatible media endpoint を呼び出し、現行 CPA の `video.file_id` resolver で生成結果を引き継ぎ、無出力ポーリング後に実ファイルを安全に保存 |
| [`article-to-short-video`](skills/article-to-short-video/) | 中国語の長文・人物記事・論説を 60〜120 秒の縦型動画へ変換 | 証拠境界、Fish 参照音声、Suno BGM、実音声ベースのタイミング、FFmpeg 合成、音量・黒フレーム・字幕の受け入れ確認 |
| [`suno-music-generation`](skills/suno-music-generation/) | 曲の説明または独自歌詞から音楽を生成 | Suno 非同期タスクの送信、5 秒間隔のローカル無出力ポーリング、全候補音声・カバー・任意動画のダウンロードと個別確認 |
| [`fish-audio-speech`](skills/fish-audio-speech/) | Fish Audio のナレーション、音声参照、文字起こし | OpenAI-compatible TTS/STT、reference id、ローカル参照音声、言語・タイムスタンプ制御、安全な保存 |

### CLI 開発 worker

4 つの CLI Skill は共通の閉ループを採用します。**メイン Agent が契約を定義 → 可視 Terminal + tmux で実装 → 軽量な状態/納品ファイル → メイン Agent が独立 Review → 同じセッションで修正**。worker の思考過程は収集せず、要件判断を CLI に丸投げしません。

| Skill | Worker | 特徴 |
| --- | --- | --- |
| [`grok-cli-development`](skills/grok-cli-development/) | Grok CLI | 開発、画像/動画生成、中国語の計画、自己確認、同一セッションでの修正 |
| [`gemini-cli-development`](skills/gemini-cli-development/) | Gemini CLI | ローカルで検証した CLI 契約に基づく開発と納品 |
| [`claude-code-cli-development`](skills/claude-code-cli-development/) | Claude Code | 権限モード、セッション継続、状態納品、独立した受け入れ確認 |
| [`codex-cli-development`](skills/codex-cli-development/) | Codex CLI | 独立した対話 TUI で実装し、Codex App のタスク管理とは分離 |

## 実例：Amazon 向けスリッパ商品メディア

この実例では、架空のミストブルー人体工学 EVA スライドサンダルを題材に、商品ビジュアル一式を作成しました。色、ストラップの溝、ロッカーソールを固定し、Amazon 向け白背景メイン画像、浴室での着用画像、素材ディテール画像を生成。その後 Grok と Seedance でそれぞれ 5 秒の商品動画を作成し、デコード、メタデータ、代表フレームを検証しました。

![Amazon スリッパのメイン画像](docs/assets/amazon-slippers-main.jpg)

| 成果物 | 能力 | 検証結果 |
| --- | --- | --- |
| メイン、使用シーン、ディテール画像 | `gpt-image-generation` / `gpt-image-2` | 1536 px の商品画像。メイン画像の四隅は純白 |
| スタジオ商品動画 | `grok-media-generation` / `grok-imagine-video` | 5.04 秒、848 × 480、24 fps |
| 回転商品動画 | `seedance-video-generation` / `doubao-seedance-2-0-260128` | 5.04 秒、1280 × 720、24 fps |

![上段は Grok、下段は Seedance の代表フレーム](docs/assets/amazon-slippers-video-comparison.jpg)

この例は制作上の限界も示します。text-to-video は方向性の確認には速い一方、商品の色、溝、アウトソール形状が変化する場合があります。実際の商品ページでは承認済みの商品写真を image-to-video の参照に使い、防滑・防水・クッション性などの表現には実測や仕入先の証拠を用意してください。

## クイックインストール

リポジトリを clone した後、リポジトリを唯一の情報源として維持するため、シンボリックリンクを推奨します。

```bash
git clone git@github.com:lov-team/akasha-grimoire.git
cd akasha-grimoire
```

1 つの Skill を導入：

```bash
skill_name="suno-music-generation"
skills_home="${CODEX_HOME:-$HOME/.codex}/skills"
mkdir -p "$skills_home"
ln -s "$PWD/skills/$skill_name" "$skills_home/$skill_name"
```

既存の対象を保持しながら全 Skill を導入：

```bash
skills_home="${CODEX_HOME:-$HOME/.codex}/skills"
mkdir -p "$skills_home"

for skill_dir in "$PWD"/skills/*; do
  skill_name="$(basename "$skill_dir")"
  target="$skills_home/$skill_name"
  if [ -e "$target" ] || [ -L "$target" ]; then
    echo "既存の対象を保持：$target"
  else
    ln -s "$skill_dir" "$target"
  fi
done
```

既存対象を強制上書きしないでください。先に差分を監査し、不明な内容は復元可能な形で保持します。

## 使用例

```text
$agent-task-supervisor を使ってタスクを低ノイズで監督し、納品後に独立した受け入れ確認を行ってください。

$agent-task-supervisor を使ってこの Spec を Epic/Issue の依存グラフに分解し、Codex App では準備済み Issue だけを開始し、Evidence で末端からグラフ全体を閉じてください。

$game-asset-forge を使って 2D ゲーム用の透明背景キャラクターアニメーションを作り、smoke 後に一括生成してください。

$grok-media-generation を使ってこの画像または動画を生成・編集し、保存した実ファイルを確認してください。

$suno-music-generation を使ってこの曲の説明から音楽を生成し、すべての候補をダウンロードしてください。

$fish-audio-speech を使ってナレーションを音声化し、冒頭・中盤・末尾を確認してください。
```

## 認証情報と実行環境

| 能力 | 設定 | 契約 |
| --- | --- | --- |
| 既定 new-api | `https://newapi.1234bot.com/v1` | Base URL 設定は不要。プライベート環境のみ `NEW_API_BASE_URL` または `--base-url` で上書き |
| GPT Image | `IMAGE_PROXY_API_KEY`、`NEW_API_API_KEY`、`OPENAI_API_KEY` | key をコマンド引数、prompt、ログ、リポジトリに保存しない |
| Grok / Seedance | 専用 key、`NEW_API_API_KEY`、`OPENAI_API_KEY` | 実リクエストは課金対象。規模を広げる前に 1 件の smoke を実行 |
| Suno / Fish Audio | `NEW_API_API_KEY` または `OPENAI_API_KEY` | 実リクエストはクォータを消費。基本テストでは外部生成サービスを呼び出さない |
| 公式残高リチャージ | `AKASHA_RECHARGE_USD` または各スクリプトの `--recharge-usd`（既定 10 USD） | 公式 new-api のみ。1 コマンド最大 1 回の QR 充電と失敗 HTTP の 1 回再試行。Agent は `qrPngPath` を表示し `publicPageUrl` を提示。Key/チケットを漏らさない |
| CLI worker | 対応するローカル CLI、macOS Terminal、tmux | 初回利用時と更新後に `--version` と `--help` を再確認 |

## 検証

各 Skill には標準 frontmatter と `agents/openai.yaml` があります。変更後、最低限次を実行します。

```bash
validator="${CODEX_HOME:-$HOME/.codex}/skills/.system/skill-creator/scripts/quick_validate.py"
for skill_dir in skills/*; do
  python3 "$validator" "$skill_dir"
done

git diff --check
```

新しいスクリプトには構文チェックと副作用のない動作テストも必要です。画像、音楽、音声、動画、外部書き込みでは、ローカルの模擬サービスまたは限定的な smoke test から始めます。E2E 未検証の能力は必ず明記します。

## 構成とメンテナンス

```text
skills/<skill-name>/
├── SKILL.md              # トリガー説明と中核作業契約
├── agents/openai.yaml    # Agent UI メタデータ
├── scripts/              # 再現可能で決定的な実行ロジック（任意）
└── references/           # ツール事実と専門契約（任意）
```

- `SKILL.md` は簡潔にし、複雑な事実は一階層下の `references/` に置きます。
- Skill ごとの README、changelog、cache、作業過程のまとめは追加しません。
- CLI/API 契約変更時は、実際のバージョン、help、schema、信頼できる実装を再確認します。
- 正式納品前に累積 diff を読み、TODO、認証情報、ローカル絶対パス、cache、生成物を確認します。
- push 後にローカル SHA、リモート SHA、重要ファイルの内容を照合します。

## ライセンス

本プロジェクトは [GNU General Public License v3.0](LICENSE) で公開されています。

---

<div align="center">

**Agent の能力を一度の会話で終わらせず、検証・再利用・進化できる仕事の仕組みに。**

</div>
