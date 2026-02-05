# Install

`vpm add repo https://aramaa-vr.github.io/vpm-repos/vpm.json`

[Add to VCC](https://aramaa-vr.github.io/vpm-repos/redirect.html)

# Packages
[みんなでつかめるだこちてギミック](https://github.com/aramaa-vr/HoldGimick)

# Develop unitypackage-test
[Add to VCC ver 1.1.1 develop](https://aramaa-vr.github.io/vpm-repos/develop/redirect-ver-1.1.1-unitypackage-test.html)

[Add to VCC aramaa.ochibi-chans-converter-tool.dev](https://aramaa-vr.github.io/vpm-repos/develop/redirect-ochibi-chans-converter-tool-dev.html)

# Tools
`jp.aramaa.ochibi-chans-converter-tool`の新しいバージョンを追加する場合は、最新のバージョンを複製して
バージョン番号とURLを更新するスクリプトを利用できます。

```sh
python scripts/add_create_chibi_version.py 0.3.2
```

書き込み先を別ファイルにしたい場合は `--output` を指定します。

```sh
python scripts/add_create_chibi_version.py 0.3.2 --output develop/vpm-ochibi-chans-converter-tool-dev.next.json
```
