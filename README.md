# Aramaa VPM Listing

AramaaのVPMパッケージをVCCへ配信するための登録情報と、登録情報を更新するツールを管理するリポジトリです。

## パッケージの利用

ダウンロード・追加・更新は、VRChat Creator Companion（VCC）で行います。[Add to VCC](https://aramaa-vr.github.io/vpm-repos/redirect.html)から配布リポジトリを登録し、対象プロジェクトの `Manage Project` でパッケージを追加してください。

手動で登録する場合のURL：`https://aramaa-vr.github.io/vpm-repos/vpm.json`

- [みんなでつかめるだこちてギミック](https://github.com/aramaa-vr/HoldGimick)
- [だこちてギミック【ワールド版】の説明サイト](https://aramaa-vr.github.io/player-carry-and-throw-pages/)

## 管理するファイル

| ファイル | 用途 |
| --- | --- |
| `vpm.json` | VCCが参照するパッケージのバージョン・配信URL・依存関係・SHA-256 |
| `latest.json` | パッケージごとの最新バージョン情報 |
| `redirect.html` | VCCへこのリポジトリを登録するための案内ページ |
| `scripts/add_release.py` | 確定したローカルZIPから登録情報を生成・更新するツール |
| `scripts/tests/` | 登録ツールのオフラインテスト |

以下は配布情報を管理するための手順です。

## ローカルZIPから登録情報を更新する

登録する内容を確定したパッケージZIPを用意します。ZIP直下の `package.json` が登録情報の入力元です。ツールはネットワークへ接続せず、公開済みReleaseからの取得や公開操作は行いません。

`vpm-repos` 直下で、まず `--dry-run` を付けて差分を確認します。以下の `<VERSION>` は登録するバージョンへ置き換えてください。

```sh
python -B scripts/add_release.py --repo aramaa-vr/player-carry-and-throw --tag "<VERSION>" --zip "../PlayerCarryAndThrow/Library/VpmPackages/jp.aramaa.player-carry-and-throw-<VERSION>.zip" --index-path ../PlayerCarryAndThrow-Distribution/index.json --dry-run
```

確認後、`--dry-run` を外して実行すると、`vpm.json`・`latest.json` と指定した `index.json` をローカルで更新します。`--index-path` を省略した場合は、このリポジトリの2つのJSONだけを更新します。

### 入力と更新の条件

- `--repo` は配信先GitHubリポジトリを `OWNER/REPOSITORY` 形式で指定します。
- `--tag` はZIP内のバージョンと完全一致させます。版番号はSemVer形式とし、先頭に `v` を付けません。
- ZIP名は `<package-name>-<version>.zip` にします。`package.json` にURLがある場合は、生成するRelease添付ファイルのURLとの一致も確認します。
- ZIPのSHA-256を実測し、同じZIPに基づく登録情報を各Listingへ書き込みます。`zipSHA256` はZIP内の `package.json` に含めません。
- `latest.json` は登録済みの版も含めて比較し、既存の最新バージョンを下げません。
- 同一内容の再登録では書き換えません。同じ版に異なる登録情報がある場合はエラーにします。
- 入力不足・不正なJSON・既存登録との競合は書き込み前に検出します。通常の書き込み失敗では変更済みのファイルを復元します。復元にも失敗した場合は、元データを保持する退避ファイルの場所をエラーに表示します。
- ツールはコミット・Pushを行いません。別のListingを対象にする場合は `--path` と `--latest-path` を指定します。

## 配信時の確認

ローカルでの登録情報の更新だけでは、ZIPやListingは公開されません。配信する際は次の順序で確認します。

1. 登録情報の生成に使ったZIPを、そのままGitHub Releaseへアップロードします。
2. 登録した配信URLから別ファイルへダウンロードし、元ZIP・登録情報のSHA-256と一致することを確認します。
3. 配布側の `index.json` と、このリポジトリの `vpm.json`・`latest.json` の対象パッケージ情報を確認して公開します。
4. VCCでリポジトリを読み込み、パッケージの表示・追加・更新を確認します。

取得失敗やハッシュの不一致がある場合はListingの公開を止め、ZIPと登録情報の組み合わせを確認してください。確認用にダウンロードしたファイルから登録情報を作り直したり、異なるハッシュで既存登録を上書きしたりしないでください。

## ツールの検証

```sh
python -B -m unittest discover -s scripts/tests -v
```

テストは一時ファイルを使ってオフラインで実行します。公開用Listingの更新や公開操作は行いません。

既存の `add_dakochite-gimmick_version.py` と `add_ochibi-chans-converter-tool_version.py` はパッケージ別の登録スクリプトです。これらを使う場合は、`latest.json` も別途更新してください。

仕様の参照先：[VPM Packages](https://vcc.docs.vrchat.com/vpm/packages/)、[SemVer](https://semver.org/)。
