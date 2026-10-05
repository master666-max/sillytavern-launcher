# 酒馆盒子 (SillyTavern Launcher)

单 APK 的安卓「酒馆」：内置 Debian 12 + Node.js 22 + SillyTavern 1.19.0 及全部依赖，
**装完解压即用、全程离线**——不需要 Termux、不需要 root、不需要联网初始化。

- 包名：`io.github.master666max.sillytavern`（独立 keystore 签名，与 Termux 等零冲突）
- minSdk 26（Android 8.0+），targetSdk 28（保私有目录可执行权限，Termux 同款策略）
- 壳 App 零第三方依赖：纯 Java + WebView；Linux 侧用 termux fork 的 proot 隔离运行

## App 能做什么

- 首次启动自动解压内置环境（进度条），之后离线可用
- 图形化主页：启动 / 停止（通知栏常驻服务）/ 重置环境
- 全屏 WebView 承载酒馆界面，支持角色卡等文件上传
- 服务掉线自动重启（看门狗），node 以低优先级运行避免饿死系统 UI

## 扩展（Extensions）安装

扩展机制与 PC 完全一致：SillyTavern 内置 isomorphic-git 安装第三方扩展，
不依赖系统 git。唯一差异是**网络**：

- 扩展面板的在线列表直连 GitHub，国内移动网络下大概率加载失败
- 用「Install from GIT URL」手动安装时，**在扩展的 GitHub 地址前加加速前缀**：

  ```
  https://ghfast.top/https://github.com/<作者>/<扩展仓库>
  ```

- 服务端插件（server plugins）依赖 npm，内置环境已预配 npmmirror 镜像源
- 个别依赖原生二进制或外部 CDN 的扩展可能不可用，与 PC 浏览器端行为一致

## 从源码构建

前提：JDK 17、Gradle 8.9、Android SDK（platform 35 / build-tools 35.0.0）、Python 3.10+（仅标准库）、Node.js（预装 ST 依赖用）。

```bash
# 1. 预装 SillyTavern 依赖（纯 JS/wasm，跨平台通用）
unzip SillyTavern-release.zip -d assets-src && mv assets-src/SillyTavern-release assets-src/SillyTavern
cd assets-src/SillyTavern && npm install --omit=dev --no-audit --no-fund
cd ../.. && python pipeline/clean_node_modules.py assets-src/SillyTavern --prune

# 2. 准备原料（见 pipeline/sources.py 清单）：Debian lxc rootfs、Node linux
#    二进制、SillyTavern release zip、termux 的 proot/libtalloc/libandroid-shmem
#    deb（抽取用 pipeline/extract_runtime.py），放入 downloads/ 或用
#    STL_DOWNLOADS 指向你的缓存目录

# 3. 组装 rootfs 并出包
python pipeline/build_rootfs.py --abi arm64-v8a --out dist/rootfs-arm64-v8a.tar.gz
STL_GRADLE=/path/to/gradle bash scripts/build_apk.sh arm64-v8a release
```

x86_64 变体（`--abi x86_64`）用于在 PC 模拟器上端到端验证。

## 测试

```bash
python -m unittest discover -s pipeline -v   # tar 合并 / 平台包清扫
./gradlew testDebugUnitTest                  # TarReader / proot 参数构造
```

## 致谢与许可

- [SillyTavern](https://github.com/SillyTavern/SillyTavern)（AGPL-3.0）—— 本项目不重新分发其源码或二进制，构建时由脚本从官方 release 拉取
- [proot (termux fork)](https://github.com/termux/proot)、[libtalloc](https://talloc.samba.org/)、[libandroid-shmem](https://github.com/termux/libandroid-shmem) —— 运行时从 termux 官方仓库的 deb 中抽取，许可随上游（GPL/LGPL）
- [Debian](https://www.debian.org/) lxc rootfs、[Node.js](https://nodejs.org/) 官方 linux-arm64/x64 二进制
- 本仓库代码仅供学习研究；请遵守你所在地区的法律法规使用 AI 前端。
