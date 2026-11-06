# LA-MULANA 2 官方简中修正

修正官方简体中文的谜题线索、剧情与名称，共 87 项、110 处文本调整。[查看全部修改](CHANGES.md)（含谜题线索）。

## 下载与安装

在 [Release](https://github.com/skeyep/La-Mulana-2-CHS-Fixes/releases/latest) 下载适合的平台包，关闭游戏并完整解压。

- **Windows**：双击 `Install.cmd`，按提示安装，在游戏设置中选择简体中文。检查和还原使用 `Support/Check.cmd`、`Support/Restore.cmd`。
- **Steam Deck／Linux**：在 Steam 游戏属性的兼容性设置中强制 Proton，等待 Windows 版下载，启动一次并退出。进入桌面模式，在解压目录打开终端，运行 `bash ./Install.sh`，然后在游戏中选择简体中文。检查和还原使用 `bash ./Support/Check.sh`、`bash ./Support/Restore.sh`。

自动查找失败时，在安装命令后加游戏目录路径。覆盖升级时直接运行新版安装入口；游戏目录的 `.lm2chs-fixes` 保留原版备份和独立还原入口。

适用于 Windows Steam 版 build 9559015（Deck 使用 Proton）。0.1.0 为测试版，长文本排版及 Steam Deck 实机兼容性待验。

## 内容

[完整修改对照](CHANGES.md) · [可编辑修改数据](translations/changes.json)

日文手写地名标题保留，简中地名在文本中统一。新增字形使用思源黑体，许可见[字体许可](licenses/NotoSansSC-OFL.txt)。
