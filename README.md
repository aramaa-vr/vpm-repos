# Aramaa VPM Listing

VCC（VRChat Creator Companion）が参照する、Aramaaのパッケージ配布情報を管理するリポジトリです。パッケージ本体は、登録されたGitHub ReleaseからVCCがダウンロードします。

## VCCで使う

1. [VCCに追加](https://aramaa-vr.github.io/vpm-repos/redirect.html)から、この配布リポジトリを登録します。
2. 対象プロジェクトの `Manage Project` で、使いたいパッケージを追加・更新します。

手動で登録する場合のURL：`https://aramaa-vr.github.io/vpm-repos/vpm.json`

## 登録パッケージ

- [みんなでつかめるだこちてギミック](https://aramaa-vr.github.io/dakochite-gimmick-pages/)
- [おちびちゃんズ化ツール](https://github.com/aramaa-vr/ochibi-chans-converter-tool/blob/master/README.md)

## 管理者向け

- `vpm.json` は配布情報、`latest.json` はパッケージごとの最新バージョンを管理します。
- `scripts/add_release.py` は、配布するZIPから両方のJSONをローカルで更新します。使い方は `python -B scripts/add_release.py --help` で確認できます。公開操作は別途行います。
- パッケージ別の `scripts/add_*_version.py` を使う場合は、`latest.json` も別途更新してください。
