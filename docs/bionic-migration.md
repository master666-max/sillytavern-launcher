# Bionic 迁移设计（v1.2 路线）：甩掉 proot，无损保留 PC 兼容性

> 状态：**已在设备上端到端实证**（2026-10-08，x86_64 模拟器，Node v26.4.0 termux 运行时）
> 目标：删除 proot/ptrace 层（归因报告 §2 的架构性成本），同时**无损保留与 PC 版一致的扩展生态与可扩展性**。
> 原则：所有兼容性声明必须实测；下表中每行都有设备上的运行记录。

## 0. 核心结论（实测）

| 验证项 | 结果 | 证据 |
|---|---|---|
| termux node 在 App 私有目录直跑 | ✅ v26.4.0 x64 android | `BIONIC_NODE v26.4.0 x64 android` |
| NodeService 直启（无 proot 进程） | ✅ `launching with bionic runtime (no proot)` | logcat + `ps` 只有 node |
| **DNS（PC 同级）** | ✅ github.com 解析成功 | 扩展安装 ECONNRESET 即证 DNS+TCP 通 |
| **在线安装扩展（PC 同机制）** | ✅ D&D Dice 2.0.0，**2.0 秒**经 gh-proxy.com | `POST /api/extensions/install` HTTP 200 |
| isomorphic-git 回退链 | ✅ 系统 git 探测失败后自动走内置实现 | st.log simple-git → builtin 回退 |
| 保存延迟（n=100/300/600 消息） | ✅ **41 / 34 / 42 ms**（proot 版 49/53/59ms） | 设备实测，比 v1.1.1 再快 20~30% |
| 16KB 页设备兼容（Android 15+） | ✅ node/全部 .so 均 16K 对齐 | pipeline/termux_node.py 逐 ELF 校验 |
| 依赖闭包 | ✅ 仅 10 包（nodejs+npm+7 库+resolv-conf） | 同上 |

## 0.1 提速包实测（v1.1.1 → v1.2 预览，同一弱模拟器）

| 阶段 | 改进前 | 改进后 | 手段 |
|---|---|---|---|
| 首启（含解压） | 702s | **339s** | 编译归零（跳过启动期 webpack + 预编译产物随包） |
| 热重启（force-stop 后重开 App） | ~75s | **17s** | 免解压 + 跳过 webpack + 模块加载走 V8 编译缓存 |
| 保存延迟 n=100/300/600 | 49/53/59ms（proot） | **41/34/42ms** | bionic 直跑免 ptrace |
| 待机唤醒 | 每 60s HTTP 探活 | 仅进程存活检查 | 看门狗瘦身 |
| 打开 App 的等待 | 手动点按钮再等 | **打开即自动启动**（就绪自动跳 WebView） | MainActivity 轮询 + 服务复用 |

注：跳过 webpack 由 `ST_SKIP_WEBPACK=1` 环境变量 + 产物存在性双保险，产物缺失（数据目录被清）时自动回退编译；补丁由 patch_st.py 幂等维护，ST 升级自动重放。

## 1. 架构设计

```
旧（v1.1.x）：App ──spawn──> proot(ptrace 翻译一切系统调用) ──> glibc node(Debian rootfs)
新（v1.2） ：App ──spawn──> bionic node(termux 构建) 直接执行
                            └ 仅剩一层：renameat2/fsync shim（zygote seccomp 所迫，保留）
```

- **运行时**：termux 的 nodejs 26.x + npm 11.x + 依赖库（libc++/openssl/c-ares/libicu/
  libsqlite/zlib/libffi），闭包 10 包、解压 ~135MB。
- **启动**：`NodeService` 检测 `/opt/bionic/bin/node` 存在即可执行 → 直启；
  否则回退现有 proot 路径（代码保留，双轨并存，见 §4 兼容包）。
- **环境**：`LD_LIBRARY_PATH=<bionic>/lib`、`PATH=<bionic>/bin:/system/bin`、
  `NODE_OPTIONS=--require <真实路径>/rename-fix.cjs`（renameat2 ENOSYS + fsync 空转继续有效）、
  `NPM_CONFIG_REGISTRY=npmmirror`。
- **配置**：`git.backend: builtin` 写进设备 config.yaml —— 免掉系统 git 探测（手机两代架构
  里都不存在系统 git），扩展安装直接走 isomorphic-git。

## 2. 无损兼容性分析（PC 对标逐项）

