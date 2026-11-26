# Antigravity macOS 会话 Fork 安装与恢复指南

本指南用于在 macOS 上启用 Antigravity 已有的会话分叉界面。回复末尾的复制、
反馈按钮旁会出现 **Fork Conversation**，选择 **Fork in Current Workspace**
即可创建独立会话；也可以从历史回复创建分叉。

[返回英文 README（Windows 与 macOS）](README.md)

本项目为非官方项目，与 Antigravity 或 Google 无关联。仓库名称仍为
`antigravity-fork-windows`，原 Windows 脚本仍为 `patch_antigravity.py`。
仓库不分发 Antigravity 应用二进制文件或其捆绑资源。MIT 许可证仅适用于本仓库
脚本，不授予 Antigravity 或其资源的使用权。

## 唯一支持的 Mac 版本

- Antigravity **2.35.2**。
- **Apple Silicon arm64**；不支持 Intel。
- 原始、未经修改的 `Contents/Resources/bin/language_server` 的 SHA-256 必须为：

```text
8b11ecde9d089ebbe4511871e75bd046e04f33865c27b617e29a3c237a2bd575
```

脚本会拒绝 Intel、其他版本以及任何不匹配的原始哈希。
已打补丁的应用不能作为原始输入。

上述精确版本已完成运行验证：完全退出并重新启动应用后，应用正常启动；
最新回复和历史回复均出现 **Fork Conversation**；选择
**Fork in Current Workspace** 后可生成独立会话，保留对应位置应有的历史，
原会话历史保持完整。分叉会话共享工作区文件，**不会创建新的 Git worktree**。

## 准备条件

- 已安装上述精确匹配的原始 Antigravity 应用。
- Python **3.8 或更新版本**。工具仅使用 Python 标准库和 macOS 内置的
  `codesign`、`ditto`、`ps`，无需安装第三方 Python 包。
- 足够的可用磁盘空间，用于完整的原始应用副本和补丁应用副本；所需空间
  **可能超过 2 GB**，安装时还会暂存被替换的应用。
- 当前用户对应用及其父目录有文件系统访问权限，并在需要时具有 macOS
  “App Management（应用管理）”权限。脚本不调用 `sudo`，也不会索要凭据。
- 安装或恢复之前，必须完全退出 Antigravity 和它的语言服务器；
  仅关闭窗口不够。

以下命令使用 `/Applications/Antigravity.app` 作为安装位置，将构建目录放在
用户主目录下。请保留整个构建目录，以便校验和恢复。

## 安装

1. 获取整个仓库，保留所有 Python 脚本。可以克隆仓库，也可以下载并解压仓库
   ZIP；Mac 流程需要 `macos_app.py` 和 `patch_antigravity_macos.py` 等仓库
   脚本，不能只下载 Windows 脚本。在终端执行：

   ```sh
   git clone https://github.com/tianyu-z/antigravity-fork-windows.git
   cd antigravity-fork-windows
   ```

   后续命令均在此仓库目录运行。
2. **完全退出 Antigravity**，并确认语言服务器已退出，例如在“活动监视器”中
   检查。然后计算原始语言服务器的哈希：

   ```sh
   shasum -a 256 "/Applications/Antigravity.app/Contents/Resources/bin/language_server"
   ```

   仅当哈希与上方一致、应用版本为 2.35.2 且架构为 Apple Silicon arm64 时继续。
3. 在全新的输出目录中准备补丁应用：

   ```sh
   python3 macos_app.py prepare /Applications/Antigravity.app "$HOME/antigravity-fork-macos-2.35.2"
   ```

   **输出目录必须尚不存在。** 如果已有同名目录，请换一个新的构建目录，并在
   后续安装和恢复命令中使用相同目录。准备步骤不会修改已安装的应用，并会生成：

   - `original/Antigravity.app`：完整、未经修改的原始应用备份。
   - `patched/Antigravity.app`：已完成本地签名与验证的待安装应用。
   - `receipt.json`：用于核验原始应用和补丁应用的指纹记录。

   此步骤会拒绝不支持的输入。请将这三项一起保留，不要修改记录或应用副本。
4. 确保应用和语言服务器仍已完全退出，然后安装：

   ```sh
   python3 macos_app.py install "$HOME/antigravity-fork-macos-2.35.2" /Applications/Antigravity.app
   ```

   安装前会验证记录、原始备份和待安装应用的签名，以及当前原始安装的精确指纹；
   如发现官方更新或意外修改则拒绝替换。安装器会将原目标保留在
   `/Applications` 下的临时同级目录中，并打印该目录路径，不会覆盖已有备份。
   替换使用原子目录重命名；替换或验证失败时会回滚。完成运行检查前，请保留
   打印出的备份路径和整个构建目录。
