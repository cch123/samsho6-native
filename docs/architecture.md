# 工程结构

本文说明仓库各目录的职责、运行时的模块划分和数据流。玩法细节见同目录下各专题文档，开发进度见 [development-plan.txt](development-plan.txt)。

## 目录

| 路径 | 内容 | 是否入库 |
|---|---|---|
| `src/` | 运行时库 `ss6-runtime`、游戏入口 `viewer.cpp`、各 `*_probe.cpp` 探针 | 是 |
| `cmake/ss6_sources.cmake` | 运行时源文件的模块分组和工具目标清单 | 是 |
| `tests/` | 不依赖光盘数据的测试，由 CTest 运行 | 是 |
| `tools/assets/` | 素材转换工具（贴图与 PNG 互转） | 是 |
| `mods/` | 素材覆盖目录，每个子目录是一组替换文件 | 仅 README |
| `docs/` | 格式说明、机制笔记、开发计划 | 是 |
| `work/ss6/*.py` | 提取脚本 `extract_*`、原版对比验证 `validate_*`、打包脚本 | 是 |
| `work/ss6/extracted/`、`work/ss6/build-*` | 提取出的原版数据、构建目录 | 否 |
| `outputs/` | 验证报告、打包后的游戏和素材 | 否 |

## 构建目标

```
ss6-runtime (静态库, 不依赖 SDL)
   ├── ss6-viewer            游戏可执行文件, 链接 SDL3      [SS6_BUILD_GAME]
   ├── ss6-*-probe, ...      探针/回放/跟踪命令行工具        [SS6_BUILD_TOOLS]
   └── ss6-test-*            单元测试                        [SS6_BUILD_TESTS]
```

预设见 `CMakePresets.json`：`release`（构建到验证脚本约定的 `work/ss6/build-native`）、`debug`、`asan`、`ci`（不需要 SDL3）。

```sh
cmake --preset release
cmake --build --preset release -j 8
ctest --preset release
```

## 运行时模块

`src/` 在磁盘上是平铺的，因为 `work/ss6` 里约 165 个验证脚本用 `-I src` 和 `src/<文件>.cpp` 直接编译驱动程序。逻辑分层记录在 `cmake/ss6_sources.cmake`，新增文件时加入对应分组：

| 分组 | 职责 |
|---|---|
| `core` | 定点/浮点模型（`ScalarFloat`、`soft_double`）、随机数、任务池、素材查找、存档 |
| `animation` | ACT/JDG 播放、对象帧、绘制准备、特效 |
| `input` | 手柄采样、指令识别、许可判定、动作选择 |
| `combat` | 接触判定、伤害、受击反应、状态机、通用招式 |
| `fighters` | 各角色专属对象与随从 |
| `cpu` | 电脑对手 |
| `stages` | 场景状态、背景条带、场景道具与事件 |
| `match` | 回合流程、比赛进度、可玩的对战驱动 `NativeMatch` |
| `modes` | 菜单与各模式画面及其美术 |
| `audio` | 音效选择、采样库、混音、音乐流 |

依赖方向自上而下：`modes`/`match` 依赖 `combat`、`stages`、`fighters`，它们再依赖 `animation`、`input`、`core`。`viewer.cpp` 是唯一接触 SDL 的翻译单元（另有两个只含头文件的 SDL 适配器 `versus_audio_output.hpp`、`versus_gamepads.hpp`）。

## 数据流

```
用户自己的光盘镜像
      │  work/ss6/extract_*.py（按 ELF 哈希校验）
      ▼
work/ss6/extracted/resources/        原版格式的文件和从 ELF 截取的表
      │  work/ss6/package_viewer.py
      ▼
outputs/.../native-viewer/assets/    游戏读取的基础素材目录（--assets）
      ▲
      │  同名文件优先
mods/<名称>/                          覆盖目录（--mod / SS6_MODS）
      ▲
      │  tools/assets/ss6tex.py encode
可编辑的 PNG + JSON
```

所有加载器都通过 `ss6::resolveAsset()`（`src/asset_files.hpp`）打开文件。没有覆盖目录时它原样返回请求的路径，因此原版数据下的行为与改造前一致。

## 两类验证

| 类别 | 位置 | 需要原版数据 | 证明什么 |
|---|---|---|---|
| 单元测试 | `tests/`，CTest | 否 | 工具和基础设施自身正确 |
| 原版对比 | `work/ss6/validate_*.py` | 是 | 运行时与原版可执行文件逐状态一致 |

修改玩法代码后必须跑对应的 `validate_*.py`；单元测试不能替代它。
