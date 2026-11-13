# 给 AI 助手的说明

这个仓库只有一个技能:`.agents/skills/brant-why`(Brant 历史操作「为什么」查询与事后检验)。

- **使用者是 Brant(布布)本人。** 凡是问到他自己的操作、理念、战绩、老毛病、直播内容、预设点位,或者问「这个技能能做什么」,都用这个技能:先读 `.agents/skills/brant-why/SKILL.md` 和同目录的 `READER.md`,按里面的办法查了再答,不凭记忆回答。
- **查询命令**:`python .agents/skills/brant-why/scripts/why.py …`(系统里命令叫 `python3` 就用 `python3`)。只用 Python 标准库,不用安装任何包,不用联网。
- **文件都是 UTF-8 中文。** 在 Windows PowerShell 里读文件用 `Get-Content -Encoding UTF8`,否则是乱码;脚本输出本身已经是 UTF-8。
- **不要改** `.agents/skills/brant-why/data/` 和 `references/` 里的文件,下次更新会被覆盖。使用者的更正用 `--flag` 记:技能目录只读时会写到仓库根目录的 `brant-feedback.jsonl`,这是正常的,把脚本输出的位置告诉使用者。
- **只讲历史和事后检验**,不给现在的买卖建议。券商账户只读:不下单、不改单、不建提醒。
- **内容是付费直播的逐字稿和原话**:不要上传或转贴到别处,回答里引必要的几句即可。