| 能力 | PC 版 | v1.2 设备 | 说明 |
|---|---|---|---|
| UI 扩展（99% 使用面） | 浏览器 ES 模块 | **完全一致**（WebView=完整 Chromium，动态 import） | — |
| 扩展安装/更新/删除 | 系统 git 或内置 | **完全一致**（内置 isomorphic-git，实测 2s 装好） | 网络同 PC 国情：直连 TLS 被 RST → 用加速前缀（gh-proxy.com/ghproxy.net 均实测可用） |
| 预装扩展 | — | 5 个随包 + 设备上新增均可行 | discover 实测 6 个 local |
| 服务端插件（默认关） | node 进程内加载 + npm | **一致**：node+npm 已随运行时；npm 脚本 shell 用 API29+ 的 /bin/sh，旧机型配 busybox sh | npm 依赖走 npmmirror |
| npm 生态 | 系统 npm | **一致**（termux npm 11.x） | — |
| 数据目录结构 | data/… | **一致**（cwd 相对路径，ST 无绝对路径依赖） | 唯一变化：`/opt/st` 幻象 → 真实路径 `<appdata>/…/opt/st` |
| TLS/证书 | node 内置 CA | 一致（node 内嵌 Mozilla 根集） | — |
| 时区/语言/编码 | — | 一致（LANG=C.UTF-8，TZ 可配） | — |
| **删除的能力**（诚实清单） | — | ① rootfs 内 `apt install` 任意 Debian 包（proot 假 root 时代的能力）② 依赖 Debian 特有程序/路径的服务端插件 | 使用者趋近于零；如确有需要 → §4 兼容包方案 |

## 3. 打包与编译器改造

- `pipeline/termux_node.py`（已实现）：解析 termux Packages 索引 → 依赖闭包 →
  拉 deb → 抽 bin/lib → **16K 对齐校验 + DT_NEEDED 闭包校验 + shebang 扫描**
  （npm 的 11 个 `#!/data/data/com.termux/files/usr/bin/env node` shebang 在打包时改写为
  `#!/system/bin/env node`；tar-slip 防护）。
- `build_rootfs.py --bionic <dir>`（已实现）：把运行时树嵌到 rootfs 的 `/opt/bionic`，
  **bin/ 强制 755**（Windows 宿主无法表达 exec 位——已踩坑修复）。
- 预期收益：APK 227MB → **~110MB**（Debian 700MB+glibc node 110MB 换成 bionic 135MB）；
  首启解压 850MB → ~475MB（模拟器 265s → ~150s，真机 UFS 摊薄）。
- `update_st.sh` 编译器新增一步：拉 termux 最新 node 闭包（版本随官方滚动，nvs 已见 26.x）。
- CI（auto-build.yml）：Debian rootfs + proot 五件套的下载步骤替换为 termux deb 拉取。

## 4. 迁移阶段与回退

1. **阶段 0（本次已完成）**：可行性 spike —— 本文件全部实证 + App 内双轨启动代码。
2. **阶段 1**：v1.2.0 默认 bionic（APK 只带 bionic 载荷）；proot 启动代码保留但不带载荷。
3. **阶段 2（可选兼容包）**：若真出现"需要 Debian 环境"的服务端场景，发布独立的
   rootfs/proot 扩展包（现状 v1.1.x 的载荷），App 检测到即启用 proot 路径——
   双轨代码已内建，仅载荷分发问题。
4. 回退：bionic 载荷有任一设备兼容问题（如特定 ROM 库加载异常）→ 发布 v1.2.1 切回
   v1.1.1 载荷，App 代码零改动（双轨自动选择）。

## 5. 风险与对策（已核）

| 风险 | 状态 | 对策 |
|---|---|---|
| 16KB 页设备（Pixel 8+/Android 15+）拒载 4K 对齐 .so | **已核 16K ✓** | 打包器每次校验，不达标即告警 |
| 依赖库缺失/符号版本冲突 | 已核 DT_NEEDED 闭包 ✓ | 打包器递归校验，缺库即构建失败 |
| 旧机型无 /bin/sh（API 26-28） | 已知 | npm 脚本 shell 指向随包 busybox sh（termux busybox 1.38，~2MB） |
| termux node 滚动升级引入不兼容 | 中 | 编译器钉版本+校验；升级走 CI 全量回归（浸泡脚本已有） |
| zygote seccomp 对 renameat2 ENOSYS | 已知 | rename-fix.cjs 继续注入（真实路径版） |
| DNS 在某些定制 ROM 的 netd 差异 | 低 | 与原生命令一致（标准 getaddrinfo），无自研解析 |

## 6. 与"自动耦合官方版本"的衔接

编译器流程变为：`官方 ST 最新版 zip` + `termux node 闭包（最新）` + `性能补丁重放` +
`webpack 预烘焙` → 双 ABI 出包。**注意**：bionic 模式下 ST 的真实路径不再是 /opt/st，
预烘焙缓存的路径对齐方案改为"在 CI 中把 ST 挂载到与设备一致的
`/data/user/0/io.github.master666max.sillytavern/files/rootfs/opt/st` 路径编译"
（包名固定，路径可精确预测）。
