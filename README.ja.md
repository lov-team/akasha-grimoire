<div align="center">

# Akasha Grimoire · アカシャ秘典

**一度きりの成功した Agent 協働を、チームが繰り返し使える能力へ。**

[![Agent Skills](https://img.shields.io/badge/Agent_Skills-22-6C5CE7?style=flat-square)](#スキル一覧)
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

1. Codex に GPT Image、Grok、Seedance、Fish Audio、Suno のメディア処理を依頼します。
2. Key がない場合、Agent は LovBrowser のデバイス認証 QR、クリック可能なリンク、短いコードを表示します。
3. スキャンして登録またはログインし、同じコードを確認します。ローカルクライアントが自動でポーリングし、認証情報を保存して `/v1/models` で検証します。
4. 検証後、元のメディア処理を一度だけ続行します。実際の Key はチャット、クリップボード、コマンド引数を通りません。

`python3 shared/akasha_credentials.py status|start|finish|cancel|rollback` でも管理できます。既定の保存先は `~/.config/akasha/credentials.env` です。優先順位は専用環境変数 > `NEW_API_API_KEY` > ユーザー認証情報 > `OPENAI_API_KEY` です。

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
| [`agent-task-supervisor`](skills/agent-task-supervisor/) | Spec/Epic/Issue グラフによる複数 task の監督、調整、受け入れ確認 | Issue が計画と受け入れマトリクスを策定し、Luna max Codex worker が実装、直接の親が監視 |
| [`codex-app-development`](skills/codex-app-development/) | 独立 Issue 計画/受け入れ task から Codex App developer を作成 | Epic 監督 → Issue 計画/受け入れ → Luna max developer、worktree 隔離、独立 diff Review |

### コンテンツ制作

| Skill | 主な用途 | 提供する能力 |
| --- | --- | --- |
| [`content-pipeline`](skills/content-pipeline/) | 中国語のアイデア、記事、資料、中断した作業を小紅書形式の画像投稿パッケージへ変換 | コンテンツ契約、出典調査、原文忠実度、コピー、内容マップ、HTML/CSS カード、必要時の画像生成、モバイル QA |

`content-pipeline` 単体ではテキスト中心の HTML/CSS カードを制作できます。写真やイラストの生成が必要な場合は、`gpt-image-generation` と `akasha-key-setup` もインストールしてください。

### 動画制作

| Skill | 主な用途 | 提供する能力 |
| --- | --- | --- |
| [`video-production`](skills/video-production/) | アイデア、記事、脚本、既存素材から完成動画を制作 | 演出 → 素材/生成 → EDL 編集 → 技術・クリエイティブ QA の段階ゲート統括 |
| [`video-director`](skills/video-director/) | 脚本、演出、絵コンテ、shot list、生成前計画 | narrative beat、coverage、撮影・motion、continuity bible、生成計画 |
| [`video-source-research`](skills/video-source-research/) | B-roll、動画、画像、音声素材の検索・取得・整理 | shot ごとの検索、yt-dlp/直接取得、ffprobe、SHA-256、追跡可能な `sources.json` |
| [`video-editing`](skills/video-editing/) | 一般的な rough/fine cut、B-roll、音声、字幕、書き出し | Review 可能な `edl.json`、決定論的 FFmpeg render、音声欠落補完、出力再検証 |
| [`video-qc`](skills/video-qc/) | 生成 clip、preview、最終動画の受け入れ確認 | 全体 decode、黒画面/freeze/silence/音量/字幕、代表 frame、物語連続性 Review |
| [`article-to-short-video`](skills/article-to-short-video/) | 中国語の長文・人物記事・論説を 60〜120 秒の縦型動画へ変換 | 共通制作 loop に証拠境界、Fish narration、Suno BGM、縦型専用検査を追加 |

完全な制作には上記 5 つの共通動画 Skill をまとめて導入してください。`video-production` は shot ごとに Seedance、Gemini Omni、Grok、GPT Image、Fish Audio、Suno へ振り分けます。Web 動画の取得には yt-dlp、決定論的な編集と QA には FFmpeg/ffprobe が必要です。

### 画像・ゲーム・音声制作

| Skill | 主な用途 | 提供する能力 |
| --- | --- | --- |
| [`game-asset-forge`](skills/game-asset-forge/) | キャラクター、背景、UI、アイコン、Tileset、VFX、Sprite、アニメーションフレーム | アセット契約、smoke 後の一括生成、alpha/halo QA、キャラクター一貫性、ループ、2×2 tile、エンジン import、スクリーンショットによる受け入れ確認 |
| [`gpt-image-generation`](skills/gpt-image-generation/) | GPT Image の生成、参照画像編集、エンドポイント診断 | OpenAI-compatible generations/edits、base URL 正規化、安全な保存、プロトコル制限、失敗診断 |
| [`grok-media-generation`](skills/grok-media-generation/) | Grok 画像/動画の生成と編集 | OpenAI-compatible media endpoint を呼び出し、現行 CPA の `video.file_id` resolver で生成結果を引き継ぎ、無出力ポーリング後に実ファイルを安全に保存 |
| [`suno-music-generation`](skills/suno-music-generation/) | 曲の説明または独自歌詞から音楽を生成 | Suno 非同期タスクの送信、5 秒間隔のローカル無出力ポーリング、全候補音声・カバー・任意動画のダウンロードと個別確認 |
| [`fish-audio-speech`](skills/fish-audio-speech/) | Fish Audio のナレーション、音声参照、文字起こし | OpenAI-compatible TTS/STT、reference id、ローカル参照音声、言語・タイムスタンプ制御、安全な保存 |

### App 子 task と CLI 開発 worker

開発は三層ループを使います。**Epic 監督 App が ready Issue を発見 → 独立 Issue App が実装計画と受け入れマトリクスを策定 → GPT-5.6 Luna・`thinking=max` の Codex worker が実装 → Issue App が独立 Review し P0–P2 を元 worker に返却 → Issue が Evidence を書き、Epic が読み取る**。すべてのコード開発は、frontend/backend や task 規模による worker の自動切り替えを行わず、隔離された Codex App task/worktree を既定とします。純粋な media 生成は対応する media Skill を使います。ユーザーが別 worker を明示した場合は最下層だけを置換します。Issue App は業務コードを書きません。一方向の指示送信後、直接の親が状態・交付ファイルを 20 秒間隔で最大 20 分監視します。

| Skill | Worker | 特徴 |
| --- | --- | --- |
| [`gemini-cli-development`](skills/gemini-cli-development/) | Gemini CLI | ユーザーが Gemini CLI を明示指定した場合に使用 |
| [`grok-cli-development`](skills/grok-cli-development/) | Grok CLI | ユーザーが Grok CLI を明示指定した場合に使用。内蔵 media 作業は別途利用可能 |
| [`codex-app-development`](skills/codex-app-development/) | Codex App developer | すべてのコード開発の既定 worker。GPT-5.6 Luna・`thinking=max` |
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

$codex-app-development を Issue task から使い、実装計画と受け入れマトリクスを策定してから GPT-5.6 Luna・`thinking=max` の別 Codex App worker を作成してください。developer は実装のみ、Issue task は独立 Review と P0–P2 の差し戻しを担当します。

$content-pipeline を使って中国語の記事を小紅書形式の画像投稿に変換し、原文の主張を保ち、先に表紙方針を確認して、再開可能なローカルパッケージを納品してください。

$video-production を使ってこの商品アイデアを 30 秒の縦型動画にし、演出 package と shot list、素材検索または生成、EDL、render、完成動画 QA まで実行してください。

$video-source-research を使ってこの shot list 向け B-roll を検索・取得し、ffprobe metadata と SHA-256 を含む sources.json を作成してください。

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
| 公式の手動／残高不足リチャージ | `python3 shared/akasha_recharge.py` で決済ページを作成し、金額は LovBrowser ページで選択 | 手動リチャージは残高不足を必要としない。Agent はクリック可能な `publicPageUrl` のみ提示し、QR コードは表示しない。Key/チケットを漏らさない |
| Codex App 三層 task | Epic 監督、Issue 計画/受け入れ task、Luna max developer task/worktree | Epic→Issue→developer の一方向指示、Issue が計画してから委託し、完全 diff を独立 Review |
| CLI worker | 対応するローカル CLI、macOS Terminal、tmux | 初回利用時と更新後に `--version` と `--help` を再確認 |
| 動画編集と素材取得 | FFmpeg/ffprobe、Web 取得には yt-dlp | macOS では `brew install ffmpeg yt-dlp`。取得後も media probe、出典、hash の記録が必要 |

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
├── references/           # ツール事実と専門契約（任意）
└── assets/               # 成果物へコピーする template と resource（任意）
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
