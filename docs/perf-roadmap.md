# 性能优化路线图（预调研 + 方案分级）

> 输入：《发热归因报告.md》（2026-10-07，静态审计 @ f60ccd66）+ 2026-10 社区调研。
> 目标：**本机模拟器上长对话长时间流畅运行**——即砍掉一切随会话时长增长的 I/O/渲染曲线。

## 0. 已实施（v1.1.0）

| 项 | 报告出处 | 预期收益 |
|---|---|---|
| `backups.chat.enabled: false` | §8.A | 砍掉保存链一半 I/O（每 10s 一次全量备份消失） |
| `fs.fsync` 空转（rename-fix.cjs） | §3.2 | 消除每条消息保存的强制刷盘等待 |
| 恢复 proot seccomp 加速（去掉 PROOT_NO_SECCOMP） | §2.2 | I/O 密集系统调用跳过 ptrace 停等（社区确认该变量是兼容修复而非加速，能开则开） |
| 就绪轮询 800ms→1500ms、看门狗 30s→60s | §6 | 探活唤醒减半 |
| **webpack 预烘焙**：PC 编译 `data/_webpack` 随包分发 | §7 首启 | 首启跳过 8 分钟冷编译（官方 Docker 即此方案，webpack.config.js 注释自证支持） |
| 调试变体自动启动 + exported service | 测试基建 | 摆脱模拟器 input 注入丢事件 |

## 1. 短期（v1.2，pipeline 自动 patch，不手改 ST 源码）

**原则**：所有 ST 源码改动做成 pipeline 的自动 patch（更新官方版本后自动重新应用），见 `scripts/update_st.sh` 编译器。

1. **流式渲染节流**（§5.2 O(n²)）：patch `public/script.js` 的 `onProgressStreaming`——每个 chunk 只更新纯文本预览，**满 150ms 或流结束才跑完整 markdown 管线**。预期把单条长回复的渲染负载降一个数量级。
2. **WI 正则缓存**（§5.1）：`world-info.js` 的 `matchKeys` 按条目 id 缓存编译后的 RegExp，条目文本变更时失效。
3. **保存链再压**：`chats.js` 的备份调用已随 backups.enabled=false 短路；主文件全量写仍在（上游行为），可观察真实热区后再决定是否 patch 增量写（工程量大，暂缓）。

## 2. 中期（架构级，最大性能杠杆）

### 2.1 bionic Node（甩掉整个 proot 层）
- 社区共识：Termux 原生（bionic）Node 的 I/O 与启动性能优于 proot-distro（glibc）路线。
- 路径：从 termux 镜像抽取 **node 包 + 其依赖库链**（libssl/libcrypto/icu/zlib/libuv 的 termux 构建版），替换 rootfs 中的 glibc node；proot 仅剩路径职责——甚至可完全去掉 proot，直接 `exec node`（App 私有目录 exec 权限已由 targetSdk 28 保证）。
- 可行性：ST 依赖纯 JS/wasm（已验证 667 包零原生绑定）✓；风险在 termux node 的库依赖闭环与 DNS/证书路径差异。
- 预期：I/O 放大从 2~5× 降回 ~1×，保存链与启动耗时同比例改善。

### 2.2 跟踪 Luker（ST 深度重构版）
- Luker（luker.cups.moe）官方宣传"extensive mobile/Android optimizations, startup performance improvements"——值得拆解其优化点并选择性移植；远期可支持 Luker 作为可替换内核。

## 3. 长期（实测驱动）

按报告 §9.2 的实验设计：perfetto 抓 ptrace 乒乓、simpleperf 量化长会话系数、f2fs ftrace 验证写放大 3N 预测、温度-负载对齐曲线。**先把 A/B 干预（v1.1.0）跑出前后对比**。

## 4. 使用侧（零代码）

- 长会话定期归档开新线（三条 O(N) 曲线全体回落）
- `chat_truncation` 保持默认 100
- 重卡书收紧 WI 扫描深度
- 不玩时通知栏"停止"

## 5. 参考资料

- [Luker — 安卓优化版 SillyTavern 重构](https://luker.cups.moe)
- [ST 官方 Docker 发布流（预烘焙先例）](https://github.com/SillyTavern/SillyTavern/blob/release/.github/workflows/docker-publish.yml)
- [PROOT_NO_SECCOMP 是兼容修复而非加速（AnLinux/XDA 社区实践）](https://github.com/EXALAB/AnLinux-App)
- [Linux 5.11 seccomp constant-action bitmap 加速](https://www.phoronix.com/news/Linux-5.11-Seccomp)
- [PRoot 机制论文（ptrace 开销模型）](https://arxiv.org)