5. 验证已安装应用的签名，再打开已安装的应用：

   ```sh
   codesign --verify --deep --strict "/Applications/Antigravity.app"
   open "/Applications/Antigravity.app"
   ```

   若 macOS 对你自己生成的版本显示安全批准提示，请在系统界面中按提示操作；
   受管理设备的策略可能阻止批准。确认完全重启后应用正常启动。分别在最新回复
   和历史回复处点击 **Fork Conversation**，再选择 **Fork in Current Workspace**，
   检查分叉会话相互独立、包含对应历史，并且原会话历史保持完整。工作区文件仍然
   共享，此操作不会创建新的 Git worktree。

## 恢复原始应用

完全退出 Antigravity 和语言服务器后执行：

```sh
python3 macos_app.py restore "$HOME/antigravity-fork-macos-2.35.2" /Applications/Antigravity.app
```

只有当前安装与该构建生成的补丁指纹一致、备份与原始指纹一致时才会恢复。
恢复的是**整个应用**，包括原始主应用签名、资源封印和应用目录元数据，并非仅替换
`language_server`。恢复成功后即可重新打开应用。

如果应用已发生官方更新或未知修改，恢复会被拒绝。官方更新可能覆盖补丁；
**不要用旧备份覆盖已更新的应用**。请重新检查当前版本、架构和原始哈希是否符合
唯一支持的版本，再决定是否重新准备补丁。

## 补丁内容与本地签名

补丁仅改变内嵌 `main.js` 中两个 Fork 默认值：
`conversationForkingEnabled` 和 `conversationForkingHistoricalStep`。
原厂 Electron 框架和辅助程序保留不变。

修改后的语言服务器会进行本地 ad-hoc 重签名，并保留原标识符、entitlements
和 hardened-runtime 标志。主应用也会进行本地 ad-hoc 重签名，保留原
entitlements 和标志，同时添加：

```text
com.apple.security.cs.disable-library-validation=true
```

这使本地签名的主应用能够加载保留的 Google 签名 Electron 依赖。
其余 hardened-runtime 选项均保留。

这会**将主应用的官方签名替换为本地签名，并放宽此应用的库签名检查**。
本地签名可能触发 macOS 安全批准提示；应通过操作系统界面批准你自己生成的版本，
受管理设备的策略可能不允许这样做。上面的
`codesign --verify --deep --strict` 仅用于验证，签名由安装工具处理。

## 常见问题

- **Operation not permitted（操作不被允许）：** 打开
  **系统设置 > 隐私与安全性 > App Management（应用管理）**，启用实际执行命令的
  应用，例如 Terminal（终端）或 ChatGPT 等 AI 桌面宿主。若系统要求 Touch ID
  或密码，请仅在 macOS 系统窗口中完成批准，不要在终端或聊天中输入密码。
  授权后重试命令。
- **输出目录已存在：** 选择新的构建目录，不要覆盖现有备份、补丁副本或记录。
- **输入不支持，或应用已打过补丁：** 使用未经修改的原始备份或精确匹配的原厂
  应用，重新检查版本、架构和原始哈希。安装目标仍须匹配准备时记录的原始
  应用指纹。
- **应用或语言服务器仍在运行：** 完全退出二者，再重试安装或恢复。
- **替换或回滚失败：** 保留错误信息中的 `previous.app` 和候选应用路径。
  原目标仍保存在该位置；先解决权限或文件系统问题，再从记录的路径恢复。
- **官方更新或其他修改导致指纹不一致：** 停止使用旧构建进行安装或恢复，
  重新核对当前应用是否符合支持条件，不要用旧备份覆盖它。

## 可选：仅生成单独的语言服务器补丁文件

```sh
python3 patch_antigravity_macos.py SOURCE_SERVER NEW_OUTPUT_SERVER
```

该底层命令只生成一个独立的补丁二进制文件，不负责完整应用安装，也不会修复
应用签名。要安装本指南描述的已签名应用，请使用 `macos_app.py` 的
prepare/install 流程。

## 许可证

本仓库脚本使用 [MIT License](LICENSE)。许可证不适用于 Antigravity 应用或其
捆绑资源；本项目不分发这些文件。
