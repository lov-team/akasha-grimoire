<div align="center">

# Akasha Grimoire · アカシャ秘典

**一度きりの成功した Agent 協働を、チームが繰り返し使える能力へ。**

[![Agent Skills](https://img.shields.io/badge/Agent_Skills-9-6C5CE7?style=flat-square)](#スキル一覧)
[![Languages](https://img.shields.io/badge/Languages-中文_·_English_·_日本語-2D9CDB?style=flat-square)](#)
[![Source of Truth](https://img.shields.io/badge/Source_of_Truth-Git-2EA44F?style=flat-square)](#設計原則)

[简体中文](README.md) · [English](README.en.md) · **日本語**

</div>

---

Akasha Grimoire は、チームで共有する Agent Skill コレクションです。タスク境界、検証済みのツール契約、決定的なスクリプト、低ノイズな待機、独立した受け入れ確認をインストール可能な能力としてまとめます。Agent の推測と無駄なポーリングを減らし、証拠に基づいて実務を完了させることが目的です。

## 設計原則

- **契約を先に定義**：トリガー、入力、出力、非対象、完了条件を実行前に明確にします。
- **実行時の事実を優先**：CLI のバージョン、引数、エンドポイント、制限は現在の環境と信頼できる実装で確認します。
- **低ノイズ実行**：機械的なポーリングはスクリプトに任せ、モデルの token は判断と Review に使います。
- **独立した受け入れ確認**：worker の完了報告だけではなく、累積 diff、テスト、成果物、リモート Git の証拠を確認します。
- **唯一の情報源**：共有 Skill の正本はこのリポジトリです。ローカルにはシンボリックリンクで導入します。

## スキル一覧

### 協働とガバナンス

| Skill | 主な用途 | 提供する能力 |
| --- | --- | --- |
| [`agent-task-supervisor`](skills/agent-task-supervisor/) | 複数タスクの監督、調整、待機、受け入れ確認 | コンパクトなタスクボード。Codex App は現在の上限である 120 秒単位、外部 Agent は 240 秒の無出力待機スクリプトを使い、ブロック、逸脱、正式 Review、P0–P2 の場合だけ詳細を確認 |

### 画像・ゲーム・音声制作

| Skill | 主な用途 | 提供する能力 |
| --- | --- | --- |
| [`game-asset-forge`](skills/game-asset-forge/) | キャラクター、背景、UI、アイコン、Tileset、VFX、Sprite、アニメーションフレーム | アセット契約、smoke 後の一括生成、alpha/halo QA、キャラクター一貫性、ループ、2×2 tile、エンジン import、スクリーンショットによる受け入れ確認 |
| [`gpt-image-generation`](skills/gpt-image-generation/) | GPT Image の生成、参照画像編集、エンドポイント診断 | OpenAI-compatible generations/edits、base URL 正規化、安全な保存、プロトコル制限、失敗診断 |
| [`suno-music-generation`](skills/suno-music-generation/) | 曲の説明または独自歌詞から音楽を生成 | Suno 非同期タスクの送信、5 秒間隔のローカル無出力ポーリング、全候補音声・カバー・任意動画のダウンロードと個別確認 |
| [`fish-audio-speech`](skills/fish-audio-speech/) | Fish Audio のナレーション、音声参照、文字起こし | new-api 経由の TTS/STT、reference id、ローカル参照音声、言語・タイムスタンプ制御、安全な保存 |

### CLI 開発 worker

4 つの CLI Skill は共通の閉ループを採用します。**メイン Agent が契約を定義 → 可視 Terminal + tmux で実装 → 軽量な状態/納品ファイル → メイン Agent が独立 Review → 同じセッションで修正**。worker の思考過程は収集せず、要件判断を CLI に丸投げしません。

| Skill | Worker | 特徴 |
| --- | --- | --- |
| [`grok-cli-development`](skills/grok-cli-development/) | Grok CLI | 開発、画像/動画生成、中国語の計画、自己確認、同一セッションでの修正 |
| [`gemini-cli-development`](skills/gemini-cli-development/) | Gemini CLI | ローカルで検証した CLI 契約に基づく開発と納品 |
| [`claude-code-cli-development`](skills/claude-code-cli-development/) | Claude Code | 権限モード、セッション継続、状態納品、独立した受け入れ確認 |
| [`codex-cli-development`](skills/codex-cli-development/) | Codex CLI | 独立した対話 TUI で実装し、Codex App のタスク管理とは分離 |

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

$game-asset-forge を使って 2D ゲーム用の透明背景キャラクターアニメーションを作り、smoke 後に一括生成してください。

$suno-music-generation を使ってこの曲の説明から音楽を生成し、すべての候補をダウンロードしてください。

$fish-audio-speech を使ってナレーションを音声化し、冒頭・中盤・末尾を確認してください。
```

## 認証情報と実行環境

| 能力 | 設定 | 契約 |
| --- | --- | --- |
| GPT Image | `IMAGE_PROXY_BASE_URL`、`IMAGE_PROXY_API_KEY`、または互換 OpenAI 環境変数 | key をコマンド引数、prompt、ログ、リポジトリに保存しない |
| Suno / Fish Audio | `NEW_API_BASE_URL`、`NEW_API_API_KEY`、または互換 OpenAI 環境変数 | 実リクエストはクォータを消費。基本テストでは外部生成サービスを呼び出さない |
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

---

<div align="center">

**Agent の能力を一度の会話で終わらせず、検証・再利用・進化できる仕事の仕組みに。**

</div>
