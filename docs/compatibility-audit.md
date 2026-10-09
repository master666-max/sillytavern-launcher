# 两条铁律专项审计报告（2026-10-09）

审计对象：v1.2.3 代码基线 → 修正发布为 v1.2.4。
审计方式：逐项核对 + 本地复现 + 设备端实测（Android 16 模拟器，含 Termux 陷阱与坏 config 极端场景）。

## 铁律一：与 PC 版同样的兼容性与可扩展性

### 发现的偏离与处置

| # | 项 | v1.2.3 状态 | 官方默认 | 处置 |
|---|---|---|---|---|
| 1 | `whitelistMode` | false（偏离） | **true** | ✅ 已对齐 true（实测 127.0.0.1 访问不受影响） |
| 2 | `backups.chat.enabled` | false（性能优化误伤） | **true** | ✅ 已恢复默认；实测备份文件生成（chat+settings 双备份） |
| 3 | `extensions.autoUpdate` | false（过度收紧，误伤用户手装扩展） | true | ✅ 已移除该覆盖；预装扩展改由 manifest 层静默（见下） |
| 4 | 用户无法修改任何 config（文件在私有目录，PC 用户可随时编辑） | 缺口 | — | ✅ 新增**外部 config 机制**：首次运行把工厂配置暴露到 `Android/data/<pkg>/files/config.yaml`（任何文件管理器可编辑），存在即每次启动生效；删除该文件=恢复出厂。实测：覆盖生效、删除后模板重新生成 |
| 5 | 用户 config 容错 | 缺口（极端 config 可使 ST 崩溃，如删掉 browserLaunch 段→spawn xdg-open ENOENT） | — | ✅ 运行时内置 **xdg-open 空操作桩**：任何 config 下都不再因此崩溃（用"5 行残缺 config"实测存活） |
| 6 | 载荷变化不触发设备更新（旧机制仅比对 ST 版本号） | 缺口 | — | ✅ **payload 指纹**：版本标记 = ST版本 + 配置模板哈希 + 运行时文件清单哈希；任何载荷变化自动触发重解压（实测覆盖安装 186s 自动完成） |

### 明确保留的"安卓必要适配"（非兼容性损失，逐项理由）

| 项 | 值 | 理由 |
|---|---|---|
| `browserLaunch.enabled` | false | 安卓无桌面浏览器；PC 无头部署同样关闭。另有 xdg-open 桩兜底 |
| `git.backend` | builtin | 运行时无系统 git；PC 未装 git 的用户的自动行为一致（isomorphic-git 为 ST 官方能力） |
| `listen` | false | 仅本机回环监听（与 whitelistMode:true 双保险） |
| npm registry | npmmirror | 仅下载源默认值，用户可改；不改任何行为语义 |
| 预装扩展 `auto_update:false` | manifest 级 | 预装件是解包目录（无 .git），自动更新必然失败；**用户从 GIT URL 自装的扩展保持 PC 同款自动更新** |

### 兼容性结论

- UI 扩展加载/安装/删除/排序：与 PC 机制完全一致（浏览器动态 import + isomorphic-git）
- 用户对配置的控制权：与 PC 对等（外部 config 文件全量可编辑）
- 剩余唯一架构性差异：proot 时代的 rootfs 内 `apt`（v1.2 起已随 proot 一起移除，见 bionic-migration.md §2 的诚实清单）

## 铁律二：官方包一键自动升级 + 自动编译

### 发现的缺口与处置

| # | 项 | v1.2.3 状态 | 处置 |
|---|---|---|---|
| 1 | `update_st.sh` 编译器 | 停留在 v1.1 的 Debian/proot 流程（已与实际架构脱节） | ✅ 全面 bionic 化：官方源码→扩展确保→依赖→补丁→预编译→termux 闭包（双 ABI）→组装→签名包（8 步） |
| 2 | 预装扩展的获取与 `auto_update=false` 固化为手工操作 | 缺口（重新拉扩展会丢修复） | ✅ 新增 `scripts/fetch_extensions.sh`：自动获取 5 个扩展并固化 manifest 修复，被编译器调用 |
| 3 | CI（auto-build.yml） | 仍下载 Debian rootfs + proot 五件套 | ✅ 更新为 termux 闭包拉取 + `--bionic-only` 组装 |
| 4 | bionic 载荷缺失五件套时 `provision()` 会抛异常 | 缺口 | ✅ 容错：缺失资产跳过（bionic 模式本就不需要） |
| 5 | 构建脚本可能装错载荷（防呆） | 缺口 | ✅ `build_apk.sh` 校验 rootfs 必须含 `opt/bionic/bin/node`，否则拒绝打包 |

### 自动编译结论

`scripts/update_st.sh`（本机一键）与 `.github/workflows/auto-build.yml`（云端每日盯梢）
两者流程现已与 v1.2 架构一致；与官方 ST 的耦合点集中在两处且均为版本无关设计：
ST 版本号（package.json 自动读取）+ 三个幂等补丁锚点（patch_st.py，上游变更会显式报错而非静默失效）。

## 回归验证记录（v1.2.4）

| 场景 | 结果 |
|---|---|
| 覆盖安装（指纹不匹配） | 自动重解压，186s 就绪 ✓ |
| 外部 config 覆盖生效 / 删除后重生成 | ✓ / ✓ |
| 残缺用户 config（仅 5 行） | ST 正常启动（xdg-open 桩兜底）✓ |
| backups 恢复 | chat 与 settings 备份文件实际生成 ✓ |
| 启动无红条（清前端数据重触发） | 后端零更新失败痕迹 ✓ |
| whitelistMode=true | 本机 HTTP 200 全通过 ✓ |
| 单元测试 | Pipeline 6/6、JVM 8/8 ✓ |
